from django.contrib import admin

from teams.models import Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country_code", "api_football_team_id", "get_flag_preview")
    search_fields = ("code", "name", "api_football_team_id")
    ordering = ["name"]
    fields = ("code", "name", "country_code", "api_football_team_id")

    def get_flag_preview(self, obj):
        """Display flag emoji in admin list."""
        return obj.get_flag_emoji() or "-"

    get_flag_preview.short_description = "Flag"
