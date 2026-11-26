"""The describer is the single source of the engine's wording: its defaults are pinned here, and an overriding describer
handed to a rule, the feature gate or the rule set is what ends up in the outcome."""

from __future__ import annotations

from banxopen.foundation import BodyId
from banxopen.materials import (
    BodyMaterialAssignment,
    MaterialAssignmentPlanningInput,
    MaterialRuleSet,
    MaterialsCodes,
    MaterialsText,
)
from banxopen.materials.core.rules.feature_gate import FeatureConstraintGateRule
from banxopen.materials.core.rules.standard import RequireConfirmationOnReassignmentRule

from builders import FakeConstraintProvider, allow_only, context, make_body, make_material


class CustomText(MaterialsText):
    def reassign(self, current: str, requested: str) -> str:
        return f"custom reassign {current}->{requested}"

    def required_by(self, violation: str, source: str) -> str:
        return f"custom [{source}] {violation}"


def reassigning(from_name: str, to_name: str):
    body = make_body("body-1")
    return context(make_material(to_name), body, BodyMaterialAssignment(body.id, from_name, None, None), (body,))


def test_default_wording_is_pinned():
    text = MaterialsText.DEFAULT

    assert text.reassign("A", "B") == "Body already has 'A'. Replace with 'B'?"
    assert text.body_type_restricted("X") == "'X' is not available for this body."
    assert text.required_by("V", "S") == "V (required by S)"
    assert text.coating_display_mismatch("L", "1,2,3", "C", "4,5,6") == (
        "Library: 'L' (1,2,3) vs current: 'C' (4,5,6).\n"
        "Confirm to update to the library value, or leave unconfirmed to keep the current one."
    )


def test_csharp_wording_of_every_other_message_is_kept():
    text = MaterialsText.DEFAULT

    assert (
        text.coating_name_missing("M", "P")
        == "Material 'M' has no P defined — a default display material will be applied instead."
    )
    assert text.coating_color_invalid("M", "P") == (
        "Material 'M' has an invalid or missing P. Contact your material library administrator."
    )
    assert text.coating_not_applied(None) == (
        "Body already has material '' assigned but no display material is currently associated with it — "
        "it will be assigned automatically."
    )
    assert text.combine_warnings(["a.", "b."]) == "a. b."
    assert text.material_rules_unavailable(None) == "Material rules could not be loaded."
    assert text.apply_aborted("why") == "The material could not be applied; nothing was changed.\n\nDetails: why"
    assert text.clear_aborted(" ") == "The material could not be removed; nothing was changed."
    assert text.no_target_bodies_resolved == "No target bodies could be resolved."
    assert (
        text.partial_failure
        == "Some bodies failed. The ones that succeeded were kept; see the Listing Window for details."
    )
    assert text.confirm_load_physical_material("M", "L") == (
        "'M' is not in this part yet.\nLoad it from the NX material library 'L'?\n\n"
        "This can take a while for a large library."
    )


def test_wording_moved_from_the_material_assignment_dialog_is_kept():
    text = MaterialsText.DEFAULT

    assert text.confirm_bodies(2, "Steel", ["  [B1] x", "  [B2] y"]) == (
        "2 body(ies) need confirmation for Steel:\n  [B1] x\n  [B2] y\n\nApply to all of them?"
    )
    assert text.body_line("B1", "x") == "  [B1] x"
    assert text.blocked("no") == "blocked: no"
    assert text.not_confirmed == "not confirmed"


def test_a_rule_words_its_outcome_with_the_describer_it_is_given():
    outcome = RequireConfirmationOnReassignmentRule(CustomText()).evaluate(reassigning("Old", "New"))

    assert outcome.reason_code == MaterialsCodes.REASSIGN
    assert outcome.message == "custom reassign Old->New"


def test_the_feature_gate_attributes_a_violation_with_the_describer_it_is_given():
    gate = FeatureConstraintGateRule(
        [FakeConstraintProvider("BEAD", allow_only("SPEC BA-1", "NOT_ALLOWED", "2024-O"))], CustomText()
    )

    assert gate.evaluate(reassigning("Old", "7075-T6")).message == "custom [SPEC BA-1] '7075-T6' is not allowed."


def test_the_rule_set_hands_its_describer_to_every_baseline_rule():
    text = CustomText()
    planner = MaterialRuleSet.from_modules(MaterialRuleSet.baseline(None, text), text).create_planner()
    body = make_body("body-1")

    plan = planner.plan(
        MaterialAssignmentPlanningInput(
            requested_material=make_material("New"),
            target_bodies=(body,),
            current_assignments={body.id: BodyMaterialAssignment(BodyId("body-1"), "Old", None, None)},
        )
    )

    (confirmation,) = plan.body_evaluations[0].confirmation_outcomes
    assert confirmation.message == "custom reassign Old->New"


def test_codes_are_distinct():
    values = [v for k, v in vars(MaterialsCodes).items() if k.isupper()]

    assert values
    assert len(values) == len(set(values))
