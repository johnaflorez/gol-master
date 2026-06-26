from dataclasses import dataclass

from django.utils import timezone

from matches.models import Match


@dataclass(frozen=True)
class KnockoutPhase:
	code: str
	label: str
	short_label: str
	expected_matches: int


KNOCKOUT_PHASES = [
	KnockoutPhase("DR", "Dieciséisavos de Final", "16avos", 16),
	KnockoutPhase("OF", "Octavos de Final", "Octavos", 8),
	KnockoutPhase("CF", "Cuartos de Final", "Cuartos", 4),
	KnockoutPhase("SF", "Semifinal", "Semis", 2),
	KnockoutPhase("F", "Final", "Final", 1),
]


class KnockoutBracketService:
	"""Builds a read-only knockout bracket from existing Match records."""

	def get_bracket(self):
		matches_by_phase = self._get_matches_by_phase()
		phases = []
		total_matches = 0

		for phase in KNOCKOUT_PHASES:
			phase_matches = matches_by_phase.get(phase.code, [])
			total_matches += len(phase_matches)
			phases.append(
				{
					"code": phase.code,
					"label": phase.label,
					"short_label": phase.short_label,
					"expected_matches": phase.expected_matches,
					"matches_count": len(phase_matches),
					"slots": self._build_slots(phase, phase_matches),
				}
			)

		return {
			"phases": phases,
			"layout_columns": self._build_traditional_layout(phases),
			"total_matches": total_matches,
			"has_matches": total_matches > 0,
			"generated_at": timezone.now(),
		}

	def _build_traditional_layout(self, phases):
		phase_by_code = {phase["code"]: phase for phase in phases}
		left_codes = ["DR", "OF", "CF", "SF"]
		right_codes = ["SF", "CF", "OF", "DR"]
		columns = []

		for code in left_codes:
			phase = phase_by_code[code]
			columns.append(self._build_layout_column(phase, "left", self._split_slots(phase["slots"], "left")))

		final_phase = phase_by_code["F"]
		columns.append(self._build_layout_column(final_phase, "center", final_phase["slots"]))

		for code in right_codes:
			phase = phase_by_code[code]
			columns.append(self._build_layout_column(phase, "right", self._split_slots(phase["slots"], "right")))

		return columns

	def _build_layout_column(self, phase, side, slots):
		return {
			"code": phase["code"],
			"label": phase["label"],
			"short_label": phase["short_label"],
			"side": side,
			"matches_count": len([slot for slot in slots if slot["match"]]),
			"slots": slots,
		}

	def _split_slots(self, slots, side):
		middle = (len(slots) + 1) // 2
		return slots[:middle] if side == "left" else slots[middle:]

	def _get_matches_by_phase(self):
		phase_codes = [phase.code for phase in KNOCKOUT_PHASES]
		matches = (
			Match.objects.filter(phase__in=phase_codes)
			.select_related("home_team", "away_team")
			.order_by("kickoff_at", "id")
		)
		grouped = {phase_code: [] for phase_code in phase_codes}
		for match in matches:
			grouped.setdefault(match.phase, []).append(match)
		return grouped

	def _build_slots(self, phase, matches):
		slot_count = max(phase.expected_matches, len(matches))
		slots = []
		for index in range(slot_count):
			match = matches[index] if index < len(matches) else None
			slots.append(self._build_slot(index + 1, match))
		return slots

	def _build_slot(self, position, match):
		if not match:
			return {
				"position": position,
				"match": None,
				"status_label": "Por definir",
				"status_class": "text-bg-light",
				"winner_side": "",
				"winner_team": None,
			}

		winner_side = ""
		winner_team = None
		if match.finished and match.home_score != match.away_score:
			if match.home_score > match.away_score:
				winner_side = "home"
				winner_team = match.home_team
			else:
				winner_side = "away"
				winner_team = match.away_team

		return {
			"position": position,
			"match": match,
			"status_label": self._get_status_label(match),
			"status_class": self._get_status_class(match),
			"winner_side": winner_side,
			"winner_team": winner_team,
		}

	def _get_status_label(self, match):
		if match.finished:
			return "Finalizado"
		if match.live_status in {"LIVE", "HT"}:
			return "En juego"
		if match.kickoff_at <= timezone.now():
			return "En juego"
		return "Por jugar"

	def _get_status_class(self, match):
		if match.finished:
			return "text-bg-primary"
		if match.live_status in {"LIVE", "HT"} or match.kickoff_at <= timezone.now():
			return "text-bg-success"
		return "text-bg-light"

