from django.db import models
from django.utils import timezone

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

    LIVE_STATUS_CHOICES = [
        ("NS", "Por jugar"),
        ("LIVE", "En juego"),
        ("HT", "Descanso"),
        ("FT", "Finalizado"),
    ]
    
    home_team = models.ForeignKey(Team, related_name="home_matches", on_delete=models.CASCADE)
    away_team = models.ForeignKey(Team, related_name="away_matches", on_delete=models.CASCADE)
    kickoff_at = models.DateTimeField()
    home_score = models.IntegerField(default=0)
    away_score = models.IntegerField(default=0)
    home_penalty_score = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        help_text="Goles en tanda de penales del equipo local, si aplica.",
    )
    away_penalty_score = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        help_text="Goles en tanda de penales del equipo visitante, si aplica.",
    )
    finished = models.BooleanField(default=False)
    finished_at = models.DateTimeField(blank=True, null=True)
    points_calculated = models.BooleanField(default=False)
    phase = models.CharField(max_length=2, choices=PHASE_CHOICES, default='PR')
    bracket_position = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        db_index=True,
        help_text="Posición visual del partido dentro de su fase eliminatoria. Ej: 2, 9.",
    )
    live_status = models.CharField(max_length=5, choices=LIVE_STATUS_CHOICES, default="NS")
    live_minute = models.PositiveSmallIntegerField(blank=True, null=True)
    last_event_at = models.DateTimeField(blank=True, null=True)
    football_data_match_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        unique=True,
        help_text="ID externo del partido en football-data.org",
    )
    football_data_winner = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Ganador reportado por football-data.org: HOME_TEAM, AWAY_TEAM o DRAW.",
    )

    def __str__(self):
        return f"{self.home_team} vs {self.away_team}"

    class Meta:
        indexes = [
            models.Index(fields=["phase", "bracket_position"], name="matches_mat_phase_b_25ba5e_idx"),
        ]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        should_touch_finished_at = False

        if self.pk:
            previous = Match.objects.filter(pk=self.pk).values("finished", "finished_at").first()
        else:
            previous = None

        if self.finished:
            if not previous or not previous["finished"]:
                if not self.finished_at:
                    self.finished_at = timezone.now()
                    should_touch_finished_at = True
            elif previous["finished_at"] and not self.finished_at:
                self.finished_at = previous["finished_at"]
                should_touch_finished_at = True
        elif self.finished_at:
            self.finished_at = None
            should_touch_finished_at = True

        if should_touch_finished_at and update_fields is not None:
            kwargs["update_fields"] = list(dict.fromkeys([*update_fields, "finished_at"]))

        super().save(*args, **kwargs)

    def finish_match(self, home_score, away_score):
        self.home_score = home_score
        self.away_score = away_score
        self.finished = True
        self.live_status = "FT"
        self.save()

    @property
    def has_penalty_shootout(self):
        return self.home_penalty_score is not None and self.away_penalty_score is not None

    @property
    def penalty_score_display(self):
        if not self.has_penalty_shootout:
            return ""
        return f"{self.home_penalty_score} - {self.away_penalty_score} pen."

    @property
    def score_display(self):
        score = f"{self.home_score} - {self.away_score}"
        if self.has_penalty_shootout:
            return f"{score} ({self.penalty_score_display})"
        return score

    @property
    def winner_side(self):
        if not self.finished:
            return ""
        if self.home_score > self.away_score:
            return "home"
        if self.away_score > self.home_score:
            return "away"
        if self.has_penalty_shootout and self.home_penalty_score != self.away_penalty_score:
            return "home" if self.home_penalty_score > self.away_penalty_score else "away"
        if self.football_data_winner == "HOME_TEAM":
            return "home"
        if self.football_data_winner == "AWAY_TEAM":
            return "away"
        return ""

    @property
    def winner_team(self):
        if self.winner_side == "home":
            return self.home_team
        if self.winner_side == "away":
            return self.away_team
        return None


class MatchEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ("GOAL", "Gol"),
        ("RED", "Expulsion"),
        ("YELLOW", "Amarilla"),
        ("OTHER", "Otro"),
    ]

    match = models.ForeignKey(Match, related_name="events", on_delete=models.CASCADE)
    team = models.ForeignKey(Team, related_name="match_events", on_delete=models.CASCADE, blank=True, null=True)
    minute = models.PositiveSmallIntegerField(blank=True, null=True)
    event_type = models.CharField(max_length=10, choices=EVENT_TYPE_CHOICES, default="OTHER")
    player_name = models.CharField(max_length=100, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("minute", "id")

    def __str__(self):
        team_name = self.team.name if self.team else "Sin equipo"
        minute_text = f"{self.minute}'" if self.minute is not None else "s/min"
        return f"{minute_text} {self.get_event_type_display()} - {team_name}"

