"""What a material may be used for: its "allowed for" property, and the rules file setting that names it."""

from __future__ import annotations

import logging

import pytest

from banxopen.foundation import BodyKind
from banxopen.materials import MaterialForm, MaterialFormClassifier, MaterialLibraryRulesError, MaterialPropertyValue
from banxopen.materials.core.rules.library_rules import read_library_rules
from banxopen.materials.core.rules.material_forms import form_for_body

from builders import make_material

SOLID, SHEET_METAL = MaterialForm.SOLID, MaterialForm.SHEET_METAL


def allowed_for(value: str, name: str = "AllowedFor", property_id: str = "pr9"):
    return make_material("4010", properties=[MaterialPropertyValue(property_id, name, None, value, None)])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SheetMetal", {SHEET_METAL}),
        ("Solid", {SOLID}),
        ("Solid, SheetMetal", {SOLID, SHEET_METAL}),
        ("sheet metal", {SHEET_METAL}),  # case and spaces do not matter
        (" SHEETMETAL ,solid,", {SOLID, SHEET_METAL}),
        ("", {SOLID}),  # blank means not specified
        ("SheetMetal, BlockBar", {SHEET_METAL}),  # a later version's value is ignored
        ("BlockBar", set()),  # nothing this version knows: allowed for nothing it knows
    ],
)
def test_the_property_lists_the_forms(value, expected):
    assert MaterialFormClassifier().allowed_forms(allowed_for(value)) == expected


def test_without_the_property_a_material_is_for_solids_only():
    assert MaterialFormClassifier().allowed_forms(make_material("Steel")) == {SOLID}


def test_the_property_is_found_by_name_or_id_ignoring_case():
    classifier = MaterialFormClassifier()

    assert classifier.allowed_forms(allowed_for("SheetMetal", name="ALLOWEDFOR")) == {SHEET_METAL}
    assert classifier.allowed_forms(allowed_for("SheetMetal", name="Something", property_id="allowedfor")) == {
        SHEET_METAL
    }


def test_an_unknown_value_is_logged_once(caplog):
    classifier = MaterialFormClassifier()

    with caplog.at_level(logging.INFO, logger="banxopen.materials"):
        classifier.allowed_forms(allowed_for("BlockBar"))
        classifier.allowed_forms(allowed_for("blockbar"))

    assert caplog.text.count("Ignoring unknown AllowedFor value") == 1


def test_a_configured_property_and_values_are_used():
    classifier = MaterialFormClassifier("Form", {SHEET_METAL: "SM"})
    material = allowed_for("SM", name="Form")

    assert classifier.allowed_forms(material) == {SHEET_METAL}
    assert classifier.allowed_forms(allowed_for("SM")) == {SOLID}  # AllowedFor is not the property any more
    assert classifier.value_for(SOLID) == "Solid"


@pytest.mark.parametrize(
    ("kind", "form"),
    [
        (BodyKind.SHEET_METAL, SHEET_METAL),
        (BodyKind.SOLID, SOLID),
        (BodyKind.SHEET, SOLID),  # surfaces are treated like solids
        (BodyKind.UNKNOWN, SOLID),
    ],
)
def test_the_form_a_body_needs(kind, form):
    assert form_for_body(kind) is form


def test_the_raw_xml_check_only_rules_out_files_without_the_property_name():
    classifier = MaterialFormClassifier()

    assert classifier.may_mention("<Name>allowedfor</Name>")
    assert not classifier.may_mention("<Name>Density</Name>")


# ---- The rules file setting ----


def rules(tmp_path, json: str):
    path = tmp_path / "material-library-rules.json"
    path.write_text(json, encoding="utf-8")
    return read_library_rules(path)


def test_without_the_setting_the_default_applies(tmp_path):
    assert MaterialFormClassifier.from_rules(None) is MaterialFormClassifier.DEFAULT
    assert MaterialFormClassifier.from_rules(rules(tmp_path, '{ "sheetMetalLibraries": ["SM"] }')).property_name == (
        "AllowedFor"
    )


def test_the_setting_alone_is_a_valid_rules_file(tmp_path):
    classifier = MaterialFormClassifier.from_rules(
        rules(tmp_path, '{ "MaterialForms": { "Property": "Form", "sheetMetal": "Sheet Metal" } }')
    )

    assert classifier.property_name == "Form"
    assert classifier.allowed_forms(allowed_for("sheetmetal", name="Form")) == {SHEET_METAL}


@pytest.mark.parametrize(
    ("json", "expected"),
    [
        ('{ "materialForms": "AllowedFor" }', "must be an object"),
        ('{ "materialForms": { "property": " " } }', r"materialForms\.property\" must be a non-blank text"),
        ('{ "materialForms": { "solid": 3 } }', r"materialForms\.solid\" must be a non-blank text"),
        ('{ "materialForms": { "solid": "X", "sheetMetal": "x" } }', "same value for more than one form"),
    ],
)
def test_an_unusable_setting_is_rejected_rather_than_ignored(tmp_path, json, expected):
    with pytest.raises(MaterialLibraryRulesError, match=expected):
        MaterialFormClassifier.from_rules(rules(tmp_path, json))
