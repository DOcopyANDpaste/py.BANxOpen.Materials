"""What a material may be used for, read off the material itself.

A material property (by default `AllowedFor`) lists the forms the material can be made into, comma-separated:
`SheetMetal`, or `Solid, SheetMetal`. Without the property a material is for solids only. This is the one place that
interprets it: the body-type rule asks it which bodies a material may go on, and the library catalog asks it which
materials make up a library's sheet metal view.

Kept separate on purpose. Today a material is either a solid material or a sheet metal material; the goal is one
material (4010) that can be made into sheet metal, block, bar and more. That needs only new values in the property and
new members here, not changes in the rule or the catalog.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import Enum
from typing import Any, ClassVar, Final

from banxopen.foundation import BodyKind
from banxopen.materials.core.rules.library_rules import MATERIAL_FORMS_KEY, LibraryRules, MaterialLibraryRulesError
from banxopen.materials.model.materials import Material, same_text
from banxopen.materials.text import MaterialsText

_log = logging.getLogger(__name__)


class MaterialForm(Enum):
    """A form a material can be made into. More forms (block, bar, ...) are added here when a body kind needs them."""

    SOLID = "Solid"
    SHEET_METAL = "SheetMetal"


def form_for_body(kind: BodyKind) -> MaterialForm:
    """The form a body needs its material to allow. Surface bodies (SHEET) and unknown bodies count as solids, as the
    body-type restriction always treated them."""
    return MaterialForm.SHEET_METAL if kind is BodyKind.SHEET_METAL else MaterialForm.SOLID


def _normalized(value: str) -> str:
    """`Sheet Metal`, `sheetmetal` and `SHEETMETAL` are the same value."""
    return "".join(value.split()).upper()


class MaterialFormClassifier:
    """Reads the forms a material allows from its "allowed for" property.

    Configured in `material-library-rules.json` under `materialForms`:
    `{ "materialForms": { "property": "AllowedFor", "solid": "Solid", "sheetMetal": "SheetMetal" } }`. Every key is
    optional and defaults to the value shown; property and value names match case-insensitively, and values also
    ignore spaces. Values this version does not know are ignored, so a library written for a later version still
    loads.
    """

    DEFAULT_PROPERTY: Final = "AllowedFor"
    DEFAULT_VALUES: Final[Mapping[MaterialForm, str]] = {f: f.value for f in MaterialForm}
    DEFAULT_FORMS: Final = frozenset({MaterialForm.SOLID})
    """What a material without the property allows."""

    DEFAULT: ClassVar[MaterialFormClassifier]

    def __init__(self, property_name: str = DEFAULT_PROPERTY, values: Mapping[MaterialForm, str] | None = None) -> None:
        names = {**self.DEFAULT_VALUES, **(values or {})}
        self._property_name = property_name.strip()
        self._values = dict(names)
        self._forms_by_value = {_normalized(v): f for f, v in names.items()}
        self._reported_unknown: set[str] = set()

    @property
    def property_name(self) -> str:
        return self._property_name

    def value_for(self, form: MaterialForm) -> str:
        """How `form` is written in the property."""
        return self._values[form]

    def allowed_forms(self, material: Material) -> frozenset[MaterialForm]:
        """The forms the property lists, or `DEFAULT_FORMS` when the material has no such property or it is blank.
        A property listing only values this version does not know allows nothing it knows: the result is empty."""
        prop = next(
            (
                p
                for p in material.properties
                if same_text(p.name, self._property_name) or same_text(p.property_id, self._property_name)
            ),
            None,
        )
        values = prop.as_array() if prop is not None else ()
        if not values:
            return self.DEFAULT_FORMS
        forms: set[MaterialForm] = set()
        for value in values:
            form = self._forms_by_value.get(_normalized(value))
            if form is not None:
                forms.add(form)
            elif value.upper() not in self._reported_unknown:
                self._reported_unknown.add(value.upper())
                _log.info("Ignoring unknown %s value '%s' (on '%s').", self._property_name, value, material.name)
        return frozenset(forms)

    def allows(self, material: Material, form: MaterialForm) -> bool:
        return form in self.allowed_forms(material)

    def may_mention(self, library_xml: str) -> bool:
        """False when the raw library XML cannot contain the property, so it need not be parsed to find out. A cheap
        check only: True does not mean any material has it."""
        return self._property_name.upper() in library_xml.upper()

    @staticmethod
    def from_rules(
        rules: LibraryRules | None, path: str = "", text: MaterialsText | None = None
    ) -> MaterialFormClassifier:
        """The classifier the rules file's `materialForms` setting describes, or `DEFAULT` without one. An unusable
        setting raises `MaterialLibraryRulesError`, worded by `text`."""
        text = text or MaterialsText.DEFAULT
        setting: Any = (rules or {}).get(MATERIAL_FORMS_KEY)
        if setting is None:
            return MaterialFormClassifier.DEFAULT
        if not isinstance(setting, dict):
            raise MaterialLibraryRulesError(text.library_rules_invalid(path, text.material_forms_not_an_object))
        entries: dict[str, Any] = {str(k).upper(): v for k, v in setting.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]

        def read(key: str, default: str) -> str:
            value: Any = entries.get(key.upper())
            if value is None:
                return default
            if not isinstance(value, str) or not value.strip():
                raise MaterialLibraryRulesError(text.library_rules_invalid(path, text.material_forms_value_blank(key)))
            return value.strip()

        values = {
            MaterialForm.SOLID: read("solid", MaterialForm.SOLID.value),
            MaterialForm.SHEET_METAL: read("sheetMetal", MaterialForm.SHEET_METAL.value),
        }
        if len({_normalized(v) for v in values.values()}) != len(values):
            raise MaterialLibraryRulesError(text.library_rules_invalid(path, text.material_forms_values_not_distinct))
        return MaterialFormClassifier(read("property", MaterialFormClassifier.DEFAULT_PROPERTY), values)


MaterialFormClassifier.DEFAULT = MaterialFormClassifier()
