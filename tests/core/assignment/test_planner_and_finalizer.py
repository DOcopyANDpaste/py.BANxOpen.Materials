from banxopen.foundation import BodyId, RuleDecision, RuleOutcome
from banxopen.materials import (
    AssignmentPlan,
    AssignmentPlanFinalizer,
    BodyAssignmentEvaluation,
    MaterialAssignmentPlanner,
    MaterialAssignmentPlanningInput,
    MaterialId,
    SideEffectInstruction,
)

from builders import FakeEffectRule, FakeGateRule, make_body, make_material


def planning_input(*body_ids: str, variant: str | None = None) -> MaterialAssignmentPlanningInput:
    return MaterialAssignmentPlanningInput(
        requested_material=make_material(),
        target_bodies=tuple(make_body(b) for b in body_ids),
        current_assignments={},
        requested_variant=variant,
    )


def make_plan(*evaluations: BodyAssignmentEvaluation) -> AssignmentPlan:
    return AssignmentPlan("plan-1", MaterialId("mat"), evaluations)


def evaluation(body_id: str, decision: RuleDecision) -> BodyAssignmentEvaluation:
    codes = {
        RuleDecision.ALLOW: (None, None),
        RuleDecision.BLOCK: ("X", "x"),
        RuleDecision.REQUIRE_CONFIRMATION: ("C", "c"),
    }
    code, message = codes[decision]
    return BodyAssignmentEvaluation(BodyId(body_id), (RuleOutcome("r", decision, code, message),))


# ---- MaterialAssignmentPlannerTests ----


def test_plan_produces_one_evaluation_per_target_body():
    planner = MaterialAssignmentPlanner([FakeGateRule.always("r1", 100)])

    plan = planner.plan(planning_input("b1", "b2", "b3"))

    assert [e.body_id.value for e in plan.body_evaluations] == ["b1", "b2", "b3"]


def test_plan_runs_rules_in_ascending_order_regardless_of_registration_order():
    log: list[str] = []

    def logged(name: str, order: int) -> FakeGateRule:
        def evaluate(_):
            log.append(name)
            return RuleOutcome(name, RuleDecision.ALLOW, None, None)

        return FakeGateRule(name, order, evaluate)

    planner = MaterialAssignmentPlanner([logged("late", 300), logged("early", 100), logged("mid", 200)])

    planner.plan(planning_input("b1"))

    assert log == ["early", "mid", "late"]


def test_plan_block_short_circuits_remaining_rules_for_that_body_only():
    blocker = FakeGateRule(
        "blocker",
        100,
        lambda ctx: (
            RuleOutcome("blocker", RuleDecision.BLOCK, "X", "x")
            if ctx.target_body.id.value == "blocked"
            else RuleOutcome("blocker", RuleDecision.ALLOW, None, None)
        ),
    )
    tracker = FakeGateRule.always("later", 200)

    plan = MaterialAssignmentPlanner([blocker, tracker]).plan(planning_input("blocked", "clean"))

    blocked, clean = plan.body_evaluations
    assert blocked.is_blocked
    assert len(blocked.rule_outcomes) == 1  # "later" never ran for the blocked body
    assert not clean.is_blocked
    assert len(clean.rule_outcomes) == 2
    assert BodyId("clean") in tracker.invoked_for_bodies


def test_plan_passes_the_requested_variant_to_the_gate_rules():
    seen: list[str | None] = []

    def evaluate(ctx):
        seen.append(ctx.requested_variant)
        return RuleOutcome("r1", RuleDecision.ALLOW, None, None)

    MaterialAssignmentPlanner([FakeGateRule("r1", 100, evaluate)]).plan(planning_input("b1", variant="row-1"))

    assert seen == ["row-1"]


# ---- AssignmentPlanFinalizerTests ----


def test_finalize_partial_apply_skips_blocked_and_declined_but_applies_the_rest():
    plan = make_plan(
        evaluation("clean", RuleDecision.ALLOW),
        evaluation("blocked", RuleDecision.BLOCK),
        evaluation("declined", RuleDecision.REQUIRE_CONFIRMATION),
        evaluation("confirmed", RuleDecision.REQUIRE_CONFIRMATION),
    )

    executable = AssignmentPlanFinalizer([]).finalize(
        plan, planning_input("clean", "blocked", "declined", "confirmed"), {BodyId("confirmed")}
    )

    assert [a.body_id.value for a in executable.assignments] == ["clean", "confirmed"]
    assert [b.value for b in executable.skipped_blocked] == ["blocked"]
    assert [b.value for b in executable.skipped_declined_confirmation] == ["declined"]


def test_finalize_skips_bodies_missing_from_the_input_instead_of_throwing():
    # The part can be rescanned between planning and finalizing, dropping a body the plan still names.
    plan = make_plan(evaluation("present", RuleDecision.ALLOW), evaluation("vanished", RuleDecision.ALLOW))

    executable = AssignmentPlanFinalizer([]).finalize(plan, planning_input("present"), set())

    assert [a.body_id.value for a in executable.assignments] == ["present"]
    assert [b.value for b in executable.skipped_blocked] == ["vanished"]


def test_finalize_preserves_plan_id_on_the_executable_plan():
    plan = make_plan(evaluation("b1", RuleDecision.ALLOW))

    assert AssignmentPlanFinalizer([]).finalize(plan, planning_input("b1"), set()).plan_id == plan.plan_id


def test_finalize_only_runs_effect_rules_for_bodies_that_are_actually_assigned():
    plan = make_plan(evaluation("clean", RuleDecision.ALLOW), evaluation("blocked", RuleDecision.BLOCK))
    effect = FakeEffectRule("effect", 100, lambda _: ())

    AssignmentPlanFinalizer([effect]).finalize(plan, planning_input("clean", "blocked"), set())

    assert [b.value for b in effect.invoked_for_bodies] == ["clean"]


def test_finalize_aggregates_side_effects_from_multiple_effect_rules_onto_the_same_assignment():
    plan = make_plan(evaluation("b1", RuleDecision.ALLOW))
    effect_a = FakeEffectRule("a", 100, lambda ctx: (SideEffectInstruction("TYPE_A", ctx.target_body.id, {}),))
    effect_b = FakeEffectRule("b", 200, lambda ctx: (SideEffectInstruction("TYPE_B", ctx.target_body.id, {}),))

    executable = AssignmentPlanFinalizer([effect_b, effect_a]).finalize(plan, planning_input("b1"), set())

    (assignment,) = executable.assignments
    assert [e.instruction_type for e in assignment.side_effects] == ["TYPE_A", "TYPE_B"]


def test_finalize_passes_the_requested_variant_to_the_effect_rules():
    seen: list[str | None] = []

    def generate(ctx):
        seen.append(ctx.requested_variant)
        return ()

    AssignmentPlanFinalizer([FakeEffectRule("effect", 100, generate)]).finalize(
        make_plan(evaluation("b1", RuleDecision.ALLOW)), planning_input("b1", variant="row-1"), set()
    )

    assert seen == ["row-1"]
