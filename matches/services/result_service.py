from predictions.models import Prediction
from predictions.services.scoring import ScoreCalculator
from rankings.services.snapshot_service import SnapshotService


class MatchResultService:

    def update_match_result(self, match):
        calculator = ScoreCalculator()
        predictions = Prediction.objects.filter(match=match)

        for prediction in predictions:
            prediction.points = calculator.calculate(prediction, match)
            prediction.save()

        SnapshotService().create_snapshot()
