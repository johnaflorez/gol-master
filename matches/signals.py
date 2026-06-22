from django.db.models.signals import post_save
from django.dispatch import receiver

from matches.models import Match
from matches.services.result_service import MatchResultService
from predictions.models import Prediction
from predictions.services.scoring import ScoreCalculator
from rankings.services.snapshot_service import SnapshotService


@receiver(post_save, sender=Match)
def update_predictions(sender, instance, **kwargs):
    if instance.finished:
        service = MatchResultService()
        service.update_match_result(instance)


@receiver(post_save, sender=Match)
def handle_match_finished(sender, instance, **kwargs):
    if not instance.finished or instance.points_calculated:
        return

    predictions = Prediction.objects.filter(
        match=instance
    ).select_related("user")

    calculator = ScoreCalculator()
    for prediction in predictions:
        prediction.points = calculator.calculate(prediction, instance)
        prediction.save()

    sender.objects.filter(id=instance.id).update(points_calculated=True)

    SnapshotService().create_snapshot()
