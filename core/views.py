from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.db.models import Case, Exists, IntegerField, OuterRef, Value, When
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView

from core.forms import SuggestionForm
from core.models import Suggestion
from matches.models import Match
from core.services.final_match_announcements import get_recent_final_match_announcements
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
            has_prediction=Exists(user_predictions),
            finished_sort=Case(
                When(finished=True, then=Value(1)),
                When(live_status="FT", then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        ).order_by("finished_sort", "kickoff_at", "id")[:10]

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
        ).annotate(
            finished_sort=Case(
                When(finished=True, then=Value(1)),
                When(live_status="FT", then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        ).order_by("finished_sort", "kickoff_at", "id")

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
                "final_match_announcements": get_recent_final_match_announcements(now=now),
            }
        )


class SuggestionCreateView(LoginRequiredMixin, CreateView):
  template_name = "core/suggestions/form.html"
  form_class = SuggestionForm
  success_url = reverse_lazy("suggestion_create")

  def form_valid(self, form):
    form.instance.user = self.request.user
    messages.success(self.request, "Gracias, tu sugerencia fue enviada correctamente.")
    return super().form_valid(form)


class SuperuserRequiredMixin(UserPassesTestMixin):
  def test_func(self):
    return self.request.user.is_superuser


class SuggestionListView(LoginRequiredMixin, SuperuserRequiredMixin, ListView):
  template_name = "core/suggestions/list.html"
  context_object_name = "suggestions"
  paginate_by = 20

  def get_queryset(self):
    queryset = Suggestion.objects.select_related("user")
    status = self.request.GET.get("status", "pending")

    if status == "resolved":
      return queryset.filter(is_resolved=True)
    if status == "all":
      return queryset
    return queryset.filter(is_resolved=False)

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context["selected_status"] = self.request.GET.get("status", "pending")
    context["pending_count"] = Suggestion.objects.filter(is_resolved=False).count()
    context["resolved_count"] = Suggestion.objects.filter(is_resolved=True).count()
    return context


class SuggestionResolveView(LoginRequiredMixin, SuperuserRequiredMixin, View):
  def post(self, request, *args, **kwargs):
    suggestion = get_object_or_404(Suggestion, pk=kwargs["pk"])
    suggestion.is_resolved = True
    suggestion.save(update_fields=["is_resolved", "updated_at"])
    messages.success(request, "Sugerencia marcada como solucionada/revisada.")
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
      return redirect(next_url)
    return redirect("suggestion_list")


