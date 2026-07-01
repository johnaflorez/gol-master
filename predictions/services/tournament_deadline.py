from datetime import datetime

from django.conf import settings
from django.utils import timezone

DEFAULT_TOURNAMENT_PREDICTION_DEADLINE = "2026-07-04 12:00"


def get_tournament_prediction_deadline():
    """Return the champion/top-scorer voting deadline in the active timezone."""
    raw_value = getattr(settings, "TOURNAMENT_PREDICTION_DEADLINE", DEFAULT_TOURNAMENT_PREDICTION_DEADLINE)
    naive_deadline = datetime.strptime(raw_value, "%Y-%m-%d %H:%M")
    return timezone.make_aware(naive_deadline, timezone.get_current_timezone())


def is_tournament_prediction_closed(now=None):
    now = now or timezone.now()
    return now >= get_tournament_prediction_deadline()
