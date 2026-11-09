"""BANxOpen Materials: pure public API. Safe to import without NX.

Three audiences:
- tools use `MaterialAssignmentService` (built by `banxopen.materials.nx.MaterialEngine`): browse, plan, apply, clear;
- feature domains extend the engine through `MaterialRuleModule` and its rule, constraint and side-effect ports;
- both read the library data types.

NX wiring is in `banxopen.materials.nx`.
"""

from banxopen.materials.codes import MaterialsCodes
from banxopen.materials.core.assignment.part_materials import PartChangeOutcome, PartMaterialService
from banxopen.materials.core.assignment.pipeline import AssignmentPlanFinalizer, MaterialAssignmentPlanner
from banxopen.materials.core.assignment.planning import (
    AssignmentPlan,
    BodyAssignmentEvaluation,
    ExecutableAssignment,
    ExecutablePlan,
    MaterialAssignmentPlanningInput,
    MaterialAssignmentRuleContext,
    SideEffectInstruction,
)
from banxopen.materials.core.assignment.service import MaterialAssignmentService
from banxopen.materials.core.assignment.verdicts import PlannedAssignment
from banxopen.materials.core.library.catalog import MaterialLibraryCatalog
from banxopen.materials.core.library.category_tree import MaterialCategoryNode, build_category_tree
from banxopen.materials.core.library.loader import CachingMaterialLibraryLoader
from banxopen.materials.core.library.parser import MaterialLibraryParser, MatmlParser
from banxopen.materials.core.library.repository import FileSystemMaterialLibraryRepository, MaterialLibraryRepository
from banxopen.materials.core.rules.features import ConstraintSeverity, MaterialConstraint
from banxopen.materials.core.rules.material_forms import MaterialForm, MaterialFormClassifier
from banxopen.materials.core.rules.order import MaterialRuleOrder
from banxopen.materials.core.rules.ports import (
    FeatureMaterialConstraintProvider,
    MaterialRuleModule,
    MaterialValidationRule,
    PostAssignmentEffectRule,
)
from banxopen.materials.core.rules.rule_set import MaterialRuleSet
from banxopen.materials.core.rules.sheet_metal import MaterialLibraryRulesError, SheetMetalLibraries
from banxopen.materials.model.assignments import (
    AssignmentReport,
    BodyMaterialAssignment,
    BodyOutcome,
    BodyVerdict,
    OutcomeStatus,
    VerdictStatus,
)
from banxopen.materials.model.materials import (
    DisplayMaterial,
    Material,
    MaterialCategory,
    MaterialId,
    MaterialLibrary,
    MaterialLibraryId,
    MaterialLibraryReference,
    MaterialPropertyValue,
    Rgb,
)
from banxopen.materials.text import MaterialsText

__version__ = "1.0.0"

__all__ = [
    "AssignmentPlan",
    "AssignmentPlanFinalizer",
    "AssignmentReport",
    "BodyAssignmentEvaluation",
    "BodyMaterialAssignment",
    "BodyOutcome",
    "BodyVerdict",
    "CachingMaterialLibraryLoader",
    "ConstraintSeverity",
    "DisplayMaterial",
    "ExecutableAssignment",
    "ExecutablePlan",
    "FeatureMaterialConstraintProvider",
    "FileSystemMaterialLibraryRepository",
    "Material",
    "MaterialAssignmentPlanner",
    "MaterialAssignmentPlanningInput",
    "MaterialAssignmentRuleContext",
    "MaterialAssignmentService",
    "MaterialCategory",
    "MaterialCategoryNode",
    "MaterialConstraint",
    "MaterialForm",
    "MaterialFormClassifier",
    "MaterialId",
    "MaterialLibrary",
    "MaterialLibraryCatalog",
    "MaterialLibraryId",
    "MaterialLibraryParser",
    "MaterialLibraryReference",
    "MaterialLibraryRepository",
    "MaterialLibraryRulesError",
    "MaterialPropertyValue",
    "MaterialRuleModule",
    "MaterialRuleOrder",
    "MaterialRuleSet",
    "MaterialValidationRule",
    "MaterialsCodes",
    "MaterialsText",
    "MatmlParser",
    "OutcomeStatus",
    "PartChangeOutcome",
    "PartMaterialService",
    "PlannedAssignment",
    "PostAssignmentEffectRule",
    "Rgb",
    "SheetMetalLibraries",
    "SideEffectInstruction",
    "VerdictStatus",
    "__version__",
    "build_category_tree",
]
