from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import ListView

from matches.models import Match


class MatchListView(LoginRequiredMixin, ListView):
    model = Match
    template_name = "matches/list.html"
    context_object_name = "matches"
    paginate_by = 10

    def get_queryset(self):
        return Match.objects.select_related(
            "home_team",
            "away_team"
        ).order_by("-kickoff_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["now"] = timezone.now()
        return context


