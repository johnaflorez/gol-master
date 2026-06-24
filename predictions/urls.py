from django.urls import path

from predictions.views import (
    PredictionCreateView,
    MyPredictionsView,
    PredictionDashboardView,
    AllPredictionsView,
    TournamentPredictionView,
)

urlpatterns = [
    path("match/<int:match_id>/", PredictionCreateView.as_view(), name="prediction_create"),
    path("mine/", MyPredictionsView.as_view(), name="my_predictions"),
    path("dashboard/", PredictionDashboardView.as_view(), name="prediction_dashboard"),
    path("tournament/", TournamentPredictionView.as_view(), name="tournament_prediction"),
    path("all/", AllPredictionsView.as_view(), name="all_predictions")
]
