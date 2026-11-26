from __future__ import annotations

import pytest

from banxopen.foundation import BodyId, RuleDecision
from banxopen.materials import (
    MaterialAssignmentPlanningInput,
    MaterialRuleModule,
    MaterialRuleOrder,
    MaterialRuleSet,
    SideEffectInstruction,
)
from banxopen.materials.core.rules.display import DisplayMaterialRuleModule, SyncCoatingDisplayMaterialEffectRule
from banxopen.materials.core.rules.feature_gate import FeatureConstraintGateRule
from banxopen.materials.core.rules.standard import RequireConfirmationOnReassignmentRule, StandardRuleModule

from builders import (
    FakeConstraintProvider,
    FakeEffectRule,
    FakeGateRule,
    FakeModule,
    allow_only,
    context,
    make_body,
    make_material,
)

DOMAIN_INSTRUCTION_TYPE = "DOMAIN_SYNC"


def baseline_with(*domains: MaterialRuleModule) -> MaterialRuleSet:
    return MaterialRuleSet.from_modules((*MaterialRuleSet.baseline(), *domains))


def domain_effect() -> FakeEffectRule:
    return FakeEffectRule(
        "DOMAIN_SYNC_RULE",
        MaterialRuleOrder.SideEffect.DOMAIN_STATE,
        lambda ctx: (SideEffectInstruction(DOMAIN_INSTRUCTION_TYPE, ctx.target_body.id, {}),),
        frozenset({DOMAIN_INSTRUCTION_TYPE}),
    )


def gate(rules: MaterialRuleSet) -> FeatureConstraintGateRule:
    (found,) = [r for r in rules.validation_rules if isinstance(r, FeatureConstraintGateRule)]
    return found


def test_baseline_runs_the_validation_rules_the_standard_set_always_ran_in_the_same_order():
    assert [r.rule_id for r in baseline_with().validation_rules] == [
        "BLOCK_BODY_TYPE_RESTRICTION",
        "FEATURE_MATERIAL_CONSTRAINT",
        "CONFIRM_REASSIGNMENT",
        "VALIDATE_COATING_DISPLAY_MATERIAL",
    ]


def test_baseline_side_effects_are_display_material_sync_only():
    assert [r.rule_id for r in baseline_with().side_effect_rules] == ["SYNC_COATING_DISPLAY_MATERIAL"]


def test_validation_rules_are_returned_in_ascending_order():
    orders = [r.order for r in baseline_with().validation_rules]
    assert orders == sorted(orders)


def test_feature_constraints_are_gated_before_any_rule_that_asks_the_user_a_question():
    rules = baseline_with().validation_rules
    (confirmation,) = [r for r in rules if isinstance(r, RequireConfirmationOnReassignmentRule)]
    assert gate(baseline_with()).order < confirmation.order


def test_without_feature_constraints_the_gate_is_a_no_op():
    assert gate(baseline_with()).evaluate(context(make_material("Anything"))).decision is RuleDecision.ALLOW


def test_feature_constraints_from_every_module_reach_one_gate():
    permissive = FakeConstraintProvider("A", allow_only("SPEC A", "NOT_ALLOWED", "7075-T6"))
    restrictive = FakeConstraintProvider("B", allow_only("SPEC B", "NOT_ALLOWED", "2024-O"))
    rules = baseline_with(
        FakeModule("TEST.A", feature_constraints=[permissive]), FakeModule("TEST.B", feature_constraints=[restrictive])
    )

    assert gate(rules).evaluate(context(make_material("7075-T6"))).decision is RuleDecision.BLOCK
    assert len(permissive.queried_bodies) == 1
    assert len(restrictive.queried_bodies) == 1


def test_coating_sync_is_registered_so_every_entry_point_colours_bodies_the_same_way():
    assert any(isinstance(r, SyncCoatingDisplayMaterialEffectRule) for r in baseline_with().side_effect_rules)


def test_a_domain_side_effect_runs_after_display_material_sync():
    rules = baseline_with(FakeModule("TEST.DOMAIN", side_effect_rules=[domain_effect()]))

    assert [r.rule_id for r in rules.side_effect_rules] == ["SYNC_COATING_DISPLAY_MATERIAL", "DOMAIN_SYNC_RULE"]


def test_the_finalizer_carries_side_effects_from_every_module():
    rules = baseline_with(FakeModule("TEST.DOMAIN", side_effect_rules=[domain_effect()]))
    planning_input = MaterialAssignmentPlanningInput(
        requested_material=make_material("Steel"), target_bodies=(make_body("body-1"),), current_assignments={}
    )

    executable = rules.create_finalizer().finalize(rules.create_planner().plan(planning_input), planning_input, set())

    (assignment,) = executable.assignments
    assert [e.instruction_type for e in assignment.side_effects] == [
        SyncCoatingDisplayMaterialEffectRule.INSTRUCTION_TYPE,
        DOMAIN_INSTRUCTION_TYPE,
    ]


def test_a_module_registered_twice_is_refused():
    with pytest.raises(ValueError, match=DisplayMaterialRuleModule.ID):
        baseline_with(FakeModule(DisplayMaterialRuleModule.ID))


def test_module_ids_are_compared_ignoring_case():
    with pytest.raises(ValueError, match="registered more than once"):
        baseline_with(FakeModule("display"))


def test_a_rule_id_already_registered_by_another_module_is_refused():
    duplicate = FakeGateRule.always("CONFIRM_REASSIGNMENT", 500)

    with pytest.raises(ValueError, match="CONFIRM_REASSIGNMENT") as raised:
        baseline_with(FakeModule("TEST.DOMAIN", validation_rules=[duplicate]))
    assert StandardRuleModule.ID in str(raised.value)


def test_a_module_cannot_add_a_second_feature_constraint_gate():
    # Feature rules go in feature_constraints; a second gate would split block-beats-warn across two rules.
    with pytest.raises(ValueError):
        baseline_with(FakeModule("TEST.DOMAIN", validation_rules=[FeatureConstraintGateRule()]))


def test_a_side_effect_with_no_executor_is_refused_naming_its_type_and_module():
    rules = baseline_with(FakeModule("TEST.DOMAIN", side_effect_rules=[domain_effect()]))

    with pytest.raises(RuntimeError) as raised:
        rules.ensure_executors_for([SyncCoatingDisplayMaterialEffectRule.INSTRUCTION_TYPE])
    assert DOMAIN_INSTRUCTION_TYPE in str(raised.value)
    assert "TEST.DOMAIN" in str(raised.value)


def test_the_baseline_display_sync_needs_its_executor_too():
    with pytest.raises(RuntimeError, match=SyncCoatingDisplayMaterialEffectRule.INSTRUCTION_TYPE):
        baseline_with().ensure_executors_for([])


def test_executors_covering_every_emitted_type_are_accepted():
    rules = baseline_with(FakeModule("TEST.DOMAIN", side_effect_rules=[domain_effect()]))

    rules.ensure_executors_for([SyncCoatingDisplayMaterialEffectRule.INSTRUCTION_TYPE, DOMAIN_INSTRUCTION_TYPE])


def test_a_planner_built_from_the_baseline_plans_every_body():
    plan = (
        baseline_with()
        .create_planner()
        .plan(
            MaterialAssignmentPlanningInput(
                requested_material=make_material("Steel"), target_bodies=(make_body("b1"),), current_assignments={}
            )
        )
    )

    assert [e.body_id for e in plan.body_evaluations] == [BodyId("b1")]
