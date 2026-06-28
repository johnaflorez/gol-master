from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from matches.models import Match
from predictions.models import Prediction
from rankings.services.ranking_service import RankingService
from teams.models import Team


class RankingServiceTests(TestCase):

	def setUp(self):
		self.team_a = Team.objects.create(name="Equipo A", code="EQA")
		self.team_b = Team.objects.create(name="Equipo B", code="EQB")
		self.match = Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=timezone.now(),
			home_score=2,
			away_score=1,
			finished=True,
		)

	def _user_with_points(self, username, points, predicted_home_score=1, predicted_away_score=0):
		user = User.objects.create_user(username=username, password="secret123")
		Prediction.objects.create(
			user=user,
			match=self.match,
			predicted_home_score=predicted_home_score,
			predicted_away_score=predicted_away_score,
			points=points,
		)
		return user

	def test_get_ranking_can_limit_rows_before_materializing_result(self):
		best = self._user_with_points("best", 5)
		self._user_with_points("middle", 3)
		self._user_with_points("last", 1)

		ranking = RankingService().get_ranking(limit=1)

		self.assertEqual(len(ranking), 1)
		self.assertEqual(ranking[0]["user"], best)
		self.assertEqual(ranking[0]["points"], 5)

	def test_get_ranking_includes_points_from_total_score_hits(self):
		exact_user = self._user_with_points(
			"exact",
			5,
			predicted_home_score=2,
			predicted_away_score=1,
		)
		self._user_with_points("partial", 2, predicted_home_score=1, predicted_away_score=0)

		ranking = RankingService().get_ranking()
		exact_row = next(item for item in ranking if item["user"] == exact_user)

		self.assertEqual(exact_row["points"], 5)
		self.assertEqual(exact_row["exact_predictions"], 1)
		self.assertEqual(exact_row["exact_score_points"], 5)

	def test_get_ranking_uses_zero_points_when_user_has_no_total_score_hits(self):
		partial_user = self._user_with_points("partial", 2, predicted_home_score=1, predicted_away_score=0)

		ranking = RankingService().get_ranking()
		partial_row = next(item for item in ranking if item["user"] == partial_user)

		self.assertEqual(partial_row["exact_predictions"], 0)
		self.assertEqual(partial_row["exact_score_points"], 0)

	def test_ranking_page_shows_total_score_hit_points(self):
		self._user_with_points(
			"exact",
			5,
			predicted_home_score=2,
			predicted_away_score=1,
		)

		response = self.client.get(reverse("ranking"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Pts aciertos totales")
		self.assertContains(response, "1 exactos")

