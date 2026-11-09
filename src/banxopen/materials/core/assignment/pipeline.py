"""The planner and finalizer: rules in, plain plans out."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Set
from dataclasses import dataclass

from banxopen.foundation import BodyId, BodyInfo, RuleDecision, RuleOutcome
from banxopen.materials.core.assignment.planning import (
    AssignmentPlan,
    BodyAssignmentEvaluation,
    ExecutableAssignment,
    ExecutablePlan,
    MaterialAssignmentPlanningInput,
    MaterialAssignmentRuleContext,
)
from banxopen.materials.core.rules.ports import MaterialValidationRule, PostAssignmentEffectRule


def _context(input: MaterialAssignmentPlanningInput, body: BodyInfo) -> MaterialAssignmentRuleContext:
    return MaterialAssignmentRuleContext(
        requested_material=input.requested_material,
        target_body=body,
        current_assignment=input.current_assignments.get(body.id),
        all_target_bodies_in_batch=input.target_bodies,
        requested_variant=input.requested_variant,
    )


class MaterialAssignmentPlanner:
    """Runs the ordered gate rules for every body and produces a pure `AssignmentPlan`: no side effects, no NX. A
    BLOCK outcome short-circuits the remaining rules for that body only; other bodies are still evaluated."""

    def __init__(self, gate_rules: Iterable[MaterialValidationRule]) -> None:
        self._gate_rules = sorted(gate_rules, key=lambda r: r.order)

    def plan(self, input: MaterialAssignmentPlanningInput) -> AssignmentPlan:
        evaluations: list[BodyAssignmentEvaluation] = []
        for body in input.target_bodies:
            context = _context(input, body)
            outcomes: list[RuleOutcome] = []
            for rule in self._gate_rules:
                outcome = rule.evaluate(context)
                outcomes.append(outcome)
                if outcome.decision is RuleDecision.BLOCK:
                    break
            evaluations.append(BodyAssignmentEvaluation(body.id, tuple(outcomes)))
        return AssignmentPlan(uuid.uuid4().hex, input.requested_material.id, tuple(evaluations))


@dataclass(frozen=True, slots=True)
class AssignmentTarget:
    """One body that is going ahead, with the evaluation that cleared it."""

    evaluation: BodyAssignmentEvaluation
    body: BodyInfo


@dataclass(frozen=True, slots=True)
class AssignmentTargetSet:
    to_assign: tuple[AssignmentTarget, ...]
    skipped_blocked: tuple[BodyId, ...]
    skipped_declined_confirmation: tuple[BodyId, ...]


def select_targets(
    plan: AssignmentPlan, input: MaterialAssignmentPlanningInput, confirmed_body_ids: Set[BodyId]
) -> AssignmentTargetSet:
    """Which of a plan's bodies will actually be assigned, given the user's confirm/decline answers."""
    bodies_by_id = {b.id: b for b in input.target_bodies}
    to_assign: list[AssignmentTarget] = []
    blocked: list[BodyId] = []
    declined: list[BodyId] = []
    for evaluation in plan.body_evaluations:
        if evaluation.is_blocked:
            blocked.append(evaluation.body_id)
            continue
        if evaluation.requires_confirmation and evaluation.body_id not in confirmed_body_ids:
            declined.append(evaluation.body_id)
            continue
        # A plan evaluated against a different input (the part was rescanned and a body disappeared) skips the body
        # rather than failing the whole plan: partial-apply semantics.
        body = bodies_by_id.get(evaluation.body_id)
        if body is None:
            blocked.append(evaluation.body_id)
            continue
        to_assign.append(AssignmentTarget(evaluation, body))
    return AssignmentTargetSet(tuple(to_assign), tuple(blocked), tuple(declined))


class AssignmentPlanFinalizer:
    """Turns a plan plus the user's confirm/decline answers into the single atomic `ExecutablePlan` for one Apply.
    Blocked and declined bodies are skipped and reported; the rest are assigned in the same plan."""

    def __init__(self, effect_rules: Iterable[PostAssignmentEffectRule]) -> None:
        self._effect_rules = sorted(effect_rules, key=lambda r: r.order)

    def finalize(
        self, plan: AssignmentPlan, input: MaterialAssignmentPlanningInput, confirmed_body_ids: Set[BodyId]
    ) -> ExecutablePlan:
        """`confirmed_body_ids` are the bodies the user confirmed, of those whose rules asked for it."""
        targets = select_targets(plan, input, confirmed_body_ids)
        assignments = tuple(
            ExecutableAssignment(
                target.body.id,
                plan.requested_material_id,
                tuple(
                    effect
                    for rule in self._effect_rules
                    for effect in rule.generate_effects(_context(input, target.body))
                ),
            )
            for target in targets.to_assign
        )
        return ExecutablePlan(plan.plan_id, assignments, targets.skipped_blocked, targets.skipped_declined_confirmation)
