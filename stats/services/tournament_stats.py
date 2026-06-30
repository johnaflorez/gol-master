from django.db.models import Count, IntegerField, Sum, Value
from django.db.models.functions import Coalesce

from matches.models import Match


class TournamentStatsService:

    def get_stats(self):
        finished_matches = Match.objects.filter(finished=True)
        stats = finished_matches.aggregate(
            total_matches=Count("id"),
            total_home_goals=Coalesce(Sum("home_score"), Value(0), output_field=IntegerField()),
            total_away_goals=Coalesce(Sum("away_score"), Value(0), output_field=IntegerField()),
        )
        total_matches = stats["total_matches"]
        total_goals = stats["total_home_goals"] + stats["total_away_goals"]
        goals_by_phase = self._get_goals_by_phase(finished_matches)

        return {
            "total_matches": total_matches,
            "total_goals": total_goals,
            "avg_goals": total_goals / total_matches if total_matches else 0,
            "goals_by_phase": goals_by_phase,
        }

    def _get_goals_by_phase(self, queryset):
        phase_labels = dict(Match.PHASE_CHOICES)
        phase_order = {code: index for index, (code, _label) in enumerate(Match.PHASE_CHOICES)}
        phase_rows = queryset.values("phase").annotate(
            matches=Count("id"),
            total_home_goals=Coalesce(Sum("home_score"), Value(0), output_field=IntegerField()),
            total_away_goals=Coalesce(Sum("away_score"), Value(0), output_field=IntegerField()),
        )

        rows = []
        for row in phase_rows:
            matches = row["matches"]
            total_goals = row["total_home_goals"] + row["total_away_goals"]
            rows.append(
                {
                    "phase": row["phase"],
                    "label": phase_labels.get(row["phase"], row["phase"]),
                    "matches": matches,
                    "total_goals": total_goals,
                    "avg_goals": total_goals / matches if matches else 0,
                }
            )

        return sorted(rows, key=lambda item: phase_order.get(item["phase"], len(phase_order)))

