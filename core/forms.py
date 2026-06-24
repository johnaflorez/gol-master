from django import forms

from core.models import Suggestion


class SuggestionForm(forms.ModelForm):
	class Meta:
		model = Suggestion
		fields = ["message"]
		widgets = {
			"message": forms.Textarea(
				attrs={
					"class": "form-control suggestion-textarea",
					"rows": 5,
					"placeholder": "Cuéntanos qué mejorarías, qué problema encontraste o qué idea tienes para la app...",
				}
			),
		}
		labels = {
			"message": "Tu sugerencia",
		}

