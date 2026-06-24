from django.db import models
from django.contrib.auth.models import User

from matches.models import Match
from teams.models import Player, Team


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


class TournamentPrediction(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="tournament_prediction")
    champion_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="champion_predictions")
    top_scorer = models.ForeignKey(
        Player,
        on_delete=models.PROTECT,
        related_name="top_scorer_predictions",
        blank=True,
        null=True,
    )
    top_scorer_name = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__username",)

    def __str__(self):
        return f"{self.user.username}: {self.champion_team} / {self.get_top_scorer_name()}"

    def get_top_scorer_name(self):
        if self.top_scorer_id:
            return self.top_scorer.name
        return self.top_scorer_name

