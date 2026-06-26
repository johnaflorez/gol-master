from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from stats.models import TopScorerStanding


class TopScorersView(LoginRequiredMixin, ListView):
	template_name = "stats/top_scorers.html"
	context_object_name = "scorers"
	paginate_by = 50

	def get_queryset(self):
		return TopScorerStanding.objects.select_related("team", "player").order_by("rank", "-goals", "player_name")
