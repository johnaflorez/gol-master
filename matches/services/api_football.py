import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from matches.models import Match, MatchEvent
from teams.models import Team


class ApiFootballConfigError(RuntimeError):
    """Raised when API-Football integration is not configured."""


class ApiFootballClientError(RuntimeError):
    """Raised when API-Football returns an error or cannot be reached."""


@dataclass
class ApiFootballSyncResult:
    checked: int = 0
    updated: int = 0
    skipped: int = 0
    events_created: int = 0
    events_updated: int = 0


class ApiFootballClient:
    """Small API-Football/API-SPORTS client using Django settings."""

    def __init__(self, api_key=None, base_url=None, timeout=None):
        self.api_key = api_key if api_key is not None else settings.API_FOOTBALL_KEY
        self.base_url = (base_url or settings.API_FOOTBALL_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.API_FOOTBALL_TIMEOUT

    def _request(self, path, params=None):
        if not self.api_key:
            raise ApiFootballConfigError("API_FOOTBALL_KEY is not configured")

        query_string = urlencode({key: value for key, value in (params or {}).items() if value not in (None, "")})
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query_string:
            url = f"{url}?{query_string}"

        request = Request(url, headers={"x-apisports-key": self.api_key})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ApiFootballClientError(f"API-Football HTTP error {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ApiFootballClientError(f"API-Football request failed: {exc}") from exc

        errors = payload.get("errors")
        if errors:
            raise ApiFootballClientError(f"API-Football returned errors: {errors}")

        return payload.get("response", [])

    def get_fixture(self, fixture_id):
        fixtures = self._request("fixtures", {"id": fixture_id})
        return fixtures[0] if fixtures else None

    def get_fixtures(self, *, fixture_date: date | str | None = None, live=None, league=None, season=None):
        if isinstance(fixture_date, date):
            fixture_date = fixture_date.isoformat()

        return self._request(
            "fixtures",
            {
                "date": fixture_date,
                "live": live,
                "league": league,
                "season": season,
            },
        )

    def get_events(self, fixture_id):
        return self._request("fixtures/events", {"fixture": fixture_id})


class ApiFootballSyncService:
    """Synchronizes API-Football fixtures into local Match and MatchEvent records."""

    FINISHED_STATUSES = {"FT", "AET", "PEN"}
    LIVE_STATUSES = {"1H", "2H", "ET", "BT", "P", "LIVE", "INT"}

    def __init__(self, client=None):
        self.client = client or ApiFootballClient()

    def sync_queryset(self, queryset, *, include_events=True):
        result = ApiFootballSyncResult()
        for match in queryset:
            match_result = self.sync_match(match, include_events=include_events)
            result.checked += match_result.checked
            result.updated += match_result.updated
            result.skipped += match_result.skipped
            result.events_created += match_result.events_created
            result.events_updated += match_result.events_updated
        return result

    def sync_match(self, match, *, include_events=True):
        result = ApiFootballSyncResult(checked=1)
        if not match.api_football_fixture_id:
            result.skipped = 1
            return result

        fixture = self.client.get_fixture(match.api_football_fixture_id)
        if not fixture:
            result.skipped = 1
            return result

        updated = self._update_match_from_fixture(match, fixture)
        if updated:
            result.updated = 1

        if include_events:
            created, updated_events = self.sync_events(match, fixture=fixture)
            result.events_created = created
            result.events_updated = updated_events

        return result

    def sync_events(self, match, *, fixture=None):
        if not match.api_football_fixture_id:
            return 0, 0

        fixture = fixture or self.client.get_fixture(match.api_football_fixture_id)
        fixture_teams = (fixture or {}).get("teams", {})
        events = self.client.get_events(match.api_football_fixture_id)
        created_count = 0
        updated_count = 0

        for event in events:
            event_key = self._event_key(match.api_football_fixture_id, event)
            defaults = self._event_defaults(match, event, fixture_teams)
            _, created = MatchEvent.objects.update_or_create(
                match=match,
                api_football_event_key=event_key,
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        if created_count or updated_count:
            Match.objects.filter(id=match.id).update(last_event_at=timezone.now())

        return created_count, updated_count

    def _update_match_from_fixture(self, match, fixture):
        fixture_info = fixture.get("fixture", {})
        status = fixture_info.get("status", {})
        goals = fixture.get("goals", {})
        teams = fixture.get("teams", {})

        update_fields = []
        status_short = status.get("short") or "NS"
        live_status = self._map_live_status(status_short)
        finished = status_short in self.FINISHED_STATUSES
        live_minute = status.get("elapsed")
        home_score = goals.get("home")
        away_score = goals.get("away")

        update_fields += self._set_if_changed(match, "live_status", live_status)
        update_fields += self._set_if_changed(match, "finished", finished)
        update_fields += self._set_if_changed(match, "live_minute", live_minute)

        if home_score is not None:
            update_fields += self._set_if_changed(match, "home_score", int(home_score))
        if away_score is not None:
            update_fields += self._set_if_changed(match, "away_score", int(away_score))

        if update_fields:
            match.save(update_fields=list(dict.fromkeys(update_fields)))

        self._update_team_api_ids(match, teams)
        return bool(update_fields)

    def _update_team_api_ids(self, match, teams):
        home_api_id = self._nested_get(teams, "home", "id")
        away_api_id = self._nested_get(teams, "away", "id")

        if home_api_id and match.home_team.api_football_team_id != home_api_id:
            Team.objects.filter(id=match.home_team_id).update(api_football_team_id=home_api_id)
            match.home_team.api_football_team_id = home_api_id

        if away_api_id and match.away_team.api_football_team_id != away_api_id:
            Team.objects.filter(id=match.away_team_id).update(api_football_team_id=away_api_id)
            match.away_team.api_football_team_id = away_api_id

    def _map_live_status(self, api_status):
        if api_status in self.FINISHED_STATUSES:
            return "FT"
        if api_status == "HT":
            return "HT"
        if api_status in self.LIVE_STATUSES:
            return "LIVE"
        return "NS"

    def _event_defaults(self, match, event, fixture_teams):
        event_type = self._map_event_type(event)
        team = self._resolve_event_team(match, event, fixture_teams)
        player = event.get("player") or {}
        time = event.get("time") or {}
        detail = event.get("detail") or ""
        comments = event.get("comments") or ""
        description_parts = [part for part in [detail, comments] if part]

        return {
            "team": team,
            "minute": time.get("elapsed"),
            "event_type": event_type,
            "player_name": (player.get("name") or "")[:100],
            "description": " - ".join(description_parts)[:255],
        }

    def _map_event_type(self, event):
        event_type = (event.get("type") or "").lower()
        detail = (event.get("detail") or "").lower()

        if event_type == "goal":
            return "GOAL"
        if event_type == "card" and "red" in detail:
            return "RED"
        if event_type == "card" and "yellow" in detail:
            return "YELLOW"
        return "OTHER"

    def _resolve_event_team(self, match, event, fixture_teams):
        api_team = event.get("team") or {}
        api_team_id = api_team.get("id")
        api_team_name = (api_team.get("name") or "").strip().lower()

        if api_team_id:
            if match.home_team.api_football_team_id == api_team_id:
                return match.home_team
            if match.away_team.api_football_team_id == api_team_id:
                return match.away_team

            home_fixture_id = self._nested_get(fixture_teams, "home", "id")
            away_fixture_id = self._nested_get(fixture_teams, "away", "id")
            if home_fixture_id == api_team_id:
                return match.home_team
            if away_fixture_id == api_team_id:
                return match.away_team

            team = Team.objects.filter(api_football_team_id=api_team_id).first()
            if team:
                return team

        if api_team_name:
            if match.home_team.name.lower() == api_team_name:
                return match.home_team
            if match.away_team.name.lower() == api_team_name:
                return match.away_team

        return None

    def _event_key(self, fixture_id, event):
        time = event.get("time") or {}
        team = event.get("team") or {}
        player = event.get("player") or {}
        assist = event.get("assist") or {}
        parts = [
            fixture_id,
            time.get("elapsed"),
            time.get("extra"),
            team.get("id") or team.get("name"),
            event.get("type"),
            event.get("detail"),
            player.get("id") or player.get("name"),
            assist.get("id") or assist.get("name"),
        ]
        return ":".join(str(part or "") for part in parts)[:255]

    def _set_if_changed(self, instance, field_name, value):
        if getattr(instance, field_name) == value:
            return []
        setattr(instance, field_name, value)
        return [field_name]

    def _nested_get(self, data: dict[str, Any], *keys):
        current = data
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

