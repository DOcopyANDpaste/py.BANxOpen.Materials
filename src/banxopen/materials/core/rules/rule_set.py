"""Every material rule an entry point enforces, composed from modules."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from banxopen.materials.core.assignment.pipeline import AssignmentPlanFinalizer, MaterialAssignmentPlanner
from banxopen.materials.core.rules.display import DisplayMaterialRuleModule
from banxopen.materials.core.rules.feature_gate import FeatureConstraintGateRule
from banxopen.materials.core.rules.material_forms import MaterialFormClassifier
from banxopen.materials.core.rules.ports import MaterialRuleModule, MaterialValidationRule, PostAssignmentEffectRule
from banxopen.materials.core.rules.sheet_metal import SheetMetalLibraries, SheetMetalLibraryRuleModule
from banxopen.materials.core.rules.standard import StandardRuleModule
from banxopen.materials.text import MaterialsText


class MaterialRuleSet:
    """The Material Assignment dialog and every feature tool that assigns material build their planner and finalizer
    from the same modules, instead of hand-assembled lists that drift apart.

    Composing checks what a hand-built list could not: a module or rule id registered twice (ValueError), and, through
    `ensure_executors_for`, a side effect nothing will carry out (RuntimeError). Both are wiring mistakes that would
    otherwise show up only as a rule quietly not applying. Feature constraints from every module are enforced by a
    single `FeatureConstraintGateRule`, so a refusal from one domain still beats a warning from another.
    """

    def __init__(self, modules: Sequence[MaterialRuleModule], text: MaterialsText | None) -> None:
        """Use `from_modules`, which validates the modules first."""
        self._modules = tuple(modules)
        gate = FeatureConstraintGateRule((p for m in self._modules for p in m.feature_constraints), text)
        rules: list[MaterialValidationRule] = [r for m in self._modules for r in m.validation_rules]
        rules.append(gate)
        self._validation_rules = tuple(sorted(rules, key=lambda r: r.order))
        self._side_effect_rules = tuple(
            sorted((r for m in self._modules for r in m.side_effect_rules), key=lambda r: r.order)
        )

    @staticmethod
    def baseline(
        sheet_metal_libraries: SheetMetalLibraries | None = None,
        text: MaterialsText | None = None,
        material_forms: MaterialFormClassifier | None = None,
    ) -> tuple[MaterialRuleModule, ...]:
        """The modules every entry point starts from: standard rules, display material, and the sheet metal library
        restriction. `sheet_metal_libraries` and `material_forms` normally come from the library rules file (see
        `MaterialEngine.create`); omitted, the name-based default and the `AllowedFor` property apply."""
        return (
            StandardRuleModule(text),
            DisplayMaterialRuleModule(text),
            SheetMetalLibraryRuleModule(sheet_metal_libraries, text, material_forms),
        )

    @staticmethod
    def from_modules(modules: Iterable[MaterialRuleModule], text: MaterialsText | None = None) -> MaterialRuleSet:
        """`text` words the feature gate's outcomes; the modules word their own. Raises ValueError when a module id,
        or a rule id, is registered more than once."""
        module_list = tuple(modules)
        seen_modules: set[str] = set()
        for module in module_list:
            if module.module_id.upper() in seen_modules:
                raise ValueError(f"Material rule module '{module.module_id}' is registered more than once.")
            seen_modules.add(module.module_id.upper())

        # The rule set adds the feature gate itself, so its id is taken before any module's rules are seen.
        owners: dict[str, str] = {FeatureConstraintGateRule.ID: "MaterialRuleSet"}
        for module in module_list:
            rule_ids = [r.rule_id for r in module.validation_rules] + [r.rule_id for r in module.side_effect_rules]
            for rule_id in rule_ids:
                owner = owners.get(rule_id)
                if owner is not None:
                    raise ValueError(
                        f"Rule id '{rule_id}' in module '{module.module_id}' is already registered by '{owner}'."
                    )
                owners[rule_id] = module.module_id
        return MaterialRuleSet(module_list, text)

    @property
    def modules(self) -> tuple[MaterialRuleModule, ...]:
        return self._modules

    @property
    def validation_rules(self) -> tuple[MaterialValidationRule, ...]:
        """Every validation rule in evaluation order, including the one feature constraint gate."""
        return self._validation_rules

    @property
    def side_effect_rules(self) -> tuple[PostAssignmentEffectRule, ...]:
        return self._side_effect_rules

    def create_planner(self) -> MaterialAssignmentPlanner:
        return MaterialAssignmentPlanner(self._validation_rules)

    def create_finalizer(self) -> AssignmentPlanFinalizer:
        return AssignmentPlanFinalizer(self._side_effect_rules)

    def ensure_executors_for(self, executor_instruction_types: Iterable[str]) -> None:
        """Raises RuntimeError listing each instruction type a registered side-effect rule can emit that has no
        executor, with the rule and module that emit it."""
        available = set(executor_instruction_types)
        missing = [
            f"'{instruction_type}' (emitted by {rule.rule_id} in module {module.module_id})"
            for module in self._modules
            for rule in module.side_effect_rules
            for instruction_type in sorted(rule.instruction_types)
            if instruction_type not in available
        ]
        if missing:
            raise RuntimeError(
                f"No side-effect executor is registered for {', '.join(missing)}. "
                "Register the executor with the module that owns the rule."
            )
