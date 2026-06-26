from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from matches.models import Match
from matches.services.knockout_bracket import KnockoutBracketService
from stats.services.group_standings import GroupStandingsService
from teams.models import Team
from teams.utils import get_country_label, get_country_options, match_country_q, parse_country_filter


class MatchListView(LoginRequiredMixin, ListView):
    model = Match
    template_name = "matches/list.html"
    context_object_name = "matches"
    paginate_by = None

    def _get_selected_country(self):
        return parse_country_filter(self.request.GET.get("country"))

    def get_queryset(self):
        queryset = Match.objects.select_related(
            "home_team",
            "away_team"
        ).order_by("-kickoff_at")

        selected_country = self._get_selected_country()

        if selected_country:
            queryset = queryset.filter(match_country_q(selected_country))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_country = self._get_selected_country()
        all_matches = list(context["matches"])

        context["now"] = timezone.now()
        context["matches_count"] = len(all_matches)
        context["selected_country"] = selected_country
        phase_labels = dict(Match.PHASE_CHOICES)

        context["country_options"] = get_country_options()
        context["selected_country_label"] = get_country_label(selected_country, context["country_options"])

        context["grouped_matches"] = [
            {
                "code": phase_code,
                "label": phase_labels.get(phase_code, phase_code),
                "matches": [match for match in all_matches if match.phase == phase_code],
            }
            for phase_code, _ in Match.PHASE_CHOICES
            if any(match.phase == phase_code for match in all_matches)
        ]

        query_params = {}
        if selected_country:
            query_params["country"] = selected_country
        context["filters_query"] = urlencode(query_params)

        return context


class GroupStandingsView(LoginRequiredMixin, TemplateView):
    template_name = "matches/group_standings.html"

    def _get_selected_group(self):
        return (self.request.GET.get("group") or "").strip().upper()

    def _get_selected_country(self):
        return parse_country_filter(self.request.GET.get("country"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_group = self._get_selected_group()
        selected_country = self._get_selected_country()

        context["selected_group"] = selected_group
        context["selected_country"] = selected_country
        context["group_standings"] = GroupStandingsService().get_group_standings(
            group_code=selected_group,
            country=selected_country,
        )
        context["group_options"] = [
            {"code": code, "label": f"Grupo {code}"}
            for code in Team.objects.exclude(group_code="").order_by("group_code").values_list("group_code", flat=True).distinct()
        ]

        context["country_options"] = get_country_options(unique_by="name")
        context["selected_country_label"] = get_country_label(
            selected_country,
            context["country_options"],
            match_country_code=True,
            match_name=True,
        )
        return context


class KnockoutBracketView(LoginRequiredMixin, TemplateView):
    template_name = "matches/knockout_bracket.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bracket"] = KnockoutBracketService().get_bracket()
        return context


