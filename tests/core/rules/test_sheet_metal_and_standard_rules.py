from pathlib import Path

import pytest

from banxopen.foundation import BodyId, BodyKind, RuleDecision
from banxopen.materials import (
    BodyMaterialAssignment,
    Material,
    MaterialFormClassifier,
    MaterialLibraryId,
    MaterialLibraryRulesError,
    MaterialPropertyValue,
    MaterialRuleSet,
    SheetMetalLibraries,
)
from banxopen.materials.core.rules.sheet_metal import BlockRestrictedBodyTypeRule, sheet_metal_view_id
from banxopen.materials.core.rules.standard import RequireConfirmationOnReassignmentRule

from builders import context, make_body, make_material


def lib(name: str) -> MaterialLibraryId:
    return MaterialLibraryId(name)


# ---- BlockRestrictedBodyTypeRuleTests ----


def body_type(material_library: str, kind: BodyKind, rule: BlockRestrictedBodyTypeRule | None = None) -> RuleDecision:
    material = make_material("Sheet Steel", library=material_library)
    return (rule or BlockRestrictedBodyTypeRule()).evaluate(context(material, make_body("body1", kind))).decision


@pytest.mark.parametrize(
    ("library", "kind", "expected"),
    [
        ("Sheet Metal Materials", BodyKind.SHEET_METAL, RuleDecision.ALLOW),
        ("lib", BodyKind.SHEET_METAL, RuleDecision.BLOCK),
        ("Sheet Metal Materials", BodyKind.SOLID, RuleDecision.BLOCK),
        ("lib", BodyKind.SOLID, RuleDecision.ALLOW),
        ("Sheet Metal Materials", BodyKind.SHEET, RuleDecision.BLOCK),  # a surface body is not sheet metal
        ("lib", BodyKind.SHEET, RuleDecision.ALLOW),
    ],
    ids=[
        "sheet-metal-material-on-sheet-metal-body",
        "ordinary-material-on-sheet-metal-body",
        "sheet-metal-material-on-solid",
        "ordinary-material-on-solid",
        "sheet-metal-material-on-surface-body",
        "ordinary-material-on-surface-body",
    ],
)
def test_body_type_rule(library, kind, expected):
    assert body_type(library, kind) is expected


def allowing(value: str, library: str) -> Material:
    return make_material(
        "4010", properties=[MaterialPropertyValue("pr1", "AllowedFor", None, value, None)], library=library
    )


METALS_VIEW = sheet_metal_view_id(lib("Metals")).value


@pytest.mark.parametrize(
    ("allowed_for", "library", "kind", "expected"),
    [
        # Picked from a library's sheet metal view: as a sheet metal library always was.
        ("SheetMetal", METALS_VIEW, BodyKind.SHEET_METAL, RuleDecision.ALLOW),
        ("SheetMetal", METALS_VIEW, BodyKind.SOLID, RuleDecision.BLOCK),
        ("Solid, SheetMetal", METALS_VIEW, BodyKind.SHEET_METAL, RuleDecision.ALLOW),
        ("Solid, SheetMetal", METALS_VIEW, BodyKind.SOLID, RuleDecision.BLOCK),
        # Picked from the library file itself: solids only, and only if the material allows solids.
        ("Solid, SheetMetal", "Metals", BodyKind.SOLID, RuleDecision.ALLOW),
        ("Solid, SheetMetal", "Metals", BodyKind.SHEET_METAL, RuleDecision.BLOCK),
        ("SheetMetal", "Metals", BodyKind.SOLID, RuleDecision.BLOCK),
        ("SheetMetal", "Metals", BodyKind.SHEET, RuleDecision.BLOCK),
        # A view listing a material not allowed for sheet metal (by another route than the catalog): blocked.
        ("Solid", METALS_VIEW, BodyKind.SHEET_METAL, RuleDecision.BLOCK),
        # A sheet metal library file: its materials need no property.
        ("Solid", "Sheet Metal Materials", BodyKind.SHEET_METAL, RuleDecision.ALLOW),
    ],
)
def test_body_type_rule_with_the_allowed_for_property(allowed_for, library, kind, expected):
    material = allowing(allowed_for, library)

    decision = BlockRestrictedBodyTypeRule().evaluate(context(material, make_body("body1", kind))).decision

    assert decision is expected


def test_the_baseline_passes_the_material_forms_to_the_body_type_rule():
    forms = MaterialFormClassifier("Form")
    rules = MaterialRuleSet.from_modules(MaterialRuleSet.baseline(None, None, forms))
    (rule,) = [r for r in rules.validation_rules if isinstance(r, BlockRestrictedBodyTypeRule)]
    material = make_material(
        "4010", properties=[MaterialPropertyValue("p", "Form", None, "SheetMetal", None)], library=METALS_VIEW
    )

    assert rule.evaluate(context(material, make_body("b", BodyKind.SHEET_METAL))).decision is RuleDecision.ALLOW


def test_body_type_block_names_the_material():
    outcome = BlockRestrictedBodyTypeRule().evaluate(
        context(make_material("Sheet Steel", library="Sheet Metal Materials"))
    )

    assert outcome.reason_code == "BODY_TYPE_RESTRICTED"
    assert outcome.message == "'Sheet Steel' is not available for this body."
    assert outcome.args == {"material": "Sheet Steel"}


# ---- SheetMetalLibrariesTests ----


def write(tmp_path: Path, json: str) -> Path:
    path = tmp_path / SheetMetalLibraries.FILE_NAME
    path.write_text(json, encoding="utf-8")
    return path


