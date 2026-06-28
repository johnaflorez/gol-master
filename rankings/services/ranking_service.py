from django.db import models
from django.contrib.auth.models import User
from django.db.models.functions import Coalesce


class RankingService:

    def get_ranking(self, *, limit=None):
        exact_score_filter = models.Q(
            prediction__match__finished=True,
            prediction__predicted_home_score=models.F("prediction__match__home_score"),
            prediction__predicted_away_score=models.F("prediction__match__away_score"),
        )
        users = User.objects.select_related("profile").annotate(
            points=Coalesce(models.Sum("prediction__points"), 0),
            total_predictions=models.Count(
                "prediction",
                filter=models.Q(prediction__match__finished=True)
            ),
            correct_predictions=models.Count(
                "prediction",
                filter=models.Q(
                    prediction__match__finished=True,
                    prediction__points__gte=2,
                ),
            ),
            exact_predictions=models.Count(
                "prediction",
                filter=exact_score_filter,
            ),
            exact_score_points=Coalesce(
                models.Sum("prediction__points", filter=exact_score_filter),
                models.Value(0),
                output_field=models.IntegerField(),
            ),
        ).order_by("-points", "username")

        if limit is not None:
            users = users[:limit]

        ranking = []
        for user in users:
            hit_rate = (user.correct_predictions / user.total_predictions * 100) if user.total_predictions else 0
            ranking.append(
                {
                    "user": user,
                    "points": user.points,
                    "hit_rate": hit_rate,
                    "total_predictions": user.total_predictions,
                    "correct_predictions": user.correct_predictions,
                    "exact_predictions": user.exact_predictions,
                    "exact_score_points": user.exact_score_points,
                }
            )

        return ranking
