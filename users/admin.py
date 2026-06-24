from django.contrib import admin

from users.models import UserProfile, WhatsAppReminderLog


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "get_avatar_preview", "bio_preview", "whatsapp_notifications_enabled", "whatsapp_phone_number", "updated_at")
    list_filter = ("whatsapp_notifications_enabled",)
    search_fields = ("user__username", "user__first_name", "user__last_name", "whatsapp_phone_number")
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "user",
        "bio",
        "avatar",
        "whatsapp_phone_number",
        "whatsapp_notifications_enabled",
        "whatsapp_opt_in_at",
        "created_at",
        "updated_at",
    )

    def get_avatar_preview(self, obj):
        """Display avatar in admin list."""
        if obj.avatar:
            return "✓ Sí"
        return "-"

    get_avatar_preview.short_description = "Avatar"

    def bio_preview(self, obj):
        """Display bio preview in admin list."""
        if obj.bio:
            return obj.bio[:50] + ("..." if len(obj.bio) > 50 else "")
        return "-"

    bio_preview.short_description = "Bio"


@admin.register(WhatsAppReminderLog)
class WhatsAppReminderLogAdmin(admin.ModelAdmin):
    list_display = ("user", "reminder_date", "reminder_type", "status", "pending_match_count", "phone_number", "updated_at")
    list_filter = ("status", "reminder_type", "reminder_date")
    search_fields = ("user__username", "user__first_name", "user__last_name", "phone_number", "provider_message_id")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

