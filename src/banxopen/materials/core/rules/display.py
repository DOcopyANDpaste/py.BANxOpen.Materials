"""Display (coating/studio) material: validate the library's coating data, then sync it onto the body."""

from __future__ import annotations

from collections.abc import Sequence, Set
from typing import Final

from banxopen.foundation import RuleDecision, RuleOutcome
from banxopen.materials.codes import MaterialsCodes
from banxopen.materials.core.assignment.planning import MaterialAssignmentRuleContext, SideEffectInstruction
from banxopen.materials.core.rules.order import MaterialRuleOrder
from banxopen.materials.core.rules.ports import (
    FeatureMaterialConstraintProvider,
    MaterialValidationRule,
    PostAssignmentEffectRule,
)
from banxopen.materials.model.materials import (
    Material,
    MaterialPropertyValue,
    Rgb,
    parse_invariant_float,
    same_text,
)
from banxopen.materials.text import MaterialsText

# ---- Coating property reading (shared by both rules so they cannot drift apart) ----

MATERIAL_NAME_PROPERTY: Final = "CoatingStudioMaterialName"
COLOR_PROPERTY: Final = "CoatingVisualizationColor"
DEFAULT_DISPLAY_MATERIAL_NAME: Final = "TODO_DEFAULT_DISPLAY_MATERIAL_NAME"
"""Fallback display material when a material's MatML defines no coating. Placeholder carried from C#: replace."""
DEFAULT_DISPLAY_MATERIAL_RGB: Final = (0.7, 0.7, 0.7)
"""Fallback colour (0-1) paired with the default name. Placeholder carried from C#: replace."""

_COLOR_TOLERANCE = 1.0 / 255.0

NormalizedRgb = tuple[float, float, float]


def _find_property(material: Material, name: str) -> MaterialPropertyValue | None:
    return next((p for p in material.properties if same_text(p.name, name)), None)


def coating_display_material_name(material: Material) -> str | None:
    """The coating display material name, or None if the property is missing or blank."""
    prop = _find_property(material, MATERIAL_NAME_PROPERTY)
    raw = prop.as_string() if prop is not None else None
    return raw if raw and raw.strip() else None


def coating_rgb(material: Material) -> NormalizedRgb | None:
    """The coating colour normalised to 0-1, or None unless the property parses into exactly 3 valid components.

    NOTE (carried from C#): the source scale is not confirmed, so each component is auto-detected: above 1 is taken as
    0-255 and divided by 255, within [0, 1] as already normalised. A raw value of exactly 1 therefore reads as full
    intensity.
    """
    prop = _find_property(material, COLOR_PROPERTY)
    if prop is None:
        return None
    components = prop.as_array()
    if len(components) != 3:
        return None
    parsed = [_color_component(c) for c in components]
    if any(c is None for c in parsed):
        return None
    r, g, b = (c for c in parsed if c is not None)
    return r, g, b


def _color_component(raw: str) -> float | None:
    value = parse_invariant_float(raw)
    if value is None or value < 0:
        return None
    normalized = value / 255 if value > 1 else value
    return None if normalized > 1 else normalized  # above 255 on the assumed 0-255 scale


def colors_approximately_equal(rgb: NormalizedRgb, other: Rgb) -> bool:
    """Each channel within one 0-255 step, so floating-point rounding is not a mismatch."""
    return all(abs(c - o / 255.0) <= _COLOR_TOLERANCE for c, o in zip(rgb, other, strict=True))


# ---- Rules ----


