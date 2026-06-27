from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from matches.models import Match
from matches.services.football_data import (
    FootballDataClientError,
    FootballDataConfigError,
    FootballDataSyncService,
)


class Command(BaseCommand):
    help = (
        "Sincroniza marcadores y estado desde football-data.org. "
        "No sincroniza eventos porque football-data.org no expone un feed equivalente a MatchEvent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--match-id",
            type=int,
            action="append",
            dest="match_ids",
            help="ID externo del partido en football-data.org. Se puede repetir.",
        )
        parser.add_argument(
            "--date",
            type=str,
            help="Sincroniza partidos locales de una fecha YYYY-MM-DD con football_data_match_id.",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Sincroniza partidos mapeados no finalizados que pueden estar en vivo.",
        )
        parser.add_argument(
            "--days-back",
            type=int,
            default=1,
            help="Días hacia atrás desde hoy para incluir partidos no finalizados cuando se usa --live. Default: 1.",
        )
        parser.add_argument(
            "--days-forward",
            type=int,
            default=1,
            help="Días hacia adelante desde hoy para incluir partidos no finalizados cuando se usa --live. Default: 1.",
        )
        parser.add_argument(
            "--no-refresh-scorers",
            action="store_true",
            help="No actualiza la tabla de goleadores al terminar la sincronización de marcadores.",
        )
        parser.add_argument(
            "--fetch-padding-days",
            type=int,
            default=1,
            help=(
                "Días extra para consultar football-data.org antes/después del rango local en modo --live. "
                "Evita perder partidos nocturnos por diferencias UTC. Default: 1."
            ),
        )

    def handle(self, *args, **options):
        queryset = Match.objects.exclude(
            football_data_match_id__isnull=True,
        ).select_related(
            "home_team",
            "away_team",
        )

        match_ids = options.get("match_ids")
        if match_ids:
            queryset = queryset.filter(football_data_match_id__in=match_ids)

        sync_date = options.get("date")
        if sync_date:
            try:
                parsed_date = datetime.strptime(sync_date, "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--date debe tener formato YYYY-MM-DD") from exc
            queryset = queryset.filter(kickoff_at__date=parsed_date)

        if options.get("live"):
            today = timezone.localdate()
            start_date = today - timedelta(days=options["days_back"])
            end_date = today + timedelta(days=options["days_forward"])
            queryset = queryset.filter(
                finished=False,
            ).filter(
                Q(kickoff_at__date__range=(start_date, end_date))
                | Q(live_status__in=["LIVE", "HT"])
            )
        elif not match_ids and not sync_date:
            today = timezone.localdate()
            queryset = queryset.filter(finished=False, kickoff_at__date__gte=today)

        queryset = queryset.order_by("kickoff_at")
        selected_count = queryset.count()
        if options.get("verbosity", 1) >= 2:
            self.stdout.write(f"football-data.org selected matches: count={selected_count}")
            for match in queryset:
                self.stdout.write(
                    " - "
                    f"match_id={match.id}, football_data_match_id={match.football_data_match_id}, "
                    f"kickoff_at={match.kickoff_at.isoformat()}, live_status={match.live_status}, "
                    f"finished={match.finished}, teams={match.home_team} vs {match.away_team}"
                )

        refresh_scorers = not options.get("no_refresh_scorers")
        service = FootballDataSyncService()
        try:
            if options.get("live") and selected_count:
                date_bounds = list(queryset.dates("kickoff_at", "day", order="ASC"))
                fetch_padding = timedelta(days=options["fetch_padding_days"])
                date_from = date_bounds[0] - fetch_padding
                date_to = date_bounds[-1] + fetch_padding
                if options.get("verbosity", 1) >= 2:
                    self.stdout.write(f"football-data.org fetched range: dateFrom={date_from}, dateTo={date_to}")
                result = service.sync_queryset_from_match_list(
                    queryset,
                    date_from=date_from,
                    date_to=date_to,
                    refresh_scorers=refresh_scorers,
                )
            else:
                result = service.sync_queryset(queryset, refresh_scorers=refresh_scorers)
        except (FootballDataConfigError, FootballDataClientError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "football-data.org sync OK: "
                f"selected={selected_count}, checked={result.checked}, updated={result.updated}, skipped={result.skipped}"
            )
        )
        if result.scorers_refreshed:
            self.stdout.write(
                self.style.SUCCESS(
                    "football-data.org scorers OK: "
                    f"updated={result.scorer_rows_updated}, deleted={result.scorer_rows_deleted}"
                )
            )
        elif result.scorer_error:
            self.stdout.write(self.style.WARNING(f"football-data.org scorers WARNING: {result.scorer_error}"))

