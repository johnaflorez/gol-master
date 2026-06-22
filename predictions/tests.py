from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from matches.models import Match
from predictions.models import Prediction
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

		self.assertRedirects(response, reverse("my_predictions"))
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

		self.assertRedirects(response, reverse("my_predictions"))
		self.assertTrue(
			Prediction.objects.filter(
				user=self.user,
				match=match,
				predicted_home_score=0,
				predicted_away_score=0,
			).exists()
		)


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


