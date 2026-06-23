from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from matches.models import Match
from predictions.forms import PredictionForm
from predictions.models import Prediction
from teams.models import Team


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

    def _get_selected_country(self):
        raw_country = (self.request.GET.get("country") or "").strip()
        if not raw_country:
            return ""

        if " - " in raw_country:
            raw_country = raw_country.split(" - ", 1)[0].strip()

        team_by_name = Team.objects.filter(name__iexact=raw_country).first()
        if team_by_name:
            return team_by_name.code.upper()

        return raw_country.upper()

    def _get_selected_phase(self):
        selected_phase = (self.request.GET.get("phase") or "").strip().upper()
        valid_phases = {phase for phase, _ in Match.PHASE_CHOICES}
        return selected_phase if selected_phase in valid_phases else ""

    def _get_selected_points(self):
        selected_points = (self.request.GET.get("points") or "").strip()
        if selected_points == "":
            return ""
        try:
            return str(int(selected_points))
        except ValueError:
            return ""

    def get_queryset(self):
        queryset = Prediction.objects.filter(
            user=self.request.user
        ).select_related(
            "user",
            "user__profile",
            "match",
            "match__home_team",
            "match__away_team"
        ).order_by("-match__kickoff_at", "-created_at")

        selected_country = self._get_selected_country()
        selected_phase = self._get_selected_phase()
        selected_points = self._get_selected_points()

        if selected_country:
            queryset = queryset.filter(
                Q(match__home_team__country_code__iexact=selected_country)
                | Q(match__away_team__country_code__iexact=selected_country)
                | Q(match__home_team__code__iexact=selected_country)
                | Q(match__away_team__code__iexact=selected_country)
            )

        if selected_phase:
            queryset = queryset.filter(match__phase=selected_phase)

        if selected_points != "":
            queryset = queryset.filter(points=int(selected_points))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        phase_stats = self._get_phase_stats()
        selected_country = self._get_selected_country()
        selected_phase = self._get_selected_phase()
        selected_points = self._get_selected_points()

        country_map = {}
        for team in Team.objects.order_by("name"):
            if team.code and team.code not in country_map:
                country_map[team.code] = team.name
        country_options = [
            {"code": code, "name": name}
            for code, name in country_map.items()
        ]

        points_options = list(
            Prediction.objects.filter(user=self.request.user)
            .order_by("points")
            .values_list("points", flat=True)
            .distinct()
        )

        query_params = {}
        if self.request.GET.get("tab") == "history":
            query_params["tab"] = "history"
        if selected_country:
            query_params["country"] = selected_country
        if selected_phase:
            query_params["phase"] = selected_phase
        if selected_points != "":
            query_params["points"] = selected_points

        context["phase_stats"] = phase_stats
        context["phase_stats_totals"] = {
            "points_total": sum(item["points_total"] for item in phase_stats),
            "winner_or_draw_hits": sum(item["winner_or_draw_hits"] for item in phase_stats),
            "exact_hits": sum(item["exact_hits"] for item in phase_stats),
            "finished_predictions": sum(item["finished_predictions"] for item in phase_stats),
            "total_predictions": sum(item["total_predictions"] for item in phase_stats),
        }
        context["now"] = timezone.now()
        context["phase_options"] = Match.PHASE_CHOICES
        context["country_options"] = country_options
        context["points_options"] = points_options
        context["selected_country"] = selected_country
        context["selected_phase"] = selected_phase
        context["selected_points"] = selected_points
        context["selected_country_label"] = next(
            (
                f"{country['code']} - {country['name']}"
                for country in country_options
                if country["code"].upper() == selected_country
            ),
            selected_country,
        )
        context["filters_query"] = urlencode(query_params)
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
    historical_paginate_by = 10

    def _get_selected_country(self):
        raw_country = (self.request.GET.get("country") or "").strip()
        if not raw_country:
            return ""

        if " - " in raw_country:
            raw_country = raw_country.split(" - ", 1)[0].strip()

        team_by_name = Team.objects.filter(name__iexact=raw_country).first()
        if team_by_name:
            return team_by_name.code.upper()

        return raw_country.upper()

    def _get_selected_phase(self):
        selected_phase = (self.request.GET.get("phase") or "").strip().upper()
        valid_phases = {phase for phase, _ in Match.PHASE_CHOICES}
        return selected_phase if selected_phase in valid_phases else ""

    def _get_selected_points(self):
        selected_points = (self.request.GET.get("points") or "").strip()
        if selected_points == "":
            return ""
        try:
            return str(int(selected_points))
        except ValueError:
            return ""

    def _group_predictions_by_match(self, predictions):
        grouped = {}
        for prediction in predictions:
            if prediction.match_id not in grouped:
                grouped[prediction.match_id] = {
                    "match": prediction.match,
                    "predictions": []
                }
            grouped[prediction.match_id]["predictions"].append(prediction)

        return grouped.values()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        selected_country = self._get_selected_country()
        selected_phase = self._get_selected_phase()
        selected_points = self._get_selected_points()

        today_matches = Match.objects.filter(
            kickoff_at__date=today
        ).select_related(
            "home_team",
            "away_team"
        ).order_by(
            "kickoff_at"
        )

        today_predictions = Prediction.objects.filter(
            match__in=today_matches
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

        historical_predictions = Prediction.objects.select_related(
            "user",
            "user__profile",
            "match",
            "match__home_team",
            "match__away_team"
        ).order_by(
            "-match__kickoff_at",
            "user__first_name",
            "user__last_name",
            "user__username"
        )

        if selected_country:
            historical_predictions = historical_predictions.filter(
                Q(match__home_team__country_code__iexact=selected_country)
                | Q(match__away_team__country_code__iexact=selected_country)
                | Q(match__home_team__code__iexact=selected_country)
                | Q(match__away_team__code__iexact=selected_country)
            )

        if selected_phase:
            historical_predictions = historical_predictions.filter(match__phase=selected_phase)

        if selected_points != "":
            historical_predictions = historical_predictions.filter(points=int(selected_points))

        country_map = {}
        for team in Team.objects.order_by("name"):
            if team.code and team.code not in country_map:
                country_map[team.code] = team.name
        country_options = [
            {"code": code, "name": name}
            for code, name in country_map.items()
        ]

        points_options = list(
            Prediction.objects.order_by("points")
            .values_list("points", flat=True)
            .distinct()
        )

        history_paginator = Paginator(historical_predictions, self.historical_paginate_by)
        history_page_obj = history_paginator.get_page(self.request.GET.get("page"))

        query_params = {}
        if self.request.GET.get("tab") == "history":
            query_params["tab"] = "history"
        if selected_country:
            query_params["country"] = selected_country
        if selected_phase:
            query_params["phase"] = selected_phase
        if selected_points != "":
            query_params["points"] = selected_points

        context["today_grouped"] = self._group_predictions_by_match(today_predictions)
        context["historical_predictions"] = history_page_obj.object_list
        context["history_page_obj"] = history_page_obj
        context["history_is_paginated"] = history_page_obj.has_other_pages()
        context["country_options"] = country_options
        context["phase_options"] = Match.PHASE_CHOICES
        context["points_options"] = points_options
        context["selected_country"] = selected_country
        context["selected_phase"] = selected_phase
        context["selected_points"] = selected_points
        context["selected_country_label"] = next(
            (
                f"{country['code']} - {country['name']}"
                for country in country_options
                if country["code"].upper() == selected_country
            ),
            selected_country,
        )
        context["filters_query"] = urlencode(query_params)
        context["history_active"] = self.request.GET.get("tab") == "history" or bool(
            selected_country or selected_phase or selected_points != "" or self.request.GET.get("page")
        )
        context["today"] = today
        context["now"] = timezone.now()
        return context
