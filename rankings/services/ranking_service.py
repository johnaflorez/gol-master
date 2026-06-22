from django.db import models
from django.contrib.auth.models import User
from django.db.models.functions import Coalesce


class RankingService:

    def get_ranking(self):
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
        ).order_by("-points", "username")

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
                }
            )

        return ranking
