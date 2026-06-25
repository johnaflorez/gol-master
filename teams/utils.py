from django.db.models import Q

from teams.models import Team


def parse_country_filter(raw_country):
    """Normalize country filter values from free text or datalist labels.

    Accepts values like "COL", "CO", "Colombia" or "COL - Colombia" and
    returns an uppercase lookup token. When a team name is provided, returns
    the team code to keep filters consistent across views.
    """
    country = (raw_country or "").strip()
    if not country:
        return ""

    if " - " in country:
        country = country.split(" - ", 1)[0].strip()

    team_by_name = Team.objects.filter(name__iexact=country).first()
    if team_by_name:
        return team_by_name.code.upper()

    return country.upper()


def team_matches_country(team, selected_country):
    country = (selected_country or "").strip().upper()
    if not country or not team:
        return False

    return country in {
        (team.code or "").upper(),
        (team.country_code or "").upper(),
        (team.name or "").upper(),
    }


def match_country_q(selected_country, *, prefix=""):
    country = (selected_country or "").strip()
    if not country:
        return Q()

    base = f"{prefix}__" if prefix else ""
    return (
        Q(**{f"{base}home_team__country_code__iexact": country})
        | Q(**{f"{base}away_team__country_code__iexact": country})
        | Q(**{f"{base}home_team__code__iexact": country})
        | Q(**{f"{base}away_team__code__iexact": country})
    )


def get_country_options(*, unique_by="code"):
    """Build country datalist options.

    unique_by="code" is useful for match filters. unique_by="name" keeps all
    team names available for standings search suggestions.
    """
    options = []
    seen = set()

    for team in Team.objects.order_by("name"):
        if unique_by == "name":
            key = team.name.strip().casefold()
        else:
            key = (team.code or "").upper()

        if not key or key in seen:
            continue

        options.append(
            {
                "code": team.code,
                "country_code": team.country_code,
                "name": team.name,
            }
        )
        seen.add(key)

    return options


def get_country_label(selected_country, country_options, *, match_country_code=False, match_name=False):
    country = (selected_country or "").strip().upper()
    if not country:
        return ""

    def option_matches(option):
        values = {(option.get("code") or "").upper()}
        if match_country_code:
            values.add((option.get("country_code") or "").upper())
        if match_name:
            values.add((option.get("name") or "").upper())
        return country in values

    return next(
        (
            f"{option['code']} - {option['name']}"
            for option in country_options
            if option_matches(option)
        ),
        selected_country,
    )

