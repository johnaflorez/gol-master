from django.db import models


class Team(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3, unique=True)
    country_code = models.CharField(
        max_length=2, blank=True, default="",
        help_text="ISO 3166-1 alpha-2 code (e.g., AR, BR)"
    )
    api_football_team_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        unique=True,
        help_text="ID externo del equipo en API-Football/API-SPORTS",
    )

    def __str__(self):
        return self.name

    def get_flag_emoji(self):
        """Convert country_code to flag emoji using regional indicator symbols."""
        if not self.country_code:
            return ""
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in self.country_code.upper())

