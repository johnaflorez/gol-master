import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

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

