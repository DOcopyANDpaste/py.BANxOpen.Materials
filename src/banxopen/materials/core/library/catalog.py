"""The libraries a user picks from: each library file, plus a sheet metal view of every file holding sheet metal
materials."""

from __future__ import annotations

import logging
from dataclasses import replace

from banxopen.materials.core.library.loader import CachingMaterialLibraryLoader
from banxopen.materials.core.library.repository import MaterialLibraryRepository
from banxopen.materials.core.rules.material_forms import MaterialForm, MaterialFormClassifier
from banxopen.materials.core.rules.sheet_metal import SheetMetalLibraries, is_sheet_metal_view, sheet_metal_view_id
from banxopen.materials.model.materials import MaterialLibrary, MaterialLibraryId, MaterialLibraryReference
from banxopen.materials.text import MaterialsText

_log = logging.getLogger(__name__)


class MaterialLibraryCatalog:
    """Sheet metal materials share a library file with the others; the user still picks them from a library of their
    own, which behaves as a sheet metal library always has.

    For each library file with at least one material whose "allowed for" property lists sheet metal, the catalog lists
    a second library right after it: its sheet metal view, named `<library>_SheetMetal` (`MaterialsText`), with an id
    from `sheet_metal_view_id` and the same file path (NX loads a material from the file by name). Loaded:
    - the view holds the materials allowing sheet metal, each carrying the view's id as its `library_id`;
    - the file holds the materials allowing solids, so a sheet-metal-only material shows only in the view;
    - a sheet metal library file (`SheetMetalLibraries.is_sheet_metal_file`) is listed and loaded as it is, with no
      view: every material in it is a sheet metal material already.

    Single-threaded and cached for the session, like the loader underneath.
    """

    def __init__(
        self,
        repository: MaterialLibraryRepository,
        sheet_metal_libraries: SheetMetalLibraries | None = None,
        material_forms: MaterialFormClassifier | None = None,
        loader: CachingMaterialLibraryLoader | None = None,
        text: MaterialsText | None = None,
    ) -> None:
        self._repository = repository
        self._sheet_metal = sheet_metal_libraries or SheetMetalLibraries.NAME_HEURISTIC
        self._forms = material_forms or MaterialFormClassifier.DEFAULT
        self._loader = loader or CachingMaterialLibraryLoader(repository)
        self._text = text or MaterialsText.DEFAULT
        self._has_view: dict[MaterialLibraryId, bool] = {}
        self._view_sources: dict[MaterialLibraryId, MaterialLibraryReference] = {}
        self._loaded: dict[MaterialLibraryId, MaterialLibrary] = {}

    def list_libraries(self) -> list[MaterialLibraryReference]:
        """Every library file, each followed by its sheet metal view when it has one."""
        result: list[MaterialLibraryReference] = []
        for reference in self._repository.list_available_libraries():
            result.append(reference)
            if self._has_sheet_metal_view(reference):
                view = MaterialLibraryReference(
                    sheet_metal_view_id(reference.id),
                    self._text.sheet_metal_library_name(reference.display_name),
                    reference.file_path,
                )
                self._view_sources[view.id] = reference
                result.append(view)
        return result

    def is_sheet_metal_library(self, library_id: MaterialLibraryId) -> bool:
        return self._sheet_metal.is_sheet_metal_library(library_id)

    def load(self, reference: MaterialLibraryReference) -> MaterialLibrary:
        """The library as the user sees it (see the class). Raises as the repository and parser do for the file."""
        loaded = self._loaded.get(reference.id)
        if loaded is not None:
            return loaded
        if is_sheet_metal_view(reference.id):
            library = self._load_view(reference)
        else:
            library = self._loader.get_or_load(reference)
            if not self._sheet_metal.is_sheet_metal_file(reference.id):
                library = self._only(library, MaterialForm.SOLID)
        self._loaded[reference.id] = library
        return library

    def _load_view(self, reference: MaterialLibraryReference) -> MaterialLibrary:
        source = self._view_sources.get(reference.id)
        if source is None:
            self.list_libraries()
            source = self._view_sources.get(reference.id)
        if source is None:
            raise FileNotFoundError(f"No material library has the sheet metal view '{reference.id}'.")
        sheet_metal = self._only(self._loader.get_or_load(source), MaterialForm.SHEET_METAL)
        return replace(
            sheet_metal,
            id=reference.id,
            display_name=reference.display_name,
            materials=tuple(replace(m, library_id=reference.id) for m in sheet_metal.materials),
        )

    def _only(self, library: MaterialLibrary, form: MaterialForm) -> MaterialLibrary:
        materials = tuple(m for m in library.materials if self._forms.allows(m, form))
        return library if len(materials) == len(library.materials) else replace(library, materials=materials)

    def _has_sheet_metal_view(self, reference: MaterialLibraryReference) -> bool:
        """Whether the file holds a material allowing sheet metal. Only files whose text mentions the property are
        parsed; a file that cannot be read or parsed gets no view here, and its error shows when it is opened."""
        known = self._has_view.get(reference.id)
        if known is not None:
            return known
        has_view = False
        if not self._sheet_metal.is_sheet_metal_file(reference.id):
            try:
                if self._forms.may_mention(self._repository.read_library_xml(reference.id)):
                    library = self._loader.get_or_load(reference)
                    has_view = any(self._forms.allows(m, MaterialForm.SHEET_METAL) for m in library.materials)
            except (OSError, ValueError) as ex:
                _log.warning("Could not check '%s' for sheet metal materials: %s", reference.id, ex)
        self._has_view[reference.id] = has_view
        return has_view
