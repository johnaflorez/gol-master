import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from matches.models import Match
from matches.services.football_data import FootballDataClient, FootballDataClientError, FootballDataConfigError
from teams.models import Team


TEAM_NAME_ALIASES = {
    "alemania": {"germany"},
    "arabia saudita": {"saudi arabia"},
    "belgica": {"belgium"},
    "cabo verde": {"cape verde"},
    "corea del sur": {"korea republic", "south korea"},
    "costa de marfil": {"cote divoire", "cote d ivoire", "ivory coast"},
    "curazao": {"curacao"},
    "egipto": {"egypt"},
    "emiratos arabes unidos": {"united arab emirates", "uae"},
    "espana": {"spain"},
    "estados unidos": {"united states", "usa", "united states of america"},
    "francia": {"france"},
    "inglaterra": {"england"},
    "iran": {"iran"},
    "japon": {"japan"},
    "marruecos": {"morocco"},
    "mexico": {"mexico"},
    "nueva zelanda": {"new zealand"},
    "paises bajos": {"netherlands"},
    "polonia": {"poland"},
    "portugal": {"portugal"},
    "republica checa": {"czech republic", "czechia"},
    "suecia": {"sweden"},
    "suiza": {"switzerland"},
    "tunez": {"tunisia"},
    "turquia": {"turkiye", "turkey"},
}


@dataclass
class Candidate:
    fixture: dict
    score: int
    drift_seconds: float


