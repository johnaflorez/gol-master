from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from matches.models import Match
from stats.models import TopScorerStanding
from stats.services.group_standings import GroupStandingsService
from stats.services.tournament_stats import TournamentStatsService
from teams.models import Player, Team


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


class TournamentStatsServiceTests(TestCase):

    def setUp(self):
        self.team_a = Team.objects.create(name="Equipo A", code="EQA")
        self.team_b = Team.objects.create(name="Equipo B", code="EQB")

    def _match(self, *, home_score, away_score, finished=True, phase="PR"):
        return Match.objects.create(
            home_team=self.team_a,
            away_team=self.team_b,
            kickoff_at=timezone.now(),
            home_score=home_score,
            away_score=away_score,
            finished=finished,
            phase=phase,
        )

    def test_get_stats_uses_finished_matches_totals(self):
        self._match(home_score=2, away_score=1)
        self._match(home_score=0, away_score=3)
        self._match(home_score=5, away_score=5, finished=False)

        stats = TournamentStatsService().get_stats()

        self.assertEqual(stats["total_matches"], 2)
        self.assertEqual(stats["total_goals"], 6)
        self.assertEqual(stats["avg_goals"], 3)

    def test_get_stats_includes_average_goals_by_phase(self):
        self._match(home_score=2, away_score=1, phase="PR")
        self._match(home_score=1, away_score=1, phase="PR")
        self._match(home_score=3, away_score=2, phase="DR")
        self._match(home_score=4, away_score=4, phase="OF", finished=False)

        stats = TournamentStatsService().get_stats()

        self.assertEqual([row["phase"] for row in stats["goals_by_phase"]], ["PR", "DR"])
        primera_ronda = stats["goals_by_phase"][0]
        dieciseisavos = stats["goals_by_phase"][1]

        self.assertEqual(primera_ronda["label"], "Primera Ronda")
        self.assertEqual(primera_ronda["matches"], 2)
        self.assertEqual(primera_ronda["total_goals"], 5)
        self.assertEqual(primera_ronda["avg_goals"], 2.5)

        self.assertEqual(dieciseisavos["label"], "Dieciséisavos de Final")
        self.assertEqual(dieciseisavos["matches"], 1)
        self.assertEqual(dieciseisavos["total_goals"], 5)
        self.assertEqual(dieciseisavos["avg_goals"], 5)


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

    def test_top_scorers_view_filters_by_player_and_country(self):
        self.client.login(username="scorers-user", password="secret123")
        brasil = Team.objects.create(name="Brasil", code="BRA", tla="BRA")
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
            goals=4,
        )
        TopScorerStanding.objects.create(
            competition_code="WC",
            season=2026,
            rank=2,
            external_key="player:11",
            football_data_player_id=11,
            player_name="Neymar",
            team=brasil,
            team_name="Brasil",
            team_tla="BRA",
            goals=3,
        )

        response = self.client.get(reverse("top_scorers"), {"player": "Luis", "country": "COL - Colombia"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Luis Díaz")
        self.assertContains(response, "Colombia")
        self.assertNotContains(response, "Neymar")
        self.assertEqual(response.context["selected_player"], "Luis")
        self.assertEqual(response.context["selected_country"], "COL")

    def test_top_scorers_view_filters_by_player_datalist_selection(self):
        self.client.login(username="scorers-user", password="secret123")
        brasil = Team.objects.create(name="Brasil", code="BRA", tla="BRA")
        player = Player.objects.create(
            team=self.team,
            name="Luis Díaz",
            football_data_player_id=10,
            position="Attacker",
            nationality="Colombia",
        )
        Player.objects.create(team=brasil, name="Neymar", football_data_player_id=11)
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
            goals=4,
        )
        TopScorerStanding.objects.create(
            competition_code="WC",
            season=2026,
            rank=2,
            external_key="player:11",
            football_data_player_id=11,
            player_name="Neymar",
            team=brasil,
            team_name="Brasil",
            team_tla="BRA",
            goals=3,
        )
        TopScorerStanding.objects.create(
            competition_code="WC",
            season=2026,
            rank=3,
            external_key="player:99",
            football_data_player_id=99,
            player_name="Luis Díaz",
            team=brasil,
            team_name="Brasil",
            team_tla="BRA",
            goals=2,
        )

        response = self.client.get(reverse("top_scorers"), {"player": "Luis Díaz - Colombia"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'list="scorer-player-options"')
        self.assertContains(response, 'value="Luis Díaz - Colombia"')
        self.assertContains(response, '<option value="Neymar - Brasil"></option>', html=True)
        self.assertContains(response, "Luis Díaz")
        self.assertContains(response, "Colombia")
        self.assertEqual([scorer.player_name for scorer in response.context["scorers"]], ["Luis Díaz"])
        self.assertEqual(response.context["selected_player_id"], player.id)
        self.assertEqual(response.context["selected_player"], "Luis Díaz")
        self.assertEqual(response.context["selected_player_label"], "Luis Díaz - Colombia")
        self.assertEqual(
            [option["label"] for option in response.context["player_options"]],
            ["Luis Díaz - Colombia", "Neymar - Brasil"],
        )

    def test_top_scorers_view_keeps_legacy_player_id_filter(self):
        self.client.login(username="scorers-user", password="secret123")
        player = Player.objects.create(team=self.team, name="Luis Díaz", football_data_player_id=10)
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
            goals=4,
        )

        response = self.client.get(reverse("top_scorers"), {"player_id": str(player.id)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([scorer.player_name for scorer in response.context["scorers"]], ["Luis Díaz"])
        self.assertEqual(response.context["selected_player_id"], player.id)
        self.assertEqual(response.context["selected_player_label"], "Luis Díaz - Colombia")
        self.assertContains(response, 'value="Luis Díaz - Colombia"')

    def test_top_scorers_view_paginates_and_preserves_filters(self):
        self.client.login(username="scorers-user", password="secret123")
        for index in range(55):
            TopScorerStanding.objects.create(
                competition_code="WC",
                season=2026,
                rank=index + 1,
                external_key=f"player:{index}",
                football_data_player_id=index,
                player_name=f"Jugador Colombia {index:02d}",
                team=self.team,
                team_name="Colombia",
                team_tla="COL",
                goals=max(0, 55 - index),
            )

        response = self.client.get(reverse("top_scorers"), {"player": "Jugador", "country": "COL"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(len(response.context["scorers"]), 50)
        self.assertContains(response, "Página 1 de 2")
        self.assertContains(response, "player=Jugador&amp;country=COL&amp;page=2")
        self.assertContains(response, "55 goleadores")

    def test_sidebar_links_to_top_scorers(self):
        self.client.login(username="scorers-user", password="secret123")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("top_scorers"))
        self.assertContains(response, "Goleadores")