class ValidateCoatingDisplayMaterialRule:
    """Validates the requested material's coating data and, for a body that already has a material, cross-checks it
    against the body's current display material:

    - name present, colour valid, no conflict with the current display material: ALLOW;
    - name present, colour missing or malformed: BLOCK (bad library data; the message directs the user to the
      material library administrator);
    - name missing, whatever the colour: WARN (the sync falls back to the default display material);
    - body has a material but no display material: ALLOW, with a reason code for reference (first sync);
    - body's current display material differs in name or colour: REQUIRE_CONFIRMATION (keep current or update).
    """

    rule_id = "VALIDATE_COATING_DISPLAY_MATERIAL"
    order = MaterialRuleOrder.Validation.APPEARANCE

    def __init__(self, text: MaterialsText | None = None) -> None:
        self._text = text or MaterialsText.DEFAULT

    def evaluate(self, context: MaterialAssignmentRuleContext) -> RuleOutcome:
        material = context.requested_material
        name = coating_display_material_name(material)
        if name is None:
            return RuleOutcome(
                self.rule_id,
                RuleDecision.WARN,
                MaterialsCodes.COATING_NAME_MISSING,
                self._text.coating_name_missing(material.name, MATERIAL_NAME_PROPERTY),
                args={"material": material.name, "property": MATERIAL_NAME_PROPERTY},
            )

        rgb = coating_rgb(material)
        if rgb is None:
            return RuleOutcome(
                self.rule_id,
                RuleDecision.BLOCK,
                MaterialsCodes.COATING_COLOR_INVALID,
                self._text.coating_color_invalid(material.name, COLOR_PROPERTY),
                args={"material": material.name, "property": COLOR_PROPERTY},
            )

        current = context.current_assignment
        if current is not None:
            display = current.current_display_material
            if display is None:
                return RuleOutcome(
                    self.rule_id,
                    RuleDecision.ALLOW,
                    MaterialsCodes.COATING_NOT_APPLIED,
                    self._text.coating_not_applied(current.material_name),
                    args={"current": current.material_name or ""},
                )
            if not same_text(name, display.name) or not colors_approximately_equal(rgb, display.rgb):
                library_rgb = ",".join(str(round(c * 255)) for c in rgb)
                current_rgb = ",".join(str(c) for c in display.rgb)
                return RuleOutcome(
                    self.rule_id,
                    RuleDecision.REQUIRE_CONFIRMATION,
                    MaterialsCodes.COATING_DISPLAY_MISMATCH,
                    self._text.coating_display_mismatch(name, library_rgb, display.name, current_rgb),
                    args={
                        "libraryName": name,
                        "libraryRgb": library_rgb,
                        "currentName": display.name,
                        "currentRgb": current_rgb,
                    },
                )
        return RuleOutcome(self.rule_id, RuleDecision.ALLOW, None, None)


class SyncCoatingDisplayMaterialEffectRule:
    """Emits an ASSIGN_DISPLAY_MATERIAL instruction carrying the coating's display material name and RGB. It
    re-validates the data itself rather than trusting the validation rule ran: effect rules must not assume a
    particular gate rule executed. Every assignment syncs a display material; incomplete coating data falls back to the
    default."""

    INSTRUCTION_TYPE: Final = "ASSIGN_DISPLAY_MATERIAL"
    """The executor (`DisplayMaterialHelper`) registers under this, so the two cannot drift apart via a typo."""
    DISPLAY_MATERIAL_NAME_KEY: Final = "DisplayMaterialName"
    """Data key: a `str`."""
    RGB_KEY: Final = "RGB"
    """Data key: a `tuple[float, float, float]` of normalised 0-1 components, in R, G, B order."""
    USED_DEFAULT_KEY: Final = "UsedDefault"
    """Data key: a `bool`, true when the default display material was used, so the executor can warn."""

    rule_id = "SYNC_COATING_DISPLAY_MATERIAL"
    order = MaterialRuleOrder.SideEffect.APPEARANCE
    instruction_types: Set[str] = frozenset({INSTRUCTION_TYPE})

    def generate_effects(self, context: MaterialAssignmentRuleContext) -> Sequence[SideEffectInstruction]:
        material = context.requested_material
        name = coating_display_material_name(material)
        rgb = coating_rgb(material)
        used_default = name is None or rgb is None
        data: dict[str, object] = {
            self.DISPLAY_MATERIAL_NAME_KEY: DEFAULT_DISPLAY_MATERIAL_NAME if used_default else name,
            # Rounded to 6 places: far more precision than a colour channel needs, just to keep the value clean.
            self.RGB_KEY: DEFAULT_DISPLAY_MATERIAL_RGB
            if rgb is None or used_default
            else tuple(round(c, 6) for c in rgb),
            self.USED_DEFAULT_KEY: used_default,
        }
        return (SideEffectInstruction(self.INSTRUCTION_TYPE, context.target_body.id, data),)


class DisplayMaterialRuleModule:
    """The executor for the sync is `DisplayMaterialHelper` in this library's NX adapters, registered by
    `MaterialEngine`."""

    ID = "DISPLAY"

    def __init__(self, text: MaterialsText | None = None) -> None:
        self._validation: tuple[MaterialValidationRule, ...] = (ValidateCoatingDisplayMaterialRule(text),)
        self._effects: tuple[PostAssignmentEffectRule, ...] = (SyncCoatingDisplayMaterialEffectRule(),)

    @property
    def module_id(self) -> str:
        return self.ID

    @property
    def validation_rules(self) -> Sequence[MaterialValidationRule]:
        return self._validation

    @property
    def feature_constraints(self) -> Sequence[FeatureMaterialConstraintProvider]:
        return ()

    @property
    def side_effect_rules(self) -> Sequence[PostAssignmentEffectRule]:
        return self._effects
