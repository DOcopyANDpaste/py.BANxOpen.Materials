"""The material engine as an entry point uses it: rules, executors, part service and the per-gesture service."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable

from banxopen.foundation import OperationResult
from banxopen.foundation.nx import BodyResolver, NxSessionContext
from banxopen.materials.codes import MaterialsCodes
from banxopen.materials.core.assignment.service import MaterialAssignmentService
from banxopen.materials.core.library.repository import FileSystemMaterialLibraryRepository
from banxopen.materials.core.rules.library_rules import MaterialLibraryRulesError, read_library_rules, resolve_path
from banxopen.materials.core.rules.material_forms import MaterialFormClassifier
from banxopen.materials.core.rules.rule_set import MaterialRuleSet
from banxopen.materials.core.rules.sheet_metal import SheetMetalLibraries
from banxopen.materials.nx_adapters.display_material_helper import DisplayMaterialHelper
from banxopen.materials.nx_adapters.part_material_service import NxPartMaterialService
from banxopen.materials.nx_adapters.physical_material_source import NxPhysicalMaterialSource
from banxopen.materials.nx_adapters.ports import NxMaterialRuleModule, SideEffectExecutor
from banxopen.materials.text import MaterialsText

_log = logging.getLogger(__name__)


class MaterialEngine:
    """Building it here, once, keeps the Material Assignment dialog and every feature tool enforcing the same rules
    with the same wiring.

    A configuration problem the user can fix (an invalid library rules file, no library folder) comes back as a failed
    result to show. A wiring mistake (a duplicate rule id, a side effect with no executor) raises, because it is a
    defect the first launch should expose rather than a dialog running with a rule missing.
    """

    def __init__(
        self,
        rules: MaterialRuleSet,
        part_materials: NxPartMaterialService,
        repository: FileSystemMaterialLibraryRepository,
        sheet_metal_libraries: SheetMetalLibraries,
        service: MaterialAssignmentService,
        text: MaterialsText,
        material_forms: MaterialFormClassifier | None = None,
    ) -> None:
        """Use `create`."""
        self.rules = rules
        self.part_materials = part_materials
        self.repository = repository
        self.sheet_metal_libraries = sheet_metal_libraries
        """The same list the body-type rule enforces, so a tool looking a sheet metal material up by name searches
        exactly the libraries the rules accept. Includes every library's `_SheetMetal` view."""
        self.material_forms = material_forms or MaterialFormClassifier.DEFAULT
        """What each material may be used for (its "allowed for" property), as the body-type rule reads it."""
        self.service = service
        """The per-gesture operations for tools: browse, plan, apply, clear."""
        self.text = text

    @staticmethod
    def create(
        context: NxSessionContext,
        domain_modules: Iterable[NxMaterialRuleModule] = (),
        *,
        library_root: str | os.PathLike[str] | None = None,
        body_resolver: BodyResolver | None = None,
        confirm_load: Callable[[str], bool] | None = None,
        text: MaterialsText | None = None,
    ) -> OperationResult[MaterialEngine]:
        """`domain_modules` are the feature domains' modules (e.g. SheetMetal's). `library_root` defaults to the NX
        material library folder. `confirm_load` asks before the slow load of a material from NX's own library; it
        defaults to an NX message box."""
        text = text or MaterialsText.DEFAULT
        try:
            repository = FileSystemMaterialLibraryRepository(library_root)
        except RuntimeError as ex:
            _log.error("Material library folder could not be resolved: %s", ex)
            return OperationResult.fail(
                MaterialsCodes.MATERIAL_RULES_UNAVAILABLE, text.material_rules_unavailable(str(ex))
            )

        rules_path = resolve_path(repository.root_directory)
        try:
            library_rules = read_library_rules(rules_path, text)
            sheet_metal_libraries = SheetMetalLibraries.from_rules(library_rules, str(rules_path), text)
            material_forms = MaterialFormClassifier.from_rules(library_rules, str(rules_path), text)
        except (MaterialLibraryRulesError, OSError) as ex:
            _log.error("Material library rules could not be loaded: %s", ex)
            return OperationResult.fail(
                MaterialsCodes.MATERIAL_RULES_UNAVAILABLE, text.material_rules_unavailable(str(ex))
            )
        if not sheet_metal_libraries.is_configured:
            _log.info(
                "No sheet metal library list in %s; sheet metal library files are recognised by name.", rules_path
            )
        _log.info("Material forms are read from the '%s' property.", material_forms.property_name)

        domains = tuple(domain_modules)
        rules = MaterialRuleSet.from_modules(
            (*MaterialRuleSet.baseline(sheet_metal_libraries, text, material_forms), *domains), text
        )

        # Display material sync is a baseline side effect, so its executor is the one this library owns.
        display = DisplayMaterialHelper(context)
        executors: list[SideEffectExecutor] = [display, *(e for d in domains for e in d.side_effect_executors)]
        rules.ensure_executors_for(e.instruction_type for e in executors)

        physical = NxPhysicalMaterialSource(context, confirm_load or _ask_with_message_box, text)
        part = NxPartMaterialService(
            context, executors, body_resolver or BodyResolver(context), display, physical, text
        )
        service = MaterialAssignmentService(
            rules,
            part,
            repository,
            sheet_metal_libraries,
            is_sheet_metal_application=context.is_sheet_metal_application,
            material_forms=material_forms,
            text=text,
        )
        return OperationResult.success(
            MaterialEngine(rules, part, repository, sheet_metal_libraries, service, text, material_forms)
        )


def _ask_with_message_box(question: str) -> bool:
    from banxopen.foundation.ui import NxMessenger

    return NxMessenger().ask(question)
