from django.test import TestCase

from teams.models import Team
from teams.templatetags.team_flags import team_with_flag


class TeamFlagsTests(TestCase):

    def test_team_with_flag_renders_image_for_country_code(self):
        team = Team.objects.create(name="Colombia", code="COL", country_code="CO")

        rendered = team_with_flag(team)

        self.assertIn('flagcdn.com/24x18/co.png', rendered)
        self.assertIn('Colombia', rendered)

    def test_team_with_flag_falls_back_to_name_when_no_country_code(self):
        team = Team.objects.create(name="Seleccion X", code="SLX", country_code="")

        rendered = team_with_flag(team)

        self.assertEqual(rendered, "Seleccion X")
