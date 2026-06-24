from django.contrib import admin

from core.models import Suggestion


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
	list_display = ("id", "user", "short_message", "is_resolved", "created_at", "updated_at")
	list_filter = ("is_resolved", "created_at")
	search_fields = ("message", "user__username", "user__first_name", "user__last_name", "user__email")
	list_editable = ("is_resolved",)
	readonly_fields = ("created_at", "updated_at")
	date_hierarchy = "created_at"

	def short_message(self, obj):
		return obj.message[:80] + ("..." if len(obj.message) > 80 else "")

	short_message.short_description = "Sugerencia"
