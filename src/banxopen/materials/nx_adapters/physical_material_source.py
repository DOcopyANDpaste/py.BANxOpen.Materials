"""Turns a (library, material name) pair into a PhysicalMaterial that exists in the work part."""

# NX 2412's Python stubs declare instance methods without `self`, type enum members as int and give collections
# no __iter__; these rules would only report those stub defects here. Everything else is still checked.
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportReturnType=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import NXOpen

from banxopen.foundation.nx import NxSessionContext, nx_error_detail
from banxopen.materials.text import MaterialsText

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Resolved:
    material: NXOpen.PhysicalMaterial | None
    failure_reason: str | None = None
    """User-facing (MaterialsText), set when `material` is None."""


class NxPhysicalMaterialSource:
    """The single place that pays the cost of NX's material library, and the reason browsing never does.

    Tools browse through the MatML reader, which is instant and the only source of categories and properties. NX's
    own library is much slower and is consulted only at the moment a material is assigned: never in bulk, never on a
    library switch. Both read the same files, so the NX library is addressed by our library's file path.

    Resolution order: cache, then materials already in the part, then (after asking, because this is the slow step) a
    load from the NX library.
    """

    def __init__(
        self,
        context: NxSessionContext,
        confirm_load: Callable[[str], bool],
        text: MaterialsText | None = None,
    ) -> None:
        """`confirm_load` asks the user whether to run the slow load (e.g. `NxMessenger().ask`). Injected so this
        stays free of UI."""
        self._context = context
        self._confirm_load = confirm_load
        self._text = text or MaterialsText.DEFAULT
        self._resolved: dict[str, NXOpen.PhysicalMaterial] = {}
        """Resolved this session: assigning one material to fifty bodies pays the load once."""
        self._declined: set[str] = set()
        """Declined loads; shorter-lived than `_resolved`, see `begin_batch`."""

    def begin_batch(self) -> None:
        """Starts a new apply. A decline suppresses re-prompting for the rest of THIS apply (fifty bodies ask once)
        without suppressing it for the rest of the session, which would leave the user unable to change their mind."""
        self._declined.clear()

    def resolve(self, library_path: str, material_name: str) -> Resolved:
        """The material, or None with the reason: the user declined the load, or NX does not have it. Callers fail
        only the body in hand, never the whole plan."""
        key = material_name.upper()
        cached = self._resolved.get(key)
        if cached is not None:
            return Resolved(cached)
        if key in self._declined:
            return Resolved(None, self._text.physical_material_load_declined(material_name))

        in_part = self._find_in_part(material_name)
        if in_part is not None:
            self._resolved[key] = in_part
            return Resolved(in_part)

        if not self._confirm_load(self._text.confirm_load_physical_material(material_name, library_path)):
            self._declined.add(key)
            return Resolved(None, self._text.physical_material_load_declined(material_name))

        try:
            _log.info("Loading physical material '%s' from NX library '%s'...", material_name, library_path)
            loaded = self._context.work_part.MaterialManager.PhysicalMaterials.LoadFromLibrary(
                library_path, material_name
            )
            _log.info("Loaded '%s'.", material_name)
        except NXOpen.NXException as ex:
            return Resolved(
                None, self._text.physical_material_not_found(material_name, library_path, nx_error_detail(ex))
            )
        self._resolved[key] = loaded
        return Resolved(loaded)

    def _find_in_part(self, material_name: str) -> NXOpen.PhysicalMaterial | None:
        try:
            # The collection is typed to the Material base; only a PhysicalMaterial can be a bulk material.
            for material in self._context.work_part.MaterialManager.PhysicalMaterials:
                if isinstance(material, NXOpen.PhysicalMaterial) and material.Name.upper() == material_name.upper():
                    return material
        except NXOpen.NXException as ex:
            _log.warning("Could not list the physical materials already in the part: %s", nx_error_detail(ex))
        return None
