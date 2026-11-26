"""The port to the NX work part, implemented by the NX adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from banxopen.foundation import BodyId, BodyInfo, OperationResult
from banxopen.materials.core.assignment.planning import ExecutablePlan
from banxopen.materials.model.assignments import BodyMaterialAssignment
from banxopen.materials.model.materials import MaterialLibrary


def _no_failures() -> Mapping[BodyId, str]:
    return {}


@dataclass(frozen=True, slots=True)
class PartChangeOutcome:
    """What the part service could not do, per body, as user-facing reasons (`MaterialsText`). Every body of the
    plan not listed here was changed."""

    failed: Mapping[BodyId, str] = field(default_factory=_no_failures)


class PartMaterialService(Protocol):
    """Seam to the NX work part. `get_bodies` and `get_current_assignments` are always a fresh rescan: what a tool
    shows must reflect the live part, never session-cached state.

    `apply_plan` and `clear_material` return their `PartChangeOutcome` as the result's value on failure too
    (APPLY_ABORTED, CLEAR_ABORTED, PARTIAL_FAILURE), so a caller always knows which bodies did not change.
    """

    def get_bodies(self) -> Sequence[BodyInfo]:
        """Every body in the work part (solid, sheet, sheet metal and unknown alike); callers filter on `kind`."""
        ...

    def get_current_assignments(self) -> Mapping[BodyId, BodyMaterialAssignment]: ...

    def set_resolution_libraries(self, libraries: Sequence[MaterialLibrary]) -> None:
        """Which loaded libraries physical-material names are matched against. Re-register whenever the library
        selection changes."""
        ...

    def apply_plan(self, plan: ExecutablePlan) -> OperationResult[PartChangeOutcome]:
        """One plan-wide undo scope, one mark per body: one Ctrl+Z takes the whole apply back."""
        ...

    def clear_material(self, body_ids: Sequence[BodyId]) -> OperationResult[PartChangeOutcome]:
        """Clears both the physical and the display material. Bypasses the planner: there is no material to plan."""
        ...

    def get_preferred_material(self) -> str | None:
        """The part's preferred-material attribute (`MaterialPartAttributes`), fresh from the part. None when the
        attribute is missing or blank."""
        ...

    def set_preferred_material(self, name: str) -> OperationResult[None]:
        """Writes `name` to the preferred-material attribute in its own undo mark, creating the attribute in its
        category when the part does not have it yet."""
        ...
