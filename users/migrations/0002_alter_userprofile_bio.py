# Generated manually on 2026-06-26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="bio",
            field=models.TextField(blank=True, default="", help_text="Breve descripción o bio personal", max_length=5000),
        ),
    ]

