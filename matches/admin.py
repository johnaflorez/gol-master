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
        "kickoff_at",
        "finished"
    )
    list_filter = ("finished", "live_status", "phase", "kickoff_at")
    autocomplete_fields = [
        "home_team",
        "away_team",
    ]
    search_fields = ("home_team__name", "away_team__name")
    actions = [finish_matches]


@admin.register(MatchEvent)
class MatchEventAdmin(admin.ModelAdmin):
    list_display = ("match", "minute", "event_type", "team", "player_name", "created_at")
    list_filter = ("event_type", "match__phase", "match__kickoff_at")
    search_fields = ("player_name", "description", "team__name", "match__home_team__name", "match__away_team__name")
    autocomplete_fields = ("match", "team")

