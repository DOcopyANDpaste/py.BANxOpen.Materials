"""The part attributes the material engine reads and writes. Names, not wording: other tools and downstream processes
read these attributes by exactly these names."""

from __future__ import annotations

from typing import Final


class MaterialPartAttributes:
    CATEGORY: Final = "Material"
    """The attribute category the material attributes live in."""
    PREFERRED_MATERIAL: Final = "Preferred Material"
    """String. The part's preferred physical material, by name. One per part."""
