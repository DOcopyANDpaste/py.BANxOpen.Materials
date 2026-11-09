"""Builders and fakes shared across the suite (ports of the C# TestFixtures and ConstraintFixtures)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, field

from banxopen.foundation import BodyId, BodyInfo, BodyKind, OperationResult, RuleDecision, RuleOutcome
from banxopen.materials import (
    BodyMaterialAssignment,
    ConstraintSeverity,
    ExecutablePlan,
    FeatureMaterialConstraintProvider,
    Material,
    MaterialAssignmentRuleContext,
    MaterialCategory,
    MaterialConstraint,
    MaterialId,
    MaterialLibrary,
    MaterialLibraryId,
    MaterialPropertyValue,
    MaterialValidationRule,
    PartChangeOutcome,
    PostAssignmentEffectRule,
    SideEffectInstruction,
)

CATEGORY = MaterialCategory("cat", "Category", ("Category",))


def make_material(
    name: str = "Steel",
    material_id: MaterialId | None = None,
    properties: Sequence[MaterialPropertyValue] = (),
    library: str = "lib",
    category: MaterialCategory = CATEGORY,
) -> Material:
    return Material(
        id=material_id or MaterialId(name),
        library_id=MaterialLibraryId(library),
        name=name,
        category=category,
        properties=tuple(properties),
    )


def make_body(body_id: str, kind: BodyKind = BodyKind.SOLID) -> BodyInfo:
    return BodyInfo(BodyId(body_id), body_id, kind, 1.0, {})


def context(
    material: Material,
    body: BodyInfo | None = None,
    current: BodyMaterialAssignment | None = None,
    batch: Sequence[BodyInfo] = (),
) -> MaterialAssignmentRuleContext:
    target = body or make_body("b1")
    return MaterialAssignmentRuleContext(
        requested_material=material,
        target_body=target,
        current_assignment=current,
        all_target_bodies_in_batch=tuple(batch),
    )


class FakeGateRule:
    """A gate rule with controllable behaviour and an invocation log."""

    def __init__(self, rule_id: str, order: int, evaluate: Callable[[MaterialAssignmentRuleContext], RuleOutcome]):
        self.rule_id = rule_id
        self.order = order
        self._evaluate = evaluate
        self.invoked_for_bodies: list[BodyId] = []

    def evaluate(self, context: MaterialAssignmentRuleContext) -> RuleOutcome:
        self.invoked_for_bodies.append(context.target_body.id)
        return self._evaluate(context)

    @staticmethod
    def always(rule_id: str, order: int, decision: RuleDecision = RuleDecision.ALLOW) -> FakeGateRule:
        code, message = {
            RuleDecision.ALLOW: (None, None),
            RuleDecision.BLOCK: ("BLOCKED", "blocked"),
            RuleDecision.REQUIRE_CONFIRMATION: ("CONFIRM", "confirm?"),
            RuleDecision.WARN: ("WARN", "careful"),
        }[decision]
        return FakeGateRule(rule_id, order, lambda _: RuleOutcome(rule_id, decision, code, message))


class FakeEffectRule:
    def __init__(
        self,
        rule_id: str,
        order: int,
        generate: Callable[[MaterialAssignmentRuleContext], Sequence[SideEffectInstruction]],
        instruction_types: Set[str] = frozenset(),
    ):
        self.rule_id = rule_id
        self.order = order
        self.instruction_types = instruction_types
        self._generate = generate
        self.invoked_for_bodies: list[BodyId] = []

    def generate_effects(self, context: MaterialAssignmentRuleContext) -> Sequence[SideEffectInstruction]:
        self.invoked_for_bodies.append(context.target_body.id)
        return self._generate(context)


def allow_only(source_label: str, reason_code: str, *allowed_names: str) -> MaterialConstraint:
    return MaterialConstraint(
        domain_id="TEST",
        source_label=source_label,
        reason_code=reason_code,
        is_satisfied_by=lambda m: m.name in allowed_names,
        describe_violation=lambda m: f"'{m.name}' is not allowed.",
    )


def warn_always(source_label: str, reason_code: str, message: str) -> MaterialConstraint:
    return MaterialConstraint(
        domain_id="TEST",
        source_label=source_label,
        reason_code=reason_code,
        is_satisfied_by=lambda _: False,
        describe_violation=lambda _: message,
        severity=ConstraintSeverity.WARN,
    )


class FakeConstraintProvider:
    """A fixed answer and a log of which bodies it was asked about."""

    def __init__(self, domain_id: str, *constraints: MaterialConstraint) -> None:
        self.domain_id = domain_id
        self._constraints = constraints
        self.queried_bodies: list[BodyId] = []

    def constraints_for(self, body_id: BodyId) -> Sequence[MaterialConstraint]:
        self.queried_bodies.append(body_id)
        return self._constraints


@dataclass
class FakeModule:
    module_id: str
    validation_rules: Sequence[MaterialValidationRule] = ()
    feature_constraints: Sequence[FeatureMaterialConstraintProvider] = ()
    side_effect_rules: Sequence[PostAssignmentEffectRule] = ()


@dataclass
class FakePartMaterialService:
    """An in-memory work part. `fail_on` makes apply/clear fail for those bodies, as NX would."""

    bodies: list[BodyInfo]
    assignments: dict[BodyId, BodyMaterialAssignment] = field(default_factory=dict)
    fail_on: Mapping[BodyId, str] = field(default_factory=dict)
    applied_plans: list[ExecutablePlan] = field(default_factory=list)
    cleared: list[list[BodyId]] = field(default_factory=list)
    resolution_libraries: list[MaterialLibrary] = field(default_factory=list)

    def get_bodies(self) -> Sequence[BodyInfo]:
        return list(self.bodies)

    def get_current_assignments(self) -> Mapping[BodyId, BodyMaterialAssignment]:
        return dict(self.assignments)

    def set_resolution_libraries(self, libraries: Sequence[MaterialLibrary]) -> None:
        self.resolution_libraries = list(libraries)

    def apply_plan(self, plan: ExecutablePlan) -> OperationResult[PartChangeOutcome]:
        self.applied_plans.append(plan)
        return self._outcome([a.body_id for a in plan.assignments])

    def clear_material(self, body_ids: Sequence[BodyId]) -> OperationResult[PartChangeOutcome]:
        self.cleared.append(list(body_ids))
        return self._outcome(body_ids)

    def _outcome(self, body_ids: Sequence[BodyId]) -> OperationResult[PartChangeOutcome]:
        failed = {b: self.fail_on[b] for b in body_ids if b in self.fail_on}
        if not failed:
            return OperationResult.success(PartChangeOutcome())
        return OperationResult(False, PartChangeOutcome(failed), "PARTIAL_FAILURE", "Some bodies failed.")
