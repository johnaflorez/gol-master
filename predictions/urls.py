from django.urls import path

from predictions.views import (
    PredictionCreateView,
    MyPredictionsView,
    PredictionDashboardView,
    AllPredictionsView,
)

urlpatterns = [
    path("match/<int:match_id>/", PredictionCreateView.as_view(), name="prediction_create"),
    path("mine/", MyPredictionsView.as_view(), name="my_predictions"),
    path("dashboard/", PredictionDashboardView.as_view(), name="prediction_dashboard"),
    path("all/", AllPredictionsView.as_view(), name="all_predictions")
]
