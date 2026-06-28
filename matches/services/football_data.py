import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.dateparse import parse_date

from matches.models import Match
from stats.models import TopScorerStanding
from teams.models import Player
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
    scorers_refreshed: bool = False
    scorer_rows_updated: int = 0
    scorer_rows_deleted: int = 0
    scorer_error: str = ""


@dataclass
class FootballDataTopScorersResult:
    checked: int = 0
    updated: int = 0
    deleted: int = 0


@dataclass
class FootballDataPlayersImportResult:
    checked_teams: int = 0
    matched_teams: int = 0
    skipped_teams: int = 0
    detail_fetches: int = 0
    checked_players: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    reactivated: int = 0
    skipped_players: int = 0
    deactivated: int = 0


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

    def get_competition_matches(
        self,
        *,
        competition_code=None,
        season=None,
        date_from: date | str | None = None,
        date_to: date | str | None = None,
        status=None,
        stage=None,
    ):
        competition_code = competition_code or settings.FOOTBALL_DATA_COMPETITION_CODE
        if isinstance(date_from, date):
            date_from = date_from.isoformat()
        if isinstance(date_to, date):
            date_to = date_to.isoformat()

        return self._request(
            f"competitions/{competition_code}/matches",
            {
                "season": season if season is not None else settings.FOOTBALL_DATA_SEASON,
                "dateFrom": date_from,
                "dateTo": date_to,
                "status": status,
                "stage": stage,
            },
        ).get("matches", [])

    def get_scorers(self, *, competition_code=None, season=None, limit=None):
        competition_code = competition_code or settings.FOOTBALL_DATA_COMPETITION_CODE
        if limit is None:
            limit = getattr(settings, "FOOTBALL_DATA_SCORERS_LIMIT", 500)
        return self._request(
            f"competitions/{competition_code}/scorers",
            {
                "season": season if season is not None else settings.FOOTBALL_DATA_SEASON,
                "limit": limit,
            },
        ).get("scorers", [])

    def get_competition_teams(self, *, competition_code=None, season=None):
        competition_code = competition_code or settings.FOOTBALL_DATA_COMPETITION_CODE
        return self._request(
            f"competitions/{competition_code}/teams",
            {"season": season if season is not None else settings.FOOTBALL_DATA_SEASON},
        ).get("teams", [])

    def get_team(self, team_id):
        return self._request(f"teams/{team_id}")


class FootballDataPlayersImportService:
    """Imports national-team squad players from football-data.org into Player."""

    def __init__(self, client=None, competition_code=None, season=None):
        self.client = client or FootballDataClient()
        self.competition_code = competition_code or settings.FOOTBALL_DATA_COMPETITION_CODE
        self.season = season if season is not None else settings.FOOTBALL_DATA_SEASON

    def import_players(self, *, commit=False, deactivate_missing=False):
        competition_teams = self.client.get_competition_teams(
            competition_code=self.competition_code,
            season=self.season,
        )
        result = FootballDataPlayersImportResult(checked_teams=len(competition_teams))
        seen_player_ids = set()
        seen_team_player_keys = set()
        seen_team_ids = set()

        for team_payload in competition_teams:
            local_team = self._find_team(team_payload)
            if not local_team:
                result.skipped_teams += 1
                continue

            result.matched_teams += 1
            seen_team_ids.add(local_team.id)
            if commit:
                self._update_team_from_payload(local_team, team_payload)

            squad = team_payload.get("squad") or []
            if not squad and team_payload.get("id"):
                detailed_team_payload = self.client.get_team(team_payload["id"])
                result.detail_fetches += 1
                squad = detailed_team_payload.get("squad") or []
                if commit:
                    self._update_team_from_payload(local_team, detailed_team_payload)

            for player_payload in squad:
                outcome, player_key = self._upsert_player(local_team, player_payload, commit=commit)
                setattr(result, outcome, getattr(result, outcome) + 1)
                result.checked_players += 1
                if player_payload.get("id"):
                    seen_player_ids.add(player_payload["id"])
                if player_key:
                    seen_team_player_keys.add(player_key)

        if commit and deactivate_missing:
            result.deactivated = self._deactivate_missing(seen_player_ids, seen_team_player_keys, seen_team_ids)

        return result

    def _upsert_player(self, team, player_payload, *, commit):
        name = (player_payload.get("name") or "").strip()
        if not name:
            return "skipped_players", ""

        player = self._find_player(team, player_payload, name)
        defaults = self._player_defaults(player_payload)
        team_player_key = f"{team.pk}:{name.casefold()}"

        if not player:
            if commit:
                Player.objects.create(team=team, name=name, active=True, **defaults)
            return "created", team_player_key

        changed_fields = []
        if player.team_id != team.id:
            player.team = team
            changed_fields.append("team")
        if player.name != name:
            player.name = name
            changed_fields.append("name")
        if not player.active:
            player.active = True
            changed_fields.append("active")
        for field, value in defaults.items():
            if getattr(player, field) != value:
                setattr(player, field, value)
                changed_fields.append(field)

        if changed_fields:
            if commit:
                player.save(update_fields=[*dict.fromkeys(changed_fields), "updated_at"])
            if "active" in changed_fields and len(changed_fields) == 1:
                return "reactivated", team_player_key
            return "updated", team_player_key

        return "unchanged", team_player_key

    def _find_team(self, team_payload):
        football_data_team_id = team_payload.get("id")
        if football_data_team_id:
            team = Team.objects.filter(football_data_team_id=football_data_team_id).first()
            if team:
                return team

        tla = (team_payload.get("tla") or "").strip().upper()
        if tla:
            team = Team.objects.filter(tla__iexact=tla).first() or Team.objects.filter(code__iexact=tla).first()
            if team:
                return team
        return None

    def _find_player(self, team, player_payload, name):
        football_data_player_id = player_payload.get("id")
        if football_data_player_id:
            player = Player.objects.filter(football_data_player_id=football_data_player_id).first()
            if player:
                return player
        return Player.objects.filter(team=team, name__iexact=name).first()

    def _player_defaults(self, player_payload):
        raw_date_of_birth = player_payload.get("dateOfBirth") or player_payload.get("date_of_birth")
        defaults = {
            "position": (player_payload.get("position") or "").strip(),
            "date_of_birth": parse_date(raw_date_of_birth) if raw_date_of_birth else None,
            "nationality": (player_payload.get("nationality") or "").strip(),
        }
        if player_payload.get("id"):
            defaults["football_data_player_id"] = player_payload["id"]
        return defaults

    def _update_team_from_payload(self, team, team_payload):
        updates = {}
        football_data_team_id = team_payload.get("id")
        tla = (team_payload.get("tla") or "").strip().upper()
        crest = (team_payload.get("crest") or "").strip()
        if football_data_team_id and team.football_data_team_id != football_data_team_id:
            updates["football_data_team_id"] = football_data_team_id
        if tla and team.tla != tla:
            updates["tla"] = tla
        if crest and team.flag != crest:
            updates["flag"] = crest
        if updates:
            Team.objects.filter(pk=team.pk).update(**updates)
            for field, value in updates.items():
                setattr(team, field, value)

    def _deactivate_missing(self, seen_player_ids, seen_team_player_keys, seen_team_ids):
        queryset = Player.objects.filter(active=True, team_id__in=seen_team_ids)
        deactivated = 0
        for player in queryset.select_related("team"):
            if player.football_data_player_id and player.football_data_player_id in seen_player_ids:
                continue
            if f"{player.team_id}:{player.name.casefold()}" in seen_team_player_keys:
                continue
            player.active = False
            player.save(update_fields=["active", "updated_at"])
            deactivated += 1
        return deactivated


