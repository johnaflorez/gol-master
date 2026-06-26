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


class FootballDataCommandForm(forms.Form):
    OPERATION_SYNC_LIVE = "sync_live_matches"
    OPERATION_MAP_MATCHES = "map_football_data_matches"
    OPERATION_IMPORT_MATCHES = "import_football_data_matches"
    OPERATION_REFRESH_SCORERS = "refresh_football_data_scorers"

    OPERATION_CHOICES = [
        (OPERATION_SYNC_LIVE, "Sincronizar marcadores en vivo"),
        (OPERATION_MAP_MATCHES, "Asignar football_data_match_id a partidos existentes"),
        (OPERATION_IMPORT_MATCHES, "Importar partidos faltantes desde football-data.org"),
        (OPERATION_REFRESH_SCORERS, "Actualizar tabla de goleadores"),
    ]

    STATUS_CHOICES = [
        ("", "Todos"),
        ("TIMED", "TIMED"),
        ("SCHEDULED", "SCHEDULED"),
        ("IN_PLAY", "IN_PLAY"),
        ("FINISHED", "FINISHED"),
    ]

    operation = forms.ChoiceField(
        choices=OPERATION_CHOICES,
        label="Acción",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        label="Fecha específica",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        help_text="Si se llena, ignora fecha inicial/final.",
    )
    from_date = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        label="Fecha inicial",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    to_date = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        label="Fecha final",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    commit = forms.BooleanField(
        required=False,
        label="Guardar cambios en la DB",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Déjalo desmarcado para ejecutar en modo prueba/dry-run cuando aplique.",
    )
    include_mapped = forms.BooleanField(
        required=False,
        label="Incluir partidos ya mapeados",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Solo aplica para asignar IDs a partidos existentes.",
    )
    status = forms.ChoiceField(
        required=False,
        choices=STATUS_CHOICES,
        label="Status football-data.org",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Solo aplica para importar partidos faltantes.",
    )
    days_back = forms.IntegerField(
        min_value=0,
        max_value=30,
        initial=1,
        label="Días hacia atrás",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Solo aplica para sincronizar marcadores en vivo.",
    )
    days_forward = forms.IntegerField(
        min_value=0,
        max_value=30,
        initial=1,
        label="Días hacia adelante",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Solo aplica para sincronizar marcadores en vivo.",
    )
    max_drift_minutes = forms.IntegerField(
        min_value=0,
        max_value=720,
        initial=180,
        label="Tolerancia horario (min)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Solo aplica para asignar IDs a partidos existentes.",
    )
    fetch_padding_days = forms.IntegerField(
        min_value=0,
        max_value=7,
        initial=1,
        label="Días extra consulta API",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Aplica para mapear/importar por diferencias UTC.",
    )

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        if from_date and to_date and from_date > to_date:
            raise forms.ValidationError("La fecha inicial no puede ser mayor que la fecha final.")
        return cleaned_data

    def build_command(self):
        operation = self.cleaned_data["operation"]

        if operation == self.OPERATION_SYNC_LIVE:
            return "sync_football_data", [
                "--live",
                "--days-back", str(self.cleaned_data["days_back"]),
                "--days-forward", str(self.cleaned_data["days_forward"]),
            ]

        if operation == self.OPERATION_MAP_MATCHES:
            args = [
                "--max-drift-minutes", str(self.cleaned_data["max_drift_minutes"]),
                "--fetch-padding-days", str(self.cleaned_data["fetch_padding_days"]),
            ]
            self._append_date_args(args)
            if self.cleaned_data.get("commit"):
                args.append("--commit")
            if self.cleaned_data.get("include_mapped"):
                args.append("--include-mapped")
            return "map_football_data_matches", args

        if operation == self.OPERATION_REFRESH_SCORERS:
            return "refresh_football_data_scorers", []

        args = ["--fetch-padding-days", str(self.cleaned_data["fetch_padding_days"])]
        self._append_date_args(args)
        if self.cleaned_data.get("status"):
            args.extend(["--status", self.cleaned_data["status"]])
        if self.cleaned_data.get("commit"):
            args.append("--commit")
        return "import_football_data_matches", args

    def _append_date_args(self, args):
        if self.cleaned_data.get("date"):
            args.extend(["--date", self.cleaned_data["date"].isoformat()])
            return
        if self.cleaned_data.get("from_date"):
            args.extend(["--from-date", self.cleaned_data["from_date"].isoformat()])
        if self.cleaned_data.get("to_date"):
            args.extend(["--to-date", self.cleaned_data["to_date"].isoformat()])


