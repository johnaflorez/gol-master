from django import template
from django.core.exceptions import ObjectDoesNotExist
from django.utils.safestring import mark_safe

from users.services.rich_text import sanitize_profile_bio


register = template.Library()


@register.simple_tag
def user_avatar_url(user):
    """Return avatar URL safely, even when profile does not exist."""
    if not user:
        return ""

    try:
        profile = user.profile
    except ObjectDoesNotExist:
        return ""

    if profile and profile.avatar:
        try:
            return profile.avatar.url
        except (OSError, ValueError):
            return ""

    return ""


@register.filter
def rich_profile_bio(value):
    """Render sanitized profile bio HTML for the profile editor preview."""
    return mark_safe(sanitize_profile_bio(value))


@register.filter
def user_bio_or_username(user):
    """Return user bio when available, fallback to @username."""
    if not user:
        return ""

    username = getattr(user, "username", "")

    try:
        profile = user.profile
    except ObjectDoesNotExist:
        return f"@{username}" if username else ""

    bio = (profile.bio or "").strip() if profile else ""
    if bio:
        return mark_safe(sanitize_profile_bio(bio))

    return f"@{username}" if username else ""


