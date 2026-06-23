# Generated for API-Football integration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0003_team_api_football_team_id'),
        ('matches', '0005_match_last_event_at_match_live_minute_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='match',
            name='api_football_fixture_id',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='ID externo del fixture en API-Football/API-SPORTS',
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='matchevent',
            name='api_football_event_key',
            field=models.CharField(blank=True, db_index=True, default='', max_length=255),
        ),
    ]

