"""A plan flattened to one verdict per body: what a tool shows before anything is applied."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from banxopen.foundation import RuleOutcome
from banxopen.materials.core.assignment.planning import AssignmentPlan, MaterialAssignmentPlanningInput
from banxopen.materials.model.assignments import BodyVerdict, VerdictStatus
from banxopen.materials.text import MaterialsText


@dataclass(frozen=True, slots=True)
class PlannedAssignment:
    """A planned (not applied) assignment: the plan, its input, and one verdict per target body in target order."""

    input: MaterialAssignmentPlanningInput
    plan: AssignmentPlan
    verdicts: tuple[BodyVerdict, ...]

    @property
    def needing_confirmation(self) -> tuple[BodyVerdict, ...]:
        return tuple(v for v in self.verdicts if v.status is VerdictStatus.NEEDS_CONFIRMATION)

    @property
    def blocked(self) -> tuple[BodyVerdict, ...]:
        return tuple(v for v in self.verdicts if v.status is VerdictStatus.BLOCKED)


def verdicts_for(
    input: MaterialAssignmentPlanningInput, plan: AssignmentPlan, text: MaterialsText | None = None
) -> tuple[BodyVerdict, ...]:
    """One verdict per target body: BLOCKED with the blocking messages, NEEDS_CONFIRMATION with the questions, or OK
    with any warnings, since warnings gate nothing but are the only thing the user would otherwise never see. A body
    with no evaluation had no rule to say otherwise, so it is OK."""
    text = text or MaterialsText.DEFAULT
    evaluations = {e.body_id: e for e in plan.body_evaluations}
    verdicts: list[BodyVerdict] = []
    for body in input.target_bodies:
        evaluation = evaluations.get(body.id)
        if evaluation is None:
            verdicts.append(BodyVerdict(body, VerdictStatus.OK, None))
        elif evaluation.is_blocked:
            verdicts.append(BodyVerdict(body, VerdictStatus.BLOCKED, _describe(evaluation.blocking_outcomes, text)))
        elif evaluation.requires_confirmation:
            verdicts.append(
                BodyVerdict(body, VerdictStatus.NEEDS_CONFIRMATION, _describe(evaluation.confirmation_outcomes, text))
            )
        else:
            verdicts.append(BodyVerdict(body, VerdictStatus.OK, _describe(evaluation.warning_outcomes, text)))
    return tuple(verdicts)


def _describe(outcomes: Sequence[RuleOutcome], text: MaterialsText) -> str | None:
    """The outcomes' messages as their rules worded them."""
    messages = [o.message for o in outcomes if o.message and o.message.strip()]
    return text.combine_outcome_messages(messages) if messages else None
