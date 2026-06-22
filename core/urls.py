from django.urls import path

from core.views import HomeView, DashboardLiveSnapshotView, DashboardView


urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("home", HomeView.as_view(), name="home"),
    path("dashboard/live-snapshot/", DashboardLiveSnapshotView.as_view(), name="dashboard_live_snapshot"),
]
