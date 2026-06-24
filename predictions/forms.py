from django import forms

from predictions.models import Prediction, TournamentPrediction
from teams.models import Team


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


class TournamentPredictionForm(forms.ModelForm):

    class Meta:
        model = TournamentPrediction
        fields = ("champion_team", "top_scorer_name")
        labels = {
            "champion_team": "Selección campeona",
            "top_scorer_name": "Goleador del mundial",
        }
        widgets = {
            "champion_team": forms.Select(
                attrs={
                    "class": "form-select form-select-lg",
                }
            ),
            "top_scorer_name": forms.TextInput(
                attrs={
                    "class": "form-control form-control-lg",
                    "placeholder": "Ej: Kylian Mbappé",
                    "maxlength": 120,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["champion_team"].queryset = Team.objects.order_by("name")
        self.fields["champion_team"].empty_label = "Selecciona una selección"

    def clean_top_scorer_name(self):
        value = (self.cleaned_data.get("top_scorer_name") or "").strip()
        if not value:
            raise forms.ValidationError("Ingresa el nombre del goleador.")
        return value
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

