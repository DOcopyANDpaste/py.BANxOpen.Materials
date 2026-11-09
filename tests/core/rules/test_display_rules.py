from banxopen.foundation import BodyId, RuleDecision
from banxopen.materials import BodyMaterialAssignment, DisplayMaterial, MaterialId, MaterialPropertyValue
from banxopen.materials.core.rules.display import (
    SyncCoatingDisplayMaterialEffectRule,
    ValidateCoatingDisplayMaterialRule,
)

from builders import context, make_material

MATERIAL_NAME_PROPERTY = "CoatingStudioMaterialName"
COLOR_PROPERTY = "CoatingVisualizationColor"
DEFAULT_NAME = "TODO_DEFAULT_DISPLAY_MATERIAL_NAME"
DEFAULT_RGB = (0.7, 0.7, 0.7)


def name_property(value: str) -> MaterialPropertyValue:
    return MaterialPropertyValue("pr-name", MATERIAL_NAME_PROPERTY, None, value, None)


def color_property(value: str) -> MaterialPropertyValue:
    return MaterialPropertyValue("pr-color", COLOR_PROPERTY, None, value, None)


# ---- SyncCoatingDisplayMaterialEffectRuleTests ----


def sync(*properties: MaterialPropertyValue):
    (effect,) = SyncCoatingDisplayMaterialEffectRule().generate_effects(
        context(make_material("Coated Steel", properties=properties))
    )
    return effect


def test_generate_effects_valid_name_and_color_on_0_to_255_scale_normalizes_to_0_to_1():
    effect = sync(name_property("Chrome"), color_property("255,128,0"))

    assert effect.instruction_type == "ASSIGN_DISPLAY_MATERIAL"
    assert effect.body_id.value == "b1"
    assert effect.data["DisplayMaterialName"] == "Chrome"
    assert effect.data[SyncCoatingDisplayMaterialEffectRule.RGB_KEY] == (1.0, 0.501961, 0.0)


def test_generate_effects_valid_name_and_color_already_on_0_to_1_scale_passes_through_unchanged():
    assert sync(name_property("Chrome"), color_property("1,0.5,0")).data["RGB"] == (1.0, 0.5, 0.0)


def test_generate_effects_name_missing_falls_back_to_default():
    effect = sync(color_property("255,128,0"))

    assert effect.data["DisplayMaterialName"] == DEFAULT_NAME
    assert effect.data["RGB"] == DEFAULT_RGB
    assert effect.data["UsedDefault"] is True


def test_generate_effects_color_invalid_falls_back_to_default():
    effect = sync(name_property("Chrome"), color_property("not,a,color"))

    assert effect.data["DisplayMaterialName"] == DEFAULT_NAME
    assert effect.data["UsedDefault"] is True


def test_generate_effects_no_coating_properties_at_all_falls_back_to_default():
    effect = sync()

    assert effect.data["DisplayMaterialName"] == DEFAULT_NAME
    assert effect.data["UsedDefault"] is True


# ---- ValidateCoatingDisplayMaterialRuleTests ----


def validate(*properties: MaterialPropertyValue, current: BodyMaterialAssignment | None = None):
    return ValidateCoatingDisplayMaterialRule().evaluate(
        context(make_material("Coated Steel", properties=properties), current=current)
    )


def display(name: str, r: int, g: int, b: int) -> DisplayMaterial:
    return DisplayMaterial(MaterialId("dm-1"), name, (r, g, b))


def assigned(current_display: DisplayMaterial | None) -> BodyMaterialAssignment:
    return BodyMaterialAssignment(BodyId("b1"), "Coated Steel", None, current_display)


def test_evaluate_name_and_valid_color_allows():
    assert validate(name_property("Chrome"), color_property("255,128,0")).decision is RuleDecision.ALLOW


def test_evaluate_name_present_color_missing_blocks():
    assert validate(name_property("Chrome")).decision is RuleDecision.BLOCK


def test_evaluate_name_present_color_wrong_component_count_blocks():
    assert validate(name_property("Chrome"), color_property("255,128")).decision is RuleDecision.BLOCK


def test_evaluate_name_present_color_non_numeric_blocks():
    assert validate(name_property("Chrome"), color_property("red,green,blue")).decision is RuleDecision.BLOCK


def test_evaluate_name_present_color_out_of_range_blocks():
    assert validate(name_property("Chrome"), color_property("300,0,0")).decision is RuleDecision.BLOCK


def test_evaluate_name_missing_color_present_warns():
    assert validate(color_property("255,128,0")).decision is RuleDecision.WARN


def test_evaluate_neither_property_present_still_warns():
    assert validate().decision is RuleDecision.WARN


def test_evaluate_name_blank_treated_as_missing_warns():
    assert validate(name_property("   "), color_property("255,128,0")).decision is RuleDecision.WARN


def test_evaluate_existing_assignment_no_current_display_material_allows_with_reference_info():
    outcome = validate(name_property("Chrome"), color_property("255,128,0"), current=assigned(None))

    assert outcome.decision is RuleDecision.ALLOW
    assert outcome.reason_code == "COATING_NOT_APPLIED"


def test_evaluate_existing_assignment_name_differs_color_matches_requires_confirmation():
    outcome = validate(
        name_property("Chrome"), color_property("255,128,0"), current=assigned(display("Brushed Nickel", 255, 128, 0))
    )

    assert outcome.decision is RuleDecision.REQUIRE_CONFIRMATION
    assert outcome.reason_code == "COATING_DISPLAY_MISMATCH"
    assert outcome.args["libraryName"] == "Chrome"
    assert outcome.args["currentName"] == "Brushed Nickel"
    assert outcome.args["currentRgb"] == "255,128,0"
    assert outcome.args["libraryRgb"] == "255,128,0"


def test_evaluate_existing_assignment_name_matches_color_differs_requires_confirmation():
    outcome = validate(
        name_property("Chrome"), color_property("255,128,0"), current=assigned(display("Chrome", 0, 0, 0))
    )

    assert outcome.decision is RuleDecision.REQUIRE_CONFIRMATION
    assert outcome.reason_code == "COATING_DISPLAY_MISMATCH"


def test_evaluate_existing_assignment_color_within_tolerance_allows():
    # One 0-255 step off in the red channel (255 vs 254): within the accepted rounding tolerance.
    outcome = validate(
        name_property("Chrome"), color_property("255,128,0"), current=assigned(display("Chrome", 254, 128, 0))
    )

    assert outcome.decision is RuleDecision.ALLOW


def test_evaluate_existing_assignment_name_and_color_match_allows():
    outcome = validate(
        name_property("Chrome"), color_property("255,128,0"), current=assigned(display("chrome", 255, 128, 0))
    )

    assert outcome.decision is RuleDecision.ALLOW
