"""What a body has, and what an assignment did to it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from banxopen.foundation import BodyId, BodyInfo
from banxopen.materials.model.materials import DisplayMaterial, MaterialId


@dataclass(frozen=True, slots=True)
class BodyMaterialAssignment:
    """The material currently assigned to a body, as read off the part.

    `material_name` is the raw name NX stores on the body; `resolved_material_id` is set only when that name matched
    (case-insensitively) a material in a loaded library. `current_display_material` is the display/coating material
    associated with the body in NX, or None.
    """

    body_id: BodyId
    material_name: str | None
    resolved_material_id: MaterialId | None
    current_display_material: DisplayMaterial | None = None


class VerdictStatus(Enum):
    """What the rules decided about one body, flattened to the single value a tool shows."""

    OK = "Ok"
    NEEDS_CONFIRMATION = "NeedsConfirmation"
    BLOCKED = "Blocked"


@dataclass(frozen=True, slots=True)
class BodyVerdict:
    """One body of a planned assignment. `message` is the rules' own wording (each library's describer): why it is
    blocked, what needs confirming, or the warnings that ride along on an OK body. None when there is nothing to say."""

    body: BodyInfo
    status: VerdictStatus
    message: str | None


class OutcomeStatus(Enum):
    """What an apply or clear did to one body."""

    APPLIED = "Applied"
    BLOCKED = "Blocked"
    DECLINED = "Declined"
    """A rule asked for confirmation and it was not given."""
    FAILED = "Failed"
    """NX refused, or the material could not be made available in the part."""
    NOT_IN_PART = "NotInPart"
    NO_MATERIAL = "NoMaterial"
    """A clear found nothing to remove."""


@dataclass(frozen=True, slots=True)
class BodyOutcome:
    """`message` is user-facing (MaterialsText): the reason a body was not changed, or a warning on one that was."""

    body_id: BodyId
    body_name: str
    status: OutcomeStatus
    message: str | None = None


@dataclass(frozen=True, slots=True)
class AssignmentReport:
    """Every target body of one apply or clear, in target order, with what happened to it. Exact per body: no need
    to re-read the part to tell which bodies of a partial failure took."""

    outcomes: tuple[BodyOutcome, ...]

    @property
    def applied(self) -> tuple[BodyOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status is OutcomeStatus.APPLIED)

    @property
    def not_applied(self) -> tuple[BodyOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status is not OutcomeStatus.APPLIED)

    @property
    def all_applied(self) -> bool:
        return all(o.status is OutcomeStatus.APPLIED for o in self.outcomes)
