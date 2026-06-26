from django.db import models

from teams.models import Player, Team


class TopScorerStanding(models.Model):
	competition_code = models.CharField(max_length=20, default="WC", db_index=True)
	season = models.PositiveIntegerField(blank=True, null=True, db_index=True)
	rank = models.PositiveSmallIntegerField(default=0, db_index=True)
	external_key = models.CharField(max_length=180)
	football_data_player_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
	player = models.ForeignKey(Player, related_name="top_scorer_standings", on_delete=models.SET_NULL, blank=True, null=True)
	player_name = models.CharField(max_length=120)
	team = models.ForeignKey(Team, related_name="top_scorer_standings", on_delete=models.SET_NULL, blank=True, null=True)
	team_name = models.CharField(max_length=120, blank=True, default="")
	team_tla = models.CharField(max_length=3, blank=True, default="", db_index=True)
	team_crest = models.URLField(max_length=255, blank=True, default="")
	played_matches = models.PositiveSmallIntegerField(default=0)
	goals = models.PositiveSmallIntegerField(default=0, db_index=True)
	assists = models.PositiveSmallIntegerField(blank=True, null=True)
	penalties = models.PositiveSmallIntegerField(blank=True, null=True)
	raw_payload = models.JSONField(default=dict, blank=True)
	refreshed_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["rank", "-goals", "player_name"]
		constraints = [
			models.UniqueConstraint(
				fields=["competition_code", "season", "external_key"],
				name="unique_top_scorer_per_competition_season",
			)
		]

	def __str__(self):
		return f"{self.rank}. {self.player_name} - {self.goals} goles"
