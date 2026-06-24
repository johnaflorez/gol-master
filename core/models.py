from django.db import models
from django.conf import settings


class Suggestion(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="suggestions", on_delete=models.CASCADE)
	message = models.TextField("Sugerencia")
	is_resolved = models.BooleanField("Solucionado/Revisado", default=False)
	created_at = models.DateTimeField("Creado", auto_now_add=True)
	updated_at = models.DateTimeField("Actualizado", auto_now=True)

	class Meta:
		ordering = ["is_resolved", "-created_at"]
		verbose_name = "Sugerencia"
		verbose_name_plural = "Sugerencias"

	def __str__(self):
		return f"Sugerencia de {self.user} - {self.created_at:%d/%m/%Y}"
