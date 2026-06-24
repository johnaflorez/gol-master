from django import forms

from predictions.models import Prediction, TournamentPrediction
from teams.models import Player, Team


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
                    "class": "form-control text-center prediction-score-input",
                    "min": 0,
                    "inputmode": "numeric",
                    "placeholder": "0",
                }
            ),
            "predicted_away_score": forms.NumberInput(
                attrs={
                    "class": "form-control text-center prediction-score-input",
                    "min": 0,
                    "inputmode": "numeric",
                    "placeholder": "0",
                }
            ),
        }


class TournamentPredictionForm(forms.ModelForm):
    champion_team = forms.CharField(
        label="Selección campeona",
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "list": "champion-team-options",
                "placeholder": "Escribe o selecciona una selección...",
                "autocomplete": "off",
            }
        ),
    )
    top_scorer = forms.CharField(
        label="Goleador del mundial",
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "list": "top-scorer-options",
                "placeholder": "Escribe o selecciona un jugador...",
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = TournamentPrediction
        fields = ("champion_team", "top_scorer")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.team_options = list(Team.objects.order_by("name"))
        self.player_options = list(Player.objects.filter(active=True).select_related("team").order_by("team__name", "name"))

    def _strip_datalist_code(self, value):
        value = (value or "").strip()
        if " - " in value:
            return value.split(" - ", 1)[0].strip()
        return value

    def _parse_player_label(self, value):
        value = (value or "").strip()
        if " - " in value:
            value = value.split(" - ", 1)[0].strip()
        team_code = ""
        if value.endswith(")") and " (" in value:
            value, team_code = value.rsplit(" (", 1)
            value = value.strip()
            team_code = team_code[:-1].strip().upper()
        return value, team_code

    def clean_champion_team(self):
        raw_value = (self.cleaned_data.get("champion_team") or "").strip()
        if not raw_value:
            raise forms.ValidationError("Selecciona la selección campeona.")

        lookup = self._strip_datalist_code(raw_value)
        queryset = Team.objects.all()

        if lookup.isdigit():
            team = queryset.filter(id=int(lookup)).first()
            if team:
                return team

        team = queryset.filter(code__iexact=lookup).first() or queryset.filter(name__iexact=raw_value).first()
        if team:
            return team

        raise forms.ValidationError("Selecciona una selección válida de la lista.")

    def clean_top_scorer(self):
        raw_value = (self.cleaned_data.get("top_scorer") or "").strip()
        if not raw_value:
            raise forms.ValidationError("Selecciona el goleador del mundial.")

        lookup, team_code = self._parse_player_label(raw_value)
        queryset = Player.objects.filter(active=True).select_related("team")

        if lookup.isdigit():
            player = queryset.filter(id=int(lookup)).first()
            if player:
                return player

        player_queryset = queryset.filter(name__iexact=lookup)
        if team_code:
            player_queryset = player_queryset.filter(team__code__iexact=team_code)
        player = player_queryset.first()
        if player:
            return player

        raise forms.ValidationError("Selecciona un jugador válido de la lista.")

