"""Material library data: plain values read from MatML, crossing every layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

Rgb = tuple[int, int, int]
"""An RGB colour as 0-255 components."""

SORT_LAST = 2_147_483_647
"""Sort order of a category with none of its own (C#'s int.MaxValue), so ordered categories come first."""


def parse_invariant_float(raw: str | None) -> float | None:
    """A number written in the invariant culture (`7.872`, `1e-3`, `NaN`), or None. Matches C#'s
    `double.TryParse(..., NumberStyles.Float, InvariantCulture)`: surrounding whitespace is allowed, Python-only forms
    such as `1_000` are not."""
    if raw is None or "_" in raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def same_text(a: str | None, b: str | None) -> bool:
    """Ordinal, case-insensitive equality, as the libraries compare material, library and property names."""
    if a is None or b is None:
        return a is b
    return a.upper() == b.upper()


@dataclass(frozen=True, slots=True)
class MaterialId:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MaterialLibraryId:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MaterialCategory:
    """Normalised grouping used to render one dialog tab. `key` identifies the category (equality/grouping key);
    `path_segments` preserves the source class hierarchy for display and debugging."""

    UNCATEGORIZED: ClassVar[MaterialCategory]

    key: str
    display_name: str
    path_segments: tuple[str, ...]
    sort_order: int | None = None


MaterialCategory.UNCATEGORIZED = MaterialCategory("uncategorized", "Uncategorized", (), sort_order=SORT_LAST)


@dataclass(frozen=True, slots=True)
class MaterialPropertyValue:
    """A single property read off a material entry (MatML PropertyData/PropertyDetails).

    MatML properties come in different practical shapes (plain text like a grade name, a single number like density,
    or a comma-separated list), and nothing in the XML reliably declares which. So this holds only the raw text plus
    metadata, and interpretation happens on demand via `as_string` / `as_array` / `as_number`.
    """

    property_id: str
    name: str
    symbol: str | None
    raw_value: str
    unit: str | None

    def as_string(self) -> str:
        return self.raw_value or ""

    def as_array(self) -> tuple[str, ...]:
        """Splits a comma-separated raw value into trimmed, non-empty entries."""
        return tuple(v.strip() for v in self.as_string().split(",") if v.strip())

    def as_number(self) -> float | None:
        """The raw value as a single number; None if it isn't one (text, or a comma-separated list)."""
        return parse_invariant_float(self.raw_value)


@dataclass(frozen=True, slots=True, kw_only=True)
class Material:
    id: MaterialId
    library_id: MaterialLibraryId
    name: str
    category: MaterialCategory
    properties: tuple[MaterialPropertyValue, ...]
    description: str | None = None
    appearance_color: Rgb | None = None
    image_path: str | None = None


@dataclass(frozen=True, slots=True)
class MaterialLibrary:
    id: MaterialLibraryId
    display_name: str
    materials: tuple[Material, ...]
    file_path: str = ""


@dataclass(frozen=True, slots=True)
class MaterialLibraryReference:
    """A library the user can pick, before its XML has been read and parsed."""

    id: MaterialLibraryId
    display_name: str
    file_path: str


@dataclass(frozen=True, slots=True)
class DisplayMaterial:
    """The display/coating material associated with a body in NX, as read off the part. Distinct from a library
    `Material`: just an identity and a colour."""

    id: MaterialId
    name: str
    rgb: Rgb