class Command(BaseCommand):
    help = (
        "Consulta partidos de football-data.org y asigna football_data_match_id a partidos locales existentes. "
        "Por defecto solo muestra propuestas; usa --commit para guardar."
    )

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Fecha local YYYY-MM-DD. Equivale a --from-date y --to-date.")
        parser.add_argument("--from-date", dest="from_date", help="Fecha local inicial YYYY-MM-DD.")
        parser.add_argument("--to-date", dest="to_date", help="Fecha local final YYYY-MM-DD.")
        parser.add_argument(
            "--max-drift-minutes",
            type=int,
            default=180,
            help="Diferencia máxima permitida entre kickoff local y utcDate de football-data.org. Default: 180.",
        )
        parser.add_argument(
            "--fetch-padding-days",
            type=int,
            default=1,
            help="Días extra para consultar football-data.org antes/después del rango local por diferencias UTC. Default: 1.",
        )
        parser.add_argument(
            "--include-mapped",
            action="store_true",
            help="Incluye partidos locales que ya tienen football_data_match_id. Sin --commit no modifica nada.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Guarda los IDs encontrados. Sin esta opción el comando es dry-run.",
        )
        parser.add_argument(
            "--aliases-file",
            help="JSON opcional con alias adicionales: {'Nombre local': ['Football Data name']}.",
        )

    def handle(self, *args, **options):
        from_date, to_date = self._parse_date_range(options)
        max_drift = timedelta(minutes=options["max_drift_minutes"])
        aliases = self._load_aliases(options.get("aliases_file"))

        query_from = from_date - timedelta(days=options["fetch_padding_days"])
        query_to = to_date + timedelta(days=options["fetch_padding_days"])

        client = FootballDataClient()
        try:
            fixtures = client.get_matches(date_from=query_from, date_to=query_to)
        except (FootballDataConfigError, FootballDataClientError) as exc:
            raise CommandError(str(exc)) from exc

        queryset = Match.objects.select_related("home_team", "away_team").filter(
            kickoff_at__date__range=(from_date, to_date),
        )
        if not options["include_mapped"]:
            queryset = queryset.filter(football_data_match_id__isnull=True)
        queryset = queryset.order_by("kickoff_at", "id")

        existing_ids = set(
            Match.objects.exclude(football_data_match_id__isnull=True).values_list("football_data_match_id", flat=True)
        )
        if options["include_mapped"]:
            existing_ids = {
                external_id
                for external_id in existing_ids
                if external_id not in queryset.values_list("football_data_match_id", flat=True)
            }

        mode = "COMMIT" if options["commit"] else "DRY-RUN"
        self.stdout.write(
            f"football-data.org mapper {mode}: local_range={from_date}..{to_date}, "
            f"fetched_range={query_from}..{query_to}, fixtures={len(fixtures)}, local_matches={queryset.count()}"
        )

        mapped = 0
        proposed = 0
        skipped = 0
        ambiguous = 0

        for match in queryset:
            candidate_result = self._best_candidate(match, fixtures, max_drift, aliases, existing_ids)
            if candidate_result == "ambiguous":
                ambiguous += 1
                skipped += 1
                self.stdout.write(self.style.WARNING(f"AMBIGUO: {self._match_label(match)}"))
                continue
            if candidate_result is None:
                skipped += 1
                self.stdout.write(f"SIN MATCH: {self._match_label(match)}")
                continue

            candidate = candidate_result
            fixture = candidate.fixture
            fixture_id = fixture.get("id")
            proposed += 1
            self.stdout.write(
                f"MAP: local_match_id={match.id} -> football_data_match_id={fixture_id} "
                f"score={candidate.score} drift={int(candidate.drift_seconds // 60)}m | "
                f"{self._match_label(match)} == {self._fixture_label(fixture)}"
            )

            if options["commit"]:
                try:
                    match.football_data_match_id = fixture_id
                    match.save(update_fields=["football_data_match_id"])
                    self._update_team_ids(match, fixture)
                    existing_ids.add(fixture_id)
                    mapped += 1
                except IntegrityError as exc:
                    skipped += 1
                    self.stdout.write(self.style.ERROR(f"ERROR guardando match_id={match.id}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"football-data.org mapper OK: mode={mode}, proposed={proposed}, mapped={mapped}, "
                f"ambiguous={ambiguous}, skipped={skipped}"
            )
        )

    def _parse_date_range(self, options):
        if options.get("date"):
            from_date = to_date = self._parse_date(options["date"], "--date")
        else:
            from_date = self._parse_date(options.get("from_date"), "--from-date") if options.get("from_date") else timezone.localdate()
            to_date = self._parse_date(options.get("to_date"), "--to-date") if options.get("to_date") else from_date

        if from_date > to_date:
            raise CommandError("--from-date no puede ser mayor que --to-date")
        return from_date, to_date

    def _parse_date(self, raw_date, option_name):
        try:
            return datetime.strptime(raw_date, "%Y-%m-%d").date()
        except (TypeError, ValueError) as exc:
            raise CommandError(f"{option_name} debe tener formato YYYY-MM-DD") from exc

    def _load_aliases(self, aliases_file):
        aliases = {key: set(values) for key, values in TEAM_NAME_ALIASES.items()}
        if not aliases_file:
            return aliases

        try:
            with open(aliases_file, encoding="utf-8") as file:
                raw_aliases = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"No se pudo leer --aliases-file: {exc}") from exc

        for local_name, external_names in raw_aliases.items():
            normalized_local = self._normalize_text(local_name)
            aliases.setdefault(normalized_local, set())
            if isinstance(external_names, str):
                external_names = [external_names]
            aliases[normalized_local].update(self._normalize_text(name) for name in external_names)
        return aliases

    def _best_candidate(self, match, fixtures, max_drift, aliases, existing_ids):
        candidates = []
        for fixture in fixtures:
            fixture_id = fixture.get("id")
            if not fixture_id or fixture_id in existing_ids:
                continue

            fixture_datetime = self._fixture_datetime(fixture)
            if not fixture_datetime:
                continue

            drift = abs(match.kickoff_at - fixture_datetime)
            if drift > max_drift:
                continue

            home_score = self._team_score(match.home_team, fixture.get("homeTeam") or {}, aliases)
            away_score = self._team_score(match.away_team, fixture.get("awayTeam") or {}, aliases)
            if not home_score or not away_score:
                continue

            candidates.append(
                Candidate(
                    fixture=fixture,
                    score=home_score + away_score,
                    drift_seconds=drift.total_seconds(),
                )
            )

        if not candidates:
            return None

        candidates.sort(key=lambda candidate: (-candidate.score, candidate.drift_seconds))
        best = candidates[0]
        tied = [candidate for candidate in candidates if candidate.score == best.score and candidate.drift_seconds == best.drift_seconds]
        if len(tied) > 1:
            return "ambiguous"
        return best

    def _team_score(self, team, fixture_team, aliases):
        fixture_id = fixture_team.get("id")
        fixture_tla = (fixture_team.get("tla") or "").strip().upper()
        fixture_name = self._normalize_text(fixture_team.get("name"))
        team_name = self._normalize_text(team.name)
        team_tla = (getattr(team, "tla", "") or "").strip().upper()

        if team.football_data_team_id and fixture_id == team.football_data_team_id:
            return 5

        # When the local team has a football-data TLA, use it as the authoritative key.
        # This avoids false positives because Team.code can differ from football-data.org
        # values (e.g. DEU vs GER, NLD vs NED, PRT vs POR).
        if team_tla:
            return 4 if fixture_tla == team_tla else 0

        # Fallbacks only apply to teams that still do not have tla populated.
        if team.code and fixture_tla and team.code.upper() == fixture_tla:
            return 3
        if fixture_name and fixture_name == team_name:
            return 3
        if fixture_name and fixture_name in aliases.get(team_name, set()):
            return 3
        return 0

    def _fixture_datetime(self, fixture):
        raw_datetime = fixture.get("utcDate")
        parsed = parse_datetime(raw_datetime) if raw_datetime else None
        if not parsed:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone=dt_timezone.utc)
        return parsed.astimezone(dt_timezone.utc)

    def _normalize_text(self, value):
        value = unicodedata.normalize("NFKD", value or "")
        value = "".join(character for character in value if not unicodedata.combining(character))
        value = value.lower().replace("&", " and ")
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    def _update_team_ids(self, match, fixture):
        home_team = fixture.get("homeTeam") or {}
        away_team = fixture.get("awayTeam") or {}
        updates = []

        home_updates = self._team_updates_from_fixture(match.home_team, home_team)
        if home_updates:
            Team.objects.filter(id=match.home_team_id).update(**home_updates)
            updates.append("home_team")

        away_updates = self._team_updates_from_fixture(match.away_team, away_team)
        if away_updates:
            Team.objects.filter(id=match.away_team_id).update(**away_updates)
            updates.append("away_team")

        return updates

    def _team_updates_from_fixture(self, team, fixture_team):
        updates = {}
        fixture_id = fixture_team.get("id")
        fixture_tla = (fixture_team.get("tla") or "").strip().upper()
        fixture_flag = (fixture_team.get("crest") or "").strip()

        if fixture_id and team.football_data_team_id != fixture_id:
            updates["football_data_team_id"] = fixture_id
        if fixture_tla and team.tla != fixture_tla:
            updates["tla"] = fixture_tla
        if fixture_flag and team.flag != fixture_flag:
            updates["flag"] = fixture_flag

        return updates

    def _match_label(self, match):
        return f"{match.kickoff_at.isoformat()} {match.home_team} vs {match.away_team}"

    def _fixture_label(self, fixture):
        home = (fixture.get("homeTeam") or {}).get("name") or "?"
        away = (fixture.get("awayTeam") or {}).get("name") or "?"
        return f"{fixture.get('utcDate')} {home} vs {away}"

