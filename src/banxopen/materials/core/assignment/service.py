"""The per-gesture operations every material tool uses. Pure: NX is reached only through `PartMaterialService`."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence, Set

from banxopen.foundation import BodyId, BodyInfo, OperationResult
from banxopen.materials.codes import MaterialsCodes
from banxopen.materials.core.assignment.part_materials import PartChangeOutcome, PartMaterialService
from banxopen.materials.core.assignment.planning import MaterialAssignmentPlanningInput
from banxopen.materials.core.assignment.verdicts import PlannedAssignment, verdicts_for
from banxopen.materials.core.library.catalog import MaterialLibraryCatalog
from banxopen.materials.core.library.category_tree import MaterialCategoryNode, build_category_tree
from banxopen.materials.core.library.loader import CachingMaterialLibraryLoader
from banxopen.materials.core.library.repository import MaterialLibraryRepository
from banxopen.materials.core.rules.material_forms import MaterialFormClassifier
from banxopen.materials.core.rules.rule_set import MaterialRuleSet
from banxopen.materials.core.rules.sheet_metal import SheetMetalLibraries
from banxopen.materials.model.assignments import (
    AssignmentReport,
    BodyMaterialAssignment,
    BodyOutcome,
    OutcomeStatus,
    VerdictStatus,
)
from banxopen.materials.model.materials import (
    Material,
    MaterialLibrary,
    MaterialLibraryId,
    MaterialLibraryReference,
)
from banxopen.materials.text import MaterialsText

_log = logging.getLogger(__name__)


class MaterialAssignmentService:
    """Browse libraries, plan, apply and clear: each call is one user gesture, and every business decision behind it
    (which libraries to offer, what the rules say per body, what to ask, which bodies took) is made here, so every tool
    that assigns material behaves the same and a rule change needs no tool change.

    Normally built by `banxopen.materials.nx.MaterialEngine.create`; any `PartMaterialService` (a fake in tests) works.
    """

    def __init__(
        self,
        rules: MaterialRuleSet,
        part: PartMaterialService,
        repository: MaterialLibraryRepository,
        sheet_metal_libraries: SheetMetalLibraries,
        *,
        is_sheet_metal_application: bool = False,
        material_forms: MaterialFormClassifier | None = None,
        loader: CachingMaterialLibraryLoader | None = None,
        text: MaterialsText | None = None,
    ) -> None:
        """`sheet_metal_libraries` and `material_forms` must be the ones `rules` was built with, so the libraries
        offered and the rules enforced agree."""
        self._planner = rules.create_planner()
        self._finalizer = rules.create_finalizer()
        self._part = part
        self._text = text or MaterialsText.DEFAULT
        self._catalog = MaterialLibraryCatalog(
            repository,
            sheet_metal_libraries,
            material_forms,
            loader or CachingMaterialLibraryLoader(repository),
            self._text,
        )
        self._is_sheet_metal_application = is_sheet_metal_application

    # ---- Libraries ----

    def list_libraries(self) -> list[MaterialLibraryReference]:
        """Every library, each followed by its `<name>_SheetMetal` view when it holds sheet metal materials (see
        `MaterialLibraryCatalog`). In the NX Sheet Metal application only sheet metal libraries are offered; if there
        is none, every library is offered rather than none, and the gap is logged."""
        everything = self._catalog.list_libraries()
        if not self._is_sheet_metal_application:
            return everything
        sheet_metal = [r for r in everything if self._catalog.is_sheet_metal_library(r.id)]
        if sheet_metal:
            return sheet_metal
        _log.warning(
            "NX is in the Sheet Metal application, but no available library is a sheet metal library; "
            "listing every library."
        )
        return everything

    def is_sheet_metal_library(self, library_id: MaterialLibraryId) -> bool:
        """True for a sheet metal library file and for a library's `_SheetMetal` view."""
        return self._catalog.is_sheet_metal_library(library_id)

    def load_library(self, reference: MaterialLibraryReference) -> MaterialLibrary:
        """The library as offered (cached): a file's solid materials, or its sheet metal view. It also becomes the
        library current assignments are resolved against."""
        library = self._catalog.load(reference)
        self._part.set_resolution_libraries([library])
        return library

    def category_tree(self, library: MaterialLibrary) -> tuple[MaterialCategoryNode, ...]:
        return build_category_tree(library)

    # ---- The part ----

    def bodies(self) -> Sequence[BodyInfo]:
        """A fresh scan of the work part's bodies."""
        return self._part.get_bodies()

    def current_assignments(self) -> dict[BodyId, BodyMaterialAssignment]:
        """A fresh read of every body's physical and display material."""
        return dict(self._part.get_current_assignments())

    # ---- Gestures ----

    def plan(self, material: Material, body_ids: Iterable[BodyId], *, variant: str | None = None) -> PlannedAssignment:
        """What the rules say about assigning `material` to the bodies still in the part, without changing anything.
        `variant` is the domain's variant of the material (for sheet metal, the standards file row)."""
        targets, _ = self._present(body_ids)
        return self._plan(material, targets, self._part.get_current_assignments(), variant)

    def apply(
        self,
        material: Material,
        body_ids: Iterable[BodyId],
        *,
        variant: str | None = None,
        confirmed: Set[BodyId] = frozenset(),
        confirm_remaining: bool | None = None,
    ) -> OperationResult[AssignmentReport]:
        """Re-plans against the part as it stands now, then applies in one undoable step.

        Confirmation: bodies in `confirmed` are taken as confirmed (e.g. when staged earlier). If others need it and
        `confirm_remaining` is None, nothing is changed and an `OperationResult.confirm` comes back with one question
        covering them; call again with `confirm_remaining=True` (apply to them too) or `False` (skip them, apply the
        rest).

        The report covers every requested body. `ok` is false only when NX could not do what it was asked
        (APPLY_ABORTED, PARTIAL_FAILURE); blocked, declined and vanished bodies are reported, not failures.
        """
        targets, gone = self._present(body_ids)
        planned = self._plan(material, targets, self._part.get_current_assignments(), variant)

        confirmed_ids = set(confirmed)
        remaining = [v for v in planned.needing_confirmation if v.body.id not in confirmed_ids]
        if remaining:
            if confirm_remaining is None:
                lines = [self._text.body_line(v.body.name, v.message or "") for v in remaining]
                return OperationResult.confirm(self._text.confirm_bodies(len(remaining), material.name, lines))
            if confirm_remaining:
                confirmed_ids.update(v.body.id for v in remaining)

        executable = self._finalizer.finalize(planned.plan, planned.input, confirmed_ids)
        result: OperationResult[PartChangeOutcome] = OperationResult.success(PartChangeOutcome())
        if executable.assignments:
            result = self._part.apply_plan(executable)
        failed = _failures(result, (a.body_id for a in executable.assignments), self._text)

        blocked = set(executable.skipped_blocked)
        declined = set(executable.skipped_declined_confirmation)
        outcomes = [*gone]
        for verdict in planned.verdicts:
            body = verdict.body
            if body.id in blocked:
                outcomes.append(
                    BodyOutcome(body.id, body.name, OutcomeStatus.BLOCKED, self._text.blocked(verdict.message))
                )
            elif body.id in declined:
                outcomes.append(BodyOutcome(body.id, body.name, OutcomeStatus.DECLINED, self._text.not_confirmed))
            elif body.id in failed:
                outcomes.append(BodyOutcome(body.id, body.name, OutcomeStatus.FAILED, failed[body.id]))
            else:
                warning = verdict.message if verdict.status is VerdictStatus.OK and verdict.message else None
                outcomes.append(
                    BodyOutcome(
                        body.id, body.name, OutcomeStatus.APPLIED, self._text.warning(warning) if warning else None
                    )
                )
        return _with_report(result, AssignmentReport(tuple(outcomes)))

    def clear(self, body_ids: Iterable[BodyId]) -> OperationResult[AssignmentReport]:
        """Removes the physical and display material from the bodies still in the part, in one undoable step. A body
        with no material has nothing to remove and is reported as such."""
        targets, gone = self._present(body_ids)
        assignments = self._part.get_current_assignments()
        with_material = [b for b in targets if _material_of(assignments, b.id) is not None]

        result: OperationResult[PartChangeOutcome] = OperationResult.success(PartChangeOutcome())
        if with_material:
            result = self._part.clear_material([b.id for b in with_material])
        failed = _failures(result, (b.id for b in with_material), self._text)

        outcomes = [*gone]
        clearing = {b.id for b in with_material}
        for body in targets:
            if body.id not in clearing:
                outcomes.append(BodyOutcome(body.id, body.name, OutcomeStatus.NO_MATERIAL, self._text.has_no_material))
            elif body.id in failed:
                outcomes.append(BodyOutcome(body.id, body.name, OutcomeStatus.FAILED, failed[body.id]))
            else:
                outcomes.append(BodyOutcome(body.id, body.name, OutcomeStatus.APPLIED))
        return _with_report(result, AssignmentReport(tuple(outcomes)))

    # ---- Preferred material ----

    def preferred_material(self) -> str | None:
        """A fresh read of the part's preferred material (`MaterialPartAttributes.PREFERRED_MATERIAL`)."""
        name = self._part.get_preferred_material()
        return (name.strip() or None) if name is not None else None

    def set_preferred_material(self, name: str) -> OperationResult[None]:
        """Writes the part's preferred material. Any material name is accepted, whether or not a body carries it: that
        policy is the tool's. Writing the value the part already holds (case-insensitively) changes nothing."""
        wanted = name.strip()
        if not wanted:
            return OperationResult.fail(MaterialsCodes.PREFERRED_MATERIAL_BLANK, self._text.preferred_material_blank)
        current = self.preferred_material()
        if current is not None and current.casefold() == wanted.casefold():
            _log.debug("Preferred material is already '%s'; not rewritten.", current)
            return OperationResult.success()
        result = self._part.set_preferred_material(wanted)
        if result.ok:
            _log.info("Preferred material set to '%s' (was '%s').", wanted, current or "unset")
        return result

    # ---- Helpers ----

    def _present(self, body_ids: Iterable[BodyId]) -> tuple[list[BodyInfo], list[BodyOutcome]]:
        """The requested bodies still in the part (in request order, once each), and an outcome for each one gone."""
        by_id = {b.id: b for b in self._part.get_bodies()}
        present: list[BodyInfo] = []
        gone: list[BodyOutcome] = []
        for body_id in dict.fromkeys(body_ids):
            body = by_id.get(body_id)
            if body is None:
                gone.append(BodyOutcome(body_id, str(body_id), OutcomeStatus.NOT_IN_PART, self._text.no_longer_in_part))
            else:
                present.append(body)
        return present, gone

    def _plan(
        self,
        material: Material,
        targets: Sequence[BodyInfo],
        assignments: Mapping[BodyId, BodyMaterialAssignment],
        variant: str | None,
    ) -> PlannedAssignment:
        planning_input = MaterialAssignmentPlanningInput(
            requested_material=material,
            target_bodies=tuple(targets),
            current_assignments=dict(assignments),
            requested_variant=variant,
        )
        plan = self._planner.plan(planning_input)
        return PlannedAssignment(planning_input, plan, verdicts_for(planning_input, plan, self._text))


def _material_of(assignments: Mapping[BodyId, BodyMaterialAssignment], body_id: BodyId) -> str | None:
    assignment = assignments.get(body_id)
    return assignment.material_name if assignment is not None else None


def _failures(
    result: OperationResult[PartChangeOutcome], attempted: Iterable[BodyId], text: MaterialsText
) -> dict[BodyId, str]:
    """Per-body failure reasons. A failed result without a per-body outcome failed every body it was given."""
    if result.value is not None:
        return dict(result.value.failed)
    if result.ok:
        return {}
    reason = result.message or text.nx_failed_on_body(result.error_code or "")
    return dict.fromkeys(attempted, reason)


def _with_report(
    result: OperationResult[PartChangeOutcome], report: AssignmentReport
) -> OperationResult[AssignmentReport]:
    if result.ok:
        return OperationResult.success(report, message=result.message)
    return OperationResult(False, report, result.error_code, result.message)
