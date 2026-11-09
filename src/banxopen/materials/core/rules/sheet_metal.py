"""Sheet metal material libraries are reserved for sheet metal bodies, and sheet metal bodies take their materials from
those libraries only.

A sheet metal library is either a library file named as one (legacy: a separate XML of sheet metal materials), or the
sheet metal view of an ordinary library: the materials whose "allowed for" property lists sheet metal, offered as a
library of their own (see `banxopen.materials.core.library.catalog`).

Part of the baseline rather than the BANxOpen.SheetMetal domain on purpose: a tool that never registers the sheet
metal domain must still refuse a sheet metal material on a solid.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, ClassVar, Final

from banxopen.foundation import BodyKind, RuleDecision, RuleOutcome
from banxopen.materials.codes import MaterialsCodes
from banxopen.materials.core.assignment.planning import MaterialAssignmentRuleContext
from banxopen.materials.core.rules import library_rules
from banxopen.materials.core.rules.library_rules import (
    SHEET_METAL_LIBRARIES_KEY,
    LibraryRules,
    MaterialLibraryRulesError,
    read_library_rules,
)
from banxopen.materials.core.rules.material_forms import MaterialFormClassifier, form_for_body
from banxopen.materials.core.rules.order import MaterialRuleOrder
from banxopen.materials.core.rules.ports import (
    FeatureMaterialConstraintProvider,
    MaterialValidationRule,
    PostAssignmentEffectRule,
)
from banxopen.materials.model.materials import MaterialLibraryId
from banxopen.materials.text import MaterialsText

__all__ = [
    "BlockRestrictedBodyTypeRule",
    "MaterialLibraryRulesError",
    "SheetMetalLibraries",
    "SheetMetalLibraryRuleModule",
    "is_sheet_metal_view",
    "sheet_metal_view_id",
]

_VIEW_SUFFIX: Final = "::SHEETMETAL"
"""Ends the id of a library's sheet metal view. `:` cannot occur in a Windows file name, so a view id never clashes
with a library file."""


def sheet_metal_view_id(source: MaterialLibraryId) -> MaterialLibraryId:
    """The id of the sheet metal view of library `source`."""
    return MaterialLibraryId(source.value + _VIEW_SUFFIX)


def is_sheet_metal_view(library_id: MaterialLibraryId) -> bool:
    return library_id.value.upper().endswith(_VIEW_SUFFIX)


class SheetMetalLibraries:
    """Which material libraries hold sheet metal materials.

    Configured in `material-library-rules.json` beside the library XML files, so every tool reading those libraries
    reads the same rules: `{ "sheetMetalLibraries": [ "Sheet Metal Materials" ] }`. Names are library ids (the XML
    file name without extension), compared exactly and case-insensitively. Without the list, the original rule applies:
    a library whose name contains "sheetmetal", ignoring spaces and case.

    The sheet metal view of any library (`sheet_metal_view_id`) is a sheet metal library too, whatever is configured.
    """

    FILE_NAME: Final = library_rules.FILE_NAME
    PATH_ENVIRONMENT_VARIABLE: Final = library_rules.PATH_ENVIRONMENT_VARIABLE
    """Points at a rules file elsewhere, e.g. when the library folder is under Program Files and not writable."""

    NAME_HEURISTIC: ClassVar[SheetMetalLibraries]
    """The name-based rule used when nothing is configured."""

    def __init__(self, names: Iterable[str] | None) -> None:
        self._names = frozenset(n.upper() for n in names) if names is not None else None
        self._configured_names = tuple(names) if names is not None else ()

    @staticmethod
    def from_names(names: Iterable[str], text: MaterialsText | None = None) -> SheetMetalLibraries:
        """Raises ValueError when no non-blank name is given."""
        cleaned = [n.strip() for n in names if n.strip()]
        if not cleaned:
            raise ValueError((text or MaterialsText.DEFAULT).library_rules_list_empty)
        return SheetMetalLibraries(cleaned)

    @property
    def is_configured(self) -> bool:
        """True when the list came from configuration rather than the name heuristic."""
        return self._names is not None

    @property
    def configured_names(self) -> tuple[str, ...]:
        return self._configured_names

    def is_sheet_metal_library(self, library_id: MaterialLibraryId) -> bool:
        """True for a library file of sheet metal materials and for the sheet metal view of any library."""
        return is_sheet_metal_view(library_id) or self.is_sheet_metal_file(library_id)

    def is_sheet_metal_file(self, library_id: MaterialLibraryId) -> bool:
        """True for a library file that holds only sheet metal materials (the configured list, or the name rule): its
        materials need no "allowed for" property, and it has no separate sheet metal view."""
        if is_sheet_metal_view(library_id):
            return False
        if self._names is not None:
            return library_id.value.upper() in self._names
        return "SHEETMETAL" in library_id.value.replace(" ", "").upper()

    @staticmethod
    def resolve_path(library_root_directory: str | os.PathLike[str]) -> Path:
        """The rules file: `BANXOPEN_MATERIAL_LIBRARY_RULES` if set, otherwise `FILE_NAME` in the library folder."""
        return library_rules.resolve_path(library_root_directory)

    @staticmethod
    def load(path: str | os.PathLike[str], text: MaterialsText | None = None) -> SheetMetalLibraries:
        """Missing file: the name heuristic. Present but invalid: `MaterialLibraryRulesError`, worded by `text`.
        `OSError` (unreadable file) propagates. Property names match case-insensitively, as the C# reader did."""
        return SheetMetalLibraries.from_rules(read_library_rules(path, text), str(path), text)

    @staticmethod
    def from_rules(
        rules: LibraryRules | None, path: str = "", text: MaterialsText | None = None
    ) -> SheetMetalLibraries:
        """The list in the rules file's `sheetMetalLibraries`, or the name heuristic without one. An unusable list
        raises `MaterialLibraryRulesError`, worded by `text`."""
        text = text or MaterialsText.DEFAULT
        names: Any = (rules or {}).get(SHEET_METAL_LIBRARIES_KEY)
        if names is None:
            return SheetMetalLibraries.NAME_HEURISTIC
        if not isinstance(names, list):
            raise MaterialLibraryRulesError(
                text.library_rules_invalid_json(path, '"sheetMetalLibraries" is not a list')
            )
        try:
            return SheetMetalLibraries.from_names((str(n) for n in names if n is not None), text)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        except ValueError as ex:
            raise MaterialLibraryRulesError(text.library_rules_invalid(path, str(ex))) from ex


