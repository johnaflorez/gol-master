from collections import OrderedDict

from matches.models import Match
from teams.models import Team


class GroupStandingsService:
    """Calcula la tabla de posiciones desde partidos finalizados de rondas de grupos."""

    GROUP_STAGE_PHASES = ("PR", "SR", "TR")

    def get_group_standings(self, *, group_code="", country=""):
        rows_by_team_id = {}
        standings_by_group = OrderedDict()
        selected_group = (group_code or "").strip().upper()
        selected_country = (country or "").strip().upper()

        teams = Team.objects.exclude(group_code="").order_by("group_code", "name")
        for team in teams:
            group_code = team.group_code.upper()
            standings_by_group.setdefault(
                group_code,
                {
                    "code": group_code,
                    "label": f"Grupo {group_code}",
                    "rows": [],
                },
            )
            row = self._empty_row(team)
            rows_by_team_id[team.id] = row
            standings_by_group[group_code]["rows"].append(row)

        matches = Match.objects.filter(
            finished=True,
            phase__in=self.GROUP_STAGE_PHASES,
            home_team__group_code__gt="",
            away_team__group_code__gt="",
        ).select_related("home_team", "away_team")

        for match in matches:
            home_group = match.home_team.group_code.upper()
            away_group = match.away_team.group_code.upper()
            if home_group != away_group:
                continue

            home_row = rows_by_team_id.get(match.home_team_id)
            away_row = rows_by_team_id.get(match.away_team_id)
            if not home_row or not away_row:
                continue

            self._apply_match_result(
                home_row,
                goals_for=match.home_score,
                goals_against=match.away_score,
            )
            self._apply_match_result(
                away_row,
                goals_for=match.away_score,
                goals_against=match.home_score,
            )

        for group in standings_by_group.values():
            if selected_country:
                group["rows"] = [
                    row for row in group["rows"]
                    if self._matches_country_filter(row["team"], selected_country)
                ]
            group["rows"].sort(
                key=lambda row: (
                    -row["points"],
                    -row["goal_difference"],
                    -row["goals_for"],
                    row["team"].name,
                )
            )

        return [
            group for group in standings_by_group.values()
            if group["rows"] and (not selected_group or group["code"] == selected_group)
        ]

    def _empty_row(self, team):
        return {
            "team": team,
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
            "points": 0,
        }

    def _apply_match_result(self, row, *, goals_for, goals_against):
        row["played"] += 1
        row["goals_for"] += goals_for
        row["goals_against"] += goals_against
        row["goal_difference"] = row["goals_for"] - row["goals_against"]

        if goals_for > goals_against:
            row["wins"] += 1
            row["points"] += 3
        elif goals_for == goals_against:
            row["draws"] += 1
            row["points"] += 1
        else:
            row["losses"] += 1

    def _matches_country_filter(self, team, selected_country):
        return selected_country in {
            (team.code or "").upper(),
            (team.country_code or "").upper(),
            (team.name or "").upper(),
        }

