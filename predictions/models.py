from django.db import models
from django.contrib.auth.models import User

from matches.models import Match
from teams.models import Player, Team


class Prediction(models.Model):
    PENALTY_HOME = "HOME"
    PENALTY_AWAY = "AWAY"
    PENALTY_WINNER_CHOICES = [
        (PENALTY_HOME, "Gana local por penales"),
        (PENALTY_AWAY, "Gana visitante por penales"),
    ]
    KNOCKOUT_PHASES_WITH_PENALTIES = {"DR", "OF", "CF", "SF", "F"}

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    predicted_home_score = models.IntegerField()
    predicted_away_score = models.IntegerField()
    predicted_penalty_winner = models.CharField(
        max_length=4,
        choices=PENALTY_WINNER_CHOICES,
        blank=True,
        default="",
        help_text="Ganador por penales cuando el pronóstico de eliminatorias es empate.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    points = models.IntegerField(default=0)

    class Meta:
        unique_together = ("user", "match")

    @property
    def predicts_draw(self):
        return self.predicted_home_score == self.predicted_away_score

    @property
    def can_have_penalty_winner(self):
        return self.match.phase in self.KNOCKOUT_PHASES_WITH_PENALTIES

    @property
    def requires_penalty_winner(self):
        return self.can_have_penalty_winner and self.predicts_draw

    @property
    def predicted_penalty_winner_team(self):
        if self.predicted_penalty_winner == self.PENALTY_HOME:
            return self.match.home_team
        if self.predicted_penalty_winner == self.PENALTY_AWAY:
            return self.match.away_team
        return None


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

