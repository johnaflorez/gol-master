from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0009_remove_match_api_football_fixture_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="bracket_position",
            field=models.PositiveSmallIntegerField(
                blank=True,
                db_index=True,
                help_text="Posición visual del partido dentro de su fase eliminatoria. Ej: 2, 9.",
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="match",
            index=models.Index(fields=["phase", "bracket_position"], name="matches_mat_phase_b_25ba5e_idx"),
        ),
    ]

