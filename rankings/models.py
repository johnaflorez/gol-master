from django.db import models
from django.contrib.auth.models import User


class RankingSnapshot(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    points = models.IntegerField()
    position = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
