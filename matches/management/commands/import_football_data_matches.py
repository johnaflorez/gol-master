from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from matches.models import Match
from matches.services.football_data import FootballDataClient, FootballDataClientError, FootballDataConfigError
from teams.models import Team


class Command(BaseCommand):
    help = (
        "Consulta partidos de football-data.org y crea en la app los partidos que no existen. "
        "Usa Team.tla como llave principal para identificar selecciones. "
        "Por defecto solo muestra propuestas; usa --commit para guardar."
    )

    FINISHED_STATUSES = {"FINISHED"}
    LIVE_STATUSES = {"IN_PLAY", "LIVE"}
    HALF_TIME_STATUSES = {"PAUSED"}

    STAGE_PHASE_MAP = {
        "LAST_32": "DR",
        "ROUND_OF_32": "DR",
        "LAST_16": "OF",
        "ROUND_OF_16": "OF",
        "EIGHTH_FINALS": "OF",
        "QUARTER_FINALS": "CF",
        "SEMI_FINALS": "SF",
        "SEMI_FINAL": "SF",
        "FINAL": "F",
        "THIRD_PLACE": "F",
    }
    KNOCKOUT_PHASES = {"DR", "OF", "CF", "SF", "F"}

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Fecha local YYYY-MM-DD. Equivale a --from-date y --to-date.")
        parser.add_argument("--from-date", dest="from_date", help="Fecha local inicial YYYY-MM-DD.")
        parser.add_argument("--to-date", dest="to_date", help="Fecha local final YYYY-MM-DD.")
        parser.add_argument(
            "--fetch-padding-days",
            type=int,
            default=1,
            help="Días extra para consultar football-data.org antes/después del rango local por diferencias UTC. Default: 1.",
        )
        parser.add_argument(
            "--status",
            help="Status opcional para football-data.org (por ejemplo SCHEDULED, TIMED, IN_PLAY, FINISHED).",
        )
        parser.add_argument(
            "--stage",
            help="Stage opcional de football-data.org (por ejemplo LAST_32, LAST_16, QUARTER_FINALS).",
        )
        parser.add_argument(
            "--competition",
            default=settings.FOOTBALL_DATA_COMPETITION_CODE,
            help="Código de competencia football-data.org. Default: FOOTBALL_DATA_COMPETITION_CODE.",
        )
        parser.add_argument(
            "--season",
            type=int,
            default=settings.FOOTBALL_DATA_SEASON,
            help="Temporada football-data.org. Default: FOOTBALL_DATA_SEASON.",
        )
        parser.add_argument(
            "--global-matches",
            action="store_true",
            help="Usa el endpoint global /matches. Por defecto usa /competitions/<competition>/matches.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Crea los partidos. Sin esta opción el comando es dry-run.",
        )

    def handle(self, *args, **options):
        from_date, to_date = self._parse_date_range(options)
        query_from = from_date - timedelta(days=options["fetch_padding_days"])
        query_to = to_date + timedelta(days=options["fetch_padding_days"])

        client = FootballDataClient()
        try:
            if options.get("global_matches"):
                fixtures = client.get_matches(date_from=query_from, date_to=query_to, status=options.get("status"))
                source = "matches"
            else:
                fixtures = client.get_competition_matches(
                    competition_code=options.get("competition"),
                    season=options.get("season"),
                    date_from=query_from,
                    date_to=query_to,
                    status=options.get("status"),
                    stage=options.get("stage"),
                )
                source = f"competitions/{options.get('competition')}/matches"
        except (FootballDataConfigError, FootballDataClientError) as exc:
            raise CommandError(str(exc)) from exc

        mode = "COMMIT" if options["commit"] else "DRY-RUN"
        self.stdout.write(
            f"football-data.org importer {mode}: source={source}, local_range={from_date}..{to_date}, "
            f"fetched_range={query_from}..{query_to}, status={options.get('status') or 'ALL'}, "
            f"stage={options.get('stage') or 'ALL'}, fixtures={len(fixtures)}"
        )

        proposed = 0
        created = 0
        updated = 0
        skipped = 0
        out_of_range = 0

        for fixture in fixtures:
            fixture_datetime = self._fixture_datetime(fixture)
            if not fixture_datetime:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"SIN FECHA: {self._fixture_label(fixture)}"))
                continue

            local_date = timezone.localtime(fixture_datetime).date()
            if not from_date <= local_date <= to_date:
                out_of_range += 1
                continue

            external_id = fixture.get("id")
            if not external_id:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"SIN ID: {self._fixture_label(fixture)}"))
                continue

            if Match.objects.filter(football_data_match_id=external_id).exists():
                skipped += 1
                if options.get("verbosity", 1) >= 2:
                    self.stdout.write(f"YA EXISTE ID: football_data_match_id={external_id} | {self._fixture_label(fixture)}")
                continue

            home_team = self._find_team(fixture.get("homeTeam") or {})
            away_team = self._find_team(fixture.get("awayTeam") or {})
            if not home_team or not away_team:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        "SIN EQUIPO LOCAL: "
                        f"home={self._fixture_team_label(fixture.get('homeTeam') or {})} "
                        f"away={self._fixture_team_label(fixture.get('awayTeam') or {})} | "
                        f"{self._fixture_label(fixture)}"
                    )
                )
                continue

            match_data = self._match_data_from_fixture(fixture, home_team, away_team, fixture_datetime)

            placeholder_match = self._find_placeholder_knockout_match(match_data)
            if placeholder_match:
                proposed += 1
                self.stdout.write(
                    f"UPDATE CUADRO: match_id={placeholder_match.id} -> football_data_match_id={external_id} "
                    f"phase={match_data['phase']} bracket_position={match_data.get('bracket_position') or '-'} "
                    f"status={match_data['live_status']} finished={match_data['finished']} | "
                    f"{home_team} vs {away_team} | kickoff_at={fixture_datetime.isoformat()}"
                )
                if options["commit"]:
                    for field, value in match_data.items():
                        setattr(placeholder_match, field, value)
                    placeholder_match.save(update_fields=list(match_data.keys()))
                    self._update_team_from_fixture(home_team, fixture.get("homeTeam") or {})
                    self._update_team_from_fixture(away_team, fixture.get("awayTeam") or {})
                    updated += 1
                continue

            similar_match = self._find_similar_local_match(home_team, away_team, fixture_datetime)
            if similar_match:
                proposed += 1
                self.stdout.write(
                    f"UPDATE EXISTENTE: match_id={similar_match.id} -> football_data_match_id={external_id} "
                    f"phase={match_data['phase']} bracket_position={match_data.get('bracket_position') or '-'} "
                    f"status={match_data['live_status']} finished={match_data['finished']} | "
                    f"{home_team} vs {away_team} | kickoff_at={fixture_datetime.isoformat()}"
                )
                if options["commit"]:
                    for field, value in match_data.items():
                        setattr(similar_match, field, value)
                    similar_match.save(update_fields=list(match_data.keys()))
                    self._update_team_from_fixture(home_team, fixture.get("homeTeam") or {})
                    self._update_team_from_fixture(away_team, fixture.get("awayTeam") or {})
                    updated += 1
                continue

            proposed += 1
            self.stdout.write(
                f"CREATE: football_data_match_id={external_id} phase={match_data['phase']} "
                f"bracket_position={match_data.get('bracket_position') or '-'} "
                f"status={match_data['live_status']} finished={match_data['finished']} | "
                f"{home_team} vs {away_team} | kickoff_at={fixture_datetime.isoformat()}"
            )

            if options["commit"]:
                try:
                    match = Match.objects.create(**match_data)
                    self._update_team_from_fixture(home_team, fixture.get("homeTeam") or {})
                    self._update_team_from_fixture(away_team, fixture.get("awayTeam") or {})
                    created += 1
                    if options.get("verbosity", 1) >= 2:
                        self.stdout.write(self.style.SUCCESS(f"CREADO: match_id={match.id}"))
                except IntegrityError as exc:
                    skipped += 1
                    self.stdout.write(self.style.ERROR(f"ERROR creando football_data_match_id={external_id}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"football-data.org importer OK: mode={mode}, proposed={proposed}, created={created}, "
                f"updated={updated}, skipped={skipped}, out_of_range={out_of_range}"
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

    def _fixture_datetime(self, fixture):
        raw_datetime = fixture.get("utcDate")
        parsed = parse_datetime(raw_datetime) if raw_datetime else None
        if not parsed:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone=dt_timezone.utc)
        return parsed.astimezone(dt_timezone.utc)

    def _find_team(self, fixture_team):
        football_data_team_id = fixture_team.get("id")
        if football_data_team_id:
            team = Team.objects.filter(football_data_team_id=football_data_team_id).first()
            if team:
                return team

        tla = (fixture_team.get("tla") or "").strip().upper()
        if not tla:
            return None

        matches = list(Team.objects.filter(tla__iexact=tla).order_by("id")[:2])
        if len(matches) == 1:
            return matches[0]

        code_matches = list(Team.objects.filter(code__iexact=tla).order_by("id")[:2])
        if len(code_matches) == 1:
            return code_matches[0]
        return None

    def _find_similar_local_match(self, home_team, away_team, fixture_datetime):
        start = fixture_datetime - timedelta(minutes=10)
        end = fixture_datetime + timedelta(minutes=10)
        return Match.objects.filter(
            home_team=home_team,
            away_team=away_team,
            kickoff_at__range=(start, end),
            football_data_match_id__isnull=True,
        ).order_by("id").first()

    def _find_placeholder_knockout_match(self, match_data):
        phase = match_data.get("phase")
        bracket_position = match_data.get("bracket_position")
        if phase not in self.KNOCKOUT_PHASES or not bracket_position:
            return None

        return Match.objects.filter(
            phase=phase,
            bracket_position=bracket_position,
            home_team=match_data["home_team"],
            away_team=match_data["away_team"],
            football_data_match_id__isnull=True,
        ).order_by("id").first()

    def _match_data_from_fixture(self, fixture, home_team, away_team, fixture_datetime):
        status = self._normalize_status(fixture.get("status"))
        score = fixture.get("score") or {}
        home_score, away_score = self._extract_score(score)
        home_penalty_score, away_penalty_score = self._extract_penalties(score)
        finished = status in self.FINISHED_STATUSES
        phase = self._map_phase(fixture)

        return {
            "home_team": home_team,
            "away_team": away_team,
            "kickoff_at": fixture_datetime,
            "home_score": int(home_score) if home_score is not None else 0,
            "away_score": int(away_score) if away_score is not None else 0,
            "home_penalty_score": home_penalty_score,
            "away_penalty_score": away_penalty_score,
            "finished": finished,
            "phase": phase,
            "bracket_position": self._bracket_position_from_fixture(fixture, phase),
            "live_status": self._map_live_status(status),
            "football_data_match_id": fixture.get("id"),
            "football_data_winner": self._normalize_winner(score.get("winner")),
        }

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

    def _map_phase(self, fixture):
        stage = self._normalize_status(fixture.get("stage"))
        if stage in {"GROUP_STAGE", "GROUP"}:
            matchday = fixture.get("matchday")
            if matchday == 2:
                return "SR"
            if matchday == 3:
                return "TR"
            return "PR"
        return self.STAGE_PHASE_MAP.get(stage, "PR")

    def _bracket_position_from_fixture(self, fixture, phase):
        if phase not in self.KNOCKOUT_PHASES:
            return None
        try:
            matchday = int(fixture.get("matchday") or 0)
        except (TypeError, ValueError):
            return None
        return matchday or None

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
        return (status or "").strip().upper()

    def _normalize_winner(self, winner):
        winner = (winner or "").strip().upper()
        return winner if winner in {"HOME_TEAM", "AWAY_TEAM", "DRAW"} else ""

    def _update_team_from_fixture(self, team, fixture_team):
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
            Team.objects.filter(id=team.id).update(**updates)

    def _fixture_label(self, fixture):
        home = self._fixture_team_label(fixture.get("homeTeam") or {})
        away = self._fixture_team_label(fixture.get("awayTeam") or {})
        return f"{fixture.get('utcDate')} {home} vs {away}"

    def _fixture_team_label(self, fixture_team):
        name = fixture_team.get("name") or "?"
        tla = fixture_team.get("tla") or "?"
        return f"{name} ({tla})"

