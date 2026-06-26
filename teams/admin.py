from django.contrib import admin
from django.utils.html import format_html

from teams.models import Player, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("code", "tla", "name", "group_code", "country_code", "football_data_team_id", "get_flag_preview")
    list_filter = ("group_code",)
    search_fields = ("code", "tla", "name", "football_data_team_id")
    ordering = ["group_code", "name"]
    fields = ("code", "tla", "name", "group_code", "country_code", "flag", "football_data_team_id")

    def get_flag_preview(self, obj):
        """Display football-data crest/flag when available."""
        if obj.flag:
            return format_html(
                '<img src="{}" alt="Bandera {}" width="24" height="18" style="object-fit:contain;">',
                obj.flag,
                obj.tla or obj.code,
            )
        return obj.get_flag_emoji() or "-"

    get_flag_preview.short_description = "Flag"


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "team", "football_data_player_id", "position", "nationality", "active", "photo", "updated_at")
    list_filter = ("active", "team", "position", "nationality")
    search_fields = ("name", "=football_data_player_id", "team__name", "team__code", "team__tla")
    autocomplete_fields = ("team",)
    ordering = ("team__name", "name")

