from django.contrib import admin

from stats.models import TopScorerStanding


@admin.register(TopScorerStanding)
class TopScorerStandingAdmin(admin.ModelAdmin):
	list_display = ("rank", "player_name", "team_name", "goals", "assists", "penalties", "competition_code", "season", "refreshed_at")
	list_filter = ("competition_code", "season", "team_name")
	search_fields = ("player_name", "team_name", "team_tla", "football_data_player_id")
	readonly_fields = ("raw_payload", "refreshed_at")
