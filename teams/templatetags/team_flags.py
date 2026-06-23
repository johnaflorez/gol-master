from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def team_with_flag(team):
    """Display team with a cross-platform flag icon fallback."""
    if not team:
        return ""

    country_code = (getattr(team, "country_code", "") or "").strip().lower()
    team_name = getattr(team, "name", "")

    if len(country_code) == 2 and country_code.isalpha():
        return format_html(
            '<span class="d-inline-flex align-items-center gap-1">'
            '<img src="https://flagcdn.com/24x18/{}.png" alt="Bandera {}" '
            'loading="lazy" width="18" height="14" style="border-radius:2px;">'
            '<span>{}</span></span>',
            country_code,
            country_code.upper(),
            team_name,
        )

    flag = team.get_flag_emoji()
    if flag:
        return f"{flag} {team_name}"

    return team_name
