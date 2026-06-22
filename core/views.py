from django.utils import timezone
from django.views.generic import TemplateView

from matches.models import Match
from rankings.services.ranking_service import RankingService
from stats.services.tournament_stats import TournamentStatsService


class HomeView(TemplateView):
    template_name = "core/home.html"


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        latest_matches = Match.objects.select_related(
            "home_team",
            "away_team"
        ).filter(
            kickoff_at__date=today
        ).order_by("-kickoff_at")[:10]

        ranking_service = RankingService()
        ranking = ranking_service.get_ranking()[:10]
        tournament_stats = TournamentStatsService().get_stats()

        context.update(
            {
                "matches": latest_matches,
                "ranking": ranking,
                "tournament_stats": tournament_stats,
            }
        )

        return context

