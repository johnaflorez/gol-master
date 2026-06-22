from matches.models import Match


class TournamentStatsService:

    def get_stats(self):
        matches = Match.objects.filter(finished=True)

        total_goals = 0
        total_matches = matches.count()

        for m in matches:
            total_goals += (m.home_score or 0)
            total_goals += (m.away_score or 0)

        return {
            "total_matches": total_matches,
            "total_goals": total_goals,
            "avg_goals": total_goals / total_matches if total_matches else 0
        }
