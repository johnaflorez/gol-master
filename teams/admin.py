from django.contrib import admin

from teams.models import Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "group_code", "country_code", "api_football_team_id", "football_data_team_id", "get_flag_preview")
    list_filter = ("group_code",)
    search_fields = ("code", "name", "api_football_team_id", "football_data_team_id")
    ordering = ["group_code", "name"]
    fields = ("code", "name", "group_code", "country_code", "api_football_team_id", "football_data_team_id")

    def get_flag_preview(self, obj):
        """Display flag emoji in admin list."""
        return obj.get_flag_emoji() or "-"

    get_flag_preview.short_description = "Flag"
