from django.test import TestCase

from teams.models import Team
from teams.templatetags.team_flags import team_with_flag


class TeamFlagsTests(TestCase):

    def test_team_with_flag_renders_image_from_flag_url(self):
        team = Team.objects.create(
            name="Colombia",
            code="COL",
            country_code="CO",
            flag="https://crests.football-data.org/818.svg",
            tla="COL",
        )

        rendered = team_with_flag(team)

        self.assertIn('https://crests.football-data.org/818.svg', rendered)
        self.assertIn('alt="Bandera COL"', rendered)
        self.assertIn('Colombia', rendered)

    def test_team_with_flag_does_not_use_country_code_image_without_flag_url(self):
        team = Team.objects.create(name="Colombia", code="COL", country_code="CO")

        rendered = team_with_flag(team)

        self.assertNotIn('flagcdn.com/24x18/co.png', rendered)
        self.assertIn('Colombia', rendered)

    def test_team_with_flag_falls_back_to_name_when_no_country_code(self):
        team = Team.objects.create(name="Seleccion X", code="SLX", country_code="")

        rendered = team_with_flag(team)

        self.assertEqual(rendered, "Seleccion X")
