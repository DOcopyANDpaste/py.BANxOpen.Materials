"""The material library rules file, `material-library-rules.json`, read once and shared by every setting in it.

It holds library-wide settings (which libraries are sheet metal, which property says what a material may be used for),
so every tool reading the libraries reads the same rules. Each setting parses its own part of the document.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from banxopen.materials.text import MaterialsText

FILE_NAME: Final = "material-library-rules.json"
PATH_ENVIRONMENT_VARIABLE: Final = "BANXOPEN_MATERIAL_LIBRARY_RULES"
"""Points at a rules file elsewhere, e.g. when the library folder is under Program Files and not writable."""

SHEET_METAL_LIBRARIES_KEY: Final = "SHEETMETALLIBRARIES"
MATERIAL_FORMS_KEY: Final = "MATERIALFORMS"

LibraryRules = Mapping[str, Any]
"""The top-level settings of the rules file, keyed by upper-cased property name (names match case-insensitively, as
the C# reader did)."""


class MaterialLibraryRulesError(ValueError):
    """The library rules file exists but cannot be used. The message is user-facing (`MaterialsText`) and is shown at
    start-up: silently falling back would drop a restriction someone configured on purpose."""


def resolve_path(library_root_directory: str | os.PathLike[str]) -> Path:
    """The rules file: `BANXOPEN_MATERIAL_LIBRARY_RULES` if set, otherwise `FILE_NAME` in the library folder."""
    override = os.environ.get(PATH_ENVIRONMENT_VARIABLE)
    if override is None or not override.strip():
        return Path(library_root_directory) / FILE_NAME
    return Path(override)


def read_library_rules(path: str | os.PathLike[str], text: MaterialsText | None = None) -> LibraryRules | None:
    """The file's settings, or None when there is no file. Present but unusable: `MaterialLibraryRulesError`, worded
    by `text`; a file with none of the known settings is unusable too. `OSError` (unreadable file) propagates."""
    text = text or MaterialsText.DEFAULT
    file = Path(path)
    if not file.is_file():
        return None

    try:
        document: Any = json.loads(file.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as ex:
        raise MaterialLibraryRulesError(text.library_rules_invalid_json(str(path), str(ex))) from ex
    if not isinstance(document, dict):
        raise MaterialLibraryRulesError(text.library_rules_invalid_json(str(path), "the top level is not an object"))

    entries: dict[str, Any] = {str(k).upper(): v for k, v in document.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if SHEET_METAL_LIBRARIES_KEY not in entries and MATERIAL_FORMS_KEY not in entries:
        raise MaterialLibraryRulesError(text.library_rules_missing_list(str(path)))
    return entries
