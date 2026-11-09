"""The single gate that enforces every module's feature constraints."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from banxopen.foundation import RuleDecision, RuleOutcome
from banxopen.materials.core.assignment.planning import MaterialAssignmentRuleContext
from banxopen.materials.core.rules.features import ConstraintSeverity, MaterialConstraint
from banxopen.materials.core.rules.order import MaterialRuleOrder
from banxopen.materials.core.rules.ports import FeatureMaterialConstraintProvider
from banxopen.materials.model.materials import Material
from banxopen.materials.text import MaterialsText


class FeatureConstraintGateRule:
    """Blocks an assignment that the features already on the target body forbid.

    Ordered at `MaterialRuleOrder.Validation.FEATURE_CONSTRAINTS`, after the body-type restriction and before the
    reassignment confirmation: a material the body's features rule out is rejected outright, never confirmed. The rule
    set adds exactly one, fed by every module's providers; with none registered it always allows.
    """

    ID = "FEATURE_MATERIAL_CONSTRAINT"

    def __init__(
        self, providers: Iterable[FeatureMaterialConstraintProvider] = (), text: MaterialsText | None = None
    ) -> None:
        self._providers = tuple(providers)
        self._text = text or MaterialsText.DEFAULT

    @property
    def rule_id(self) -> str:
        return self.ID

    @property
    def order(self) -> int:
        return MaterialRuleOrder.Validation.FEATURE_CONSTRAINTS

    def evaluate(self, context: MaterialAssignmentRuleContext) -> RuleOutcome:
        """The first unsatisfied BLOCK constraint refuses the assignment, wherever it sits relative to warnings: a
        warning never masks a refusal. Without a refusal, unsatisfied WARN constraints produce one WARN outcome carrying
        every warning message, each also kept as its own outcome in `inner`. Every outcome from a constraint carries
        its `violation_args` plus `source` and `material`."""
        material = context.requested_material
        warnings: list[RuleOutcome] = []
        for provider in self._providers:
            for constraint in provider.constraints_for(context.target_body.id):
                if constraint.is_satisfied_by(material):
                    continue
                decision = RuleDecision.BLOCK if constraint.severity is ConstraintSeverity.BLOCK else RuleDecision.WARN
                outcome = RuleOutcome(
                    self.ID,
                    decision,
                    constraint.reason_code,
                    self._text.required_by(constraint.describe_violation(material), constraint.source_label),
                    args=_args_for(constraint, material),
                )
                if decision is RuleDecision.BLOCK:
                    return outcome
                warnings.append(outcome)

        if not warnings:
            return RuleOutcome(self.ID, RuleDecision.ALLOW, None, None)
        return RuleOutcome(
            self.ID,
            RuleDecision.WARN,
            warnings[0].reason_code,
            self._text.combine_warnings(w.message or "" for w in warnings),
            args=warnings[0].args,
            inner=tuple(warnings),
        )


def _args_for(constraint: MaterialConstraint, material: Material) -> Mapping[str, str]:
    args = dict(constraint.violation_args(material)) if constraint.violation_args is not None else {}
    args["source"] = constraint.source_label
    args["material"] = material.name
    return args
