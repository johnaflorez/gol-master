from django.urls import path

from rankings.views import RankingView


urlpatterns = [
    path("", RankingView.as_view(), name="ranking")
]