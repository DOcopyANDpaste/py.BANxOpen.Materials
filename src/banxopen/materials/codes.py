"""Stable codes the material engine puts on rule outcomes (`RuleOutcome.reason_code`) and failed operations
(`OperationResult.error_code`). Codes, not wording, are the contract: tools branch on these and show the message as-is.
The wording is `MaterialsText`'s."""

from __future__ import annotations

from typing import Final


class MaterialsCodes:
    # ---- Rule outcomes ----
    REASSIGN: Final = "REASSIGN"
    """Args: current, requested."""
    COATING_NAME_MISSING: Final = "COATING_NAME_MISSING"
    """Args: material, property."""
    COATING_COLOR_INVALID: Final = "COATING_COLOR_INVALID"
    """Args: material, property."""
    COATING_NOT_APPLIED: Final = "COATING_NOT_APPLIED"
    """Args: current."""
    COATING_DISPLAY_MISMATCH: Final = "COATING_DISPLAY_MISMATCH"
    """Args: libraryName, libraryRgb, currentName, currentRgb."""
    BODY_TYPE_RESTRICTED: Final = "BODY_TYPE_RESTRICTED"
    """Args: material."""

    # ---- Failures ----
    MATERIAL_RULES_UNAVAILABLE: Final = "MATERIAL_RULES_UNAVAILABLE"
    APPLY_ABORTED: Final = "APPLY_ABORTED"
    CLEAR_ABORTED: Final = "CLEAR_ABORTED"
    PARTIAL_FAILURE: Final = "PARTIAL_FAILURE"
    """Some bodies changed and some did not; the ones that did are kept. The report says which."""
    UNSUPPORTED_INSTRUCTION: Final = "UNSUPPORTED_INSTRUCTION"
    """A side-effect executor was handed an instruction type it does not carry out. Shared by every executor."""
    MALFORMED_INSTRUCTION: Final = "MALFORMED_INSTRUCTION"
    """A side-effect instruction is missing a value its executor needs."""
