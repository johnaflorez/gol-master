from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, Q, Sum
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from matches.models import Match
from predictions.forms import PredictionForm
from predictions.models import Prediction


class PredictionCreateView(LoginRequiredMixin, FormView):
    template_name = "predictions/form.html"
    form_class = PredictionForm

    def dispatch(self, request, *args, **kwargs):
        self.match = get_object_or_404(Match, id=kwargs["match_id"])
        prediction_exists = Prediction.objects.filter(user=request.user, match=self.match).exists()

        if self.match.finished or prediction_exists:
            return redirect("match_list")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        previous_team_results = Match.objects.filter(
            finished=True,
            kickoff_at__lt=self.match.kickoff_at
        ).filter(
            Q(home_team=self.match.home_team) |
            Q(away_team=self.match.home_team) |
            Q(home_team=self.match.away_team) |
            Q(away_team=self.match.away_team)
        ).exclude(
            id=self.match.id
        ).select_related(
            "home_team",
            "away_team"
        ).order_by("-kickoff_at")[:6]

        previous_match_ids = [m.id for m in previous_team_results]
        user_predictions = Prediction.objects.filter(
            user=self.request.user,
            match_id__in=previous_match_ids
        ).values_list("match_id", "predicted_home_score", "predicted_away_score", "points")
        prediction_map = {match_id: {"home": home, "away": away, "points": points}
                          for match_id, home, away, points in user_predictions}

        context["match"] = self.match
        context["previous_team_results"] = previous_team_results
        context["prediction_map"] = prediction_map
        return context

    def form_valid(self, form):
        prediction = form.save(commit=False)
        prediction.user = self.request.user
        prediction.match = self.match
        prediction.save()
        return redirect("dashboard")


class MyPredictionsView(LoginRequiredMixin, ListView):
    template_name = "predictions/my_predictions.html"
    context_object_name = "predictions"
    paginate_by = 10

    def get_queryset(self):
        return Prediction.objects.filter(
            user=self.request.user
        ).select_related(
            "user",
            "user__profile",
            "match",
            "match__home_team",
            "match__away_team"
        ).order_by("-match__kickoff_at", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        phase_stats = self._get_phase_stats()

        context["phase_stats"] = phase_stats
        context["phase_stats_totals"] = {
            "points_total": sum(item["points_total"] for item in phase_stats),
            "winner_or_draw_hits": sum(item["winner_or_draw_hits"] for item in phase_stats),
            "exact_hits": sum(item["exact_hits"] for item in phase_stats),
            "finished_predictions": sum(item["finished_predictions"] for item in phase_stats),
            "total_predictions": sum(item["total_predictions"] for item in phase_stats),
        }
        context["now"] = timezone.now()
        return context

    def _get_phase_stats(self):
        winner_or_draw_condition = (
            Q(
                predicted_home_score__gt=F("predicted_away_score"),
                match__home_score__gt=F("match__away_score"),
            )
            | Q(
                predicted_home_score=F("predicted_away_score"),
                match__home_score=F("match__away_score"),
            )
            | Q(
                predicted_home_score__lt=F("predicted_away_score"),
                match__home_score__lt=F("match__away_score"),
            )
        )

        rows = Prediction.objects.filter(user=self.request.user).values("match__phase").annotate(
            total_predictions=Count("id"),
            finished_predictions=Count("id", filter=Q(match__finished=True)),
            points_total=Sum("points", filter=Q(match__finished=True)),
            winner_or_draw_hits=Count(
                "id",
                filter=Q(match__finished=True) & winner_or_draw_condition,
            ),
            exact_hits=Count(
                "id",
                filter=Q(
                    match__finished=True,
                    predicted_home_score=F("match__home_score"),
                    predicted_away_score=F("match__away_score"),
                ),
            ),
        )

        phase_names = dict(Match.PHASE_CHOICES)
        phase_order = {code: index for index, (code, _) in enumerate(Match.PHASE_CHOICES)}

        phase_stats = []
        for row in rows:
            phase_code = row["match__phase"]
            phase_stats.append(
                {
                    "phase": phase_code,
                    "phase_label": phase_names.get(phase_code, phase_code),
                    "points_total": row["points_total"] or 0,
                    "winner_or_draw_hits": row["winner_or_draw_hits"],
                    "exact_hits": row["exact_hits"],
                    "finished_predictions": row["finished_predictions"],
                    "total_predictions": row["total_predictions"],
                }
            )

        return sorted(phase_stats, key=lambda item: phase_order.get(item["phase"], 999))


class PredictionDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "predictions/dashboard.html"

    def _open_matches(self):
        return Match.objects.filter(
            finished=False,
            kickoff_at__gt=timezone.now()
        )

    def post(self, request, *args, **kwargs):
        for match in self._open_matches():
            home = request.POST.get(f"home_{match.id}")
            away = request.POST.get(f"away_{match.id}")

            if home in (None, "") or away in (None, ""):
                continue

            Prediction.objects.update_or_create(
                user=request.user,
                match=match,
                defaults={
                    "predicted_home_score": home,
                    "predicted_away_score": away
                }
            )

        return redirect("prediction_dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        predictions = Prediction.objects.filter(user=self.request.user)
        prediction_map = {p.match_id: p for p in predictions}
        predicted_match_ids = predictions.values_list("match_id", flat=True)
        matches = self._open_matches().exclude(id__in=predicted_match_ids)

        context.update(
            {
                "matches": matches,
                "prediction_map": prediction_map,
            }
        )
        return context


class AllPredictionsView(LoginRequiredMixin, TemplateView):
    template_name = "predictions/all_predictions.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        matches = Match.objects.filter(
            finished=False
        ).select_related(
            "home_team",
            "away_team"
        ).order_by(
            "kickoff_at"
        )

        predictions = Prediction.objects.filter(
            match__in=matches
        ).select_related(
            "user",
            "user__profile",
            "match",
            "match__home_team",
            "match__away_team"
        ).order_by(
            "match__kickoff_at",
            "user__first_name",
            "user__last_name",
            "user__username"
        )

        grouped = {}
        for prediction in predictions:
            if prediction.match_id not in grouped:
                grouped[prediction.match_id] = {
                    "match": prediction.match,
                    "predictions": []
                }
            grouped[prediction.match_id]["predictions"].append(prediction)

        context["grouped"] = grouped.values()
        return context