def test_without_a_file_the_name_based_rule_applies(tmp_path: Path):
    libraries = SheetMetalLibraries.load(tmp_path / SheetMetalLibraries.FILE_NAME)

    assert not libraries.is_configured
    assert libraries.is_sheet_metal_library(lib("Sheet Metal Materials"))
    assert libraries.is_sheet_metal_library(lib("SHEETMETAL_ALUMINUM"))
    assert not libraries.is_sheet_metal_library(lib("Castings"))


def test_a_configured_list_is_matched_exactly_and_case_insensitively(tmp_path: Path):
    libraries = SheetMetalLibraries.load(
        write(tmp_path, '{ "sheetMetalLibraries": [ "Sheet Metal Materials", "Aero Skins" ] }')
    )

    assert libraries.is_configured
    assert libraries.is_sheet_metal_library(lib("sheet metal materials"))
    assert libraries.is_sheet_metal_library(lib("Aero Skins"))
    assert libraries.configured_names == ("Sheet Metal Materials", "Aero Skins")


def test_a_configured_list_replaces_the_name_rule_entirely(tmp_path: Path):
    libraries = SheetMetalLibraries.load(write(tmp_path, '{ "sheetMetalLibraries": [ "Aero Skins" ] }'))

    assert not libraries.is_sheet_metal_library(lib("Sheet Metal Materials"))
    assert not libraries.is_sheet_metal_library(lib("Aero Skins Archive"))


def test_property_names_match_case_insensitively_like_the_csharp_reader(tmp_path: Path):
    libraries = SheetMetalLibraries.load(write(tmp_path, '{ "SheetMetalLibraries": [ "Aero Skins" ] }'))

    assert libraries.is_sheet_metal_library(lib("Aero Skins"))


@pytest.mark.parametrize(
    ("json", "expected"),
    [
        ('{ "sheetMetalLibraries": [] }', "at least one library"),
        ('{ "sheetMetalLibraries": [ "  " ] }', "at least one library"),
        ('{ "somethingElse": true }', 'no "sheetMetalLibraries" list'),
        ("not json", "not valid JSON"),
        ('{ "sheetMetalLibraries": "Aero Skins" }', "not valid JSON"),
        ('[ "Aero Skins" ]', "not valid JSON"),
    ],
)
def test_an_invalid_file_is_rejected_rather_than_ignored(tmp_path: Path, json, expected):
    with pytest.raises(MaterialLibraryRulesError, match=expected):
        SheetMetalLibraries.load(write(tmp_path, json))


def test_a_file_with_only_material_forms_keeps_the_name_based_rule(tmp_path: Path):
    libraries = SheetMetalLibraries.load(write(tmp_path, '{ "materialForms": { "property": "AllowedFor" } }'))

    assert not libraries.is_configured
    assert libraries.is_sheet_metal_library(lib("Sheet Metal Materials"))


def test_a_sheet_metal_view_is_a_sheet_metal_library_but_not_a_file():
    libraries = SheetMetalLibraries.from_names(["Aero Skins"])
    view = sheet_metal_view_id(lib("Metals"))

    assert libraries.is_sheet_metal_library(view)
    assert not libraries.is_sheet_metal_file(view)
    assert not SheetMetalLibraries.NAME_HEURISTIC.is_sheet_metal_file(view)


def test_the_rules_file_is_found_beside_the_libraries_unless_overridden(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(SheetMetalLibraries.PATH_ENVIRONMENT_VARIABLE, raising=False)
    assert SheetMetalLibraries.resolve_path(tmp_path) == tmp_path / SheetMetalLibraries.FILE_NAME

    elsewhere = tmp_path / "shared" / "rules.json"
    monkeypatch.setenv(SheetMetalLibraries.PATH_ENVIRONMENT_VARIABLE, str(elsewhere))
    assert SheetMetalLibraries.resolve_path(tmp_path) == elsewhere


def test_the_body_type_rule_uses_the_configured_list():
    rule = BlockRestrictedBodyTypeRule(SheetMetalLibraries.from_names(["Aero Skins"]))

    assert body_type("Aero Skins", BodyKind.SHEET_METAL, rule) is RuleDecision.ALLOW
    assert body_type("Sheet Metal Materials", BodyKind.SHEET_METAL, rule) is RuleDecision.BLOCK


def test_the_baseline_passes_the_configured_list_to_the_body_type_rule():
    rules = MaterialRuleSet.from_modules(MaterialRuleSet.baseline(SheetMetalLibraries.from_names(["Aero Skins"])))
    (rule,) = [r for r in rules.validation_rules if isinstance(r, BlockRestrictedBodyTypeRule)]

    assert body_type("Aero Skins", BodyKind.SHEET_METAL, rule) is RuleDecision.ALLOW


# ---- RequireConfirmationOnReassignmentRuleTests ----


def reassign(current_name: str | None):
    current = BodyMaterialAssignment(BodyId("b1"), current_name, None) if current_name is not None else None
    return RequireConfirmationOnReassignmentRule().evaluate(context(make_material("Steel"), current=current))


def test_requires_confirmation_when_body_has_a_different_material_assigned():
    outcome = reassign("Aluminum")

    assert outcome.decision is RuleDecision.REQUIRE_CONFIRMATION
    assert outcome.args == {"current": "Aluminum", "requested": "Steel"}


def test_allows_when_body_has_no_current_assignment():
    assert reassign(None).decision is RuleDecision.ALLOW


def test_allows_when_reassigning_the_same_material_name_case_insensitively():
    assert reassign("steel").decision is RuleDecision.ALLOW
