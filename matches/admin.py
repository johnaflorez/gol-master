from django.contrib import admin
from matches.models import Match, MatchEvent


@admin.action(description="Finalizar partido")
def finish_matches(modeladmin, request, queryset):
    for match in queryset:
        match.finish_match(
            match.home_score or 0,
            match.away_score or 0
        )


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "home_team",
        "home_score",
        "away_team",
        "away_score",
        "live_status",
        "live_minute",
        "phase",
        "api_football_fixture_id",
        "football_data_match_id",
        "kickoff_at",
        "finished"
    )
    list_filter = ("finished", "live_status", "phase", "kickoff_at")
    autocomplete_fields = [
        "home_team",
        "away_team",
    ]
    search_fields = ("home_team__name", "away_team__name", "api_football_fixture_id", "football_data_match_id")
    actions = [finish_matches]


@admin.register(MatchEvent)
class MatchEventAdmin(admin.ModelAdmin):
    list_display = ("match", "minute", "event_type", "team", "player_name", "api_football_event_key", "created_at")
    list_filter = ("event_type", "match__phase", "match__kickoff_at")
    search_fields = (
        "player_name",
        "description",
        "api_football_event_key",
        "team__name",
        "match__home_team__name",
        "match__away_team__name",
    )
    autocomplete_fields = ("match", "team")

