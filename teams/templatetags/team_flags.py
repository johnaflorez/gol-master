from django import template

register = template.Library()


@register.filter
def team_with_flag(team):
    """Display team name with country flag emoji."""
    if not team:
        return ""
    flag = team.get_flag_emoji()
    if flag:
        return f"{flag} {team.name}"
    return team.name

