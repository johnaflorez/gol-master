from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from matches.models import Match
from matches.services.football_data import FootballDataClient, FootballDataSyncResult, FootballDataSyncService, FootballDataTopScorersService
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
        self.assertContains(response, "Tabla de posiciones por grupo")
        self.assertContains(response, reverse("group_standings"))
        self.assertContains(response, "Ver tabla de posiciones")
        self.assertNotContains(response, "Consulta J, G, E, P, GF, GC, DIF y PTS en una vista dedicada.")
        self.assertNotContains(response, "Grupo A")
        self.assertNotContains(response, "Selecci&oacute;n")

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
        self.assertContains(response, "Tabla de posiciones")
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
        service_cls.return_value.sync_queryset.return_value = FootballDataSyncResult(checked=2)
        out = StringIO()

        call_command("sync_football_data", "--live", "--days-back", "1", "--days-forward", "1", stdout=out)

        queryset = service_cls.return_value.sync_queryset.call_args[0][0]
        selected_ids = {match.id for match in queryset}
        self.assertIn(included.id, selected_ids)
        self.assertIn(old_live.id, selected_ids)
        self.assertNotIn(finished.id, selected_ids)
        self.assertNotIn(unmapped.id, selected_ids)
        self.assertNotIn(old_not_live.id, selected_ids)
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
        home_tla="COL",
        away_tla="BRA",
        stage="GROUP_STAGE",
        matchday=1,
        status="TIMED",
        home_score=None,
        away_score=None,
    ):
        return {
            "id": fixture_id,
            "utcDate": self.kickoff.isoformat().replace("+00:00", "Z"),
            "stage": stage,
            "matchday": matchday,
            "status": status,
            "homeTeam": {
                "id": 100,
                "name": "Colombia",
                "tla": home_tla,
                "crest": "https://crests.example/col.svg",
            },
            "awayTeam": {
                "id": 200,
                "name": "Brazil",
                "tla": away_tla,
                "crest": "https://crests.example/bra.svg",
            },
            "score": {"fullTime": {"home": home_score, "away": away_score}},
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
    def test_import_football_data_matches_rejects_when_tla_is_missing_locally(self):
        self.colombia.tla = ""
        self.colombia.save(update_fields=["tla"])
        FakeFootballDataListClient.fixtures = [self._fixture(fixture_id=7003)]
        out = StringIO()

        call_command("import_football_data_matches", "--date", "2026-06-25", "--commit", stdout=out)

        self.assertFalse(Match.objects.exists())
        self.assertIn("SIN EQUIPO LOCAL", out.getvalue())

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


