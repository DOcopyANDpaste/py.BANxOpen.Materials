"""Pins Materials' public API. A failure here means the API changed: update the pin deliberately, bump the version and
add a CHANGELOG entry, then run every downstream repo's tests."""

from __future__ import annotations

import importlib
import inspect

import banxopen.materials as api
import banxopen.materials.nx as nx


def test_pure_api_names_are_pinned():
    assert set(api.__all__) == {
        # library data
        "DisplayMaterial",
        "Material",
        "MaterialCategory",
        "MaterialId",
        "MaterialLibrary",
        "MaterialLibraryId",
        "MaterialLibraryReference",
        "MaterialPropertyValue",
        "Rgb",
        # library reading
        "CachingMaterialLibraryLoader",
        "FileSystemMaterialLibraryRepository",
        "MaterialCategoryNode",
        "MaterialLibraryParser",
        "MaterialLibraryRepository",
        "MatmlParser",
        "build_category_tree",
        # tools: per-gesture service and its results
        "AssignmentReport",
        "BodyMaterialAssignment",
        "BodyOutcome",
        "BodyVerdict",
        "MaterialAssignmentService",
        "OutcomeStatus",
        "PlannedAssignment",
        "VerdictStatus",
        # feature domains: rule extension points
        "ConstraintSeverity",
        "FeatureMaterialConstraintProvider",
        "MaterialConstraint",
        "MaterialRuleModule",
        "MaterialRuleOrder",
        "MaterialRuleSet",
        "MaterialValidationRule",
        "PostAssignmentEffectRule",
        "SheetMetalLibraries",
        "MaterialLibraryRulesError",
        "MaterialForm",
        "MaterialFormClassifier",
        "MaterialLibraryCatalog",
        # planning pipeline
        "AssignmentPlan",
        "AssignmentPlanFinalizer",
        "BodyAssignmentEvaluation",
        "ExecutableAssignment",
        "ExecutablePlan",
        "MaterialAssignmentPlanner",
        "MaterialAssignmentPlanningInput",
        "MaterialAssignmentRuleContext",
        "SideEffectInstruction",
        # NX seam
        "PartChangeOutcome",
        "PartMaterialService",
        # wording, codes and attribute names
        "MaterialPartAttributes",
        "MaterialsCodes",
        "MaterialsText",
        "__version__",
    }


def test_nx_api_names_are_pinned():
    assert set(nx.__all__) == {
        "DisplayMaterialHelper",
        "MaterialEngine",
        "NxMaterialRuleModule",
        "NxPartMaterialService",
        "SideEffectExecutor",
    }


def test_public_packages_import_without_nx():
    for module in ("banxopen.materials", "banxopen.materials.nx"):
        importlib.import_module(module)


def test_service_gestures_are_pinned():
    service = api.MaterialAssignmentService
    assert list(inspect.signature(service.plan).parameters) == ["self", "material", "body_ids", "variant"]
    assert list(inspect.signature(service.apply).parameters) == [
        "self",
        "material",
        "body_ids",
        "variant",
        "confirmed",
        "confirm_remaining",
    ]
    assert list(inspect.signature(service.clear).parameters) == ["self", "body_ids"]
    assert list(inspect.signature(service.preferred_material).parameters) == ["self"]
    assert list(inspect.signature(service.set_preferred_material).parameters) == ["self", "name"]


def test_preferred_material_attribute_names_are_pinned():
    # Downstream tools read the attribute by these exact names.
    assert api.MaterialPartAttributes.CATEGORY == "Material"
    assert api.MaterialPartAttributes.PREFERRED_MATERIAL == "Preferred Material"


def test_part_material_port_is_pinned():
    port = api.PartMaterialService
    assert [
        name
        for name in (
            "get_bodies",
            "get_current_assignments",
            "set_resolution_libraries",
            "apply_plan",
            "clear_material",
            "get_preferred_material",
            "set_preferred_material",
        )
        if hasattr(port, name)
    ] == [
        "get_bodies",
        "get_current_assignments",
        "set_resolution_libraries",
        "apply_plan",
        "clear_material",
        "get_preferred_material",
        "set_preferred_material",
    ]


def test_rule_module_port_is_pinned():
    module = api.MaterialRuleModule
    for name in ("module_id", "validation_rules", "feature_constraints", "side_effect_rules"):
        assert hasattr(module, name)
