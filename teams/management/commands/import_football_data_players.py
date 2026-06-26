from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from matches.services.football_data import (
    FootballDataClientError,
    FootballDataConfigError,
    FootballDataPlayersImportService,
)


class Command(BaseCommand):
    help = (
        "Importa jugadores/squads desde football-data.org hacia teams.Player. "
        "Por defecto solo muestra resumen; usa --commit para guardar."
    )

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
            "--commit",
            action="store_true",
            help="Guarda los jugadores. Sin esta opción el comando es dry-run.",
        )
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Con --commit, marca inactive los jugadores locales que no estén en los squads consultados.",
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        mode = "COMMIT" if commit else "DRY-RUN"
        service = FootballDataPlayersImportService(
            competition_code=options["competition"],
            season=options["season"],
        )

        self.stdout.write(
            f"football-data.org players importer {mode}: "
            f"competition={options['competition']}, season={options['season']}"
        )
        if options["deactivate_missing"] and not commit:
            self.stdout.write(self.style.WARNING("--deactivate-missing solo aplica cuando también usas --commit."))

        try:
            result = service.import_players(
                commit=commit,
                deactivate_missing=options["deactivate_missing"] and commit,
            )
        except (FootballDataConfigError, FootballDataClientError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "football-data.org players OK: "
                f"mode={mode}, teams_checked={result.checked_teams}, teams_matched={result.matched_teams}, "
                f"teams_skipped={result.skipped_teams}, team_detail_fetches={result.detail_fetches}, "
                f"players_checked={result.checked_players}, created={result.created}, updated={result.updated}, "
                f"unchanged={result.unchanged}, reactivated={result.reactivated}, "
                f"players_skipped={result.skipped_players}, deactivated={result.deactivated}"
            )
        )

