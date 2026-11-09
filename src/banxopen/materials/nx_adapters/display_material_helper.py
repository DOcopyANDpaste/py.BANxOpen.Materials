"""Reads and writes a body's display/coating material, and executes ASSIGN_DISPLAY_MATERIAL instructions."""

# NX 2412's Python stubs declare instance methods without `self`, type enum members as int and give collections
# no __iter__; these rules would only report those stub defects here. Everything else is still checked.
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportReturnType=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false

from __future__ import annotations

import logging
from collections.abc import Sequence

import NXOpen

from banxopen.foundation import OperationResult
from banxopen.foundation.nx import BodyResolver, NxSessionContext, nx_error_code, nx_error_detail
from banxopen.materials.codes import MaterialsCodes
from banxopen.materials.core.assignment.planning import SideEffectInstruction
from banxopen.materials.core.rules.display import SyncCoatingDisplayMaterialEffectRule as Sync
from banxopen.materials.nx_adapters import uf_disp

_log = logging.getLogger(__name__)


class DisplayMaterialHelper:
    """Finds the named display material in the part (creating it if missing), assigns it to the body, and colours the
    body to match the coating.

    The colour half is not what it looks like: NX has NO API to set a display material's colour (a Studio material's
    appearance comes from its own definition). NX's own sample code colours a coating by assigning the display
    material AND setting `Body.Color` to the nearest entry in the colour table, which is what this does. The mapping is
    lossy on purpose: the colour read back will not equal the coating RGB written.

    No undo handling here: the part material service calls this inside the per-body undo scope, and an undo mark
    captures these UF calls like any other change.
    """

    def __init__(self, context: NxSessionContext) -> None:
        self._context = context

    @property
    def instruction_type(self) -> str:
        return Sync.INSTRUCTION_TYPE

    def execute(self, instruction: SideEffectInstruction, body: NXOpen.Body) -> OperationResult[None]:
        if instruction.instruction_type != self.instruction_type:
            return OperationResult.fail(
                MaterialsCodes.UNSUPPORTED_INSTRUCTION,
                f"DisplayMaterialHelper cannot execute instruction type '{instruction.instruction_type}'.",
            )
        # The data bag's shape is a contract with the rule that produced it, so it is validated, not trusted.
        name = instruction.data.get(Sync.DISPLAY_MATERIAL_NAME_KEY)
        if not isinstance(name, str) or not name.strip():
            return OperationResult.fail(
                MaterialsCodes.MALFORMED_INSTRUCTION,
                f"'{Sync.DISPLAY_MATERIAL_NAME_KEY}' is missing or not a non-empty string.",
            )
        rgb = instruction.data.get(Sync.RGB_KEY)
        if not _is_rgb(rgb):
            return OperationResult.fail(
                MaterialsCodes.MALFORMED_INSTRUCTION, f"'{Sync.RGB_KEY}' is missing or not three numbers."
            )
        used_default = instruction.data.get(Sync.USED_DEFAULT_KEY) is True

        try:
            uf = self._context.uf
            material_tag = uf_disp.find_material_in_part(uf, self._context.work_part.Tag, name)
            if material_tag is None:
                # UF_DISP_create_material has no get-or-create: calling it for an existing name makes a duplicate.
                material_tag = uf_disp.create_material(uf, name)
            uf_disp.assign_material(uf, material_tag, body.Tag)
            body.Color = uf_disp.closest_color(uf, _unit_rgb(rgb))  # type: ignore[arg-type]  # checked by _is_rgb
            body.RedisplayObject()
            uf_disp.refresh_material_display(uf, material_tag)
        except NXOpen.NXException as ex:
            _log.error("Failed to assign coating display material: %s", nx_error_detail(ex))
            return OperationResult.fail(nx_error_code(ex), nx_error_detail(ex))

        if used_default:
            _log.warning(
                "Body '%s': material has no coating properties defined — "
                "applied default display material '%s' instead.",
                BodyResolver.body_id(body),
                name,
            )
        else:
            _log.info(
                "Body '%s': assigned display material '%s' (tag %s).", BodyResolver.body_id(body), name, material_tag
            )
        return OperationResult.success()

    def remove(self, body: NXOpen.Body) -> OperationResult[None]:
        """Clears whatever display material is on `body`. Not instruction-driven: clearing bypasses the planner."""
        try:
            uf_disp.remove_material_assignment(self._context.uf, body.Tag)
        except NXOpen.NXException as ex:
            _log.error("Failed to remove display material: %s", nx_error_detail(ex))
            return OperationResult.fail(nx_error_code(ex), nx_error_detail(ex))
        return OperationResult.success()


def _is_rgb(value: object) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, str)
        and len(value) == 3  # pyright: ignore[reportUnknownArgumentType]
        and all(isinstance(c, int | float) for c in value)  # pyright: ignore[reportUnknownVariableType]
    )


def _unit_rgb(rgb: Sequence[float]) -> list[float]:
    """UF_DISP_rgb_model wants 0-1. Coating tables have been seen giving either 0-1 or 0-255 with nothing declaring
    which, so the range is inferred, the same defensive normalisation as the NX reference code."""
    return [c / 255.0 for c in rgb] if any(c > 1.0 for c in rgb) else [float(c) for c in rgb]
