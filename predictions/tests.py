from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from matches.models import Match
from predictions.models import Prediction, TournamentPrediction
from predictions.services.scoring import ScoreCalculator
from teams.models import Player, Team


class PredictionCreateViewTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="pred-user", password="secret123")
		self.client.login(username="pred-user", password="secret123")
		self.team_a = Team.objects.create(name="Team One", code="ONE")
		self.team_b = Team.objects.create(name="Team Two", code="TWO")

	def _match(self, *, days_offset, finished=False):
		return Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now() + timedelta(days=days_offset),
			finished=finished,
		)

	def test_redirects_if_match_is_finished(self):
		match = self._match(days_offset=1, finished=True)

		response = self.client.get(reverse("prediction_create", args=[match.id]))

		self.assertRedirects(response, reverse("match_list"))

	def test_redirects_if_match_has_already_started(self):
		match = self._match(days_offset=-1, finished=False)

		response = self.client.get(reverse("prediction_create", args=[match.id]))

		self.assertRedirects(response, reverse("match_list"))

	def test_redirects_if_prediction_already_exists(self):
		match = self._match(days_offset=1)
		Prediction.objects.create(
			user=self.user,
			match=match,
			predicted_home_score=1,
			predicted_away_score=1,
		)

		response = self.client.get(reverse("prediction_create", args=[match.id]))

		self.assertRedirects(response, reverse("match_list"))

	def test_creates_prediction_when_match_is_open(self):
		match = self._match(days_offset=1)

		response = self.client.post(
			reverse("prediction_create", args=[match.id]),
			{
				"predicted_home_score": 2,
				"predicted_away_score": 1,
			},
		)

		self.assertRedirects(response, reverse("dashboard"))
		self.assertTrue(
			Prediction.objects.filter(
				user=self.user,
				match=match,
				predicted_home_score=2,
				predicted_away_score=1,
			).exists()
		)

	def test_does_not_create_prediction_when_kickoff_has_passed_but_match_not_finished(self):
		match = self._match(days_offset=-1, finished=False)

		response = self.client.post(
			reverse("prediction_create", args=[match.id]),
			{
				"predicted_home_score": 0,
				"predicted_away_score": 0,
			},
		)

		self.assertRedirects(response, reverse("match_list"))
		self.assertFalse(Prediction.objects.filter(user=self.user, match=match).exists())

	def test_prediction_form_includes_previous_results_for_match_teams(self):
		target_match = self._match(days_offset=2, finished=False)

		recent_related = self._match(days_offset=-1, finished=True)
		recent_related.home_score = 2
		recent_related.away_score = 1
		recent_related.save()

		older_related = self._match(days_offset=-4, finished=True)
		older_related.home_score = 0
		older_related.away_score = 0
		older_related.save()

		third_team = Team.objects.create(name="Team Three", code="THR")
		unrelated = Match.objects.create(
			home_team=third_team,
			away_team=third_team,
			kickoff_at=timezone.now() - timedelta(days=2),
			finished=True,
			home_score=1,
			away_score=1,
		)

		recent_pred = Prediction.objects.create(
			user=self.user,
			match=recent_related,
			predicted_home_score=2,
			predicted_away_score=0,
			points=2,
		)

		response = self.client.get(reverse("prediction_create", args=[target_match.id]))

		self.assertEqual(response.status_code, 200)
		previous_team_results = list(response.context["previous_team_results"])
		prediction_map = response.context["prediction_map"]

		self.assertEqual(len(previous_team_results), 2)
		self.assertEqual(previous_team_results[0].id, recent_related.id)
		self.assertEqual(previous_team_results[1].id, older_related.id)
		self.assertNotIn(unrelated.id, [match.id for match in previous_team_results])

		self.assertIn(recent_related.id, prediction_map)
		self.assertEqual(prediction_map[recent_related.id]["home"], 2)
		self.assertEqual(prediction_map[recent_related.id]["away"], 0)
		self.assertEqual(prediction_map[recent_related.id]["points"], 2)
		self.assertNotIn(older_related.id, prediction_map)

	def test_prediction_dashboard_orders_open_matches_by_kickoff(self):
		later = self._match(days_offset=2)
		earlier = self._match(days_offset=1)

		response = self.client.get(reverse("prediction_dashboard"))

		self.assertEqual(response.status_code, 200)
		matches = list(response.context["matches"])
		self.assertEqual([match.id for match in matches], [earlier.id, later.id])


class TournamentPredictionViewTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="global-user", password="secret123")
		self.team_a = Team.objects.create(name="Colombia", code="COL", country_code="CO")
		self.team_b = Team.objects.create(name="Brasil", code="BRA", country_code="BR")
		self.player_a = Player.objects.create(name="Luis Díaz", team=self.team_a, photo="players/luis-diaz.png")
		self.player_b = Player.objects.create(name="Vinicius Jr", team=self.team_b, photo="players/vinicius.png")

	def test_requires_login(self):
		response = self.client.get(reverse("tournament_prediction"))

		self.assertEqual(response.status_code, 302)

	def test_creates_tournament_prediction(self):
		self.client.login(username="global-user", password="secret123")

		response = self.client.post(
			reverse("tournament_prediction"),
			{
				"champion_team": self.team_a.id,
				"top_scorer": self.player_a.id,
			},
		)

		self.assertRedirects(response, reverse("tournament_prediction"))
		prediction = TournamentPrediction.objects.get(user=self.user)
		self.assertEqual(prediction.champion_team, self.team_a)
		self.assertEqual(prediction.top_scorer, self.player_a)
		self.assertEqual(prediction.top_scorer_name, "Luis Díaz")

	def test_tournament_prediction_uses_searchable_datalists(self):
		self.client.login(username="global-user", password="secret123")

		response = self.client.get(reverse("tournament_prediction"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'list="champion-team-options"')
		self.assertContains(response, 'list="top-scorer-options"')
		self.assertContains(response, "COL - Colombia")
		self.assertContains(response, "Luis Díaz (COL)")

	def test_creates_tournament_prediction_from_datalist_text_values(self):
		self.client.login(username="global-user", password="secret123")

		response = self.client.post(
			reverse("tournament_prediction"),
			{
				"champion_team": "COL - Colombia",
				"top_scorer": "Luis Díaz (COL)",
			},
		)

		self.assertRedirects(response, reverse("tournament_prediction"))
		prediction = TournamentPrediction.objects.get(user=self.user)
		self.assertEqual(prediction.champion_team, self.team_a)
		self.assertEqual(prediction.top_scorer, self.player_a)
		self.assertEqual(prediction.top_scorer_name, "Luis Díaz")

	def test_existing_tournament_prediction_cannot_be_modified(self):
		TournamentPrediction.objects.create(
			user=self.user,
			champion_team=self.team_a,
			top_scorer=self.player_a,
			top_scorer_name="Luis Díaz",
		)
		self.client.login(username="global-user", password="secret123")

		response = self.client.post(
			reverse("tournament_prediction"),
			{
				"champion_team": self.team_b.id,
				"top_scorer": self.player_b.id,
			},
		)

		self.assertRedirects(response, reverse("tournament_prediction"))
		self.assertEqual(TournamentPrediction.objects.filter(user=self.user).count(), 1)
		prediction = TournamentPrediction.objects.get(user=self.user)
		self.assertEqual(prediction.champion_team, self.team_a)
		self.assertEqual(prediction.top_scorer, self.player_a)
		self.assertEqual(prediction.top_scorer_name, "Luis Díaz")

	def test_shows_existing_prediction(self):
		TournamentPrediction.objects.create(
			user=self.user,
			champion_team=self.team_a,
			top_scorer=self.player_a,
			top_scorer_name="Luis Díaz",
		)
		self.client.login(username="global-user", password="secret123")

		response = self.client.get(reverse("tournament_prediction"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Colombia")
		self.assertContains(response, "Luis Díaz")
		self.assertContains(response, "Bandera CO")
		self.assertContains(response, "players/luis-diaz.png")
		self.assertContains(response, "no se puede modificar")
		self.assertNotContains(response, "Tu elección actual")
		self.assertNotContains(response, "Guardar pronóstico")
		self.assertNotContains(response, "Editar pronóstico")


class MyPredictionsViewTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="viewer", password="secret123")
		self.client.login(username="viewer", password="secret123")
		self.team_a = Team.objects.create(name="Alpha", code="ALP", country_code="CO")
		self.team_b = Team.objects.create(name="Bravo", code="BRV", country_code="BR")
		self.player_a = Player.objects.create(name="Jugador Alpha", team=self.team_a, photo="players/jugador-alpha.png")

	def _create_prediction(
		self,
		*,
		days_offset,
		home_score=1,
		away_score=1,
		phase="PR",
		points=0,
		home_team=None,
		away_team=None,
	):
		match = Match.objects.create(
			home_team=home_team or self.team_a,
			away_team=away_team or self.team_b,
			kickoff_at=timezone.now() + timedelta(days=days_offset),
			finished=False,
			phase=phase,
		)
		return Prediction.objects.create(
			user=self.user,
			match=match,
			predicted_home_score=home_score,
			predicted_away_score=away_score,
			points=points,
		)

	def test_my_predictions_orders_by_recent_match_first(self):
		older = self._create_prediction(days_offset=-3, home_score=1, away_score=0)
		newer = self._create_prediction(days_offset=1, home_score=2, away_score=1)

		response = self.client.get(reverse("my_predictions"))

		self.assertEqual(response.status_code, 200)
		items = list(response.context["predictions"])
		self.assertEqual(items[0].id, newer.id)
		self.assertEqual(items[1].id, older.id)

	def test_my_predictions_shows_user_tournament_prediction(self):
		TournamentPrediction.objects.create(
			user=self.user,
			champion_team=self.team_a,
			top_scorer=self.player_a,
			top_scorer_name="Jugador Alpha",
		)

		response = self.client.get(reverse("my_predictions"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["tournament_prediction"].champion_team, self.team_a)
		self.assertContains(response, "Mi campeón y goleador")
		self.assertContains(response, "Campeón elegido")
		self.assertContains(response, "Goleador elegido")
		self.assertContains(response, "Alpha")
		self.assertContains(response, "Jugador Alpha")
		self.assertContains(response, "Bandera CO")
		self.assertContains(response, "players/jugador-alpha.png")
		self.assertContains(response, "no se puede modificar")
		self.assertNotContains(response, "Crear elección")

	def test_my_predictions_links_to_create_tournament_prediction_when_missing(self):
		response = self.client.get(reverse("my_predictions"))

		self.assertEqual(response.status_code, 200)
		self.assertIsNone(response.context["tournament_prediction"])
		self.assertContains(response, "Aún no has elegido campeón y goleador del mundial")
		self.assertContains(response, "Crear elección")
		self.assertContains(response, reverse("tournament_prediction"))

	def test_my_predictions_is_paginated(self):
		for index in range(11):
			self._create_prediction(days_offset=index)

		response_page_1 = self.client.get(reverse("my_predictions"))
		response_page_2 = self.client.get(reverse("my_predictions"), {"page": 2})

		self.assertEqual(response_page_1.status_code, 200)
		self.assertTrue(response_page_1.context["is_paginated"])
		self.assertEqual(len(response_page_1.context["predictions"]), 10)
		self.assertEqual(response_page_1.context["page_obj"].number, 1)

		self.assertEqual(response_page_2.status_code, 200)
		self.assertEqual(len(response_page_2.context["predictions"]), 1)
		self.assertEqual(response_page_2.context["page_obj"].number, 2)

	def test_my_predictions_includes_phase_stats(self):
		match_pr_winner = Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now() - timedelta(days=2),
			finished=True,
			home_score=2,
			away_score=1,
			phase="PR",
		)
		Prediction.objects.create(
			user=self.user,
			match=match_pr_winner,
			predicted_home_score=1,
			predicted_away_score=0,
			points=2,
		)

		match_pr_exact = Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now() - timedelta(days=1),
			finished=True,
			home_score=1,
			away_score=1,
			phase="PR",
		)
		Prediction.objects.create(
			user=self.user,
			match=match_pr_exact,
			predicted_home_score=1,
			predicted_away_score=1,
			points=5,
		)

		match_of_winner = Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now() - timedelta(hours=5),
			finished=True,
			home_score=0,
			away_score=2,
			phase="OF",
		)
		Prediction.objects.create(
			user=self.user,
			match=match_of_winner,
			predicted_home_score=0,
			predicted_away_score=1,
			points=2,
		)

		match_pr_pending = Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now() + timedelta(hours=5),
			finished=False,
			phase="PR",
		)
		Prediction.objects.create(
			user=self.user,
			match=match_pr_pending,
			predicted_home_score=0,
			predicted_away_score=0,
			points=0,
		)

		response = self.client.get(reverse("my_predictions"))

		self.assertEqual(response.status_code, 200)
		stats = {row["phase"]: row for row in response.context["phase_stats"]}

		self.assertIn("PR", stats)
		self.assertIn("OF", stats)

		self.assertEqual(stats["PR"]["points_total"], 7)
		self.assertEqual(stats["PR"]["winner_or_draw_hits"], 2)
		self.assertEqual(stats["PR"]["exact_hits"], 1)
		self.assertEqual(stats["PR"]["finished_predictions"], 2)
		self.assertEqual(stats["PR"]["total_predictions"], 3)

		self.assertEqual(stats["OF"]["points_total"], 2)
		self.assertEqual(stats["OF"]["winner_or_draw_hits"], 1)
		self.assertEqual(stats["OF"]["exact_hits"], 0)

		totals = response.context["phase_stats_totals"]
		self.assertEqual(totals["points_total"], 9)
		self.assertEqual(totals["winner_or_draw_hits"], 3)
		self.assertEqual(totals["exact_hits"], 1)

	def test_my_predictions_status_changes_to_en_juego_after_kickoff(self):
		live_match = Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now() - timedelta(minutes=10),
			finished=False,
		)
		Prediction.objects.create(
			user=self.user,
			match=live_match,
			predicted_home_score=1,
			predicted_away_score=0,
		)

		upcoming_match = Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now() + timedelta(minutes=45),
			finished=False,
		)
		Prediction.objects.create(
			user=self.user,
			match=upcoming_match,
			predicted_home_score=0,
			predicted_away_score=0,
		)

		response = self.client.get(reverse("my_predictions"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "En juego")
		self.assertContains(response, "Pendiente")

	def test_my_predictions_filters_by_country(self):
		colombia = Team.objects.create(name="Colombia", code="COL", country_code="")
		brasil = Team.objects.create(name="Brasil", code="BRA", country_code="")
		argentina = Team.objects.create(name="Argentina", code="ARG", country_code="AR")

		prediction_col = self._create_prediction(
			days_offset=1,
			home_team=colombia,
			away_team=brasil,
		)
		self._create_prediction(
			days_offset=2,
			home_team=argentina,
			away_team=brasil,
		)

		response = self.client.get(reverse("my_predictions"), {"country": "COL - Colombia"})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'list="country-options"')
		self.assertContains(response, "COL - Colombia")
		items = list(response.context["predictions"])
		self.assertEqual(len(items), 1)
		self.assertEqual(items[0].id, prediction_col.id)

	def test_my_predictions_filters_by_phase(self):
		prediction_final = self._create_prediction(days_offset=1, phase="F")
		self._create_prediction(days_offset=2, phase="PR")

		response = self.client.get(reverse("my_predictions"), {"phase": "F"})

		self.assertEqual(response.status_code, 200)
		items = list(response.context["predictions"])
		self.assertEqual(len(items), 1)
		self.assertEqual(items[0].id, prediction_final.id)
		self.assertEqual(response.context["selected_phase"], "F")

	def test_my_predictions_filters_by_points(self):
		prediction_exact = self._create_prediction(days_offset=1, points=5)
		self._create_prediction(days_offset=2, points=2)

		response = self.client.get(reverse("my_predictions"), {"points": "5"})

		self.assertEqual(response.status_code, 200)
		items = list(response.context["predictions"])
		self.assertEqual(len(items), 1)
		self.assertEqual(items[0].id, prediction_exact.id)
		self.assertEqual(response.context["selected_points"], "5")

	def test_my_predictions_pagination_preserves_filters(self):
		for index in range(11):
			self._create_prediction(days_offset=index, phase="PR", points=0)

		response = self.client.get(reverse("my_predictions"), {"country": "ALP", "phase": "PR", "points": "0"})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "?country=ALP&amp;phase=PR&amp;points=0&amp;page=2")


class AllPredictionsViewTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="all-viewer", password="secret123")
		self.other_user = User.objects.create_user(username="other-viewer", password="secret123")
		self.client.login(username="all-viewer", password="secret123")
		self.colombia = Team.objects.create(name="Colombia", code="COL", country_code="CO")
		self.brasil = Team.objects.create(name="Brasil", code="BRA", country_code="BR")
		self.argentina = Team.objects.create(name="Argentina", code="ARG", country_code="AR")
		self.luis_diaz = Player.objects.create(name="Luis Díaz", team=self.colombia, photo="players/luis-diaz.png")
		self.vinicius = Player.objects.create(name="Vinicius Jr", team=self.brasil, photo="players/vinicius.png")

	def _prediction(self, *, user=None, kickoff_at=None, phase="PR", points=0, finished=False, home_team=None, away_team=None):
		match = Match.objects.create(
			home_team=home_team or self.colombia,
			away_team=away_team or self.brasil,
			kickoff_at=kickoff_at or timezone.now(),
			finished=finished,
			home_score=2 if finished else 0,
			away_score=1 if finished else 0,
			phase=phase,
		)
		return Prediction.objects.create(
			user=user or self.user,
			match=match,
			predicted_home_score=2,
			predicted_away_score=1,
			points=points,
		)

	def test_all_predictions_today_tab_includes_finished_today_matches(self):
		prediction = self._prediction(
			kickoff_at=timezone.now() - timedelta(hours=1),
			finished=True,
			phase="F",
			points=5,
		)

		response = self.client.get(reverse("all_predictions"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Del día")
		self.assertContains(response, "Histórico")
		self.assertContains(response, "Campeón y goleador")
		self.assertContains(response, "Final:")
		self.assertContains(response, "Final")
		self.assertContains(response, "badge text-bg-secondary")
		self.assertContains(response, 'text-secondary"></i>Final:')
		self.assertContains(response, "5 pts")
		self.assertContains(response, "col-lg-6")
		groups = list(response.context["today_grouped"])
		self.assertEqual(groups[0]["predictions"][0].id, prediction.id)

	def test_all_predictions_today_tab_orders_finished_matches_last(self):
		today = timezone.localdate()
		finished_early = self._prediction(
			kickoff_at=timezone.make_aware(datetime.combine(today, time(hour=9))),
			finished=True,
		)
		upcoming_first = self._prediction(
			kickoff_at=timezone.make_aware(datetime.combine(today, time(hour=10))),
		)
		upcoming_second = self._prediction(
			kickoff_at=timezone.make_aware(datetime.combine(today, time(hour=11))),
		)

		response = self.client.get(reverse("all_predictions"))

		self.assertEqual(response.status_code, 200)
		groups = list(response.context["today_grouped"])
		self.assertEqual(
			[group["match"].id for group in groups],
			[upcoming_first.match_id, upcoming_second.match_id, finished_early.match_id],
		)

	def test_all_predictions_historical_filters_by_country_phase_and_points(self):
		wanted = self._prediction(
			kickoff_at=timezone.now() - timedelta(days=2),
			phase="F",
			points=5,
			home_team=self.colombia,
			away_team=self.brasil,
		)
		self._prediction(
			kickoff_at=timezone.now() - timedelta(days=1),
			phase="PR",
			points=2,
			home_team=self.argentina,
			away_team=self.brasil,
		)

		response = self.client.get(
			reverse("all_predictions"),
			{"country": "COL - Colombia", "phase": "F", "points": "5"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'list="country-options"')
		self.assertContains(response, "COL - Colombia")
		self.assertContains(response, "Todas las fases")
		self.assertContains(response, "Puntos")
		items = list(response.context["historical_predictions"])
		self.assertEqual(len(items), 1)
		self.assertEqual(items[0].id, wanted.id)
		self.assertTrue(response.context["history_active"])

	def test_all_predictions_historical_filters_by_user(self):
		wanted = self._prediction(
			user=self.other_user,
			kickoff_at=timezone.now() - timedelta(days=2),
			points=5,
		)
		self._prediction(
			user=self.user,
			kickoff_at=timezone.now() - timedelta(days=1),
			points=2,
		)

		response = self.client.get(
			reverse("all_predictions"),
			{"tab": "history", "user": str(self.other_user.id)},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'name="user"')
		self.assertContains(response, "Todos los usuarios")
		self.assertContains(response, self.other_user.username)
		self.assertEqual(response.context["selected_user_id"], self.other_user.id)
		items = list(response.context["historical_predictions"])
		self.assertEqual(len(items), 1)
		self.assertEqual(items[0].id, wanted.id)
		self.assertTrue(response.context["history_active"])

	def test_all_predictions_historical_is_paginated_and_preserves_filters(self):
		for index in range(11):
			self._prediction(
				kickoff_at=timezone.now() - timedelta(days=index + 1),
				phase="PR",
				points=0,
				home_team=self.colombia,
				away_team=self.brasil,
			)

		response = self.client.get(reverse("all_predictions"), {"country": "COL", "phase": "PR", "points": "0", "user": str(self.user.id)})

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context["history_is_paginated"])
		self.assertEqual(len(response.context["historical_predictions"]), 10)
		self.assertEqual(response.context["history_page_obj"].number, 1)
		self.assertContains(response, f"?country=COL&amp;phase=PR&amp;points=0&amp;user={self.user.id}&amp;page=2")

	def test_all_predictions_keeps_history_tab_active_without_filters(self):
		for index in range(11):
			self._prediction(kickoff_at=timezone.now() - timedelta(days=index + 1))

		response = self.client.get(reverse("all_predictions"), {"tab": "history"})

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context["history_active"])
		self.assertContains(response, 'name="tab" value="history"')
		self.assertContains(response, 'href="?tab=history"')
		self.assertContains(response, "?tab=history&amp;page=2")

	def test_all_predictions_uses_general_page_name(self):
		response = self.client.get(reverse("all_predictions"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Pronósticos")
		self.assertContains(response, "Pronósticos del día e histórico general")

	def test_all_predictions_tournament_tab_shows_champion_and_top_scorer_choices(self):
		TournamentPrediction.objects.create(
			user=self.user,
			champion_team=self.colombia,
			top_scorer=self.luis_diaz,
			top_scorer_name="Luis Díaz",
		)
		TournamentPrediction.objects.create(
			user=self.other_user,
			champion_team=self.brasil,
			top_scorer=self.vinicius,
			top_scorer_name="Vinicius Jr",
		)

		response = self.client.get(reverse("all_predictions"), {"tab": "tournament"})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["active_tab"], "tournament")
		self.assertTrue(response.context["tournament_active"])
		self.assertContains(response, "Campeón y goleador")
		self.assertContains(response, "Campeón y goleador elegidos")
		self.assertContains(response, "Campeón elegido")
		self.assertContains(response, "Goleador elegido")
		self.assertContains(response, "Colombia")
		self.assertContains(response, "Brasil")
		self.assertContains(response, "Luis Díaz")
		self.assertContains(response, "Vinicius Jr")
		self.assertContains(response, "Bandera CO")
		self.assertContains(response, "Bandera BR")
		self.assertContains(response, "players/luis-diaz.png")
		self.assertContains(response, "players/vinicius.png")
		self.assertContains(response, reverse("tournament_prediction"))
		self.assertEqual(list(response.context["tournament_predictions"]), list(TournamentPrediction.objects.all()))

	def test_all_predictions_tournament_tab_shows_empty_state(self):
		response = self.client.get(reverse("all_predictions"), {"tab": "tournament"})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["active_tab"], "tournament")
		self.assertContains(response, "Aún no hay pronósticos de campeón y goleador para mostrar")
		self.assertContains(response, "Crear mi elección")


class ScoreCalculatorTests(TestCase):

	def setUp(self):
		self.team_a = Team.objects.create(name="Score Alpha", code="SCA")
		self.team_b = Team.objects.create(name="Score Bravo", code="SCB")
		self.user = User.objects.create_user(username="score-user", password="secret123")
		self.calculator = ScoreCalculator()

	def _build_match_and_prediction(self, *, real_home, real_away, pred_home, pred_away):
		match = Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now(),
			home_score=real_home,
			away_score=real_away,
			finished=True,
		)
		prediction = Prediction(
			user=self.user,
			match=match,
			predicted_home_score=pred_home,
			predicted_away_score=pred_away,
		)
		return prediction, match

	def test_correct_winner_gives_two_points(self):
		prediction, match = self._build_match_and_prediction(
			real_home=2,
			real_away=1,
			pred_home=3,
			pred_away=0,
		)

		self.assertEqual(self.calculator.calculate(prediction, match), 2)

	def test_exact_score_gives_five_points_total(self):
		prediction, match = self._build_match_and_prediction(
			real_home=1,
			real_away=1,
			pred_home=1,
			pred_away=1,
		)

		self.assertEqual(self.calculator.calculate(prediction, match), 5)


