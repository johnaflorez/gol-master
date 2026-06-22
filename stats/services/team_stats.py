from matches.models import Match


class TeamStatisticsService:

    def get_team_stats(self, team):
        matches = Match.objects.filter(
            finished=True
        ).filter(
            home_team=team
        ) | Match.objects.filter(
            finished=True
        ).filter(
            away_team=team
        )

        wins = 0
        draws = 0
        losses = 0
        goals_for = 0
        goals_against = 0

        for match in matches:
            if match.home_score is None:
                continue

            is_home = match.home_team == team
            gf = match.home_score if is_home else match.away_score
            ga = match.away_score if is_home else match.home_score

            goals_for += gf
            goals_against += ga

            if match.home_score == match.away_score:
                draws += 1

            elif (is_home and match.home_score > match.away_score) or \
                    (not is_home and match.away_score > match.home_score):
                wins += 1
            else:
                losses += 1

        return {
            "team": team,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
        }