class FootballDataTopScorersService:
    """Refreshes top scorer standings from football-data.org."""

    def __init__(self, client=None, competition_code=None, season=None):
        self.client = client or FootballDataClient()
        self.competition_code = competition_code or settings.FOOTBALL_DATA_COMPETITION_CODE
        self.season = season if season is not None else settings.FOOTBALL_DATA_SEASON

    def refresh(self, *, limit=None):
        scorers = self.client.get_scorers(
            competition_code=self.competition_code,
            season=self.season,
            limit=limit,
        )
        result = FootballDataTopScorersResult(checked=len(scorers))
        seen_keys = set()

        for index, scorer in enumerate(scorers, start=1):
            defaults, external_key = self._build_standing_defaults(index, scorer)
            seen_keys.add(external_key)
            _, created = TopScorerStanding.objects.update_or_create(
                competition_code=self.competition_code,
                season=self.season,
                external_key=external_key,
                defaults=defaults,
            )
            result.updated += 1 if created or defaults else 0

        stale_queryset = TopScorerStanding.objects.filter(
            competition_code=self.competition_code,
            season=self.season,
        ).exclude(external_key__in=seen_keys)
        result.deleted = stale_queryset.count()
        stale_queryset.delete()
        return result

    def _build_standing_defaults(self, rank, scorer):
        player_payload = scorer.get("player") or {}
        team_payload = scorer.get("team") or {}
        player_name = (player_payload.get("name") or "Jugador sin nombre").strip()
        team = self._find_team(team_payload)
        player = self._find_player(team, player_name)
        team_tla = (team_payload.get("tla") or "").strip().upper()
        team_crest = (team_payload.get("crest") or "").strip()
        team_name = (team_payload.get("name") or getattr(team, "name", "") or "").strip()
        football_data_player_id = player_payload.get("id")
        external_key = self._build_external_key(football_data_player_id, player_name, team_payload)

        if team:
            self._update_team_from_payload(team, team_payload)

        return {
            "rank": rank,
            "football_data_player_id": football_data_player_id,
            "player": player,
            "player_name": player_name,
            "team": team,
            "team_name": team_name,
            "team_tla": team_tla,
            "team_crest": team_crest,
            "played_matches": self._safe_int(scorer.get("playedMatches")),
            "goals": self._safe_int(scorer.get("goals")),
            "assists": self._safe_nullable_int(scorer.get("assists")),
            "penalties": self._safe_nullable_int(scorer.get("penalties")),
            "raw_payload": scorer,
        }, external_key

    def _find_team(self, team_payload):
        football_data_team_id = team_payload.get("id")
        if football_data_team_id:
            team = Team.objects.filter(football_data_team_id=football_data_team_id).first()
            if team:
                return team

        tla = (team_payload.get("tla") or "").strip().upper()
        if tla:
            return Team.objects.filter(tla__iexact=tla).first()
        return None

    def _find_player(self, team, player_name):
        if not team or not player_name:
            return None
        return Player.objects.filter(team=team, name__iexact=player_name).first()

    def _update_team_from_payload(self, team, team_payload):
        updates = {}
        football_data_team_id = team_payload.get("id")
        tla = (team_payload.get("tla") or "").strip().upper()
        crest = (team_payload.get("crest") or "").strip()
        if football_data_team_id and team.football_data_team_id != football_data_team_id:
            updates["football_data_team_id"] = football_data_team_id
        if tla and team.tla != tla:
            updates["tla"] = tla
        if crest and team.flag != crest:
            updates["flag"] = crest
        if updates:
            Team.objects.filter(pk=team.pk).update(**updates)

    def _build_external_key(self, football_data_player_id, player_name, team_payload):
        if football_data_player_id:
            return f"player:{football_data_player_id}"
        team_key = team_payload.get("id") or team_payload.get("tla") or team_payload.get("name") or "unknown"
        return f"name:{self._normalize_key(player_name)}|team:{self._normalize_key(str(team_key))}"

    def _normalize_key(self, value):
        normalized = unicodedata.normalize("NFKD", value or "")
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-") or "unknown"

    def _safe_int(self, value):
        return int(value or 0)

    def _safe_nullable_int(self, value):
        return None if value is None else int(value)


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

    def sync_queryset(self, queryset, *, refresh_scorers=True):
        result = FootballDataSyncResult()
        for match in queryset:
            match_result = self.sync_match(match, refresh_scorers=False)
            result.checked += match_result.checked
            result.updated += match_result.updated
            result.skipped += match_result.skipped
        if refresh_scorers and result.updated:
            self._refresh_scorers(result)
        return result

    def sync_queryset_from_match_list(self, queryset, *, date_from, date_to, refresh_scorers=True):
        fixtures = self.client.get_matches(date_from=date_from, date_to=date_to)
        fixtures_by_id = {fixture.get("id"): fixture for fixture in fixtures if fixture.get("id")}
        result = FootballDataSyncResult()

        for match in queryset:
            match_result = self._sync_match_from_fixture(match, fixtures_by_id.get(match.football_data_match_id))
            result.checked += match_result.checked
            result.updated += match_result.updated
            result.skipped += match_result.skipped

        if refresh_scorers and result.updated:
            self._refresh_scorers(result)
        return result

    def sync_match(self, match, *, refresh_scorers=True):
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
            if refresh_scorers:
                self._refresh_scorers(result)

        return result

    def _sync_match_from_fixture(self, match, fixture):
        result = FootballDataSyncResult(checked=1)
        if not match.football_data_match_id or not fixture:
            result.skipped = 1
            return result

        updated = self._update_match_from_fixture(match, fixture)
        if updated:
            result.updated = 1
        return result

    def _refresh_scorers(self, result):
        try:
            scorer_result = FootballDataTopScorersService(client=self.client).refresh()
        except (FootballDataConfigError, FootballDataClientError) as exc:
            result.scorer_error = str(exc)
            return

        result.scorers_refreshed = True
        result.scorer_rows_updated = scorer_result.updated
        result.scorer_rows_deleted = scorer_result.deleted

    def _update_match_from_fixture(self, match, fixture):
        update_fields = []
        status = self._normalize_status(fixture.get("status"))
        score = fixture.get("score") or {}
        home_score, away_score = self._extract_score(score)
        home_penalty_score, away_penalty_score = self._extract_penalties(score)

        update_fields += self._set_if_changed(match, "live_status", self._map_live_status(status))
        update_fields += self._set_if_changed(match, "finished", status in self.FINISHED_STATUSES)
        update_fields += self._set_if_changed(match, "football_data_winner", self._normalize_winner(score.get("winner")))

        if home_score is not None:
            update_fields += self._set_if_changed(match, "home_score", int(home_score))
        if away_score is not None:
            update_fields += self._set_if_changed(match, "away_score", int(away_score))
        update_fields += self._set_if_changed(match, "home_penalty_score", home_penalty_score)
        update_fields += self._set_if_changed(match, "away_penalty_score", away_penalty_score)

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

    def _extract_penalties(self, score):
        penalties = score.get("penalties") or {}
        home = penalties.get("home")
        away = penalties.get("away")
        return (
            int(home) if home is not None else None,
            int(away) if away is not None else None,
        )

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

    def _normalize_winner(self, winner):
        winner = (winner or "").strip().upper()
        return winner if winner in {"HOME_TEAM", "AWAY_TEAM", "DRAW"} else ""

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

