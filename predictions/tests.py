from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from matches.models import Match
from predictions.models import Prediction
from predictions.services.scoring import ScoreCalculator
from teams.models import Team


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

	def test_creates_prediction_when_kickoff_has_passed_but_match_not_finished(self):
		match = self._match(days_offset=-1, finished=False)

		response = self.client.post(
			reverse("prediction_create", args=[match.id]),
			{
				"predicted_home_score": 0,
				"predicted_away_score": 0,
			},
		)

		self.assertRedirects(response, reverse("dashboard"))
		self.assertTrue(
			Prediction.objects.filter(
				user=self.user,
				match=match,
				predicted_home_score=0,
				predicted_away_score=0,
			).exists()
		)

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


class MyPredictionsViewTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="viewer", password="secret123")
		self.client.login(username="viewer", password="secret123")
		self.team_a = Team.objects.create(name="Alpha", code="ALP")
		self.team_b = Team.objects.create(name="Bravo", code="BRV")

	def _create_prediction(self, *, days_offset, home_score=1, away_score=1):
		match = Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now() + timedelta(days=days_offset),
			finished=False,
		)
		return Prediction.objects.create(
			user=self.user,
			match=match,
			predicted_home_score=home_score,
			predicted_away_score=away_score,
		)

	def test_my_predictions_orders_by_recent_match_first(self):
		older = self._create_prediction(days_offset=-3, home_score=1, away_score=0)
		newer = self._create_prediction(days_offset=1, home_score=2, away_score=1)

		response = self.client.get(reverse("my_predictions"))

		self.assertEqual(response.status_code, 200)
		items = list(response.context["predictions"])
		self.assertEqual(items[0].id, newer.id)
		self.assertEqual(items[1].id, older.id)

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


