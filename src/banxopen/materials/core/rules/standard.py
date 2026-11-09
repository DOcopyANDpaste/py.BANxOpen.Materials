"""Rules that apply to every material assignment regardless of material, body or feature."""

from __future__ import annotations

from collections.abc import Sequence

from banxopen.foundation import RuleDecision, RuleOutcome
from banxopen.materials.codes import MaterialsCodes
from banxopen.materials.core.assignment.planning import MaterialAssignmentRuleContext
from banxopen.materials.core.rules.order import MaterialRuleOrder
from banxopen.materials.core.rules.ports import (
    FeatureMaterialConstraintProvider,
    MaterialValidationRule,
    PostAssignmentEffectRule,
)
from banxopen.materials.model.materials import same_text
from banxopen.materials.text import MaterialsText


class RequireConfirmationOnReassignmentRule:
    """If the body already has a different material, the user confirms the overwrite before it proceeds."""

    rule_id = "CONFIRM_REASSIGNMENT"
    order = MaterialRuleOrder.Validation.CONFIRMATION

    def __init__(self, text: MaterialsText | None = None) -> None:
        self._text = text or MaterialsText.DEFAULT

    def evaluate(self, context: MaterialAssignmentRuleContext) -> RuleOutcome:
        current = context.current_assignment.material_name if context.current_assignment else None
        requested = context.requested_material.name
        if not current or same_text(current, requested):
            return RuleOutcome(self.rule_id, RuleDecision.ALLOW, None, None)
        return RuleOutcome(
            self.rule_id,
            RuleDecision.REQUIRE_CONFIRMATION,
            MaterialsCodes.REASSIGN,
            self._text.reassign(current, requested),
            args={"current": current, "requested": requested},
        )


class StandardRuleModule:
    ID = "STANDARD"

    def __init__(self, text: MaterialsText | None = None) -> None:
        self._validation: tuple[MaterialValidationRule, ...] = (RequireConfirmationOnReassignmentRule(text),)

    @property
    def module_id(self) -> str:
        return self.ID

    @property
    def validation_rules(self) -> Sequence[MaterialValidationRule]:
        return self._validation

    @property
    def feature_constraints(self) -> Sequence[FeatureMaterialConstraintProvider]:
        return ()

    @property
    def side_effect_rules(self) -> Sequence[PostAssignmentEffectRule]:
        return ()
