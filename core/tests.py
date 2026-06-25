from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Suggestion
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

	def test_dashboard_orders_unfinished_matches_first_and_finished_last(self):
		today = timezone.localdate()
		finished_early = self._create_match(timezone.make_aware(datetime.combine(today, time(hour=9))))
		finished_early.finished = True
		finished_early.live_status = "FT"
		finished_early.home_score = 1
		finished_early.away_score = 0
		finished_early.save()
		upcoming_first = self._create_match(timezone.make_aware(datetime.combine(today, time(hour=10))))
		upcoming_second = self._create_match(timezone.make_aware(datetime.combine(today, time(hour=11))))

		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		matches = list(response.context["matches"])
		self.assertEqual([match.id for match in matches], [upcoming_first.id, upcoming_second.id, finished_early.id])

	def test_dashboard_exposes_tournament_stats(self):
		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertIn("tournament_stats", response.context)
		self.assertIn("total_matches", response.context["tournament_stats"])
		self.assertIn("total_goals", response.context["tournament_stats"])
		self.assertIn("avg_goals", response.context["tournament_stats"])

	def test_dashboard_shows_predict_button_only_for_available_matches(self):
		today = timezone.localdate()
		fixed_now = timezone.make_aware(datetime.combine(today, time(hour=10)))

		available = self._create_match(fixed_now + timedelta(hours=1))
		finished = self._create_match(fixed_now + timedelta(hours=2))
		finished.finished = True
		finished.home_score = 1
		finished.away_score = 0
		finished.save()

		already_predicted = self._create_match(fixed_now + timedelta(hours=3))
		Prediction.objects.create(
			user=self.user,
			match=already_predicted,
			predicted_home_score=1,
			predicted_away_score=1,
		)
		started = self._create_match(fixed_now - timedelta(minutes=5))

		with patch("core.views.timezone.now", return_value=fixed_now), patch("core.views.timezone.localdate", return_value=today):
			response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, reverse("prediction_create", args=[available.id]))
		self.assertNotContains(response, reverse("prediction_create", args=[finished.id]))
		self.assertNotContains(response, reverse("prediction_create", args=[already_predicted.id]))
		self.assertNotContains(response, reverse("prediction_create", args=[started.id]))

	def test_dashboard_marks_match_as_live_after_kickoff(self):
		now = timezone.now()
		self._create_match(now - timedelta(minutes=5))

		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "En juego")
		self.assertContains(response, "text-bg-success")

	def test_dashboard_shows_final_match_marquee_for_exact_prediction(self):
		match = self._create_match(timezone.now() - timedelta(hours=2))
		match.home_score = 2
		match.away_score = 1
		match.finished = True
		match.save()
		Prediction.objects.create(
			user=self.user,
			match=match,
			predicted_home_score=2,
			predicted_away_score=1,
		)

		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "final-match-marquee")
		self.assertContains(response, "Felicitaciones")
		self.assertContains(response, self.user.username)
		self.assertContains(response, "2-1")

	def test_dashboard_renders_multiple_final_announcements_in_single_marquee(self):
		first_match = self._create_match(timezone.now() - timedelta(hours=2))
		first_match.home_score = 2
		first_match.away_score = 1
		first_match.finished = True
		first_match.save()
		Prediction.objects.create(
			user=self.user,
			match=first_match,
			predicted_home_score=2,
			predicted_away_score=1,
		)

		second_match = self._create_match(timezone.now() - timedelta(hours=1))
		second_match.home_score = 0
		second_match.away_score = 0
		second_match.finished = True
		second_match.save()

		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'class="final-match-marquee"', count=1)
		self.assertContains(response, 'class="final-match-marquee__text"', count=2)
		self.assertContains(response, "Felicitaciones")
		self.assertContains(response, "No hubo ningún acierto exacto")
		self.assertContains(response, "final-match-marquee__separator")

	def test_dashboard_shows_final_match_marquee_without_exact_predictions(self):
		match = self._create_match(timezone.now() - timedelta(hours=2))
		match.home_score = 1
		match.away_score = 1
		match.finished = True
		match.save()
		Prediction.objects.create(
			user=self.user,
			match=match,
			predicted_home_score=2,
			predicted_away_score=1,
		)

		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "No hubo ningún acierto exacto")

	def test_dashboard_does_not_show_expired_final_match_marquee(self):
		match = self._create_match(timezone.now() - timedelta(hours=2))
		match.home_score = 1
		match.away_score = 0
		match.finished = True
		match.save()
		Match.objects.filter(id=match.id).update(finished_at=timezone.now() - timedelta(minutes=6))

		response = self.client.get(reverse("dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, "No hubo ningún acierto exacto")

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

	def test_live_snapshot_orders_finished_matches_last(self):
		today = timezone.localdate()
		finished_early = self._create_match(timezone.make_aware(datetime.combine(today, time(hour=9))))
		finished_early.finished = True
		finished_early.live_status = "FT"
		finished_early.save()
		upcoming = self._create_match(timezone.make_aware(datetime.combine(today, time(hour=10))))

		response = self.client.get(reverse("dashboard_live_snapshot"))

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual([match["id"] for match in payload["matches"]], [upcoming.id, finished_early.id])


class SuggestionViewTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="suggestion-user", password="secret123")
		self.superuser = User.objects.create_superuser(username="suggestion-admin", password="secret123")

	def test_suggestion_create_requires_login(self):
		response = self.client.get(reverse("suggestion_create"))

		self.assertEqual(response.status_code, 302)

	def test_authenticated_user_can_create_suggestion(self):
		self.client.login(username="suggestion-user", password="secret123")

		response = self.client.post(
			reverse("suggestion_create"),
			{"message": "Agregar modo oscuro para ver mejor en la noche."},
		)

		self.assertRedirects(response, reverse("suggestion_create"))
		self.assertTrue(
			Suggestion.objects.filter(
				user=self.user,
				message="Agregar modo oscuro para ver mejor en la noche.",
				is_resolved=False,
			).exists()
		)

	def test_non_superuser_cannot_view_suggestion_list(self):
		self.client.login(username="suggestion-user", password="secret123")

		response = self.client.get(reverse("suggestion_list"))

		self.assertEqual(response.status_code, 403)

	def test_superuser_list_shows_only_pending_by_default(self):
		pending = Suggestion.objects.create(user=self.user, message="Pendiente")
		resolved = Suggestion.objects.create(user=self.user, message="Resuelta", is_resolved=True)
		self.client.login(username="suggestion-admin", password="secret123")

		response = self.client.get(reverse("suggestion_list"))

		self.assertEqual(response.status_code, 200)
		suggestions = list(response.context["suggestions"])
		self.assertIn(pending, suggestions)
		self.assertNotIn(resolved, suggestions)
		self.assertContains(response, "Pendiente")
		self.assertNotContains(response, "Resuelta")

	def test_superuser_can_filter_resolved_suggestions(self):
		Suggestion.objects.create(user=self.user, message="Pendiente")
		resolved = Suggestion.objects.create(user=self.user, message="Resuelta", is_resolved=True)
		self.client.login(username="suggestion-admin", password="secret123")

		response = self.client.get(reverse("suggestion_list") + "?status=resolved")

		self.assertEqual(response.status_code, 200)
		suggestions = list(response.context["suggestions"])
		self.assertEqual(suggestions, [resolved])

	def test_superuser_can_mark_suggestion_as_resolved(self):
		suggestion = Suggestion.objects.create(user=self.user, message="Revisar colores")
		self.client.login(username="suggestion-admin", password="secret123")

		response = self.client.post(reverse("suggestion_resolve", args=[suggestion.id]))

		self.assertRedirects(response, reverse("suggestion_list"))
		suggestion.refresh_from_db()
		self.assertTrue(suggestion.is_resolved)


