"""The extension points a rule category (a module) plugs into the material engine."""

from __future__ import annotations

from collections.abc import Sequence, Set
from typing import Protocol

from banxopen.foundation import BodyId, GateRule, RuleOutcome
from banxopen.materials.core.assignment.planning import MaterialAssignmentRuleContext, SideEffectInstruction
from banxopen.materials.core.rules.features import MaterialConstraint


class MaterialValidationRule(GateRule[MaterialAssignmentRuleContext, RuleOutcome], Protocol):
    """Decides whether an assignment is allowed, warned about, blocked, or needs user confirmation. Add a business rule
    by implementing this and registering it in the `MaterialRuleModule` for its category; the planner and every other
    rule stay untouched. Order it with `MaterialRuleOrder.Validation`."""


class PostAssignmentEffectRule(Protocol):
    """Given an assignment that IS going to happen, produces side-effect instructions for the adapter layer to carry
    out. Core never performs the effect; it only describes it as plain data."""

    @property
    def rule_id(self) -> str: ...

    @property
    def order(self) -> int:
        """Ascending; see `MaterialRuleOrder.SideEffect`."""
        ...

    @property
    def instruction_types(self) -> Set[str]:
        """Every instruction type this rule can emit. `MaterialRuleSet.ensure_executors_for` checks each has an
        executor, so a side effect cannot be registered without the code that carries it out."""
        ...

    def generate_effects(self, context: MaterialAssignmentRuleContext) -> Sequence[SideEffectInstruction]: ...


class FeatureMaterialConstraintProvider(Protocol):
    """Implemented once per feature domain to say what the features already on a body demand of its material. The
    engine calls this; it never learns what a bead, a louver or a casting is.

    Keep implementations pure: any NX access belongs behind a seam injected into the implementation. An empty list
    means "nothing to say about this body", which is indistinguishable from "could not tell", so a provider that fails
    to read the part should say so rather than return nothing: constraints that vanish fail open.
    """

    @property
    def domain_id(self) -> str:
        """Stable identifier for the domain, e.g. "SHEETMETAL.BEAD"."""
        ...

    def constraints_for(self, body_id: BodyId) -> Sequence[MaterialConstraint]: ...


class MaterialRuleModule(Protocol):
    """One category of material business rules (standard, display material, sheet metal, or a feature domain such as
    beads), holding everything that category enforces when a material is assigned.

    Where a new rule goes:
    - a check that allows, warns, asks, or refuses: a `MaterialValidationRule` in `validation_rules`;
    - a restriction that features already on the body place on its material: a `FeatureMaterialConstraintProvider` in
      `feature_constraints` (preferred for feature rules: the same predicate that refuses an assignment can filter the
      materials offered);
    - something to do once the assignment is going ahead: a `PostAssignmentEffectRule` in `side_effect_rules`, plus an
      executor for its instruction type on the NX side of the module.

    Unused collections are empty, never None.
    """

    @property
    def module_id(self) -> str:
        """Stable identifier, e.g. "DISPLAY" or "SHEETMETAL.BEAD". Unique within a rule set."""
        ...

    @property
    def validation_rules(self) -> Sequence[MaterialValidationRule]: ...

    @property
    def feature_constraints(self) -> Sequence[FeatureMaterialConstraintProvider]: ...

    @property
    def side_effect_rules(self) -> Sequence[PostAssignmentEffectRule]: ...
