from django.db import models

from teams.models import Team


class Match(models.Model):
    PHASE_CHOICES = [
        ('PR', 'Primera Ronda'),
        ('SR', 'Segunda Ronda'),
        ('TR', 'Tercera Ronda'),
        ('DR', 'Dieciséisavos de Final'),
        ('OF', 'Octavos de Final'),
        ('CF', 'Cuartos de Final'),
        ('SF', 'Semifinal'),
        ('F', 'Final'),
    ]
    
    home_team = models.ForeignKey(Team, related_name="home_matches", on_delete=models.CASCADE)
    away_team = models.ForeignKey(Team, related_name="away_matches", on_delete=models.CASCADE)
    kickoff_at = models.DateTimeField()
    home_score = models.IntegerField(default=0)
    away_score = models.IntegerField(default=0)
    finished = models.BooleanField(default=False)
    points_calculated = models.BooleanField(default=False)
    phase = models.CharField(max_length=2, choices=PHASE_CHOICES, default='PR')

    def __str__(self):
        return f"{self.home_team} vs {self.away_team}"

    def finish_match(self, home_score, away_score):
        self.home_score = home_score
        self.away_score = away_score
        self.finished = True
        self.save()
