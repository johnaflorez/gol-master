# Generated for API-Football integration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0002_team_country_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='api_football_team_id',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='ID externo del equipo en API-Football/API-SPORTS',
                null=True,
                unique=True,
            ),
        ),
    ]

