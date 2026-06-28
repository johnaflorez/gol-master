from django.db.models import Count, IntegerField, Sum, Value
from django.db.models.functions import Coalesce

from matches.models import Match


class TournamentStatsService:

    def get_stats(self):
        stats = Match.objects.filter(finished=True).aggregate(
            total_matches=Count("id"),
            total_home_goals=Coalesce(Sum("home_score"), Value(0), output_field=IntegerField()),
            total_away_goals=Coalesce(Sum("away_score"), Value(0), output_field=IntegerField()),
        )
        total_matches = stats["total_matches"]
        total_goals = stats["total_home_goals"] + stats["total_away_goals"]

        return {
            "total_matches": total_matches,
            "total_goals": total_goals,
            "avg_goals": total_goals / total_matches if total_matches else 0
        }
