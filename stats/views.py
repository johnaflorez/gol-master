from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import ListView

from stats.models import TopScorerStanding
from teams.models import Player
from teams.utils import (
	find_player_from_filter,
	get_country_label,
	get_country_options,
	get_player_label,
	get_player_options,
	parse_country_filter,
)


class TopScorersView(LoginRequiredMixin, ListView):
	template_name = "stats/top_scorers.html"
	context_object_name = "scorers"
	paginate_by = 50

	def _get_player_id_filter(self):
		try:
			return int(self.request.GET.get("player_id") or 0) or None
		except (TypeError, ValueError):
			return None

	def _get_player_filter(self):
		return (self.request.GET.get("player") or "").strip()

	def _get_selected_player(self):
		if hasattr(self, "_selected_player"):
			return self._selected_player
		player_text = self._get_player_filter()
		if player_text:
			self._selected_player = find_player_from_filter(player_text)
			if self._selected_player:
				return self._selected_player
		player_id = self._get_player_id_filter()
		if not player_id:
			self._selected_player = None
			return self._selected_player
		self._selected_player = Player.objects.select_related("team").filter(pk=player_id).first()
		return self._selected_player

	def _get_country_filter(self):
		return parse_country_filter(self.request.GET.get("country"))

	def get_queryset(self):
		queryset = TopScorerStanding.objects.select_related("team", "player").order_by("rank", "-goals", "player_name")
		selected_player = self._get_selected_player()
		player = self._get_player_filter()
		country = self._get_country_filter()

		if selected_player:
			player_query = Q(player=selected_player)
			if selected_player.football_data_player_id:
				player_query |= Q(football_data_player_id=selected_player.football_data_player_id)
			if selected_player.team_id:
				player_query |= Q(player_name__iexact=selected_player.name, team=selected_player.team)
				if selected_player.team.tla:
					player_query |= Q(player_name__iexact=selected_player.name, team_tla__iexact=selected_player.team.tla)
				if selected_player.team.name:
					player_query |= Q(player_name__iexact=selected_player.name, team_name__iexact=selected_player.team.name)
			queryset = queryset.filter(player_query)
		elif player:
			queryset = queryset.filter(Q(player__name__icontains=player) | Q(player_name__icontains=player))

		if country:
			queryset = queryset.filter(
				Q(team__code__iexact=country)
				| Q(team__country_code__iexact=country)
				| Q(team__tla__iexact=country)
				| Q(team__name__iexact=country)
				| Q(team_name__iexact=country)
				| Q(team_tla__iexact=country)
			)

		return queryset

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		selected_player = self._get_selected_player()
		selected_player_id = selected_player.id if selected_player else None
		player_text = self._get_player_filter()
		selected_player_label = get_player_label(selected_player) if selected_player else player_text
		selected_country = self._get_country_filter()
		country_options = get_country_options(unique_by="name")
		filter_params = {}
		if selected_player_label:
			filter_params["player"] = selected_player_label
		if selected_country:
			filter_params["country"] = selected_country

		context["player_options"] = get_player_options()
		context["selected_player_id"] = selected_player_id
		context["selected_player"] = selected_player.name if selected_player else player_text
		context["selected_player_label"] = selected_player_label
		context["selected_country"] = selected_country
		context["country_options"] = country_options
		context["selected_country_label"] = get_country_label(
			selected_country,
			country_options,
			match_country_code=True,
			match_name=True,
		)
		context["filters_query"] = urlencode(filter_params)
		return context
