from django.urls import path

from .views import GroupStandingsView, KnockoutBracketView, MatchListView

urlpatterns = [
    path("", MatchListView.as_view(), name="match_list"),
    path("tabla-posiciones/", GroupStandingsView.as_view(), name="group_standings"),
    path("eliminatorias/", KnockoutBracketView.as_view(), name="knockout_bracket"),
]
