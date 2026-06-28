from datetime import timedelta

from django.utils import timezone

from matches.models import Match
from predictions.models import Prediction


ANNOUNCEMENT_WINDOW = timedelta(minutes=5)


def _user_display_name(user):
    return user.get_full_name() or user.username


def _join_names(names):
    if len(names) <= 1:
        return names[0] if names else ""
    if len(names) == 2:
        return f"{names[0]} y {names[1]}"
    return f"{', '.join(names[:-1])} y {names[-1]}"


def build_final_match_announcement(match, exact_predictions=None):
    if exact_predictions is None:
        exact_predictions = Prediction.objects.filter(
            match=match,
            predicted_home_score=match.home_score,
            predicted_away_score=match.away_score,
        ).select_related("user").order_by("user__first_name", "user__username")

    names = [_user_display_name(prediction.user) for prediction in exact_predictions]
    score = f"{match.home_score}-{match.away_score}"
    teams = f"{match.home_team} vs {match.away_team}"

    if not names:
        message = f"📢 Finalizó {teams} {score}. No hubo ningún acierto exacto del marcador."
    elif len(names) == 1:
        message = f"🎉 ¡Felicitaciones a {names[0]}! Acertó el marcador exacto de {teams}: {score}."
    else:
        message = f"🎉 ¡Felicitaciones a {_join_names(names)}! Acertaron el marcador exacto de {teams}: {score}."

    return {
        "match_id": match.id,
        "message": message,
        "finished_at": match.finished_at.isoformat() if match.finished_at else "",
    }


def get_recent_final_match_announcements(*, now=None, window=ANNOUNCEMENT_WINDOW):
    now = now or timezone.now()
    since = now - window
    matches = list(Match.objects.select_related(
        "home_team",
        "away_team",
    ).filter(
        finished=True,
        finished_at__isnull=False,
        finished_at__gte=since,
        finished_at__lte=now,
    ).order_by("-finished_at"))

    predictions_by_match = {match.id: [] for match in matches}
    if matches:
        predictions = Prediction.objects.filter(match__in=matches).select_related("user").order_by(
            "user__first_name",
            "user__username",
        )
        scores_by_match = {match.id: (match.home_score, match.away_score) for match in matches}
        for prediction in predictions:
            if scores_by_match.get(prediction.match_id) == (
                prediction.predicted_home_score,
                prediction.predicted_away_score,
            ):
                predictions_by_match[prediction.match_id].append(prediction)

    return [
        build_final_match_announcement(match, predictions_by_match.get(match.id, []))
        for match in matches
    ]

