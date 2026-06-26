from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def team_with_flag(team):
    """Display team with a cross-platform flag icon fallback."""
    if not team:
        return ""

    flag_url = (getattr(team, "flag", "") or "").strip()
    flag_alt = (getattr(team, "tla", "") or getattr(team, "code", "") or "").strip().upper()
    team_name = getattr(team, "name", "")

    if flag_url:
        return format_html(
            '<span class="d-inline-flex align-items-center gap-1">'
            '<img src="{}" alt="Bandera {}" '
            'loading="lazy" width="18" height="14" style="border-radius:2px; object-fit:contain;">'
            '<span>{}</span></span>',
            flag_url,
            flag_alt,
            team_name,
        )

    flag = team.get_flag_emoji()
    if flag:
        return f"{flag} {team_name}"

    return team_name
