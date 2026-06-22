from django.db import models
from django.contrib.auth.models import User
from predictions.models import Prediction
from matches.models import Match


class RankingService:

    def get_ranking(self):
        users = User.objects.all()
        ranking = []

        for user in users:
            points = Prediction.objects.filter(
                user=user
            ).aggregate(
                total=models.Sum("points")
            )["total"] or 0

            # Calcular porcentaje de acierto (hit_rate)
            # Acierto = predicción donde puntos >= 2 (acertó al menos el ganador)
            predictions_completed = Prediction.objects.filter(
                user=user,
                match__finished=True
            )
            total_completed = predictions_completed.count()
            correct_predictions = predictions_completed.filter(
                points__gte=2
            ).count()
            hit_rate = (correct_predictions / total_completed * 100) if total_completed > 0 else 0

            ranking.append({
                "user": user,
                "points": points,
                "hit_rate": hit_rate,
                "total_predictions": total_completed,
                "correct_predictions": correct_predictions
            })

        ranking.sort(
            key=lambda x: x["points"],
            reverse=True
        )
        return ranking
