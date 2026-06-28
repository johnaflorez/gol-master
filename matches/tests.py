import json
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from matches.admin import MatchAdmin
from matches.models import Match
from matches.services.football_data import (
    FootballDataClient,
    FootballDataPlayersImportService,
    FootballDataSyncResult,
    FootballDataSyncService,
    FootballDataTopScorersService,
)
from matches.services.knockout_bracket import KnockoutAdvancementService
from stats.models import TopScorerStanding
from teams.models import Player, Team


class MatchListViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="secret123")
        self.client.login(username="tester", password="secret123")

        self.team_a = Team.objects.create(name="Team A", code="TMA", country_code="CO")
        self.team_b = Team.objects.create(name="Team B", code="TMB", country_code="BR")

    def _create_match(self, *, kickoff_at, finished=False, phase="PR", home_team=None, away_team=None):
        return Match.objects.create(
            home_team=home_team or self.team_a,
            away_team=away_team or self.team_b,
            kickoff_at=kickoff_at,
            finished=finished,
            phase=phase,
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

    def test_match_list_shows_all_matches_grouped_without_pagination(self):
        now = timezone.now()
        for index in range(11):
            self._create_match(kickoff_at=now + timedelta(minutes=index))

        response = self.client.get(reverse("match_list"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_paginated"])
        self.assertEqual(len(response.context["matches"]), 11)
        self.assertEqual(response.context["matches_count"], 11)

    def test_match_list_shows_en_juego_when_kickoff_has_passed(self):
        self._create_match(kickoff_at=timezone.now() - timedelta(minutes=10), finished=False)

        response = self.client.get(reverse("match_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "En juego")

    def test_match_list_shows_tabs_grouped_by_phase(self):
        self._create_match(kickoff_at=timezone.now() + timedelta(hours=1), phase="PR")
        self._create_match(kickoff_at=timezone.now() + timedelta(hours=2), phase="F")

        response = self.client.get(reverse("match_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primera Ronda")
        self.assertContains(response, "Final")
        self.assertContains(response, "text-bg-secondary")
        self.assertContains(response, "text-bg-warning")

    def test_match_list_shows_phases_even_after_ten_matches(self):
        now = timezone.now()
        for index in range(11):
            self._create_match(kickoff_at=now + timedelta(minutes=index), phase="PR")
        self._create_match(kickoff_at=now - timedelta(days=1), phase="F")

        response = self.client.get(reverse("match_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primera Ronda")
        self.assertContains(response, "Final")

    def test_match_list_filters_by_country(self):
        team_c = Team.objects.create(name="Team C", code="TMC", country_code="AR")
        team_d = Team.objects.create(name="Team D", code="TMD", country_code="UY")

        match_co = self._create_match(
            kickoff_at=timezone.now() + timedelta(hours=1),
            home_team=self.team_a,
            away_team=team_d,
        )
        self._create_match(
            kickoff_at=timezone.now() + timedelta(hours=2),
            home_team=team_c,
            away_team=team_d,
        )

        response = self.client.get(reverse("match_list"), {"country": "CO"})

        self.assertEqual(response.status_code, 200)
        matches = list(response.context["matches"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, match_co.id)

    def test_match_list_country_filter_uses_team_code_when_country_code_is_empty(self):
        colombia = Team.objects.create(name="Colombia", code="COL", country_code="")
        brasil = Team.objects.create(name="Brasil", code="BRA", country_code="")
        argentina = Team.objects.create(name="Argentina", code="ARG", country_code="AR")

        match_col = self._create_match(
            kickoff_at=timezone.now() + timedelta(hours=1),
            home_team=colombia,
            away_team=brasil,
        )
        self._create_match(
            kickoff_at=timezone.now() + timedelta(hours=2),
            home_team=argentina,
            away_team=brasil,
        )

        response = self.client.get(reverse("match_list"), {"country": "COL - Colombia"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'list="country-options"')
        self.assertContains(response, "COL - Colombia")
        matches = list(response.context["matches"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, match_col.id)

    def test_match_list_keeps_selected_country_filter_visible(self):
        now = timezone.now()
        for index in range(11):
            self._create_match(kickoff_at=now + timedelta(minutes=index), phase="PR")

        response = self.client.get(reverse("match_list"), {"country": "CO"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="CO"')

    def test_match_list_links_to_group_standings(self):
        self.team_a.group_code = "A"
        self.team_a.save(update_fields=["group_code"])
        self.team_b.group_code = "A"
        self.team_b.save(update_fields=["group_code"])
        Match.objects.create(
            home_team=self.team_a,
            away_team=self.team_b,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=2,
            away_score=1,
            finished=True,
            phase="PR",
        )

        response = self.client.get(reverse("match_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tabla de grupos")
        self.assertContains(response, reverse("group_standings"))
        self.assertContains(response, "Ver tabla de grupos")
        self.assertNotContains(response, "Consulta J, G, E, P, GF, GC, DIF y PTS en una vista dedicada.")
        self.assertNotContains(response, "Grupo A")
        self.assertNotContains(response, "Selecci&oacute;n")

    def test_match_list_links_to_knockout_bracket(self):
        response = self.client.get(reverse("match_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Esquema de clasificación")
        self.assertContains(response, reverse("knockout_bracket"))
        self.assertContains(response, "Ver eliminatorias")

    def test_group_standings_view_shows_table(self):
        self.team_a.group_code = "A"
        self.team_a.save(update_fields=["group_code"])
        self.team_b.group_code = "A"
        self.team_b.save(update_fields=["group_code"])
        Match.objects.create(
            home_team=self.team_a,
            away_team=self.team_b,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=2,
            away_score=1,
            finished=True,
            phase="PR",
        )

        response = self.client.get(reverse("group_standings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tabla de grupos")
        self.assertContains(response, "primera, segunda y tercera ronda")
        self.assertContains(response, 'name="group"')
        self.assertContains(response, 'name="country"')
        self.assertContains(response, "group-standings-col-team")
        self.assertContains(response, "group-standings-col-stat")
        self.assertContains(response, "group-standings-scroll-hint")
        self.assertContains(response, "Desliza para ver toda la tabla")
        self.assertContains(response, "fa-arrows-left-right")
        self.assertNotContains(response, "group-standings-scroll-shell")
        self.assertNotContains(response, "group-standings-table-wrap")
        self.assertNotContains(response, "group-standing-sticky-cell")
        self.assertContains(response, "Grupo A")
        self.assertContains(response, "Selecci&oacute;n")
        self.assertContains(response, "Team A")
        self.assertContains(response, "Team B")
        self.assertContains(response, "J")
        self.assertContains(response, "G")
        self.assertContains(response, "E")
        self.assertContains(response, "P")
        self.assertContains(response, "GF")
        self.assertContains(response, "GC")
        self.assertContains(response, "DIF")
        self.assertContains(response, "PTS")
        self.assertContains(response, "+1")
        self.assertEqual(response.context["group_standings"][0]["rows"][0]["points"], 3)

    def test_group_standings_view_filters_by_group_and_country(self):
        self.team_a.group_code = "A"
        self.team_a.save(update_fields=["group_code"])
        self.team_b.group_code = "A"
        self.team_b.save(update_fields=["group_code"])
        team_c = Team.objects.create(name="Team C", code="TMC", country_code="AR", group_code="B")
        team_d = Team.objects.create(name="Team D", code="TMD", country_code="UY", group_code="B")
        francia = Team.objects.create(name="Francia", code="FRA", country_code="FR", group_code="B")
        Match.objects.create(
            home_team=self.team_a,
            away_team=self.team_b,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=2,
            away_score=1,
            finished=True,
            phase="SR",
        )
        Match.objects.create(
            home_team=team_c,
            away_team=team_d,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=0,
            away_score=0,
            finished=True,
            phase="TR",
        )
        Match.objects.create(
            home_team=francia,
            away_team=team_d,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=3,
            away_score=1,
            finished=True,
            phase="PR",
        )

        response = self.client.get(reverse("group_standings"), {"group": "B", "country": "AR"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grupo B")
        self.assertContains(response, "Team C")
        self.assertNotContains(response, "standing-title-A")
        self.assertEqual(response.context["selected_group"], "B")
        self.assertEqual(response.context["selected_country"], "AR")
        self.assertEqual(len(response.context["group_standings"]), 1)
        self.assertEqual(response.context["group_standings"][0]["code"], "B")
        self.assertEqual(
            [row["team"].code for row in response.context["group_standings"][0]["rows"]],
            ["TMC"],
        )

        response_by_name = self.client.get(reverse("group_standings"), {"country": "Francia"})

        self.assertEqual(response_by_name.status_code, 200)
        self.assertContains(response_by_name, 'value="FRA - Francia"')
        self.assertContains(response_by_name, "Francia")
        self.assertEqual(response_by_name.context["selected_country"], "FRA")
        self.assertEqual(
            [row["team"].code for row in response_by_name.context["group_standings"][0]["rows"]],
            ["FRA"],
        )


class MatchAdminTests(TestCase):

    def setUp(self):
        self.team_a = Team.objects.create(name="Equipo A", code="EQA")
        self.team_b = Team.objects.create(name="Equipo B", code="EQB")
        self.admin = MatchAdmin(Match, AdminSite())
        self.request = RequestFactory().get("/admin/matches/match/")

    def _match(self, *, phase, bracket_position=None, kickoff_at=None):
        return Match.objects.create(
            home_team=self.team_a,
            away_team=self.team_b,
            kickoff_at=kickoff_at or timezone.now(),
            phase=phase,
            bracket_position=bracket_position,
        )

    def test_admin_orders_matches_by_most_advanced_phase_first(self):
        first_round = self._match(phase="PR")
        semifinal = self._match(phase="SF")
        last_32 = self._match(phase="DR")
        final = self._match(phase="F")
        quarter_final = self._match(phase="CF")

        matches = list(self.admin.get_queryset(self.request))

        self.assertEqual(matches, [final, semifinal, quarter_final, last_32, first_round])


class KnockoutBracketViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="bracket-user", password="secret123")
        self.colombia = Team.objects.create(name="Colombia", code="COL", tla="COL", flag="https://crests.example/col.svg")
        self.brasil = Team.objects.create(name="Brasil", code="BRA", tla="BRA", flag="https://crests.example/bra.svg")
        self.argentina = Team.objects.create(name="Argentina", code="ARG", tla="ARG")
        self.uruguay = Team.objects.create(name="Uruguay", code="URY", tla="URU")

    def test_requires_login(self):
        response = self.client.get(reverse("knockout_bracket"))

        self.assertEqual(response.status_code, 302)

    def test_knockout_bracket_lists_phases_matches_winners_and_placeholders(self):
        self.client.login(username="bracket-user", password="secret123")
        Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=2,
            away_score=1,
            finished=True,
            phase="DR",
        )
        Match.objects.create(
            home_team=self.argentina,
            away_team=self.uruguay,
            kickoff_at=timezone.now() + timedelta(days=1),
            phase="OF",
        )

        response = self.client.get(reverse("knockout_bracket"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Esquema de clasificación")
        self.assertContains(response, "16avos")
        self.assertContains(response, "Octavos")
        self.assertContains(response, "Cuartos")
        self.assertContains(response, "Semis")
        self.assertContains(response, "Final")
        self.assertContains(response, "Colombia")
        self.assertContains(response, "Brasil")
        self.assertContains(response, "knockout-team-short")
        self.assertContains(response, "COL")
        self.assertContains(response, "2")
        self.assertContains(response, "Clasifica Colombia")
        self.assertContains(response, "Partido pendiente por cargar")
        self.assertNotContains(response, "knockout-scroll-hint")

        bracket = response.context["bracket"]
        self.assertTrue(bracket["has_matches"])
        self.assertEqual(bracket["total_matches"], 2)
        self.assertEqual([phase["code"] for phase in bracket["phases"]], ["DR", "OF", "CF", "SF", "F"])
        self.assertEqual(
            [column["code"] for column in bracket["layout_columns"]],
            ["DR", "OF", "CF", "SF", "F", "SF", "CF", "OF", "DR"],
        )
        self.assertEqual([column["side"] for column in bracket["layout_columns"]], ["left", "left", "left", "left", "center", "right", "right", "right", "right"])
        self.assertEqual(bracket["layout_columns"][4]["short_label"], "Final")
        self.assertEqual(len(bracket["phases"][0]["slots"]), 16)
        self.assertEqual(len(bracket["layout_columns"][0]["slots"]), 8)
        self.assertEqual(len(bracket["layout_columns"][-1]["slots"]), 8)
        self.assertEqual(bracket["phases"][0]["slots"][0]["winner_team"], self.colombia)

    def test_knockout_bracket_uses_bracket_position_before_kickoff_order(self):
        self.client.login(username="bracket-user", password="secret123")
        later_but_first_slot = Match.objects.create(
            home_team=self.argentina,
            away_team=self.uruguay,
            kickoff_at=timezone.now() + timedelta(days=2),
            phase="DR",
            bracket_position=1,
        )
        earlier_but_second_slot = Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() + timedelta(days=1),
            phase="DR",
            bracket_position=2,
        )

        response = self.client.get(reverse("knockout_bracket"))

        dr_slots = response.context["bracket"]["phases"][0]["slots"]
        self.assertEqual(dr_slots[0]["position"], 1)
        self.assertEqual(dr_slots[0]["match"], later_but_first_slot)
        self.assertEqual(dr_slots[1]["position"], 2)
        self.assertEqual(dr_slots[1]["match"], earlier_but_second_slot)

    def test_knockout_bracket_places_match_in_exact_bracket_position(self):
        self.client.login(username="bracket-user", password="secret123")
        ninth_slot_match = Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() + timedelta(days=1),
            phase="DR",
            bracket_position=9,
        )

        response = self.client.get(reverse("knockout_bracket"))

        dr_slots = response.context["bracket"]["phases"][0]["slots"]
        self.assertIsNone(dr_slots[0]["match"])
        self.assertEqual(dr_slots[8]["position"], 9)
        self.assertEqual(dr_slots[8]["match"], ninth_slot_match)

    def test_knockout_bracket_projects_single_winner_into_empty_next_round_slot(self):
        self.client.login(username="bracket-user", password="secret123")
        Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=2,
            away_score=1,
            finished=True,
            phase="DR",
            bracket_position=1,
        )

        response = self.client.get(reverse("knockout_bracket"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clasificado proyectado")
        self.assertNotContains(response, "16avos 1")
        of_slot = response.context["bracket"]["phases"][1]["slots"][0]
        self.assertIsNone(of_slot["match"])
        self.assertEqual(of_slot["status_label"], "Parcial")
        self.assertEqual([row["team"] for row in of_slot["projected_rows"]], [self.colombia])
        self.assertEqual([row["source_position"] for row in of_slot["projected_rows"]], [1])

    def test_finishing_adjacent_knockout_matches_creates_next_round_match(self):
        first_source = Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=2,
            away_score=1,
            finished=True,
            phase="DR",
            bracket_position=1,
        )

        self.assertFalse(Match.objects.filter(phase="OF", bracket_position=1).exists())

        Match.objects.create(
            home_team=self.argentina,
            away_team=self.uruguay,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=0,
            away_score=1,
            finished=True,
            phase="DR",
            bracket_position=2,
        )

        next_match = Match.objects.get(phase="OF", bracket_position=1)
        self.assertEqual(next_match.home_team, self.colombia)
        self.assertEqual(next_match.away_team, self.uruguay)
        self.assertFalse(next_match.finished)
        self.assertEqual(next_match.live_status, "NS")
        self.assertIsNone(next_match.football_data_match_id)
        self.assertGreater(next_match.kickoff_at, first_source.kickoff_at)

    def test_knockout_advancement_is_idempotent_when_next_match_exists(self):
        first_source = Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=2,
            away_score=1,
            finished=True,
            phase="DR",
            bracket_position=1,
        )
        Match.objects.create(
            home_team=self.argentina,
            away_team=self.uruguay,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=0,
            away_score=1,
            finished=True,
            phase="DR",
            bracket_position=2,
        )

        self.assertEqual(Match.objects.filter(phase="OF", bracket_position=1).count(), 1)

        KnockoutAdvancementService().create_next_round_match_if_ready(first_source)

        self.assertEqual(Match.objects.filter(phase="OF", bracket_position=1).count(), 1)

    def test_knockout_advancement_ignores_tied_finished_match_without_winner(self):
        Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=1,
            away_score=1,
            finished=True,
            phase="DR",
            bracket_position=1,
        )
        Match.objects.create(
            home_team=self.argentina,
            away_team=self.uruguay,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=0,
            away_score=1,
            finished=True,
            phase="DR",
            bracket_position=2,
        )

        self.assertFalse(Match.objects.filter(phase="OF", bracket_position=1).exists())

    def test_knockout_advancement_uses_penalty_winner_for_tied_match(self):
        Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=1,
            away_score=1,
            home_penalty_score=4,
            away_penalty_score=3,
            football_data_winner="HOME_TEAM",
            finished=True,
            phase="DR",
            bracket_position=1,
        )
        Match.objects.create(
            home_team=self.argentina,
            away_team=self.uruguay,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=0,
            away_score=1,
            finished=True,
            phase="DR",
            bracket_position=2,
        )

        next_match = Match.objects.get(phase="OF", bracket_position=1)
        self.assertEqual(next_match.home_team, self.colombia)
        self.assertEqual(next_match.away_team, self.uruguay)

    def test_knockout_bracket_displays_penalty_score(self):
        self.client.login(username="bracket-user", password="secret123")
        Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=1,
            away_score=1,
            home_penalty_score=4,
            away_penalty_score=3,
            football_data_winner="HOME_TEAM",
            finished=True,
            phase="DR",
            bracket_position=1,
        )

        response = self.client.get(reverse("knockout_bracket"))

        self.assertContains(response, "Pen. 4-3")
        self.assertContains(response, "Clasifica Colombia")

    def test_knockout_bracket_view_materializes_existing_ready_pair_without_signals(self):
        self.client.login(username="bracket-user", password="secret123")
        kickoff_at = timezone.now() - timedelta(days=1)
        Match.objects.bulk_create(
            [
                Match(
                    home_team=self.colombia,
                    away_team=self.brasil,
                    kickoff_at=kickoff_at,
                    home_score=2,
                    away_score=1,
                    finished=True,
                    phase="DR",
                    bracket_position=1,
                ),
                Match(
                    home_team=self.argentina,
                    away_team=self.uruguay,
                    kickoff_at=kickoff_at,
                    home_score=0,
                    away_score=1,
                    finished=True,
                    phase="DR",
                    bracket_position=2,
                ),
            ]
        )

        response = self.client.get(reverse("knockout_bracket"))

        self.assertEqual(response.status_code, 200)
        next_match = Match.objects.get(phase="OF", bracket_position=1)
        self.assertEqual(next_match.home_team, self.colombia)
        self.assertEqual(next_match.away_team, self.uruguay)
        self.assertEqual(response.context["bracket"]["phases"][1]["slots"][0]["match"], next_match)

    def test_knockout_bracket_does_not_project_when_next_round_match_exists(self):
        self.client.login(username="bracket-user", password="secret123")
        Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() - timedelta(days=1),
            home_score=2,
            away_score=1,
            finished=True,
            phase="DR",
            bracket_position=1,
        )
        next_match = Match.objects.create(
            home_team=self.argentina,
            away_team=self.uruguay,
            kickoff_at=timezone.now() + timedelta(days=1),
            phase="OF",
            bracket_position=1,
        )

        response = self.client.get(reverse("knockout_bracket"))

        of_slot = response.context["bracket"]["phases"][1]["slots"][0]
        self.assertEqual(of_slot["match"], next_match)
        self.assertEqual(of_slot["projected_rows"], [])

    def test_knockout_bracket_shows_empty_schema_when_no_matches_exist(self):
        self.client.login(username="bracket-user", password="secret123")

        response = self.client.get(reverse("knockout_bracket"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0 partidos cargados")
        self.assertContains(response, "Aún no hay partidos de eliminatorias cargados")
        self.assertFalse(response.context["bracket"]["has_matches"])

    def test_sidebar_links_to_knockout_bracket(self):
        self.client.login(username="bracket-user", password="secret123")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("knockout_bracket"))
        self.assertContains(response, "Clasificación")


class MatchFinishedAtTests(TestCase):

    def setUp(self):
        self.team_a = Team.objects.create(name="Equipo A", code="EQA")
        self.team_b = Team.objects.create(name="Equipo B", code="EQB")

    def _match(self, *, finished=False):
        return Match.objects.create(
            home_team=self.team_a,
            away_team=self.team_b,
            kickoff_at=timezone.now(),
            finished=finished,
        )

    def test_finished_at_is_set_when_match_transitions_to_finished(self):
        match = self._match(finished=False)
        self.assertIsNone(match.finished_at)

        match.finished = True
        match.save()

        match.refresh_from_db()
        self.assertIsNotNone(match.finished_at)

    def test_finished_at_is_not_reset_when_finished_match_is_saved_again(self):
        match = self._match(finished=True)
        original_finished_at = match.finished_at

        match.home_score = 2
        match.save()

        match.refresh_from_db()
        self.assertEqual(match.finished_at, original_finished_at)

    def test_finished_at_is_cleared_when_match_is_unfinished(self):
        match = self._match(finished=True)

        match.finished = False
        match.save()

        match.refresh_from_db()
        self.assertIsNone(match.finished_at)


class FakeFootballDataClient:
    def __init__(self, fixture, scorers=None):
        self.fixture = fixture
        self.scorers = scorers if scorers is not None else []

    def get_match(self, match_id):
        return self.fixture

    def get_scorers(self, *, competition_code=None, season=None, limit=None):
        return self.scorers[:limit] if limit else self.scorers


class FakeFootballDataListClient:
    fixtures = []
    calls = []

    def __init__(self):
        pass

    def get_matches(self, *, date_from=None, date_to=None, status=None):
        self.__class__.calls.append({"date_from": date_from, "date_to": date_to, "status": status})
        return self.__class__.fixtures

    def get_competition_matches(
        self,
        *,
        competition_code=None,
        season=None,
        date_from=None,
        date_to=None,
        status=None,
        stage=None,
    ):
        self.__class__.calls.append(
            {
                "competition_code": competition_code,
                "season": season,
                "date_from": date_from,
                "date_to": date_to,
                "status": status,
                "stage": stage,
            }
        )
        return self.__class__.fixtures


class FakeFootballDataTeamsClient:
    teams = []
    details = {}
    calls = []

    def get_competition_teams(self, *, competition_code=None, season=None):
        self.__class__.calls.append({"competition_code": competition_code, "season": season})
        return self.__class__.teams

    def get_team(self, team_id):
        return self.__class__.details.get(team_id, {})


class FootballDataSyncServiceTests(TestCase):

    def setUp(self):
        self.team_a = Team.objects.create(name="Colombia", code="COL")
        self.team_b = Team.objects.create(name="Brasil", code="BRA")

    def _match(self, *, match_id=12345):
        return Match.objects.create(
            home_team=self.team_a,
            away_team=self.team_b,
            kickoff_at=timezone.now(),
            football_data_match_id=match_id,
        )

    def test_sync_match_updates_scores_status_and_team_ids(self):
        match = self._match()
        fixture = {
            "id": 12345,
            "status": "IN_PLAY",
            "homeTeam": {"id": 100, "name": "Colombia", "tla": "COL", "crest": "https://crests.example/col.svg"},
            "awayTeam": {"id": 200, "name": "Brasil", "tla": "BRA", "crest": "https://crests.example/bra.svg"},
            "score": {"fullTime": {"home": 1, "away": 0}},
        }

        service = FootballDataSyncService(client=FakeFootballDataClient(fixture))
        result = service.sync_match(match)

        match.refresh_from_db()
        self.team_a.refresh_from_db()
        self.team_b.refresh_from_db()

        self.assertEqual(result.checked, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(match.live_status, "LIVE")
        self.assertFalse(match.finished)
        self.assertEqual(match.home_score, 1)
        self.assertEqual(match.away_score, 0)
        self.assertEqual(self.team_a.football_data_team_id, 100)
        self.assertEqual(self.team_b.football_data_team_id, 200)
        self.assertEqual(self.team_a.tla, "COL")
        self.assertEqual(self.team_b.tla, "BRA")
        self.assertEqual(self.team_a.flag, "https://crests.example/col.svg")
        self.assertEqual(self.team_b.flag, "https://crests.example/bra.svg")

    def test_sync_match_marks_finished(self):
        match = self._match()
        fixture = {
            "id": 12345,
            "status": "FINISHED",
            "homeTeam": {},
            "awayTeam": {},
            "score": {"fullTime": {"home": 2, "away": 1}},
        }

        service = FootballDataSyncService(client=FakeFootballDataClient(fixture))
        service.sync_match(match)

        match.refresh_from_db()
        self.assertEqual(match.live_status, "FT")
        self.assertTrue(match.finished)
        self.assertEqual(match.home_score, 2)
        self.assertEqual(match.away_score, 1)

    def test_sync_match_updates_penalties_and_api_winner(self):
        match = self._match()
        fixture = {
            "id": 12345,
            "status": "FINISHED",
            "homeTeam": {},
            "awayTeam": {},
            "score": {
                "winner": "HOME_TEAM",
                "fullTime": {"home": 1, "away": 1},
                "penalties": {"home": 4, "away": 3},
            },
        }

        FootballDataSyncService(client=FakeFootballDataClient(fixture)).sync_match(match)

        match.refresh_from_db()
        self.assertEqual(match.home_score, 1)
        self.assertEqual(match.away_score, 1)
        self.assertEqual(match.home_penalty_score, 4)
        self.assertEqual(match.away_penalty_score, 3)
        self.assertEqual(match.football_data_winner, "HOME_TEAM")
        self.assertEqual(match.winner_team, self.team_a)
        self.assertEqual(match.score_display, "1 - 1 (4 - 3 pen.)")

    def test_sync_match_finishes_match_and_sets_finished_at_from_football_data(self):
        match = self._match()
        self.assertIsNone(match.finished_at)
        fixture = {
            "id": 12345,
            "status": "finished",
            "homeTeam": {},
            "awayTeam": {},
            "score": {"fullTime": {"home": 0, "away": 0}},
        }

        service = FootballDataSyncService(client=FakeFootballDataClient(fixture))
        result = service.sync_match(match)

        match.refresh_from_db()
        self.assertEqual(result.updated, 1)
        self.assertEqual(match.live_status, "FT")
        self.assertTrue(match.finished)
        self.assertIsNotNone(match.finished_at)
        self.assertEqual(match.home_score, 0)
        self.assertEqual(match.away_score, 0)

    def test_sync_match_updates_score_from_regular_time_when_full_time_is_empty(self):
        match = self._match()
        fixture = {
            "id": 12345,
            "status": "IN_PLAY",
            "homeTeam": {},
            "awayTeam": {},
            "score": {
                "fullTime": {"home": None, "away": None},
                "regularTime": {"home": 3, "away": 2},
            },
        }

        FootballDataSyncService(client=FakeFootballDataClient(fixture)).sync_match(match)

        match.refresh_from_db()
        self.assertEqual(match.live_status, "LIVE")
        self.assertFalse(match.finished)
        self.assertEqual(match.home_score, 3)
        self.assertEqual(match.away_score, 2)

    def test_sync_match_refreshes_top_scorers_when_score_changes(self):
        self.team_a.tla = "COL"
        self.team_a.save(update_fields=["tla"])
        Player.objects.create(team=self.team_a, name="Luis Díaz")
        match = self._match()
        fixture = {
            "id": 12345,
            "status": "IN_PLAY",
            "homeTeam": {"id": 100, "name": "Colombia", "tla": "COL", "crest": "https://crests.example/col.svg"},
            "awayTeam": {},
            "score": {"fullTime": {"home": 1, "away": 0}},
        }
        scorers = [
            {
                "player": {"id": 10, "name": "Luis Díaz"},
                "team": {"id": 100, "name": "Colombia", "tla": "COL", "crest": "https://crests.example/col.svg"},
                "playedMatches": 1,
                "goals": 2,
                "assists": 1,
                "penalties": 0,
            }
        ]

        result = FootballDataSyncService(client=FakeFootballDataClient(fixture, scorers=scorers)).sync_match(match)

        standing = TopScorerStanding.objects.get(football_data_player_id=10)
        self.assertTrue(result.scorers_refreshed)
        self.assertEqual(standing.player_name, "Luis Díaz")
        self.assertEqual(standing.team, self.team_a)
        self.assertEqual(standing.goals, 2)
        self.assertEqual(standing.assists, 1)

    def test_sync_match_skips_without_football_data_match_id(self):
        match = self._match(match_id=None)
        service = FootballDataSyncService(client=FakeFootballDataClient({}))

        result = service.sync_match(match)

        self.assertEqual(result.skipped, 1)

    def test_sync_queryset_from_match_list_updates_with_single_list_request(self):
        match = self._match(match_id=12345)
        missing_from_response = self._match(match_id=99999)
        FakeFootballDataListClient.fixtures = [
            {
                "id": 12345,
                "status": "IN_PLAY",
                "homeTeam": {"id": 100, "name": "Colombia", "tla": "COL", "crest": "https://crests.example/col.svg"},
                "awayTeam": {},
                "score": {"fullTime": {"home": 1, "away": 0}},
            }
        ]
        FakeFootballDataListClient.calls = []

        result = FootballDataSyncService(client=FakeFootballDataListClient()).sync_queryset_from_match_list(
            Match.objects.filter(pk__in=[match.pk, missing_from_response.pk]).order_by("pk"),
            date_from=timezone.localdate(),
            date_to=timezone.localdate(),
            refresh_scorers=False,
        )

        match.refresh_from_db()
        missing_from_response.refresh_from_db()
        self.assertEqual(len(FakeFootballDataListClient.calls), 1)
        self.assertEqual(result.checked, 2)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(match.live_status, "LIVE")
        self.assertEqual(match.home_score, 1)
        self.assertEqual(missing_from_response.home_score, 0)

    def test_top_scorers_refresh_upserts_and_deletes_stale_rows(self):
        self.team_a.football_data_team_id = 100
        self.team_a.tla = "COL"
        self.team_a.save(update_fields=["football_data_team_id", "tla"])
        stale = TopScorerStanding.objects.create(
            competition_code="WC",
            season=2026,
            rank=1,
            external_key="player:999",
            football_data_player_id=999,
            player_name="Jugador viejo",
            team_name="Viejo",
            goals=1,
        )
        scorers = [
            {
                "player": {"id": 10, "name": "Luis Díaz"},
                "team": {"id": 100, "name": "Colombia", "tla": "COL", "crest": "https://crests.example/col.svg"},
                "playedMatches": 3,
                "goals": 4,
                "assists": None,
                "penalties": 1,
            }
        ]

        result = FootballDataTopScorersService(client=FakeFootballDataClient({}, scorers=scorers)).refresh()

        self.assertEqual(result.checked, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.deleted, 1)
        self.assertFalse(TopScorerStanding.objects.filter(pk=stale.pk).exists())
        standing = TopScorerStanding.objects.get(football_data_player_id=10)
        self.assertEqual(standing.rank, 1)
        self.assertEqual(standing.player_name, "Luis Díaz")
        self.assertEqual(standing.team, self.team_a)
        self.assertEqual(standing.team_tla, "COL")
        self.assertEqual(standing.goals, 4)
        self.assertEqual(standing.penalties, 1)


class SyncFootballDataCommandTests(TestCase):

    @override_settings(FOOTBALL_DATA_SCORERS_LIMIT=500)
    def test_football_data_client_requests_configured_scorers_limit_by_default(self):
        client = FootballDataClient(token="token", base_url="https://example.test", timeout=1)
        calls = []

        def fake_request(path, params=None):
            calls.append({"path": path, "params": params})
            return {"scorers": []}

        client._request = fake_request

        client.get_scorers(competition_code="WC", season=2026)

        self.assertEqual(calls[0]["path"], "competitions/WC/scorers")
        self.assertEqual(calls[0]["params"]["season"], 2026)
        self.assertEqual(calls[0]["params"]["limit"], 500)

    def test_football_data_client_preserves_explicit_scorers_limit(self):
        client = FootballDataClient(token="token", base_url="https://example.test", timeout=1)
        calls = []

        def fake_request(path, params=None):
            calls.append({"path": path, "params": params})
            return {"scorers": []}

        client._request = fake_request

        client.get_scorers(competition_code="WC", season=2026, limit=50)

        self.assertEqual(calls[0]["params"]["limit"], 50)

    def test_football_data_client_requests_competition_teams(self):
        client = FootballDataClient(token="token", base_url="https://example.test", timeout=1)
        calls = []

        def fake_request(path, params=None):
            calls.append({"path": path, "params": params})
            return {"teams": []}

        client._request = fake_request

        client.get_competition_teams(competition_code="WC", season=2026)

        self.assertEqual(calls[0]["path"], "competitions/WC/teams")
        self.assertEqual(calls[0]["params"]["season"], 2026)

    def test_football_data_players_service_dry_run_does_not_create_players(self):
        Team.objects.create(name="Colombia", code="COL", tla="COL", football_data_team_id=100)
        FakeFootballDataTeamsClient.teams = [
            {
                "id": 100,
                "name": "Colombia",
                "tla": "COL",
                "squad": [{"id": 10, "name": "Luis Díaz", "position": "Offence", "dateOfBirth": "1997-01-13", "nationality": "Colombia"}],
            }
        ]
        service = FootballDataPlayersImportService(client=FakeFootballDataTeamsClient())

        result = service.import_players(commit=False)

        self.assertEqual(result.checked_teams, 1)
        self.assertEqual(result.matched_teams, 1)
        self.assertEqual(result.created, 1)
        self.assertFalse(Player.objects.exists())

    def test_football_data_players_service_commit_upserts_player_and_team(self):
        colombia = Team.objects.create(name="Colombia", code="COL", tla="COL")
        FakeFootballDataTeamsClient.teams = [
            {
                "id": 100,
                "name": "Colombia",
                "tla": "COL",
                "crest": "https://crests.example/col.svg",
                "squad": [{"id": 10, "name": "Luis Díaz", "position": "Offence", "dateOfBirth": "1997-01-13", "nationality": "Colombia"}],
            }
        ]

        result = FootballDataPlayersImportService(client=FakeFootballDataTeamsClient()).import_players(commit=True)

        player = Player.objects.get(football_data_player_id=10)
        colombia.refresh_from_db()
        self.assertEqual(result.created, 1)
        self.assertEqual(player.team, colombia)
        self.assertEqual(player.name, "Luis Díaz")
        self.assertEqual(player.position, "Offence")
        self.assertEqual(player.date_of_birth.isoformat(), "1997-01-13")
        self.assertEqual(player.nationality, "Colombia")
        self.assertTrue(player.active)
        self.assertEqual(colombia.football_data_team_id, 100)
        self.assertEqual(colombia.flag, "https://crests.example/col.svg")

    def test_football_data_players_service_fetches_team_detail_when_squad_is_missing(self):
        Team.objects.create(name="Brasil", code="BRA", tla="BRA", football_data_team_id=200)
        FakeFootballDataTeamsClient.teams = [{"id": 200, "name": "Brazil", "tla": "BRA"}]
        FakeFootballDataTeamsClient.details = {
            200: {"id": 200, "name": "Brazil", "tla": "BRA", "squad": [{"id": 20, "name": "Vinicius Jr"}]}
        }

        result = FootballDataPlayersImportService(client=FakeFootballDataTeamsClient()).import_players(commit=True)

        self.assertEqual(result.detail_fetches, 1)
        self.assertTrue(Player.objects.filter(name="Vinicius Jr", football_data_player_id=20).exists())

    @patch("matches.management.commands.sync_football_data.FootballDataSyncService")
    def test_command_prints_sync_summary(self, service_cls):
        service_cls.return_value.sync_queryset.return_value = FootballDataSyncResult(checked=1, updated=1)
        out = StringIO()

        call_command("sync_football_data", "--live", stdout=out)

        self.assertIn("football-data.org sync OK", out.getvalue())
        self.assertIn("checked=1", out.getvalue())

    @patch("matches.management.commands.sync_football_data.FootballDataSyncService")
    def test_command_prints_scorer_refresh_summary(self, service_cls):
        service_cls.return_value.sync_queryset.return_value = FootballDataSyncResult(
            checked=1,
            updated=1,
            scorers_refreshed=True,
            scorer_rows_updated=2,
            scorer_rows_deleted=1,
        )
        out = StringIO()

        call_command("sync_football_data", "--live", stdout=out)

        self.assertIn("football-data.org scorers OK", out.getvalue())
        self.assertIn("updated=2", out.getvalue())
        self.assertIn("deleted=1", out.getvalue())

    @patch("matches.management.commands.sync_football_data.FootballDataSyncService")
    def test_live_command_uses_batch_sync_and_can_skip_scorers(self, service_cls):
        service_cls.return_value.sync_queryset_from_match_list.return_value = FootballDataSyncResult(checked=1, updated=1)
        team_a = Team.objects.create(name="Live A", code="LVA")
        team_b = Team.objects.create(name="Live B", code="LVB")
        Match.objects.create(
            home_team=team_a,
            away_team=team_b,
            kickoff_at=timezone.now(),
            football_data_match_id=2001,
        )

        call_command("sync_football_data", "--live", "--no-refresh-scorers", stdout=StringIO())

        service_cls.return_value.sync_queryset_from_match_list.assert_called_once()
        service_cls.return_value.sync_queryset.assert_not_called()
        self.assertFalse(service_cls.return_value.sync_queryset_from_match_list.call_args.kwargs["refresh_scorers"])

    @patch("matches.management.commands.sync_football_data.timezone.localdate")
    @patch("matches.management.commands.sync_football_data.FootballDataSyncService")
    def test_live_command_fetches_padded_dates_for_night_matches(self, service_cls, localdate_mock):
        localdate_mock.return_value = datetime(2026, 6, 26).date()
        service_cls.return_value.sync_queryset_from_match_list.return_value = FootballDataSyncResult(checked=1, updated=1)
        team_a = Team.objects.create(name="Night A", code="NTA")
        team_b = Team.objects.create(name="Night B", code="NTB")
        Match.objects.create(
            home_team=team_a,
            away_team=team_b,
            kickoff_at=datetime(2026, 6, 27, 2, 0, tzinfo=dt_timezone.utc),
            football_data_match_id=2101,
        )

        call_command(
            "sync_football_data",
            "--live",
            "--days-back", "0",
            "--days-forward", "0",
            stdout=StringIO(),
        )

        call_kwargs = service_cls.return_value.sync_queryset_from_match_list.call_args.kwargs
        self.assertEqual(call_kwargs["date_from"].isoformat(), "2026-06-25")
        self.assertEqual(call_kwargs["date_to"].isoformat(), "2026-06-27")

    @patch("matches.management.commands.refresh_football_data_scorers.FootballDataTopScorersService")
    def test_refresh_football_data_scorers_command(self, service_cls):
        service_cls.return_value.refresh.return_value.checked = 3
        service_cls.return_value.refresh.return_value.updated = 3
        service_cls.return_value.refresh.return_value.deleted = 0
        out = StringIO()

        call_command("refresh_football_data_scorers", stdout=out)

        service_cls.return_value.refresh.assert_called_once_with(limit=None)
        self.assertIn("football-data.org scorers OK", out.getvalue())
        self.assertIn("checked=3", out.getvalue())

    @patch("matches.management.commands.refresh_football_data_scorers.FootballDataTopScorersService")
    def test_refresh_football_data_scorers_command_accepts_explicit_limit(self, service_cls):
        service_cls.return_value.refresh.return_value.checked = 50
        service_cls.return_value.refresh.return_value.updated = 50
        service_cls.return_value.refresh.return_value.deleted = 0

        call_command("refresh_football_data_scorers", "--limit", "50", stdout=StringIO())

        service_cls.return_value.refresh.assert_called_once_with(limit=50)

    @patch("teams.management.commands.import_football_data_players.FootballDataPlayersImportService")
    def test_import_football_data_players_command(self, service_cls):
        service_cls.return_value.import_players.return_value.checked_teams = 2
        service_cls.return_value.import_players.return_value.matched_teams = 2
        service_cls.return_value.import_players.return_value.checked_players = 46
        service_cls.return_value.import_players.return_value.created = 46
        out = StringIO()

        call_command("import_football_data_players", "--competition", "WC", "--season", "2026", "--commit", stdout=out)

        service_cls.assert_called_once_with(competition_code="WC", season=2026)
        service_cls.return_value.import_players.assert_called_once_with(commit=True, deactivate_missing=False)
        self.assertIn("football-data.org players OK", out.getvalue())
        self.assertIn("created=46", out.getvalue())


class MapFootballDataMatchesCommandTests(TestCase):

    def setUp(self):
        FakeFootballDataListClient.fixtures = []
        FakeFootballDataListClient.calls = []
        self.team_a = Team.objects.create(name="Colombia", code="COL")
        self.team_b = Team.objects.create(name="Brasil", code="BRA")
        self.kickoff = datetime(2026, 6, 25, 20, 0, tzinfo=dt_timezone.utc)

    def _fixture(self, *, fixture_id=9001, home_name="Colombia", home_tla="COL", away_name="Brazil", away_tla="BRA"):
        return {
            "id": fixture_id,
            "utcDate": self.kickoff.isoformat().replace("+00:00", "Z"),
            "homeTeam": {"id": 100, "name": home_name, "tla": home_tla, "crest": "https://crests.example/home.svg"},
            "awayTeam": {"id": 200, "name": away_name, "tla": away_tla, "crest": "https://crests.example/away.svg"},
            "status": "TIMED",
            "score": {"fullTime": {"home": None, "away": None}},
        }

    def _match(self, *, home_team=None, away_team=None):
        return Match.objects.create(
            home_team=home_team or self.team_a,
            away_team=away_team or self.team_b,
            kickoff_at=self.kickoff,
        )

    @patch("matches.management.commands.map_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_map_football_data_matches_dry_run_does_not_update_match(self):
        match = self._match()
        FakeFootballDataListClient.fixtures = [self._fixture()]
        out = StringIO()

        call_command("map_football_data_matches", "--date", "2026-06-25", stdout=out)

        match.refresh_from_db()
        self.assertIsNone(match.football_data_match_id)
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertIn("MAP: local_match_id", out.getvalue())

    @patch("matches.management.commands.map_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_map_football_data_matches_commit_updates_match_and_team_ids(self):
        match = self._match()
        FakeFootballDataListClient.fixtures = [self._fixture(fixture_id=9002)]
        out = StringIO()

        call_command("map_football_data_matches", "--date", "2026-06-25", "--commit", stdout=out)

        match.refresh_from_db()
        self.team_a.refresh_from_db()
        self.team_b.refresh_from_db()
        self.assertEqual(match.football_data_match_id, 9002)
        self.assertEqual(self.team_a.football_data_team_id, 100)
        self.assertEqual(self.team_b.football_data_team_id, 200)
        self.assertEqual(self.team_a.tla, "COL")
        self.assertEqual(self.team_b.tla, "BRA")
        self.assertEqual(self.team_a.flag, "https://crests.example/home.svg")
        self.assertEqual(self.team_b.flag, "https://crests.example/away.svg")
        self.assertIn("mapped=1", out.getvalue())

    @patch("matches.management.commands.map_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_map_football_data_matches_uses_team_tla_when_code_differs(self):
        local_home = Team.objects.create(name="Equipo Local", code="DEU", tla="GER")
        local_away = Team.objects.create(name="Rival Local", code="NLD", tla="NED")
        match = self._match(home_team=local_home, away_team=local_away)
        FakeFootballDataListClient.fixtures = [
            self._fixture(
                fixture_id=9006,
                home_name="Germany",
                home_tla="GER",
                away_name="Netherlands",
                away_tla="NED",
            )
        ]

        call_command("map_football_data_matches", "--date", "2026-06-25", "--commit", stdout=StringIO())

        match.refresh_from_db()
        self.assertEqual(match.football_data_match_id, 9006)

    @patch("matches.management.commands.map_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_map_football_data_matches_rejects_code_match_when_tla_differs(self):
        local_home = Team.objects.create(name="Local Alemania", code="GER", tla="DEU")
        local_away = Team.objects.create(name="Local Paises Bajos", code="NED", tla="NLD")
        match = self._match(home_team=local_home, away_team=local_away)
        FakeFootballDataListClient.fixtures = [
            self._fixture(
                fixture_id=9007,
                home_name="Germany",
                home_tla="GER",
                away_name="Netherlands",
                away_tla="NED",
            )
        ]
        out = StringIO()

        call_command("map_football_data_matches", "--date", "2026-06-25", "--commit", stdout=out)

        match.refresh_from_db()
        self.assertIsNone(match.football_data_match_id)
        self.assertIn("SIN MATCH", out.getvalue())

    @patch("matches.management.commands.map_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_map_football_data_matches_uses_spanish_english_alias_when_codes_differ(self):
        espana = Team.objects.create(name="España", code="SPN")
        alemania = Team.objects.create(name="Alemania", code="DEU")
        match = self._match(home_team=espana, away_team=alemania)
        FakeFootballDataListClient.fixtures = [
            self._fixture(
                fixture_id=9003,
                home_name="Spain",
                home_tla="ESP",
                away_name="Germany",
                away_tla="GER",
            )
        ]

        call_command("map_football_data_matches", "--date", "2026-06-25", "--commit", stdout=StringIO())

        match.refresh_from_db()
        self.assertEqual(match.football_data_match_id, 9003)

    @patch("matches.management.commands.map_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_map_football_data_matches_skips_ambiguous_candidates(self):
        match = self._match()
        FakeFootballDataListClient.fixtures = [self._fixture(fixture_id=9004), self._fixture(fixture_id=9005)]
        out = StringIO()

        call_command("map_football_data_matches", "--date", "2026-06-25", "--commit", stdout=out)

        match.refresh_from_db()
        self.assertIsNone(match.football_data_match_id)
        self.assertIn("AMBIGUO", out.getvalue())

    @patch("matches.management.commands.map_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_map_football_data_matches_fetches_padded_dates_for_utc_shift(self):
        self._match()
        FakeFootballDataListClient.fixtures = []

        call_command("map_football_data_matches", "--date", "2026-06-25", stdout=StringIO())

        self.assertEqual(FakeFootballDataListClient.calls[0]["date_from"].isoformat(), "2026-06-24")
        self.assertEqual(FakeFootballDataListClient.calls[0]["date_to"].isoformat(), "2026-06-26")

    @patch("matches.management.commands.sync_football_data.FootballDataSyncService")
    def test_live_command_selects_unfinished_mapped_matches_in_window(self, service_cls):
        team_a = Team.objects.create(name="Live A", code="LVA")
        team_b = Team.objects.create(name="Live B", code="LVB")
        included = Match.objects.create(
            home_team=team_a,
            away_team=team_b,
            kickoff_at=timezone.now(),
            football_data_match_id=2001,
        )
        finished = Match.objects.create(
            home_team=team_a,
            away_team=team_b,
            kickoff_at=timezone.now(),
            football_data_match_id=2002,
            finished=True,
        )
        unmapped = Match.objects.create(
            home_team=team_a,
            away_team=team_b,
            kickoff_at=timezone.now(),
        )
        old_live = Match.objects.create(
            home_team=team_a,
            away_team=team_b,
            kickoff_at=timezone.now() - timedelta(days=3),
            football_data_match_id=2003,
            live_status="LIVE",
        )
        old_not_live = Match.objects.create(
            home_team=team_a,
            away_team=team_b,
            kickoff_at=timezone.now() - timedelta(days=3),
            football_data_match_id=2004,
        )
        service_cls.return_value.sync_queryset_from_match_list.return_value = FootballDataSyncResult(checked=2)
        out = StringIO()

        call_command("sync_football_data", "--live", "--days-back", "1", "--days-forward", "1", stdout=out)

        queryset = service_cls.return_value.sync_queryset_from_match_list.call_args[0][0]
        selected_ids = {match.id for match in queryset}
        self.assertIn(included.id, selected_ids)
        self.assertIn(old_live.id, selected_ids)
        self.assertNotIn(finished.id, selected_ids)
        self.assertNotIn(unmapped.id, selected_ids)
        self.assertNotIn(old_not_live.id, selected_ids)
        service_cls.return_value.sync_queryset.assert_not_called()
        self.assertIn("football-data.org sync OK", out.getvalue())


class ImportFootballDataMatchesCommandTests(TestCase):

    def setUp(self):
        FakeFootballDataListClient.fixtures = []
        FakeFootballDataListClient.calls = []
        self.colombia = Team.objects.create(name="Colombia", code="COL", tla="COL")
        self.brasil = Team.objects.create(name="Brasil", code="BRA", tla="BRA")
        self.kickoff = datetime(2026, 6, 25, 20, 0, tzinfo=dt_timezone.utc)

    def _fixture(
        self,
        *,
        fixture_id=7001,
        utc_datetime=None,
        home_id=100,
        home_tla="COL",
        home_name="Colombia",
        away_id=200,
        away_tla="BRA",
        away_name="Brazil",
        stage="GROUP_STAGE",
        matchday=1,
        status="TIMED",
        home_score=None,
        away_score=None,
        home_penalty_score=None,
        away_penalty_score=None,
        winner=None,
    ):
        return {
            "id": fixture_id,
            "utcDate": (utc_datetime or self.kickoff).isoformat().replace("+00:00", "Z"),
            "stage": stage,
            "matchday": matchday,
            "status": status,
            "homeTeam": {
                "id": home_id,
                "name": home_name,
                "tla": home_tla,
                "crest": "https://crests.example/col.svg",
            },
            "awayTeam": {
                "id": away_id,
                "name": away_name,
                "tla": away_tla,
                "crest": "https://crests.example/bra.svg",
            },
            "score": {
                "winner": winner,
                "fullTime": {"home": home_score, "away": away_score},
                "penalties": {"home": home_penalty_score, "away": away_penalty_score},
            },
        }

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_dry_run_does_not_create_match(self):
        FakeFootballDataListClient.fixtures = [self._fixture()]
        out = StringIO()

        call_command("import_football_data_matches", "--date", "2026-06-25", stdout=out)

        self.assertFalse(Match.objects.exists())
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertIn("CREATE: football_data_match_id=7001", out.getvalue())

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_commit_creates_match_using_tla(self):
        FakeFootballDataListClient.fixtures = [self._fixture(fixture_id=7002, status="IN_PLAY", home_score=1, away_score=0)]
        out = StringIO()

        call_command("import_football_data_matches", "--date", "2026-06-25", "--commit", stdout=out)

        match = Match.objects.get(football_data_match_id=7002)
        self.colombia.refresh_from_db()
        self.brasil.refresh_from_db()
        self.assertEqual(match.home_team, self.colombia)
        self.assertEqual(match.away_team, self.brasil)
        self.assertEqual(match.home_score, 1)
        self.assertEqual(match.away_score, 0)
        self.assertEqual(match.live_status, "LIVE")
        self.assertFalse(match.finished)
        self.assertEqual(match.phase, "PR")
        self.assertEqual(self.colombia.football_data_team_id, 100)
        self.assertEqual(self.brasil.football_data_team_id, 200)
        self.assertEqual(self.colombia.flag, "https://crests.example/col.svg")
        self.assertIn("created=1", out.getvalue())

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_uses_code_when_tla_is_missing_locally(self):
        self.colombia.tla = ""
        self.colombia.save(update_fields=["tla"])
        FakeFootballDataListClient.fixtures = [self._fixture(fixture_id=7003)]
        out = StringIO()

        call_command("import_football_data_matches", "--date", "2026-06-25", "--commit", stdout=out)

        self.assertTrue(Match.objects.filter(football_data_match_id=7003, home_team=self.colombia).exists())
        self.assertIn("created=1", out.getvalue())

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_skips_existing_external_id(self):
        Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=self.kickoff,
            football_data_match_id=7004,
        )
        FakeFootballDataListClient.fixtures = [self._fixture(fixture_id=7004)]

        call_command("import_football_data_matches", "--date", "2026-06-25", "--commit", stdout=StringIO())

        self.assertEqual(Match.objects.count(), 1)

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_maps_finished_knockout_match(self):
        FakeFootballDataListClient.fixtures = [
            self._fixture(
                fixture_id=7005,
                stage="QUARTER_FINALS",
                matchday=None,
                status="FINISHED",
                home_score=2,
                away_score=1,
            )
        ]

        call_command("import_football_data_matches", "--date", "2026-06-25", "--commit", stdout=StringIO())

        match = Match.objects.get(football_data_match_id=7005)
        self.assertEqual(match.phase, "CF")
        self.assertEqual(match.live_status, "FT")
        self.assertTrue(match.finished)
        self.assertIsNotNone(match.finished_at)

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_stores_penalties_and_api_winner(self):
        FakeFootballDataListClient.fixtures = [
            self._fixture(
                fixture_id=7015,
                stage="LAST_32",
                matchday=9,
                status="FINISHED",
                home_score=1,
                away_score=1,
                home_penalty_score=5,
                away_penalty_score=4,
                winner="HOME_TEAM",
            )
        ]

        call_command("import_football_data_matches", "--date", "2026-06-25", "--commit", stdout=StringIO())

        match = Match.objects.get(football_data_match_id=7015)
        self.assertEqual(match.home_penalty_score, 5)
        self.assertEqual(match.away_penalty_score, 4)
        self.assertEqual(match.football_data_winner, "HOME_TEAM")
        self.assertEqual(match.winner_team, self.colombia)
        self.assertEqual(match.score_display, "1 - 1 (5 - 4 pen.)")

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_sets_bracket_position_from_knockout_matchday(self):
        FakeFootballDataListClient.fixtures = [
            self._fixture(
                fixture_id=7006,
                stage="LAST_32",
                matchday=9,
            )
        ]

        call_command("import_football_data_matches", "--date", "2026-06-25", "--commit", stdout=StringIO())

        match = Match.objects.get(football_data_match_id=7006)
        self.assertEqual(match.phase, "DR")
        self.assertEqual(match.bracket_position, 9)

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_uses_competition_endpoint_with_stage(self):
        FakeFootballDataListClient.fixtures = [self._fixture(fixture_id=7007, stage="LAST_32", matchday=2)]
        out = StringIO()

        call_command(
            "import_football_data_matches",
            "--date",
            "2026-06-25",
            "--stage",
            "LAST_32",
            "--commit",
            stdout=out,
        )

        self.assertEqual(FakeFootballDataListClient.calls[0]["competition_code"], "WC")
        self.assertEqual(FakeFootballDataListClient.calls[0]["season"], 2026)
        self.assertEqual(FakeFootballDataListClient.calls[0]["stage"], "LAST_32")
        self.assertIn("source=competitions/WC/matches", out.getvalue())
        self.assertTrue(Match.objects.filter(football_data_match_id=7007, phase="DR", bracket_position=2).exists())

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_updates_similar_local_match_without_external_id(self):
        existing = Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=self.kickoff,
            phase="PR",
        )
        FakeFootballDataListClient.fixtures = [self._fixture(fixture_id=7008, stage="LAST_32", matchday=4)]
        out = StringIO()

        call_command("import_football_data_matches", "--date", "2026-06-25", "--commit", stdout=out)

        self.assertEqual(Match.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.football_data_match_id, 7008)
        self.assertEqual(existing.phase, "DR")
        self.assertEqual(existing.bracket_position, 4)
        self.assertIn("UPDATE EXISTENTE", out.getvalue())
        self.assertIn("updated=1", out.getvalue())

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_updates_knockout_placeholder_by_phase_and_position(self):
        placeholder = Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=timezone.now() + timedelta(days=1),
            phase="OF",
            bracket_position=3,
        )
        fixture_datetime = self.kickoff + timedelta(days=7)
        FakeFootballDataListClient.fixtures = [
            self._fixture(
                fixture_id=7009,
                utc_datetime=fixture_datetime,
                stage="LAST_16",
                matchday=3,
            )
        ]
        out = StringIO()

        call_command(
            "import_football_data_matches",
            "--from-date",
            "2026-07-02",
            "--to-date",
            "2026-07-02",
            "--fetch-padding-days",
            "7",
            "--stage",
            "LAST_16",
            "--commit",
            stdout=out,
        )

        self.assertEqual(Match.objects.count(), 1)
        placeholder.refresh_from_db()
        self.assertEqual(placeholder.football_data_match_id, 7009)
        self.assertEqual(placeholder.phase, "OF")
        self.assertEqual(placeholder.bracket_position, 3)
        self.assertEqual(placeholder.kickoff_at, fixture_datetime)
        self.assertIn("UPDATE CUADRO", out.getvalue())
        self.assertIn("updated=1", out.getvalue())

    @patch("matches.management.commands.import_football_data_matches.FootballDataClient", FakeFootballDataListClient)
    def test_import_football_data_matches_can_create_all_last_32_matches_in_range(self):
        fixtures = []
        for position in range(1, 17):
            home_tla = f"H{position:02d}"
            away_tla = f"A{position:02d}"
            Team.objects.create(name=f"Home {position}", code=home_tla, tla=home_tla)
            Team.objects.create(name=f"Away {position}", code=away_tla, tla=away_tla)
            fixtures.append(
                self._fixture(
                    fixture_id=7100 + position,
                    utc_datetime=self.kickoff + timedelta(hours=position),
                    home_id=8100 + position,
                    home_tla=home_tla,
                    home_name=f"Home {position}",
                    away_id=8200 + position,
                    away_tla=away_tla,
                    away_name=f"Away {position}",
                    stage="LAST_32",
                    matchday=position,
                )
            )
        FakeFootballDataListClient.fixtures = fixtures
        out = StringIO()

        call_command(
            "import_football_data_matches",
            "--from-date",
            "2026-06-25",
            "--to-date",
            "2026-06-26",
            "--stage",
            "LAST_32",
            "--commit",
            stdout=out,
        )

        self.assertEqual(Match.objects.filter(phase="DR").count(), 16)
        self.assertEqual(
            set(Match.objects.filter(phase="DR").values_list("bracket_position", flat=True)),
            set(range(1, 17)),
        )
        self.assertIn("created=16", out.getvalue())

    def test_assign_bracket_positions_command_updates_from_json(self):
        match = Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=self.kickoff,
            phase="DR",
            football_data_match_id=7010,
        )
        payload = {"DR": {"2": 7010}}
        out = StringIO()

        with NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as json_file:
            json.dump(payload, json_file)
            json_file.flush()
            call_command("assign_bracket_positions", json_file.name, "--commit", stdout=out)

        match.refresh_from_db()
        self.assertEqual(match.phase, "DR")
        self.assertEqual(match.bracket_position, 2)
        self.assertIn("updated=1", out.getvalue())

    def test_assign_bracket_positions_command_is_dry_run_by_default(self):
        match = Match.objects.create(
            home_team=self.colombia,
            away_team=self.brasil,
            kickoff_at=self.kickoff,
            phase="DR",
            football_data_match_id=7011,
        )
        payload = {"matches": [{"football_data_match_id": 7011, "phase": "DR", "position": 3}]}

        with NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as json_file:
            json.dump(payload, json_file)
            json_file.flush()
            call_command("assign_bracket_positions", json_file.name, stdout=StringIO())

        match.refresh_from_db()
        self.assertIsNone(match.bracket_position)


