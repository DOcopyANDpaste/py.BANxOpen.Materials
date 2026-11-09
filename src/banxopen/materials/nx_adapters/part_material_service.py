"""The seam to the live NX work part: implements `PartMaterialService`."""

# NX 2412's Python stubs declare instance methods without `self`, type enum members as int and give collections
# no __iter__; these rules would only report those stub defects here. Everything else is still checked.
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportReturnType=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence

import NXOpen

from banxopen.foundation import BodyId, BodyInfo, BodyKind, OperationResult
from banxopen.foundation.nx import BodyResolver, NxDialogText, NxSessionContext, UndoScope, nx_error_detail
from banxopen.materials.codes import MaterialsCodes
from banxopen.materials.core.assignment.part_materials import PartChangeOutcome
from banxopen.materials.core.assignment.planning import ExecutablePlan, SideEffectInstruction
from banxopen.materials.model.assignments import BodyMaterialAssignment
from banxopen.materials.model.materials import DisplayMaterial, MaterialId, MaterialLibrary, same_text
from banxopen.materials.nx_adapters import uf_disp
from banxopen.materials.nx_adapters.display_material_helper import DisplayMaterialHelper
from banxopen.materials.nx_adapters.physical_material_source import NxPhysicalMaterialSource
from banxopen.materials.nx_adapters.ports import SideEffectExecutor
from banxopen.materials.text import MaterialsText

_log = logging.getLogger(__name__)


