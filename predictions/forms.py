from django import forms

from predictions.models import Prediction


class PredictionForm(forms.ModelForm):

    class Meta:
        model = Prediction

        fields = (
            "predicted_home_score",
            "predicted_away_score"
        )

        labels = {
            "predicted_home_score": "Goles local",
            "predicted_away_score": "Goles visitante",
        }

        widgets = {
            "predicted_home_score": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-lg text-center",
                    "min": 0,
                    "placeholder": "0",
                }
            ),
            "predicted_away_score": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-lg text-center",
                    "min": 0,
                    "placeholder": "0",
                }
            ),
        }