SheetMetalLibraries.NAME_HEURISTIC = SheetMetalLibraries(None)


class BlockRestrictedBodyTypeRule:
    """A sheet-metal-library material goes only on a SHEET_METAL body, and a sheet metal body takes only sheet metal
    library materials; any mismatch is blocked as "not available". Surface bodies (SHEET) are treated like solids.

    On top of that, a material from an ordinary library (or its sheet metal view) must allow the body's form in its
    "allowed for" property, so a material reaching the rule by another route than the library views is held to the
    same restriction. Materials in a sheet metal library file are exempt: their file says what they are for."""

    rule_id = "BLOCK_BODY_TYPE_RESTRICTION"
    order = MaterialRuleOrder.Validation.ELIGIBILITY

    def __init__(
        self,
        sheet_metal_libraries: SheetMetalLibraries | None = None,
        text: MaterialsText | None = None,
        material_forms: MaterialFormClassifier | None = None,
    ) -> None:
        self._libraries = sheet_metal_libraries or SheetMetalLibraries.NAME_HEURISTIC
        self._forms = material_forms or MaterialFormClassifier.DEFAULT
        self._text = text or MaterialsText.DEFAULT

    def evaluate(self, context: MaterialAssignmentRuleContext) -> RuleOutcome:
        material = context.requested_material
        kind = context.target_body.kind
        is_sheet_metal_library = self._libraries.is_sheet_metal_library(material.library_id)
        allowed = is_sheet_metal_library == (kind is BodyKind.SHEET_METAL) and (
            self._libraries.is_sheet_metal_file(material.library_id)
            or self._forms.allows(material, form_for_body(kind))
        )
        if allowed:
            return RuleOutcome(self.rule_id, RuleDecision.ALLOW, None, None)
        return RuleOutcome(
            self.rule_id,
            RuleDecision.BLOCK,
            MaterialsCodes.BODY_TYPE_RESTRICTED,
            self._text.body_type_restricted(material.name),
            args={"material": material.name},
        )


class SheetMetalLibraryRuleModule:
    ID = "SHEETMETAL.LIBRARY"

    def __init__(
        self,
        sheet_metal_libraries: SheetMetalLibraries | None = None,
        text: MaterialsText | None = None,
        material_forms: MaterialFormClassifier | None = None,
    ) -> None:
        self._validation: tuple[MaterialValidationRule, ...] = (
            BlockRestrictedBodyTypeRule(sheet_metal_libraries, text, material_forms),
        )

    @property
    def module_id(self) -> str:
        return self.ID

    @property
    def validation_rules(self) -> Sequence[MaterialValidationRule]:
        return self._validation

    @property
    def feature_constraints(self) -> Sequence[FeatureMaterialConstraintProvider]:
        return ()

    @property
    def side_effect_rules(self) -> Sequence[PostAssignmentEffectRule]:
        return ()
