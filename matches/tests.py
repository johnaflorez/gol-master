from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from matches.models import Match
from teams.models import Team


class MatchListViewTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="tester", password="secret123")
		self.client.login(username="tester", password="secret123")

		self.team_a = Team.objects.create(name="Team A", code="TMA")
		self.team_b = Team.objects.create(name="Team B", code="TMB")

	def _create_match(self, *, kickoff_at, finished=False):
		return Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=kickoff_at,
			finished=finished,
		)

	def test_match_list_orders_recent_first(self):
		older = self._create_match(kickoff_at=timezone.now() - timedelta(days=2))
		newer = self._create_match(kickoff_at=timezone.now() - timedelta(days=1))

		response = self.client.get(reverse("match_list"))

		self.assertEqual(response.status_code, 200)
		matches = list(response.context["matches"])
		self.assertEqual(matches[0].id, newer.id)
		self.assertEqual(matches[1].id, older.id)

	def test_match_list_does_not_show_predict_button(self):
		self._create_match(kickoff_at=timezone.now() + timedelta(days=3), finished=False)
		self._create_match(kickoff_at=timezone.now() + timedelta(days=2), finished=True)
		self._create_match(kickoff_at=timezone.now() - timedelta(minutes=5), finished=False)

		response = self.client.get(reverse("match_list"))

		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, "Pronosticar")

	def test_match_list_is_paginated(self):
		now = timezone.now()
		for index in range(11):
			self._create_match(kickoff_at=now + timedelta(minutes=index))

		response_page_1 = self.client.get(reverse("match_list"))
		response_page_2 = self.client.get(reverse("match_list"), {"page": 2})

		self.assertEqual(response_page_1.status_code, 200)
		self.assertTrue(response_page_1.context["is_paginated"])
		self.assertEqual(len(response_page_1.context["matches"]), 10)
		self.assertEqual(response_page_1.context["page_obj"].number, 1)

		self.assertEqual(response_page_2.status_code, 200)
		self.assertEqual(len(response_page_2.context["matches"]), 1)
		self.assertEqual(response_page_2.context["page_obj"].number, 2)
