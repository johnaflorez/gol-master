from django.db import models
from django.contrib.auth.models import User
from predictions.models import Prediction
from rankings.models import RankingSnapshot


class SnapshotService:

    def create_snapshot(self):
        users = User.objects.all()
        ranking = []

        for user in users:
            points = Prediction.objects.filter(
                user=user
            ).aggregate(total=models.Sum("points"))["total"] or 0
            ranking.append((user, points))

        ranking.sort(key=lambda x: x[1], reverse=True)

        for index, (user, points) in enumerate(ranking, start=1):
            RankingSnapshot.objects.create(
                user=user,
                points=points,
                position=index
            )
