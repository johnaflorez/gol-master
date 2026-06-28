from django.contrib import admin
from django.db.models import Case, IntegerField, Value, When

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
    PHASE_ADMIN_ORDER = ["F", "SF", "CF", "OF", "DR", "TR", "SR", "PR"]

    list_display = (
        "home_team",
        "home_score",
        "away_team",
        "away_score",
        "live_status",
        "live_minute",
        "phase",
        "bracket_position",
        "football_data_match_id",
        "kickoff_at",
        "finished"
    )
    list_filter = ("finished", "live_status", "phase", "bracket_position", "kickoff_at")
    list_select_related = ("home_team", "away_team")
    autocomplete_fields = [
        "home_team",
        "away_team",
    ]
    search_fields = ("home_team__name", "away_team__name", "football_data_match_id")
    ordering = ()
    actions = [finish_matches]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).annotate(
            _phase_sort=Case(
                *[
                    When(phase=phase_code, then=Value(index))
                    for index, phase_code in enumerate(self.PHASE_ADMIN_ORDER)
                ],
                default=Value(len(self.PHASE_ADMIN_ORDER)),
                output_field=IntegerField(),
            )
        )
        if request.GET.get("o"):
            return queryset
        return queryset.order_by("_phase_sort", "bracket_position", "-kickoff_at", "id")


@admin.register(MatchEvent)
class MatchEventAdmin(admin.ModelAdmin):
    list_display = ("match", "minute", "event_type", "team", "player_name", "created_at")
    list_filter = ("event_type", "match__phase", "match__kickoff_at")
    list_select_related = ("match", "match__home_team", "match__away_team", "team")
    search_fields = (
        "player_name",
        "description",
        "team__name",
        "match__home_team__name",
        "match__away_team__name",
    )
    autocomplete_fields = ("match", "team")

