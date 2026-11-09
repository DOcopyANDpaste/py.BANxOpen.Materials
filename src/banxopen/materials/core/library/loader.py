"""Reads and parses each library once."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from banxopen.materials.core.library.parser import MaterialLibraryParser, MatmlParser
from banxopen.materials.core.library.repository import MaterialLibraryRepository
from banxopen.materials.model.materials import MaterialLibrary, MaterialLibraryId, MaterialLibraryReference


class CachingMaterialLibraryLoader:
    """Reads (through the repository) and parses a library only the first time it is requested; later requests for
    the same id return the cached library without touching the repository or parser. Single-threaded by design, like
    the dialogs that use it."""

    def __init__(self, repository: MaterialLibraryRepository, parser: MaterialLibraryParser | None = None) -> None:
        self._repository = repository
        self._parser = parser or MatmlParser()
        self._cache: dict[MaterialLibraryId, MaterialLibrary] = {}

    def get_or_load(self, reference: MaterialLibraryReference) -> MaterialLibrary:
        cached = self._cache.get(reference.id)
        if cached is not None:
            return cached

        parsed = self._parser.parse(
            reference.id, reference.display_name, self._repository.read_library_xml(reference.id)
        )
        bmp_directory = Path(reference.file_path).parent / "BMPs"
        materials = tuple(replace(m, image_path=_image_path(bmp_directory, m.name)) for m in parsed.materials)
        library = replace(parsed, file_path=reference.file_path, materials=materials)
        self._cache[reference.id] = library
        return library


def _image_path(bmp_directory: Path, material_name: str) -> str:
    candidate = bmp_directory / f"{material_name}.bmp"
    return str(candidate if candidate.is_file() else bmp_directory / "default.bmp")
