from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from matches.models import Match
from matches.services.api_football import (
    ApiFootballClientError,
    ApiFootballConfigError,
    ApiFootballSyncService,
)


class Command(BaseCommand):
    help = (
        "Sincroniza automáticamente partidos mapeados que pueden estar en vivo o por finalizar "
        "usando API-Football/API-SPORTS. Pensado para ejecutarse desde cron."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-back",
            type=int,
            default=1,
            help="Días hacia atrás desde hoy para incluir partidos no finalizados. Default: 1.",
        )
        parser.add_argument(
            "--days-forward",
            type=int,
            default=1,
            help="Días hacia adelante desde hoy para incluir partidos no finalizados. Default: 1.",
        )
        parser.add_argument(
            "--no-events",
            action="store_true",
            help="No sincroniza eventos del partido.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        start_date = today - timedelta(days=options["days_back"])
        end_date = today + timedelta(days=options["days_forward"])

        queryset = Match.objects.exclude(
            api_football_fixture_id__isnull=True,
        ).filter(
            finished=False,
        ).filter(
            Q(kickoff_at__date__range=(start_date, end_date))
            | Q(live_status__in=["LIVE", "HT"])
        ).select_related(
            "home_team",
            "away_team",
        ).order_by("kickoff_at")

        selected_count = queryset.count()
        if options.get("verbosity", 1) >= 2:
            self.stdout.write(
                "Live API-Football selected matches: "
                f"count={selected_count}, window={start_date}..{end_date}"
            )
            for match in queryset:
                self.stdout.write(
                    " - "
                    f"match_id={match.id}, fixture_id={match.api_football_fixture_id}, "
                    f"kickoff_at={match.kickoff_at.isoformat()}, live_status={match.live_status}, "
                    f"finished={match.finished}, teams={match.home_team} vs {match.away_team}"
                )

        service = ApiFootballSyncService()
        try:
            result = service.sync_queryset(queryset, include_events=not options["no_events"])
        except (ApiFootballConfigError, ApiFootballClientError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Live API-Football sync OK: "
                f"selected={selected_count}, checked={result.checked}, updated={result.updated}, skipped={result.skipped}, "
                f"events_created={result.events_created}, events_updated={result.events_updated}, "
                f"window={start_date}..{end_date}"
            )
        )

