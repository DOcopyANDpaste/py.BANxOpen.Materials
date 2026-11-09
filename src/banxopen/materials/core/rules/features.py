"""Restrictions that features already on a body place on its material."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum

from banxopen.materials.model.materials import Material


class ConstraintSeverity(Enum):
    BLOCK = "Block"
    """The assignment is refused."""
    WARN = "Warn"
    """The assignment goes ahead and the message is shown as an advisory: for cases a domain wants surfaced but has
    decided not to enforce, such as a feature that matches no known specification."""


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class MaterialConstraint:
    """One restriction that features already on a body place on what material may be assigned to it. Enforced by
    the feature constraint gate.

    Fields:
        domain_id: which feature domain imposed this, e.g. "SHEETMETAL.BEAD". For grouping and diagnostics only.
        source_label: the specific thing on the body responsible, e.g. "Bead SPEC BA-1234". Shown to the user, so it
            must name something they can go and look at.
        reason_code: stable machine-readable code.
        is_satisfied_by: true when the material is acceptable. Pure and cheap. A pure advisory returns False with
            severity WARN.
        describe_violation: the user-facing message for a material that fails.
        severity: whether an unsatisfied constraint refuses or only warns.
        violation_args: the values `describe_violation` puts in its message, formatted for display and keyed by name,
            for a front end that words the violation itself. They reach it as `RuleOutcome.args`, with `source` and
            `material` added. None when there is nothing beyond those two.
    """

    domain_id: str
    source_label: str
    reason_code: str
    is_satisfied_by: Callable[[Material], bool]
    describe_violation: Callable[[Material], str]
    severity: ConstraintSeverity = ConstraintSeverity.BLOCK
    violation_args: Callable[[Material], Mapping[str, str]] | None = None
