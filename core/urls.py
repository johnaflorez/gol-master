from django.urls import path

from core.views import (
    DashboardLiveSnapshotView,
    DashboardView,
    FootballDataCommandView,
    HomeView,
    SuggestionCreateView,
    SuggestionListView,
    SuggestionResolveView,
)


urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("home", HomeView.as_view(), name="home"),
    path("dashboard/live-snapshot/", DashboardLiveSnapshotView.as_view(), name="dashboard_live_snapshot"),
    path("sugerencias/", SuggestionCreateView.as_view(), name="suggestion_create"),
    path("sugerencias/admin/", SuggestionListView.as_view(), name="suggestion_list"),
    path("sugerencias/admin/<int:pk>/resolver/", SuggestionResolveView.as_view(), name="suggestion_resolve"),
    path("admin/football-data/", FootballDataCommandView.as_view(), name="football_data_commands"),
]
