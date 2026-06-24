from django.contrib import admin

from predictions.models import Prediction, TournamentPrediction


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "match",
        "predicted_home_score",
        "predicted_away_score",
        "points"
    )
    list_filter = ("match__home_team", "match__away_team", "user")


@admin.register(TournamentPrediction)
class TournamentPredictionAdmin(admin.ModelAdmin):
    list_display = ("user", "champion_team", "top_scorer", "updated_at")
    list_filter = ("champion_team", "top_scorer__team")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "champion_team__name",
        "top_scorer__name",
        "top_scorer_name",
    )
    autocomplete_fields = ("user", "champion_team", "top_scorer")

