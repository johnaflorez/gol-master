from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from matches.services.football_data import (
    FootballDataClientError,
    FootballDataConfigError,
    FootballDataTopScorersService,
)


class Command(BaseCommand):
    help = "Actualiza manualmente la tabla de goleadores desde football-data.org."

    def add_arguments(self, parser):
        parser.add_argument(
            "--competition",
            default=settings.FOOTBALL_DATA_COMPETITION_CODE,
            help="Código de competencia football-data.org. Default: settings.FOOTBALL_DATA_COMPETITION_CODE.",
        )
        parser.add_argument(
            "--season",
            type=int,
            default=settings.FOOTBALL_DATA_SEASON,
            help="Temporada football-data.org. Default: settings.FOOTBALL_DATA_SEASON.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Límite opcional de goleadores a consultar.",
        )

    def handle(self, *args, **options):
        service = FootballDataTopScorersService(
            competition_code=options["competition"],
            season=options["season"],
        )
        try:
            result = service.refresh(limit=options.get("limit"))
        except (FootballDataConfigError, FootballDataClientError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "football-data.org scorers OK: "
                f"competition={options['competition']}, season={options['season']}, "
                f"checked={result.checked}, updated={result.updated}, deleted={result.deleted}"
            )
        )

