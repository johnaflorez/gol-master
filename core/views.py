from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from matches.models import Match
from predictions.models import Prediction
from rankings.services.ranking_service import RankingService
from stats.services.tournament_stats import TournamentStatsService


class HomeView(TemplateView):
    template_name = "core/home.html"


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        user_predictions = Prediction.objects.filter(
            user=self.request.user,
            match=OuterRef("pk")
        )

        latest_matches = Match.objects.select_related(
            "home_team",
            "away_team"
        ).prefetch_related(
            "events",
            "events__team",
        ).filter(
            kickoff_at__date=today
        ).annotate(
            has_prediction=Exists(user_predictions)
        ).order_by("-kickoff_at")[:10]

        ranking_service = RankingService()
        ranking = ranking_service.get_ranking()[:10]
        tournament_stats = TournamentStatsService().get_stats()

        context.update(
            {
                "matches": latest_matches,
                "ranking": ranking,
                "tournament_stats": tournament_stats,
                "now": timezone.now(),
            }
        )

        return context


class DashboardLiveSnapshotView(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        now = timezone.now()
        today = timezone.localdate()

        matches = Match.objects.select_related(
            "home_team",
            "away_team",
        ).prefetch_related(
            "events",
            "events__team",
        ).filter(
            kickoff_at__date=today,
        ).order_by("-kickoff_at")

        payload = []
        for match in matches:
            if match.finished or match.live_status == "FT":
                status = "FT"
                status_label = "Finalizado"
            elif match.live_status == "HT":
                status = "HT"
                status_label = "Descanso"
            elif match.live_status == "LIVE" or match.kickoff_at <= now:
                status = "LIVE"
                status_label = "En juego"
            else:
                status = "NS"
                status_label = "Por jugar"

            events = []
            for event in match.events.all():
                team_name = event.team.name if event.team else ""
                minute = f"{event.minute}'" if event.minute is not None else ""
                actor = event.player_name.strip() or event.description.strip() or team_name
                label = event.get_event_type_display()
                text_parts = [part for part in [minute, label, actor] if part]
                events.append(
                    {
                        "id": event.id,
                        "minute": event.minute,
                        "event_type": event.event_type,
                        "text": " - ".join(text_parts),
                    }
                )

            payload.append(
                {
                    "id": match.id,
                    "home_score": match.home_score,
                    "away_score": match.away_score,
                    "live_minute": match.live_minute,
                    "status": status,
                    "status_label": status_label,
                    "events": events,
                }
            )

        return JsonResponse(
            {
                "server_time": now.isoformat(),
                "matches": payload,
            }
        )


