from dataclasses import replace

from banxopen.foundation import BodyId, RuleDecision
from banxopen.materials.core.rules.feature_gate import FeatureConstraintGateRule

from builders import FakeConstraintProvider, allow_only, context, make_body, make_material, warn_always


def evaluate(rule: FeatureConstraintGateRule, material_name: str):
    body = make_body("body-1")
    return rule.evaluate(context(make_material(material_name), body, batch=(body,)))


def test_allows_when_no_providers_are_registered():
    assert evaluate(FeatureConstraintGateRule(), "Anything").decision is RuleDecision.ALLOW


def test_allows_when_a_provider_has_nothing_to_say_about_the_body():
    assert (
        evaluate(FeatureConstraintGateRule([FakeConstraintProvider("BEAD")]), "Anything").decision is RuleDecision.ALLOW
    )


def test_allows_a_material_that_satisfies_every_constraint():
    rule = FeatureConstraintGateRule(
        [FakeConstraintProvider("BEAD", allow_only("SPEC BA-1", "NOT_ALLOWED", "2024-O", "5052-O"))]
    )

    assert evaluate(rule, "5052-O").decision is RuleDecision.ALLOW


def test_blocks_a_material_a_constraint_rejects_and_reports_its_reason_code():
    rule = FeatureConstraintGateRule(
        [FakeConstraintProvider("BEAD", allow_only("SPEC BA-1", "MATERIAL_NOT_ALLOWED_BY_BEAD", "2024-O"))]
    )

    outcome = evaluate(rule, "7075-T6")

    assert outcome.decision is RuleDecision.BLOCK
    assert outcome.reason_code == "MATERIAL_NOT_ALLOWED_BY_BEAD"


def test_block_message_names_the_material_and_the_feature_responsible():
    rule = FeatureConstraintGateRule(
        [FakeConstraintProvider("BEAD", allow_only("Bead SPEC BA-1234", "NOT_ALLOWED", "2024-O"))]
    )

    message = evaluate(rule, "7075-T6").message or ""

    assert "7075-T6" in message
    assert "Bead SPEC BA-1234" in message


def test_reports_the_first_violated_constraint_when_several_fail():
    rule = FeatureConstraintGateRule(
        [
            FakeConstraintProvider(
                "BEAD", allow_only("SPEC BA-1", "FIRST", "2024-O"), allow_only("SPEC BA-2", "SECOND", "2024-O")
            )
        ]
    )

    assert evaluate(rule, "7075-T6").reason_code == "FIRST"


def test_a_violation_in_any_provider_blocks_the_assignment():
    rule = FeatureConstraintGateRule(
        [
            FakeConstraintProvider("BEAD", allow_only("SPEC BA-1", "BEAD_SAYS_NO", "7075-T6")),
            FakeConstraintProvider("LOUVER", allow_only("SPEC LV-9", "LOUVER_SAYS_NO", "2024-O")),
        ]
    )

    outcome = evaluate(rule, "7075-T6")

    assert outcome.decision is RuleDecision.BLOCK
    assert outcome.reason_code == "LOUVER_SAYS_NO"


def test_allows_only_when_every_provider_is_satisfied():
    rule = FeatureConstraintGateRule(
        [
            FakeConstraintProvider("BEAD", allow_only("SPEC BA-1", "BEAD_SAYS_NO", "2024-O", "7075-T6")),
            FakeConstraintProvider("LOUVER", allow_only("SPEC LV-9", "LOUVER_SAYS_NO", "2024-O")),
        ]
    )

    assert evaluate(rule, "2024-O").decision is RuleDecision.ALLOW


def test_a_warning_constraint_allows_the_assignment_with_a_warn_outcome():
    rule = FeatureConstraintGateRule(
        [FakeConstraintProvider("BEAD", warn_always("Bead(12)", "BEAD_UNMATCHED", "Bead(12) matches no SPEC."))]
    )

    outcome = evaluate(rule, "2024-O")

    assert outcome.decision is RuleDecision.WARN
    assert outcome.reason_code == "BEAD_UNMATCHED"
    assert "Bead(12) matches no SPEC." in (outcome.message or "")


def test_a_block_wins_even_when_a_warning_is_listed_first():
    rule = FeatureConstraintGateRule(
        [
            FakeConstraintProvider(
                "BEAD",
                warn_always("Bead(12)", "BEAD_UNMATCHED", "advisory"),
                allow_only("SPEC BA-1", "NOT_ALLOWED", "2024-O"),
            )
        ]
    )

    outcome = evaluate(rule, "7075-T6")

    assert outcome.decision is RuleDecision.BLOCK
    assert outcome.reason_code == "NOT_ALLOWED"


def test_every_warning_is_reported_together():
    rule = FeatureConstraintGateRule(
        [
            FakeConstraintProvider(
                "BEAD",
                warn_always("Bead(12)", "BEAD_UNMATCHED", "first advisory"),
                warn_always("Bead(13)", "BEAD_UNMATCHED", "second advisory"),
            )
        ]
    )

    message = evaluate(rule, "2024-O").message or ""

    assert "first advisory" in message
    assert "second advisory" in message


def test_every_warning_is_also_kept_as_its_own_inner_outcome():
    rule = FeatureConstraintGateRule(
        [
            FakeConstraintProvider(
                "BEAD",
                warn_always("Bead(12)", "BEAD_UNMATCHED", "first advisory"),
                warn_always("Bead(13)", "BEAD_OTHER", "second advisory"),
            )
        ]
    )

    outcome = evaluate(rule, "2024-O")

    assert [o.reason_code for o in outcome.inner] == ["BEAD_UNMATCHED", "BEAD_OTHER"]
    assert outcome.inner[1].args["source"] == "Bead(13)"


def test_a_block_carries_the_constraints_args_with_its_source_and_the_material():
    constraint = replace(
        allow_only("Bead SPEC BA-1234", "NOT_ALLOWED", "2024-O"), violation_args=lambda _: {"spec": "BA-1234"}
    )

    outcome = evaluate(FeatureConstraintGateRule([FakeConstraintProvider("BEAD", constraint)]), "7075-T6")

    assert outcome.args["spec"] == "BA-1234"
    assert outcome.args["source"] == "Bead SPEC BA-1234"
    assert outcome.args["material"] == "7075-T6"


def test_queries_providers_for_the_body_under_evaluation():
    provider = FakeConstraintProvider("BEAD")

    evaluate(FeatureConstraintGateRule([provider]), "Anything")

    assert provider.queried_bodies == [BodyId("body-1")]


def test_runs_at_order_150_between_body_type_and_reassignment_confirmation():
    # Load-bearing: a material the body's features forbid must be rejected outright, not confirmed at 200.
    assert FeatureConstraintGateRule().order == 150
