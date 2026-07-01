import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from matches.models import Match
from matches.services.football_data import (
    FootballDataClientError,
    FootballDataConfigError,
    FootballDataSyncResult,
    FootballDataSyncService,
)


logger = logging.getLogger(__name__)

LAST_ATTEMPT_CACHE_KEY = "football_data:opportunistic_live_sync:last_attempt"
LOCK_CACHE_KEY = "football_data:opportunistic_live_sync:lock"
LIVE_STATUSES = ["LIVE", "HT"]


@dataclass(frozen=True)
class OpportunisticLiveSyncSummary:
    attempted: bool = False
    reason: str = ""
    selected: int = 0
    checked: int = 0
    updated: int = 0
    skipped: int = 0
    error: str = ""

    def as_dict(self):
        return {
            "attempted": self.attempted,
            "reason": self.reason,
            "selected": self.selected,
            "checked": self.checked,
            "updated": self.updated,
            "skipped": self.skipped,
            "error": self.error,
        }


def maybe_sync_live_matches(now=None):
    """Best-effort live sync triggered by active app usage, throttled via cache.

    GitHub scheduled workflows are not guaranteed to run every 5 minutes. This
    gives the web app a lightweight fallback: when users are actively polling the
    live dashboard snapshot, sync mapped live/recent matches at most once per
    configured interval.
    """
    if not getattr(settings, "FOOTBALL_DATA_OPPORTUNISTIC_SYNC_ENABLED", True):
        return OpportunisticLiveSyncSummary(reason="disabled")

    now = now or timezone.now()
    interval_seconds = max(15, int(getattr(settings, "FOOTBALL_DATA_OPPORTUNISTIC_SYNC_INTERVAL_SECONDS", 60)))
    last_attempt = cache.get(LAST_ATTEMPT_CACHE_KEY)
    if last_attempt and (now - last_attempt).total_seconds() < interval_seconds:
        return OpportunisticLiveSyncSummary(reason="throttled")

    lock_timeout = max(interval_seconds, int(getattr(settings, "FOOTBALL_DATA_TIMEOUT", 15)) + 30)
    if not cache.add(LOCK_CACHE_KEY, now.isoformat(), timeout=lock_timeout):
        return OpportunisticLiveSyncSummary(reason="locked")

    # Throttle both successful and failing attempts, so repeated dashboard polls
    # do not spam football-data.org if the API or DB is temporarily unavailable.
    cache.set(LAST_ATTEMPT_CACHE_KEY, now, timeout=interval_seconds * 2)

    try:
        queryset = _live_sync_queryset(now)
        selected_count = queryset.count()
        if not selected_count:
            return OpportunisticLiveSyncSummary(attempted=True, reason="no_matches")

        date_bounds = list(queryset.dates("kickoff_at", "day", order="ASC"))
        fetch_padding = timedelta(days=int(getattr(settings, "FOOTBALL_DATA_OPPORTUNISTIC_SYNC_FETCH_PADDING_DAYS", 1)))
        date_from = date_bounds[0] - fetch_padding
        date_to = date_bounds[-1] + fetch_padding

        result = FootballDataSyncService().sync_queryset_from_match_list(
            queryset,
            date_from=date_from,
            date_to=date_to,
            refresh_scorers=False,
        )
        return _summary_from_result(selected_count, result)
    except (FootballDataConfigError, FootballDataClientError) as exc:
        logger.warning("Opportunistic football-data live sync failed: %s", exc)
        return OpportunisticLiveSyncSummary(attempted=True, reason="error", error=str(exc))
    finally:
        cache.delete(LOCK_CACHE_KEY)


def _live_sync_queryset(now):
    today = timezone.localdate(now)
    start_date = today - timedelta(days=int(getattr(settings, "FOOTBALL_DATA_OPPORTUNISTIC_SYNC_DAYS_BACK", 1)))
    end_date = today + timedelta(days=int(getattr(settings, "FOOTBALL_DATA_OPPORTUNISTIC_SYNC_DAYS_FORWARD", 1)))
    return Match.objects.exclude(
        football_data_match_id__isnull=True,
    ).select_related(
        "home_team",
        "away_team",
    ).filter(
        finished=False,
    ).filter(
        Q(kickoff_at__date__range=(start_date, end_date))
        | Q(live_status__in=LIVE_STATUSES)
    ).order_by("kickoff_at")


def _summary_from_result(selected_count, result: FootballDataSyncResult):
    return OpportunisticLiveSyncSummary(
        attempted=True,
        reason="synced",
        selected=selected_count,
        checked=result.checked,
        updated=result.updated,
        skipped=result.skipped,
    )

