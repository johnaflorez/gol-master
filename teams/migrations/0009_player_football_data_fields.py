# Generated manually for football-data player imports

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0008_team_flag_team_tla_populate_football_data_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='football_data_player_id',
            field=models.PositiveIntegerField(blank=True, help_text='ID externo del jugador en football-data.org', null=True, unique=True),
        ),
        migrations.AddField(
            model_name='player',
            name='position',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='player',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='player',
            name='nationality',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]

