from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from matches.models import Match
from matches.services.api_football import (
    ApiFootballClientError,
    ApiFootballConfigError,
    ApiFootballSyncService,
)


class Command(BaseCommand):
    help = "Sincroniza marcadores, estado en vivo y eventos desde API-Football/API-SPORTS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture-id",
            type=int,
            action="append",
            dest="fixture_ids",
            help="ID externo de API-Football. Se puede repetir.",
        )
        parser.add_argument(
            "--date",
            type=str,
            help="Sincroniza partidos locales de una fecha YYYY-MM-DD con api_football_fixture_id.",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Sincroniza partidos mapeados que no estén finalizados.",
        )
        parser.add_argument(
            "--no-events",
            action="store_true",
            help="No sincroniza eventos del partido.",
        )

    def handle(self, *args, **options):
        queryset = Match.objects.exclude(api_football_fixture_id__isnull=True).select_related(
            "home_team",
            "away_team",
        )

        fixture_ids = options.get("fixture_ids")
        if fixture_ids:
            queryset = queryset.filter(api_football_fixture_id__in=fixture_ids)

        sync_date = options.get("date")
        if sync_date:
            try:
                parsed_date = datetime.strptime(sync_date, "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--date debe tener formato YYYY-MM-DD") from exc
            queryset = queryset.filter(kickoff_at__date=parsed_date)

        if options.get("live"):
            queryset = queryset.filter(finished=False)

        if not fixture_ids and not sync_date and not options.get("live"):
            today = timezone.localdate()
            queryset = queryset.filter(finished=False, kickoff_at__date__gte=today)

        service = ApiFootballSyncService()
        try:
            result = service.sync_queryset(queryset, include_events=not options.get("no_events"))
        except (ApiFootballConfigError, ApiFootballClientError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "API-Football sync OK: "
                f"checked={result.checked}, updated={result.updated}, skipped={result.skipped}, "
                f"events_created={result.events_created}, events_updated={result.events_updated}"
            )
        )

