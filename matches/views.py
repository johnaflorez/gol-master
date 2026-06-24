from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from matches.models import Match
from stats.services.group_standings import GroupStandingsService
from teams.models import Team


class MatchListView(LoginRequiredMixin, ListView):
    model = Match
    template_name = "matches/list.html"
    context_object_name = "matches"
    paginate_by = None

    def _get_selected_country(self):
        raw_country = (self.request.GET.get("country") or "").strip()
        if not raw_country:
            return ""

        if " - " in raw_country:
            raw_country = raw_country.split(" - ", 1)[0].strip()

        country = raw_country.upper()
        country_by_name = Team.objects.filter(name__iexact=raw_country).first()
        if country_by_name:
            return country_by_name.code.upper()

        return country

    def get_queryset(self):
        queryset = Match.objects.select_related(
            "home_team",
            "away_team"
        ).order_by("-kickoff_at")

        selected_country = self._get_selected_country()

        if selected_country:
            queryset = queryset.filter(
                Q(home_team__country_code__iexact=selected_country)
                | Q(away_team__country_code__iexact=selected_country)
                | Q(home_team__code__iexact=selected_country)
                | Q(away_team__code__iexact=selected_country)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_country = self._get_selected_country()
        all_matches = list(context["matches"])

        context["now"] = timezone.now()
        context["matches_count"] = len(all_matches)
        context["selected_country"] = selected_country
        phase_labels = dict(Match.PHASE_CHOICES)

        country_map = {}
        country_teams = Team.objects.order_by("name")
        for team in country_teams:
            if team.code and team.code not in country_map:
                country_map[team.code] = team.name
        context["country_options"] = [
            {"code": code, "name": name}
            for code, name in country_map.items()
        ]
        context["selected_country_label"] = next(
            (
                f"{country['code']} - {country['name']}"
                for country in context["country_options"]
                if country["code"].upper() == selected_country
            ),
            selected_country,
        )

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
        raw_country = (self.request.GET.get("country") or "").strip()
        if not raw_country:
            return ""

        if " - " in raw_country:
            raw_country = raw_country.split(" - ", 1)[0].strip()

        country_by_name = Team.objects.filter(name__iexact=raw_country).first()
        if country_by_name:
            return country_by_name.code.upper()

        return raw_country.upper()

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

        country_options = []
        seen_names = set()
        for team in Team.objects.order_by("name"):
            normalized_name = team.name.strip().casefold()
            if team.name and normalized_name not in seen_names:
                country_options.append(
                    {
                        "code": team.code,
                        "country_code": team.country_code,
                        "name": team.name,
                    }
                )
                seen_names.add(normalized_name)
        context["country_options"] = country_options
        context["selected_country_label"] = next(
            (
                f"{country['code']} - {country['name']}"
                for country in context["country_options"]
                if selected_country in {
                    (country["code"] or "").upper(),
                    (country["country_code"] or "").upper(),
                    (country["name"] or "").upper(),
                }
            ),
            selected_country,
        )
        return context

