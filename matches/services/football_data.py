import json
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from matches.models import Match
from teams.models import Team


class FootballDataConfigError(RuntimeError):
    """Raised when football-data.org integration is not configured."""


class FootballDataClientError(RuntimeError):
    """Raised when football-data.org returns an error or cannot be reached."""


@dataclass
class FootballDataSyncResult:
    checked: int = 0
    updated: int = 0
    skipped: int = 0


class FootballDataClient:
    """Small football-data.org client using Django settings."""

    def __init__(self, token=None, base_url=None, timeout=None):
        self.token = token if token is not None else settings.FOOTBALL_DATA_TOKEN
        self.base_url = (base_url or settings.FOOTBALL_DATA_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.FOOTBALL_DATA_TIMEOUT

    def _request(self, path, params=None):
        if not self.token:
            raise FootballDataConfigError("FOOTBALL_DATA_TOKEN is not configured")

        query_string = urlencode({key: value for key, value in (params or {}).items() if value not in (None, "")})
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query_string:
            url = f"{url}?{query_string}"

        request = Request(url, headers={"X-Auth-Token": self.token})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8")[:500]
            except Exception:
                error_body = ""
            detail = f": {error_body}" if error_body else ""
            raise FootballDataClientError(f"football-data.org HTTP error {exc.code}{detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise FootballDataClientError(f"football-data.org request failed: {exc}") from exc

    def get_match(self, match_id):
        return self._request(f"matches/{match_id}")

    def get_matches(self, *, date_from: date | str | None = None, date_to: date | str | None = None, status=None):
        if isinstance(date_from, date):
            date_from = date_from.isoformat()
        if isinstance(date_to, date):
            date_to = date_to.isoformat()

        return self._request(
            "matches",
            {
                "dateFrom": date_from,
                "dateTo": date_to,
                "status": status,
            },
        ).get("matches", [])


class FootballDataSyncService:
    """Synchronizes football-data.org match results into local Match records.

    football-data.org does not provide the same event feed used by MatchEvent, so
    this service only updates score, final/live status and external team IDs.
    """

    FINISHED_STATUSES = {"FINISHED"}
    LIVE_STATUSES = {"IN_PLAY", "LIVE"}
    HALF_TIME_STATUSES = {"PAUSED"}
    NOT_STARTED_STATUSES = {"SCHEDULED", "TIMED", "POSTPONED", "SUSPENDED", "CANCELED", "CANCELLED"}

    def __init__(self, client=None):
        self.client = client or FootballDataClient()

    def sync_queryset(self, queryset):
        result = FootballDataSyncResult()
        for match in queryset:
            match_result = self.sync_match(match)
            result.checked += match_result.checked
            result.updated += match_result.updated
            result.skipped += match_result.skipped
        return result

    def sync_match(self, match):
        result = FootballDataSyncResult(checked=1)
        if not match.football_data_match_id:
            result.skipped = 1
            return result

        fixture = self.client.get_match(match.football_data_match_id)
        if not fixture:
            result.skipped = 1
            return result

        updated = self._update_match_from_fixture(match, fixture)
        if updated:
            result.updated = 1

        return result

    def _update_match_from_fixture(self, match, fixture):
        update_fields = []
        status = self._normalize_status(fixture.get("status"))
        score = fixture.get("score") or {}
        home_score, away_score = self._extract_score(score)

        update_fields += self._set_if_changed(match, "live_status", self._map_live_status(status))
        update_fields += self._set_if_changed(match, "finished", status in self.FINISHED_STATUSES)

        if home_score is not None:
            update_fields += self._set_if_changed(match, "home_score", int(home_score))
        if away_score is not None:
            update_fields += self._set_if_changed(match, "away_score", int(away_score))

        home_team = fixture.get("homeTeam") or {}
        away_team = fixture.get("awayTeam") or {}
        self._update_team_data(match, home_team, away_team)

        if update_fields:
            match.save(update_fields=list(dict.fromkeys(update_fields)))

        return bool(update_fields)

    def _extract_score(self, score):
        for key in ("fullTime", "regularTime", "halfTime"):
            value = score.get(key) or {}
            home = value.get("home")
            away = value.get("away")
            if home is not None or away is not None:
                return home, away
        return None, None

    def _map_live_status(self, status):
        status = self._normalize_status(status)
        if status in self.FINISHED_STATUSES:
            return "FT"
        if status in self.HALF_TIME_STATUSES:
            return "HT"
        if status in self.LIVE_STATUSES:
            return "LIVE"
        return "NS"

    def _normalize_status(self, status):
        return (status or "SCHEDULED").strip().upper()

    def _update_team_data(self, match, home_team, away_team):
        self._update_single_team_data(match.home_team, match.home_team_id, home_team)
        self._update_single_team_data(match.away_team, match.away_team_id, away_team)

    def _update_single_team_data(self, team, team_id, fixture_team):
        updates = {}
        football_data_team_id = fixture_team.get("id")
        tla = (fixture_team.get("tla") or "").strip().upper()
        flag = (fixture_team.get("crest") or "").strip()

        if football_data_team_id and team.football_data_team_id != football_data_team_id:
            updates["football_data_team_id"] = football_data_team_id
        if tla and team.tla != tla:
            updates["tla"] = tla
        if flag and team.flag != flag:
            updates["flag"] = flag

        if updates:
            Team.objects.filter(id=team_id).update(**updates)
            for field, value in updates.items():
                setattr(team, field, value)

    def _set_if_changed(self, instance, field, value):
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            return [field]
        return []

