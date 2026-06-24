from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.utils import timezone

from matches.models import Match
from predictions.models import Prediction
from users.models import WhatsAppReminderLog
from users.services.whatsapp import WhatsAppCloudClient


@dataclass
class ReminderRunSummary:
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    dry_run: int = 0
    users_checked: int = 0


class MorningWhatsAppReminderService:
    """Sends morning reminders to users with pending predictions for the target date."""

    def __init__(self, *, client=None):
        self.client = client or WhatsAppCloudClient()

    def _open_matches_for_date(self, reminder_date):
        return Match.objects.filter(
            kickoff_at__date=reminder_date,
            kickoff_at__gt=timezone.now(),
            finished=False,
        ).select_related("home_team", "away_team").order_by("kickoff_at")

    def _eligible_users(self):
        return User.objects.filter(
            profile__whatsapp_notifications_enabled=True,
            profile__whatsapp_phone_number__startswith="+",
        ).select_related("profile").order_by("first_name", "last_name", "username")

    def _pending_matches_for_user(self, *, user, matches):
        match_ids = [match.id for match in matches]
        predicted_match_ids = set(
            Prediction.objects.filter(user=user, match_id__in=match_ids).values_list("match_id", flat=True)
        )
        return [match for match in matches if match.id not in predicted_match_ids]

    def _body_parameters(self, *, user, pending_count):
        display_name = user.get_full_name() or user.username
        app_url = getattr(settings, "WHATSAPP_APP_URL", "") or "Mundial Familiar 2026"
        return [display_name, pending_count, app_url]

    def _get_or_create_log(self, *, user, reminder_date, phone_number, pending_count):
        try:
            log, _ = WhatsAppReminderLog.objects.get_or_create(
                user=user,
                reminder_date=reminder_date,
                reminder_type=WhatsAppReminderLog.REMINDER_MORNING_PREDICTION,
                defaults={
                    "phone_number": phone_number,
                    "pending_match_count": pending_count,
                    "status": WhatsAppReminderLog.STATUS_SKIPPED,
                },
            )
        except IntegrityError:
            log = WhatsAppReminderLog.objects.get(
                user=user,
                reminder_date=reminder_date,
                reminder_type=WhatsAppReminderLog.REMINDER_MORNING_PREDICTION,
            )
        return log

    def run(self, *, reminder_date=None, dry_run=False, force=False):
        reminder_date = reminder_date or timezone.localdate()
        matches = list(self._open_matches_for_date(reminder_date))
        summary = ReminderRunSummary()

        if not matches:
            return summary

        for user in self._eligible_users():
            summary.users_checked += 1
            pending_matches = self._pending_matches_for_user(user=user, matches=matches)
            pending_count = len(pending_matches)

            if pending_count == 0:
                summary.skipped += 1
                continue

            phone_number = user.profile.whatsapp_phone_number
            log = self._get_or_create_log(
                user=user,
                reminder_date=reminder_date,
                phone_number=phone_number,
                pending_count=pending_count,
            )

            if log.status == WhatsAppReminderLog.STATUS_SENT and not force:
                summary.skipped += 1
                continue

            log.phone_number = phone_number
            log.pending_match_count = pending_count
            log.error_message = ""

            if dry_run:
                log.status = WhatsAppReminderLog.STATUS_DRY_RUN
                log.provider_message_id = ""
                log.save(update_fields=["phone_number", "pending_match_count", "status", "provider_message_id", "error_message", "updated_at"])
                summary.dry_run += 1
                continue

            try:
                result = self.client.send_template(
                    to=phone_number,
                    template_name=getattr(settings, "WHATSAPP_TEMPLATE_NAME", "daily_prediction_reminder"),
                    language_code=getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "es"),
                    body_parameters=self._body_parameters(user=user, pending_count=pending_count),
                )
            except Exception as exc:
                log.status = WhatsAppReminderLog.STATUS_FAILED
                log.provider_message_id = ""
                log.error_message = str(exc)[:2000]
                log.save(update_fields=["phone_number", "pending_match_count", "status", "provider_message_id", "error_message", "updated_at"])
                summary.failed += 1
                continue

            log.status = WhatsAppReminderLog.STATUS_SENT
            log.provider_message_id = result.provider_message_id
            log.error_message = ""
            log.save(update_fields=["phone_number", "pending_match_count", "status", "provider_message_id", "error_message", "updated_at"])
            summary.sent += 1

        return summary

