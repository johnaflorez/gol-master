from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("predictions", "0004_tournamentprediction_top_scorer_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="prediction",
            name="predicted_penalty_winner",
            field=models.CharField(
                blank=True,
                choices=[("HOME", "Gana local por penales"), ("AWAY", "Gana visitante por penales")],
                default="",
                help_text="Ganador por penales cuando el pronóstico de eliminatorias es empate.",
                max_length=4,
            ),
        ),
    ]
