from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from matches.models import Match
from stats.models import TopScorerStanding
from stats.services.group_standings import GroupStandingsService
from teams.models import Team


class GroupStandingsServiceTests(TestCase):

    def setUp(self):
        self.colombia = Team.objects.create(name="Colombia", code="COL", group_code="A")
        self.brasil = Team.objects.create(name="Brasil", code="BRA", group_code="A")
        self.peru = Team.objects.create(name="Perú", code="PER", group_code="A")
        self.ecuador = Team.objects.create(name="Ecuador", code="ECU", group_code="A")
        self.argentina = Team.objects.create(name="Argentina", code="ARG", group_code="B")

    def _match(self, home_team, away_team, home_score, away_score, *, finished=True, phase="PR"):
        return Match.objects.create(
            home_team=home_team,
            away_team=away_team,
            kickoff_at=timezone.now(),
            home_score=home_score,
            away_score=away_score,
            finished=finished,
            phase=phase,
        )

    def test_get_group_standings_calculates_table_from_finished_group_matches(self):
        self._match(self.colombia, self.brasil, 2, 0)
        self._match(self.colombia, self.peru, 1, 1)
        self._match(self.peru, self.ecuador, 3, 2)
        self._match(self.brasil, self.ecuador, 5, 0, phase="SR")
        self._match(self.colombia, self.brasil, 1, 0, phase="TR")
        self._match(self.brasil, self.ecuador, 5, 0, finished=False)
        self._match(self.colombia, self.argentina, 0, 4, phase="OF")

        standings = GroupStandingsService().get_group_standings()

        group_a = next(group for group in standings if group["code"] == "A")
        self.assertEqual(
            [row["team"].code for row in group_a["rows"]],
            ["COL", "PER", "BRA", "ECU"],
        )

        colombia_row = group_a["rows"][0]
        self.assertEqual(colombia_row["played"], 3)
        self.assertEqual(colombia_row["wins"], 2)
        self.assertEqual(colombia_row["draws"], 1)
        self.assertEqual(colombia_row["losses"], 0)
        self.assertEqual(colombia_row["goals_for"], 4)
        self.assertEqual(colombia_row["goals_against"], 1)
        self.assertEqual(colombia_row["goal_difference"], 3)
        self.assertEqual(colombia_row["points"], 7)

        argentina_row = next(group for group in standings if group["code"] == "B")["rows"][0]
        self.assertEqual(argentina_row["played"], 0)
        self.assertEqual(argentina_row["points"], 0)

    def test_get_group_standings_filters_by_group_and_country(self):
        self._match(self.colombia, self.brasil, 2, 0)
        self._match(self.peru, self.ecuador, 3, 2)

        group_a = GroupStandingsService().get_group_standings(group_code="A")
        colombia_only = GroupStandingsService().get_group_standings(country="COL")

        self.assertEqual([group["code"] for group in group_a], ["A"])
        self.assertEqual(len(colombia_only), 1)
        self.assertEqual(colombia_only[0]["code"], "A")
        self.assertEqual([row["team"].code for row in colombia_only[0]["rows"]], ["COL"])


class TopScorersViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="scorers-user", password="secret123")
        self.team = Team.objects.create(name="Colombia", code="COL", tla="COL", flag="https://crests.example/col.svg")

    def test_requires_login(self):
        response = self.client.get(reverse("top_scorers"))

        self.assertEqual(response.status_code, 302)

    def test_top_scorers_view_lists_persisted_standings(self):
        self.client.login(username="scorers-user", password="secret123")
        TopScorerStanding.objects.create(
            competition_code="WC",
            season=2026,
            rank=1,
            external_key="player:10",
            football_data_player_id=10,
            player_name="Luis Díaz",
            team=self.team,
            team_name="Colombia",
            team_tla="COL",
            played_matches=3,
            goals=4,
            assists=1,
            penalties=0,
        )

        response = self.client.get(reverse("top_scorers"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tabla de goleadores")
        self.assertContains(response, "Luis Díaz")
        self.assertContains(response, "Colombia")
        self.assertContains(response, "4")

    def test_sidebar_links_to_top_scorers(self):
        self.client.login(username="scorers-user", password="secret123")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("top_scorers"))
        self.assertContains(response, "Goleadores")


