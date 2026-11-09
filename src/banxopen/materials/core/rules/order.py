"""Named stages for rule `order` values."""

from __future__ import annotations

from typing import Final


class MaterialRuleOrder:
    """So a rule in one module can be placed relative to rules in another without knowing their numbers. A rule that
    must sit between two stages uses an offset (e.g. `Validation.CONFIRMATION + 50`); rules sharing a value run in
    module registration order."""

    class Validation:
        ELIGIBILITY: Final = 100
        """Whether the material may go on this kind of body at all."""
        FEATURE_CONSTRAINTS: Final = 150
        """What features already on the body allow. Runs before anything that asks the user a question, so a forbidden
        material is refused rather than confirmed."""
        CONFIRMATION: Final = 200
        """Questions for the user, such as replacing an existing material."""
        APPEARANCE: Final = 300
        """Display material and coating data."""

    class SideEffect:
        MATERIAL_PROPERTIES: Final = 100
        """Properties carried over from the material itself."""
        APPEARANCE: Final = 200
        """Display material and body colour."""
        DOMAIN_STATE: Final = 300
        """State a feature domain keeps in step with the material, such as Sheet Metal Preferences."""
