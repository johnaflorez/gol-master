from django.db import models


class Team(models.Model):
    GROUP_CHOICES = [(letter, f"Grupo {letter}") for letter in "ABCDEFGHIJKL"]

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3, unique=True)
    group_code = models.CharField(
        "grupo",
        max_length=1,
        choices=GROUP_CHOICES,
        blank=True,
        default="",
        db_index=True,
        help_text="Grupo de primera ronda del Mundial 2026 (A-L).",
    )
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
    football_data_team_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        unique=True,
        help_text="ID externo del equipo en football-data.org",
    )

    def __str__(self):
        return self.name

    def get_flag_emoji(self):
        """Convert country_code to flag emoji using regional indicator symbols."""
        if not self.country_code:
            return ""
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in self.country_code.upper())

