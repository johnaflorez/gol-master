from django import template
from django.core.exceptions import ObjectDoesNotExist


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
        return bio

    return f"@{username}" if username else ""


