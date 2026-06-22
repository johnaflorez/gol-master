from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from matches.models import Match, MatchEvent
from predictions.models import Prediction
from teams.models import Team


class DashboardViewTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="dashboard-user", password="secret123")
		self.client.login(username="dashboard-user", password="secret123")
		self.team_a = Team.objects.create(name="Nueva Zelanda", code="NZL")
		self.team_b = Team.objects.create(name="Egipto", code="EGY")

	def _create_match(self, kickoff_at):
		return Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=kickoff_at,
			finished=False,
		)

	def test_dashboard_shows_only_today_matches(self):
		today = timezone.localdate()
		today_noon = timezone.make_aware(datetime.combine(today, time(hour=12)))
		yesterday_noon = today_noon - timedelta(days=1)

		today_match = self._create_match(today_noon)
		self._create_match(yesterday_noon)

		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		matches = list(response.context["matches"])
		self.assertEqual(len(matches), 1)
		self.assertEqual(matches[0].id, today_match.id)

	def test_dashboard_exposes_tournament_stats(self):
		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertIn("tournament_stats", response.context)
		self.assertIn("total_matches", response.context["tournament_stats"])
		self.assertIn("total_goals", response.context["tournament_stats"])
		self.assertIn("avg_goals", response.context["tournament_stats"])

	def test_dashboard_shows_predict_button_only_for_available_matches(self):
		today = timezone.localdate()
		today_noon = timezone.make_aware(datetime.combine(today, time(hour=12)))

		available = self._create_match(today_noon + timedelta(hours=1))
		finished = self._create_match(today_noon + timedelta(hours=2))
		finished.finished = True
		finished.home_score = 1
		finished.away_score = 0
		finished.save()

		already_predicted = self._create_match(today_noon + timedelta(hours=3))
		Prediction.objects.create(
			user=self.user,
			match=already_predicted,
			predicted_home_score=1,
			predicted_away_score=1,
		)

		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, reverse("prediction_create", args=[available.id]))
		self.assertNotContains(response, reverse("prediction_create", args=[finished.id]))
		self.assertNotContains(response, reverse("prediction_create", args=[already_predicted.id]))

	def test_dashboard_marks_match_as_live_after_kickoff(self):
		now = timezone.now()
		self._create_match(now - timedelta(minutes=5))

		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "En juego")
		self.assertContains(response, "text-bg-success")

	def test_live_snapshot_requires_login(self):
		self.client.logout()

		response = self.client.get(reverse("dashboard_live_snapshot"))

		self.assertEqual(response.status_code, 302)

	def test_live_snapshot_returns_live_fields_and_events(self):
		match = self._create_match(timezone.now() - timedelta(minutes=12))
		match.live_status = "LIVE"
		match.live_minute = 12
		match.home_score = 1
		match.away_score = 0
		match.save()

		MatchEvent.objects.create(
			match=match,
			team=self.team_a,
			minute=9,
			event_type="GOAL",
			player_name="Jugador A",
		)

		response = self.client.get(reverse("dashboard_live_snapshot"))

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertIn("matches", payload)
		self.assertEqual(len(payload["matches"]), 1)

		first = payload["matches"][0]
		self.assertEqual(first["id"], match.id)
		self.assertEqual(first["status"], "LIVE")
		self.assertEqual(first["live_minute"], 12)
		self.assertEqual(first["home_score"], 1)
		self.assertEqual(first["away_score"], 0)
		self.assertEqual(len(first["events"]), 1)
		self.assertIn("Gol", first["events"][0]["text"])

