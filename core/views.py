from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import JsonResponse
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView
from io import StringIO

from core.forms import FootballDataCommandForm, SuggestionForm
from core.models import Suggestion
from matches.models import Match
from core.services.final_match_announcements import get_recent_final_match_announcements
from core.services.live_match_sync import maybe_sync_live_matches
from matches.query_utils import order_with_finished_last
from predictions.models import Prediction, TournamentPrediction
from predictions.services.tournament_deadline import get_tournament_prediction_deadline, is_tournament_prediction_closed
from rankings.services.ranking_service import RankingService
from stats.services.tournament_stats import TournamentStatsService

LIVE_DASHBOARD_STATUSES = ["LIVE", "HT"]
RECENT_STARTED_MATCH_WINDOW = timedelta(hours=12)


def get_dashboard_matches_queryset(now=None):
    """Matches visible on the dashboard, including active matches that cross midnight."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    recent_started_at = now - RECENT_STARTED_MATCH_WINDOW

    return Match.objects.select_related(
        "home_team",
        "away_team"
    ).prefetch_related(
        "events",
        "events__team",
    ).filter(
        Q(kickoff_at__date=today)
        | Q(finished=False, live_status__in=LIVE_DASHBOARD_STATUSES, kickoff_at__gte=recent_started_at)
        | (Q(finished=False, kickoff_at__gte=recent_started_at, kickoff_at__lte=now) & ~Q(live_status="FT"))
    )


class HomeView(TemplateView):
    template_name = "core/home.html"


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()

        user_predictions = Prediction.objects.filter(
            user=self.request.user,
            match=OuterRef("pk")
        )

        latest_matches = order_with_finished_last(
            get_dashboard_matches_queryset(now=now).annotate(
                has_prediction=Exists(user_predictions),
            ),
            "kickoff_at",
            "id",
        )[:10]

        ranking_service = RankingService()
        ranking = ranking_service.get_ranking(limit=10)
        tournament_stats = TournamentStatsService().get_stats()
        tournament_prediction = TournamentPrediction.objects.select_related(
            "champion_team",
            "top_scorer",
            "top_scorer__team",
        ).filter(user=self.request.user).first()

        context.update(
            {
                "matches": latest_matches,
                "ranking": ranking,
                "tournament_stats": tournament_stats,
                "tournament_prediction": tournament_prediction,
                "tournament_prediction_deadline": get_tournament_prediction_deadline(),
                "tournament_prediction_closed": is_tournament_prediction_closed(now),
                "now": now,
            }
        )

        return context


class DashboardLiveSnapshotView(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        now = timezone.now()
        live_sync = maybe_sync_live_matches(now=now)

        matches = order_with_finished_last(
            get_dashboard_matches_queryset(now=now).only(
                "id",
                "home_score",
                "away_score",
                "home_penalty_score",
                "away_penalty_score",
                "finished",
                "kickoff_at",
                "live_status",
                "live_minute",
                "home_team__id",
                "home_team__name",
                "away_team__id",
                "away_team__name",
            ),
            "kickoff_at",
            "id",
        )

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
                    "score_display": match.score_display,
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
                "live_sync": live_sync.as_dict(),
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


class FootballDataCommandView(LoginRequiredMixin, SuperuserRequiredMixin, TemplateView):
    template_name = "core/admin/football_data_commands.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", FootballDataCommandForm())
        context.setdefault("command_output", "")
        context.setdefault("command_error", "")
        context.setdefault("executed_command", "")
        return context

    def post(self, request, *args, **kwargs):
        form = FootballDataCommandForm(request.POST)
        context = self.get_context_data(form=form)

        if not form.is_valid():
            messages.error(request, "Revisa los campos del formulario antes de ejecutar el comando.")
            return self.render_to_response(context)

        command_name, command_args = form.build_command()
        stdout = StringIO()
        stderr = StringIO()
        context["executed_command"] = "python manage.py " + " ".join([command_name, *command_args, "--verbosity", "2"])

        try:
            call_command(command_name, *command_args, stdout=stdout, stderr=stderr, verbosity=2)
        except CommandError as exc:
            context["command_error"] = str(exc)
            messages.error(request, "El comando terminó con error.")
        else:
            messages.success(request, "Comando ejecutado correctamente.")

        context["command_output"] = stdout.getvalue()
        stderr_output = stderr.getvalue()
        if stderr_output:
            context["command_error"] = "\n".join(part for part in [context["command_error"], stderr_output] if part)

        return self.render_to_response(context)


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
