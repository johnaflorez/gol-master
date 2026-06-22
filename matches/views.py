from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Exists, OuterRef
from django.views.generic import ListView

from matches.models import Match
from predictions.models import Prediction


class MatchListView(LoginRequiredMixin, ListView):
    model = Match
    template_name = "matches/list.html"
    context_object_name = "matches"
    paginate_by = 10

    def get_queryset(self):
        user_predictions = Prediction.objects.filter(
            user=self.request.user,
            match=OuterRef("pk")
        )

        return Match.objects.select_related(
            "home_team",
            "away_team"
        ).annotate(
            has_prediction=Exists(user_predictions)
        ).order_by("-kickoff_at")


