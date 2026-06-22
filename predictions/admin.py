from django.contrib import admin

from predictions.models import Prediction


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