class NxPartMaterialService:
    """Normally built by `MaterialEngine.create`, which also checks the executors cover every side effect the rules
    emit. `get_bodies` / `get_current_assignments` always rescan, per the port's contract."""

    def __init__(
        self,
        context: NxSessionContext,
        executors: Iterable[SideEffectExecutor],
        body_resolver: BodyResolver,
        display_materials: DisplayMaterialHelper,
        physical_materials: NxPhysicalMaterialSource,
        text: MaterialsText | None = None,
    ) -> None:
        self._context = context
        self._resolver = body_resolver
        self._display = display_materials
        self._physical = physical_materials
        self._text = text or MaterialsText.DEFAULT
        self._libraries: tuple[MaterialLibrary, ...] = ()
        self._executors: dict[str, SideEffectExecutor] = {}
        # A clash is a wiring error: replacing one module's effect with another's would change Apply silently.
        for executor in executors:
            if executor.instruction_type in self._executors:
                raise ValueError(
                    f"A side-effect executor for instruction type '{executor.instruction_type}' is already registered."
                )
            self._executors[executor.instruction_type] = executor

    def set_resolution_libraries(self, libraries: Sequence[MaterialLibrary]) -> None:
        self._libraries = tuple(libraries)

    # ---- Reads ----

    def get_bodies(self) -> list[BodyInfo]:
        result: list[BodyInfo] = []
        for body in self._resolver.refresh():
            kind = self._classify(body)
            result.append(
                BodyInfo(BodyResolver.body_id(body), body.Name or "", kind, self._volume(body, kind), _attributes(body))
            )
        return result

    def get_current_assignments(self) -> dict[BodyId, BodyMaterialAssignment]:
        result: dict[BodyId, BodyMaterialAssignment] = {}
        for body in self._resolver.refresh():
            body_id = BodyResolver.body_id(body)
            name = self._physical_material_name(body)
            resolved = self._resolve_by_name(name) if name else None
            result[body_id] = BodyMaterialAssignment(body_id, name, resolved, self._display_material(body))
        return result

    # ---- Writes ----

    def apply_plan(self, plan: ExecutablePlan) -> OperationResult[PartChangeOutcome]:
        # One apply is one batch: a declined load is asked about once here, not once per body.
        self._physical.begin_batch()
        try:
            self._resolver.refresh()
        except NXOpen.NXException as ex:
            _log.error("Failed to resolve bodies before applying plan: %s", nx_error_detail(ex))
            detail = self._text.apply_aborted(NxDialogText.DEFAULT.nx_error(ex))
            return _failed(MaterialsCodes.APPLY_ABORTED, detail, {a.body_id: detail for a in plan.assignments})

        failed: dict[BodyId, str] = {}
        attempted = False
        # Scope per plan, mark per body: one gesture is one Ctrl+Z, while a body that throws part-way rolls back
        # only itself and the rest of the plan proceeds.
        with UndoScope(self._context.session, "Apply Material Assignment") as plan_undo:
            for assignment in plan.assignments:
                body = self._resolver.resolve(assignment.body_id)
                if body is None:
                    _log.warning("Skipped assignment for body '%s': body could not be resolved.", assignment.body_id)
                    failed[assignment.body_id] = self._text.body_not_resolved
                    continue
                located = self._locate(assignment.material_id)
                if located is None:
                    _log.error(
                        "Skipped assignment for body '%s': material '%s' not found in the resolution libraries "
                        "(was set_resolution_libraries called with the library it came from?).",
                        assignment.body_id,
                        assignment.material_id,
                    )
                    failed[assignment.body_id] = self._text.material_not_resolved(str(assignment.material_id))
                    continue
                library_path, material_name = located
                resolved = self._physical.resolve(library_path, material_name)
                if resolved.material is None:
                    _log.error("Skipped assignment for body '%s': %s", assignment.body_id, resolved.failure_reason)
                    failed[assignment.body_id] = resolved.failure_reason or self._text.material_not_resolved(
                        material_name
                    )
                    continue

                attempted = True
                with UndoScope(self._context.session, f"Apply Material Assignment ({assignment.body_id})") as body_undo:
                    try:
                        resolved.material.AssignObjects([body])
                    except NXOpen.NXException as ex:
                        _log.error(
                            "Failed to assign physical material to body '%s': %s",
                            assignment.body_id,
                            nx_error_detail(ex),
                        )
                        failed[assignment.body_id] = self._text.nx_failed_on_body(nx_error_detail(ex))
                        continue  # body_undo rolls this body back
                    _log.debug(
                        "Body '%s': physical material '%s' written; %d side-effect(s) queued.",
                        assignment.body_id,
                        material_name,
                        len(assignment.side_effects),
                    )
                    for instruction in assignment.side_effects:
                        problem = self._run_side_effect(instruction, body)
                        if problem is not None:
                            failed[assignment.body_id] = self._text.side_effect_failed(problem)
                    body_undo.commit()

            if not attempted and plan.assignments:
                # Left uncommitted, so the plan-wide scope unwinds anything that did land.
                detail = self._text.apply_aborted(self._text.no_target_bodies_resolved)
                return _failed(MaterialsCodes.APPLY_ABORTED, detail, failed)
            if attempted:
                self._update_for_external_change("apply")
            # A partial failure still commits: the bodies that succeeded are kept.
            plan_undo.commit()

        if failed:
            return _failed(MaterialsCodes.PARTIAL_FAILURE, self._text.partial_failure, failed)
        return OperationResult.success(PartChangeOutcome())

    def clear_material(self, body_ids: Sequence[BodyId]) -> OperationResult[PartChangeOutcome]:
        try:
            self._resolver.refresh()
        except NXOpen.NXException as ex:
            _log.error("Failed to resolve bodies before clearing: %s", nx_error_detail(ex))
            detail = self._text.clear_aborted(NxDialogText.DEFAULT.nx_error(ex))
            return _failed(MaterialsCodes.CLEAR_ABORTED, detail, dict.fromkeys(body_ids, detail))

        failed: dict[BodyId, str] = {}
        attempted = False
        with UndoScope(self._context.session, "Clear Material") as clear_undo:
            for body_id in body_ids:
                body = self._resolver.resolve(body_id)
                if body is None:
                    _log.warning("Skipped clear for body '%s': body could not be resolved.", body_id)
                    failed[body_id] = self._text.body_not_resolved
                    continue
                attempted = True
                with UndoScope(self._context.session, f"Clear Material ({body_id})") as body_undo:
                    try:
                        self._remove_physical_material(body)
                    except NXOpen.NXException as ex:
                        _log.error(
                            "Failed to remove physical material from body '%s': %s", body_id, nx_error_detail(ex)
                        )
                        failed[body_id] = self._text.nx_failed_on_body(nx_error_detail(ex))
                    display = self._display.remove(body)
                    if not display.ok:
                        _log.error("Failed to remove display material from body '%s': %s", body_id, display.message)
                        failed[body_id] = self._text.nx_failed_on_body(display.message or "")
                    body_undo.commit()

            if not attempted and body_ids:
                detail = self._text.clear_aborted(self._text.no_target_bodies_resolved)
                return _failed(MaterialsCodes.CLEAR_ABORTED, detail, failed)
            if attempted:
                self._update_for_external_change("clear")
            clear_undo.commit()

        if failed:
            return _failed(MaterialsCodes.PARTIAL_FAILURE, self._text.partial_failure, failed)
        return OperationResult.success(PartChangeOutcome())

    # ---- Helpers ----

    def _run_side_effect(self, instruction: SideEffectInstruction, body: NXOpen.Body) -> str | None:
        """None on success, else a description of what went wrong."""
        instruction_type = instruction.instruction_type
        executor = self._executors.get(instruction_type)
        if executor is None:
            # MaterialEngine refuses to start without an executor, so this means a hand-built service.
            _log.error("No executor registered for instruction type '%s'.", instruction_type)
            return f"no executor for '{instruction_type}'"
        result = executor.execute(instruction, body)
        if result.ok:
            _log.debug("Side effect '%s' succeeded.", instruction_type)
            return None
        _log.error("Side effect '%s' failed: %s %s", instruction_type, result.error_code, result.message)
        return result.message or result.error_code or instruction_type

    def _locate(self, material_id: MaterialId) -> tuple[str, str] | None:
        """The library file path and NX name for a requested material. MaterialId is the library's own id, not the
        name NX identifies materials by, and NX's LoadFromLibrary needs the on-disk MatML file."""
        for library in self._libraries:
            for material in library.materials:
                if material.id == material_id:
                    return library.file_path, material.name
        return None

    def _resolve_by_name(self, name: str) -> MaterialId | None:
        for library in self._libraries:
            for material in library.materials:
                if same_text(material.name, name):
                    return material.id
        return None

    def _classify(self, body: NXOpen.Body) -> BodyKind:
        """Sheet metal first, through the sheet metal manager: NX sheet metal bodies are solids with a thickness, so
        `IsSheetBody` alone labels them Solid and the body-type rule would refuse every sheet metal material on them."""
        try:
            if self._context.work_part.Features.SheetmetalManager.IsSheetmetalBody(body):
                return BodyKind.SHEET_METAL
        except NXOpen.NXException:
            pass  # not answerable for this body: fall through to the plain solid/sheet test
        try:
            return BodyKind.SHEET if body.IsSheetBody else BodyKind.SOLID
        except NXOpen.NXException:
            return BodyKind.UNKNOWN

    def _volume(self, body: NXOpen.Body, kind: BodyKind) -> float:
        if kind not in (BodyKind.SOLID, BodyKind.SHEET_METAL):
            return 0.0
        try:
            return uf_disp.solid_volume_m3(self._context.uf, body.Tag)
        except NXOpen.NXException:
            return 0.0

    def _physical_material_name(self, body: NXOpen.Body) -> str | None:
        try:
            material = self._context.work_part.MaterialManager.PhysicalMaterials.AskMaterialOfObject(body)
        except NXOpen.NXException:
            return None  # a body with no physical material raises: the normal "unassigned" path
        name = material.Name if material is not None else None
        return name or None

    def _display_material(self, body: NXOpen.Body) -> DisplayMaterial | None:
        try:
            found = uf_disp.body_display_material(self._context.uf, body.Tag)
            if found is None:
                return None
            _tag, name = found
            r, g, b = uf_disp.color_rgb(self._context.uf, body.Color)
            return DisplayMaterial(MaterialId(name), name, (round(r * 255), round(g * 255), round(b * 255)))
        except NXOpen.NXException:
            return None

    def _remove_physical_material(self, body: NXOpen.Body) -> None:
        """Removes the physical material from `body` only. `UnassignAllObjects` is the only call that works, and it
        strips every body sharing the material, so the siblings are gathered first and reassigned afterwards."""
        materials = self._context.work_part.MaterialManager.PhysicalMaterials
        try:
            material = materials.AskMaterialOfObject(body)
        except NXOpen.NXException:
            return  # nothing assigned
        if material is None:
            return
        siblings = [
            other
            for other in self._context.work_part.Bodies
            if other.Tag != body.Tag and _has(materials, other, material)
        ]
        material.UnassignAllObjects()
        if siblings:
            material.AssignObjects(siblings)

    def _update_for_external_change(self, operation: str) -> None:
        """Tools > Update > Update for External Change. Expressions reading material properties (density, mass) do
        not refresh on their own, so this runs once after every apply or clear that touched a body, inside the caller's
        undo scope. A failure is logged, not raised: the material changes themselves have landed."""
        try:
            self._context.work_part.Expressions.UpdateForExternalChange()
        except NXOpen.NXException as ex:
            _log.error("Update for external change after %s failed: %s", operation, nx_error_detail(ex))


def _has(materials: NXOpen.PhysicalMaterialCollection, body: NXOpen.Body, material: NXOpen.PhysicalMaterial) -> bool:
    try:
        found = materials.AskMaterialOfObject(body)
    except NXOpen.NXException:
        return False
    return found is not None and found.Tag == material.Tag


def _attributes(body: NXOpen.Body) -> Mapping[str, str]:
    """The body's user attributes, title to string value. Best effort: a read failure must not block enumeration."""
    try:
        return {a.Title: a.StringValue or "" for a in body.GetUserAttributes()}
    except NXOpen.NXException:
        return {}


def _failed(code: str, message: str, failed: Mapping[BodyId, str]) -> OperationResult[PartChangeOutcome]:
    return OperationResult(False, PartChangeOutcome(dict(failed)), code, message)
