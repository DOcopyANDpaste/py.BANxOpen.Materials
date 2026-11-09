"""The plain data the planner and finalizer pass around. No NX, nothing executed."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from banxopen.foundation import BodyId, BodyInfo, RuleDecision, RuleOutcome
from banxopen.materials.model.assignments import BodyMaterialAssignment
from banxopen.materials.model.materials import Material, MaterialId


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterialAssignmentPlanningInput:
    """`requested_variant` is which variant of the material the user picked, as the domain that offers variants names
    it (for sheet metal, the standards file row the Sheet Metal Preferences are set to). None when the material was
    picked on its own. Passed through to every rule unread."""

    requested_material: Material
    target_bodies: tuple[BodyInfo, ...]
    current_assignments: Mapping[BodyId, BodyMaterialAssignment]
    requested_variant: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterialAssignmentRuleContext:
    """Everything a rule needs to evaluate one (body, requested material) pair. `all_target_bodies_in_batch` gives
    rules the whole Apply batch for cross-body reasoning, though every decision is still per body."""

    requested_material: Material
    target_body: BodyInfo
    current_assignment: BodyMaterialAssignment | None
    all_target_bodies_in_batch: tuple[BodyInfo, ...]
    requested_variant: str | None = None


@dataclass(frozen=True, slots=True)
class BodyAssignmentEvaluation:
    """All rule outcomes for one body under one requested material."""

    body_id: BodyId
    rule_outcomes: tuple[RuleOutcome, ...]

    @property
    def is_blocked(self) -> bool:
        return any(o.decision is RuleDecision.BLOCK for o in self.rule_outcomes)

    @property
    def requires_confirmation(self) -> bool:
        return not self.is_blocked and any(o.decision is RuleDecision.REQUIRE_CONFIRMATION for o in self.rule_outcomes)

    @property
    def blocking_outcomes(self) -> tuple[RuleOutcome, ...]:
        return tuple(o for o in self.rule_outcomes if o.decision is RuleDecision.BLOCK)

    @property
    def confirmation_outcomes(self) -> tuple[RuleOutcome, ...]:
        return tuple(o for o in self.rule_outcomes if o.decision is RuleDecision.REQUIRE_CONFIRMATION)

    @property
    def warning_outcomes(self) -> tuple[RuleOutcome, ...]:
        return tuple(o for o in self.rule_outcomes if o.decision is RuleDecision.WARN)


@dataclass(frozen=True, slots=True)
class AssignmentPlan:
    """The pure "what would happen" of one Apply request, before confirmations are collected and side effects
    computed."""

    plan_id: str
    requested_material_id: MaterialId
    body_evaluations: tuple[BodyAssignmentEvaluation, ...]


@dataclass(frozen=True, slots=True)
class SideEffectInstruction:
    """An instruction for the adapter layer to carry out after a material is assigned to a body.

    `instruction_type` is a string discriminator, so new rules can introduce new types without editing this type.
    `data` values are `object` so a key can hold a structured value (e.g. an RGB triple); the producing rule and the
    consuming executor agree on each key's shape through the rule's public constants.
    """

    instruction_type: str
    body_id: BodyId
    data: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ExecutableAssignment:
    body_id: BodyId
    material_id: MaterialId
    side_effects: tuple[SideEffectInstruction, ...]


@dataclass(frozen=True, slots=True)
class ExecutablePlan:
    """The single atomic unit of work for one Apply: the part material service wraps it in one plan-wide undo scope,
    however many bodies were skipped as blocked or declined (partial-apply semantics)."""

    plan_id: str
    assignments: tuple[ExecutableAssignment, ...]
    skipped_blocked: tuple[BodyId, ...]
    skipped_declined_confirmation: tuple[BodyId, ...]
