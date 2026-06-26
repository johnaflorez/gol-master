from django.urls import path

from stats.views import TopScorersView


urlpatterns = [
    path("goleadores/", TopScorersView.as_view(), name="top_scorers"),
]

