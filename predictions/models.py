from django.db import models
from django.contrib.auth.models import User

from matches.models import Match


class Prediction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    predicted_home_score = models.IntegerField()
    predicted_away_score = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    points = models.IntegerField(default=0)

    class Meta:
        unique_together = ("user", "match")
