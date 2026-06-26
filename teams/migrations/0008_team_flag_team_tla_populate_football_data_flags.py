# Generated manually on 2026-06-26

from django.db import migrations, models


WORLD_CUP_TEAMS = [
    {"code": "URY", "flag": "https://crests.football-data.org/758.svg", "tla": "URU"},
    {"code": "DEU", "flag": "https://crests.football-data.org/759.svg", "tla": "GER"},
    {"code": "ESP", "flag": "https://crests.football-data.org/760.svg", "tla": "ESP"},
    {"code": "PRY", "flag": "https://crests.football-data.org/761.svg", "tla": "PAR"},
    {"code": "ARG", "flag": "https://crests.football-data.org/ar.svg", "tla": "ARG"},
    {"code": "GHA", "flag": "https://crests.football-data.org/ghana.svg", "tla": "GHA"},
    {"code": "BRA", "flag": "https://crests.football-data.org/764.svg", "tla": "BRA"},
    {"code": "PRT", "flag": "https://crests.football-data.org/765.svg", "tla": "POR"},
    {"code": "JPN", "flag": "https://crests.football-data.org/JAP.svg", "tla": "JPN"},
    {"code": "MEX", "flag": "https://crests.football-data.org/mexico.svg", "tla": "MEX"},
    {"code": "ENG", "flag": "https://crests.football-data.org/770.svg", "tla": "ENG"},
    {"code": "USA", "flag": "https://crests.football-data.org/usa.svg", "tla": "USA"},
    {"code": "KOR", "flag": "https://crests.football-data.org/772.png", "tla": "KOR"},
    {"code": "FRA", "flag": "https://crests.football-data.org/773.svg", "tla": "FRA"},
    {"code": "ZAF", "flag": "https://crests.football-data.org/9396.svg", "tla": "RSA"},
    {"code": "DZA", "flag": "https://crests.football-data.org/algeria.svg", "tla": "ALG"},
    {"code": "AUS", "flag": "https://crests.football-data.org/779.svg", "tla": "AUS"},
    {"code": "NZL", "flag": "https://crests.football-data.org/783.svg", "tla": "NZL"},
    {"code": "CHE", "flag": "https://crests.football-data.org/788.svg", "tla": "SUI"},
    {"code": "ECU", "flag": "https://crests.football-data.org/791.svg", "tla": "ECU"},
    {"code": "SWE", "flag": "https://crests.football-data.org/792.svg", "tla": "SWE"},
    {"code": "CZE", "flag": "https://crests.football-data.org/798.svg", "tla": "CZE"},
    {"code": "HRV", "flag": "https://crests.football-data.org/799.svg", "tla": "CRO"},
    {"code": "SAU", "flag": "https://crests.football-data.org/saudi_arabia.svg", "tla": "KSA"},
    {"code": "TUN", "flag": "https://crests.football-data.org/tunisia.svg", "tla": "TUN"},
    {"code": "TUR", "flag": "https://crests.football-data.org/803.svg", "tla": "TUR"},
    {"code": "SEN", "flag": "https://crests.football-data.org/senegal.svg", "tla": "SEN"},
    {"code": "BEL", "flag": "https://crests.football-data.org/805.svg", "tla": "BEL"},
    {"code": "MAR", "flag": "https://crests.football-data.org/morocco.svg", "tla": "MAR"},
    {"code": "AUT", "flag": "https://crests.football-data.org/816.svg", "tla": "AUT"},
    {"code": "COL", "flag": "https://crests.football-data.org/818.svg", "tla": "COL"},
    {"code": "EGY", "flag": "https://crests.football-data.org/825.svg", "tla": "EGY"},
    {"code": "CAN", "flag": "https://crests.football-data.org/canada.svg", "tla": "CAN"},
    {"code": "HTI", "flag": "https://crests.football-data.org/haiti.svg", "tla": "HAI"},
    {"code": "IRN", "flag": "https://crests.football-data.org/iran.svg", "tla": "IRN"},
    {"code": "BIH", "flag": "https://crests.football-data.org/bosnia.svg", "tla": "BIH"},
    {"code": "PAN", "flag": "https://crests.football-data.org/panama.svg", "tla": "PAN"},
    {"code": "CPV", "flag": "https://crests.football-data.org/cape_verde.svg", "tla": "CPV"},
    {"code": "COD", "flag": "https://crests.football-data.org/congo_dr.svg", "tla": "COD"},
    {"code": "CIV", "flag": "https://crests.football-data.org/787.svg", "tla": "CIV"},
    {"code": "QAT", "flag": "https://crests.football-data.org/8030.svg", "tla": "QAT"},
    {"code": "JOR", "flag": "https://crests.football-data.org/8049.png", "tla": "JOR"},
    {"code": "IRQ", "flag": "https://crests.football-data.org/iraq.svg", "tla": "IRQ"},
    {"code": "UZB", "flag": "https://crests.football-data.org/8070.png", "tla": "UZB"},
    {"code": "NLD", "flag": "https://crests.football-data.org/8601.svg", "tla": "NED"},
    {"code": "NOR", "flag": "https://crests.football-data.org/813.svg", "tla": "NOR"},
    {"code": "SCT", "flag": "https://crests.football-data.org/814.svg", "tla": "SCO"},
    {"code": "CUW", "flag": "https://crests.football-data.org/curacao.svg", "tla": "CUW"},
]


def populate_team_flags(apps, schema_editor):
    Team = apps.get_model("teams", "Team")
    for item in WORLD_CUP_TEAMS:
        Team.objects.filter(code=item["code"]).update(flag=item["flag"], tla=item["tla"])


def clear_team_flags(apps, schema_editor):
    Team = apps.get_model("teams", "Team")
    codes = [item["code"] for item in WORLD_CUP_TEAMS]
    Team.objects.filter(code__in=codes).update(flag="", tla="")


class Migration(migrations.Migration):

    dependencies = [
        ("teams", "0007_remove_team_api_football_team_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="flag",
            field=models.URLField(blank=True, default="", help_text="URL de la bandera/escudo del equipo en football-data.org", max_length=255),
        ),
        migrations.AddField(
            model_name="team",
            name="tla",
            field=models.CharField(blank=True, db_index=True, default="", help_text="Código TLA usado por football-data.org (e.g., ARG, GER, NED)", max_length=3),
        ),
        migrations.RunPython(populate_team_flags, clear_team_flags),
    ]

