"""The material library directory on disk."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from banxopen.materials.model.materials import MaterialLibraryId, MaterialLibraryReference

_log = logging.getLogger(__name__)


class MaterialLibraryRepository(Protocol):
    """Seam to the material library directory. Core reads libraries only through this."""

    def list_available_libraries(self) -> Sequence[MaterialLibraryReference]: ...

    def read_library_xml(self, library_id: MaterialLibraryId) -> str: ...


class FileSystemMaterialLibraryRepository:
    """Scans a root directory for `*.xml` files: one `MaterialLibraryReference` per file, keyed by file name without
    extension. Pure file system, no NXOpen.

    The root is the material library folder: `%UGII_CUSTOMER_DIR%\\MATERIALS` when it exists, otherwise
    `%UGII_BASE_DIR%\\MATERIALS`. Library-wide settings such as the sheet metal library rules file live there too, so
    every tool reading these libraries reads the same settings.
    """

    def __init__(self, root_directory: str | os.PathLike[str] | None = None) -> None:
        self._root = Path(root_directory) if root_directory is not None else _default_root_directory()
        self._paths_by_id: dict[MaterialLibraryId, Path] | None = None

    @property
    def root_directory(self) -> Path:
        return self._root

    def list_available_libraries(self) -> list[MaterialLibraryReference]:
        references: list[MaterialLibraryReference] = []
        paths: dict[MaterialLibraryId, Path] = {}
        if not self._root.is_dir():
            _log.warning("Material library directory not found: %s", self._root)
            self._paths_by_id = paths
            return references

        for path in sorted(p for p in self._root.iterdir() if p.is_file() and p.suffix.lower() == ".xml"):
            library_id = MaterialLibraryId(path.stem)
            paths[library_id] = path
            references.append(MaterialLibraryReference(library_id, path.stem, str(path)))
        self._paths_by_id = paths
        return references

    def read_library_xml(self, library_id: MaterialLibraryId) -> str:
        if self._paths_by_id is None:
            self.list_available_libraries()
        path = (self._paths_by_id or {}).get(library_id)
        if path is None:
            raise FileNotFoundError(f"No material library found for id '{library_id}' under '{self._root}'.")
        return path.read_text(encoding="utf-8-sig")


def _default_root_directory() -> Path:
    # VERIFY (carried from C#): the conventional folder for shipped/customer libraries. A customer-authored folder
    # takes precedence when both exist.
    customer_dir = os.environ.get("UGII_CUSTOMER_DIR")
    if customer_dir:
        candidate = Path(customer_dir) / "MATERIALS"
        if candidate.is_dir():
            return candidate
    base_dir = os.environ.get("UGII_BASE_DIR")
    if not base_dir:
        raise RuntimeError("UGII_BASE_DIR is not set — cannot resolve the material library directory.")
    return Path(base_dir) / "MATERIALS"
