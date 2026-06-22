from django.contrib import admin

from users.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "get_avatar_preview", "bio_preview", "updated_at")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at")
    fields = ("user", "bio", "avatar", "created_at", "updated_at")

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
