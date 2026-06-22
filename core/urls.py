from django.urls import path

from core.views import HomeView, DashboardView


urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("home", HomeView.as_view(), name="home"),
]
