import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from matches.models import Match


class Command(BaseCommand):
    help = (
        "Asigna posiciones visuales del bracket desde un JSON. "
        "Por defecto es dry-run; usa --commit para guardar."
    )

    def add_arguments(self, parser):
        parser.add_argument("json_file", help="Ruta al archivo JSON con posiciones del bracket.")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Guarda los cambios. Sin esta opción solo muestra lo que haría.",
        )

    def handle(self, *args, **options):
        path = Path(options["json_file"])
        if not path.exists():
            raise CommandError(f"No existe el archivo JSON: {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON inválido: {exc}") from exc

        assignments = self._parse_assignments(payload)
        mode = "COMMIT" if options["commit"] else "DRY-RUN"
        updated = 0
        skipped = 0

        self.stdout.write(f"assign bracket positions {mode}: assignments={len(assignments)}")

        for assignment in assignments:
            match = self._find_match(assignment)
            if not match:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"SIN MATCH: {assignment}"))
                continue

            changes = {}
            position = assignment["position"]
            phase = assignment.get("phase")
            if match.bracket_position != position:
                changes["bracket_position"] = position
            if phase and match.phase != phase:
                changes["phase"] = phase

            if not changes:
                skipped += 1
                if options.get("verbosity", 1) >= 2:
                    self.stdout.write(f"SIN CAMBIOS: match_id={match.id} position={position}")
                continue

            self.stdout.write(
                "SET: "
                f"match_id={match.id} football_data_match_id={match.football_data_match_id or '-'} "
                f"phase={phase or match.phase} bracket_position={position} | {match}"
            )
            if options["commit"]:
                for field, value in changes.items():
                    setattr(match, field, value)
                match.save(update_fields=[*changes.keys()])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"assign bracket positions OK: mode={mode}, updated={updated}, skipped={skipped}"
            )
        )

    def _parse_assignments(self, payload):
        if isinstance(payload, list):
            return [self._normalize_assignment(item) for item in payload]

        if not isinstance(payload, dict):
            raise CommandError("El JSON debe ser una lista o un objeto.")

        if "matches" in payload:
            matches = payload["matches"]
            if not isinstance(matches, list):
                raise CommandError("La llave 'matches' debe ser una lista.")
            return [self._normalize_assignment(item) for item in matches]

        assignments = []
        for phase, slots in payload.items():
            if not isinstance(slots, dict):
                raise CommandError(f"La fase {phase} debe contener un objeto de posiciones.")
            for raw_position, value in slots.items():
                try:
                    position = int(raw_position)
                except (TypeError, ValueError) as exc:
                    raise CommandError(f"Posición inválida en fase {phase}: {raw_position}") from exc

                if isinstance(value, dict):
                    item = {**value, "phase": phase, "position": position}
                else:
                    item = {"phase": phase, "position": position, "football_data_match_id": value}
                assignments.append(self._normalize_assignment(item))
        return assignments

    def _normalize_assignment(self, item):
        if not isinstance(item, dict):
            raise CommandError(f"Asignación inválida: {item}")

        try:
            position = int(item["position"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CommandError(f"Asignación sin position numérico: {item}") from exc

        if position < 1:
            raise CommandError(f"position debe ser mayor a cero: {item}")

        assignment = {"position": position}
        if item.get("phase"):
            assignment["phase"] = str(item["phase"]).strip().upper()
        if item.get("id"):
            assignment["id"] = int(item["id"])
        if item.get("football_data_match_id"):
            assignment["football_data_match_id"] = int(item["football_data_match_id"])

        if "id" not in assignment and "football_data_match_id" not in assignment:
            raise CommandError(f"Asignación sin id ni football_data_match_id: {item}")
        return assignment

    def _find_match(self, assignment):
        if assignment.get("football_data_match_id"):
            match = Match.objects.filter(football_data_match_id=assignment["football_data_match_id"]).first()
            if match:
                return match
        if assignment.get("id"):
            return Match.objects.filter(id=assignment["id"]).first()
        return None

