from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from users.services.whatsapp_reminders import MorningWhatsAppReminderService


class Command(BaseCommand):
    help = "Envía recordatorios matutinos por WhatsApp a usuarios con pronósticos pendientes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="reminder_date",
            default="today",
            help="Fecha objetivo en formato YYYY-MM-DD o 'today'. Por defecto: today.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simula el envío y registra el resultado sin llamar a WhatsApp API.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Permite reenviar aunque ya exista un log enviado para el usuario y fecha.",
        )

    def _parse_date(self, raw_value):
        if raw_value in (None, "", "today"):
            return timezone.localdate()
        try:
            return date.fromisoformat(raw_value)
        except ValueError as exc:
            raise CommandError("La fecha debe estar en formato YYYY-MM-DD o ser 'today'.") from exc

    def handle(self, *args, **options):
        reminder_date = self._parse_date(options["reminder_date"])
        service = MorningWhatsAppReminderService()
        summary = service.run(
            reminder_date=reminder_date,
            dry_run=options["dry_run"],
            force=options["force"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Recordatorios WhatsApp procesados: "
                f"fecha={reminder_date} "
                f"usuarios_revisados={summary.users_checked} "
                f"enviados={summary.sent} "
                f"pruebas={summary.dry_run} "
                f"omitidos={summary.skipped} "
                f"fallidos={summary.failed}"
            )
        )

