from django.contrib import admin
from matches.models import Match


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
        "phase",
        "kickoff_at",
        "finished"
    )
    list_filter = ("finished", "phase", "kickoff_at")
    autocomplete_fields = [
        "home_team",
        "away_team",
    ]
    actions = [finish_matches]
