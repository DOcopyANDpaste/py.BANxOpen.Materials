"""The wording of every message the material engine can put in front of a user."""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar


class MaterialsText:
    """Rule outcomes, the failures of the part material service, configuration errors shown at start-up, and the
    per-body reasons of an apply or clear, as default text a tool may override (the describer pattern): one overridable
    member per message, and a `DEFAULT` instance. Rules and services take a `MaterialsText | None` and fall back to
    `DEFAULT`; the codes that go with these messages are `MaterialsCodes`. Log lines are not user text and are not here.

    Parameters that carry an NX error are already formatted (`NxDialogText.nx_error`): Core has no NXOpen.
    """

    DEFAULT: ClassVar[MaterialsText]

    # ---- Rule outcomes ----

    def reassign(self, current: str, requested: str) -> str:
        return f"Body already has '{current}'. Replace with '{requested}'?"

    def coating_name_missing(self, material: str, prop: str) -> str:
        return f"Material '{material}' has no {prop} defined — a default display material will be applied instead."

    def coating_color_invalid(self, material: str, prop: str) -> str:
        return f"Material '{material}' has an invalid or missing {prop}. Contact your material library administrator."

    def coating_not_applied(self, current: str | None) -> str:
        return (
            f"Body already has material '{current if current is not None else ''}' assigned but no display material "
            "is currently associated with it — it will be assigned automatically."
        )

    def coating_display_mismatch(self, library_name: str, library_rgb: str, current_name: str, current_rgb: str) -> str:
        return (
            f"Library: '{library_name}' ({library_rgb}) vs current: '{current_name}' ({current_rgb}).\n"
            "Confirm to update to the library value, or leave unconfirmed to keep the current one."
        )

    def body_type_restricted(self, material: str) -> str:
        return f"'{material}' is not available for this body."

    def required_by(self, violation: str, source: str) -> str:
        """A feature constraint's violation, naming what on the body or part imposed it."""
        return f"{violation} (required by {source})"

    def combine_warnings(self, warnings: Iterable[str]) -> str:
        """Several advisory warnings on one body, shown together."""
        return " ".join(warnings)

    def combine_outcome_messages(self, messages: Iterable[str]) -> str:
        """The messages of one body's outcomes of one kind (all blocks, all confirmations, all warnings)."""
        return "; ".join(messages)

    # ---- Material library rules file (shown at start-up) ----

    @property
    def library_rules_list_empty(self) -> str:
        return (
            "sheetMetalLibraries must list at least one library; delete the file to use the name-based default instead."
        )

    def library_rules_invalid_json(self, path: str, detail: str) -> str:
        return f"Material library rules at '{path}' are not valid JSON: {detail}"

    def library_rules_missing_list(self, path: str) -> str:
        return (
            f'Material library rules at \'{path}\' have no "sheetMetalLibraries" list and no "materialForms" '
            "setting. Add one, or delete the file to use the defaults."
        )

    def library_rules_invalid(self, path: str, detail: str) -> str:
        return f"Material library rules at '{path}': {detail}"

    @property
    def material_forms_not_an_object(self) -> str:
        return '"materialForms" must be an object, e.g. { "property": "AllowedFor" }.'

    def material_forms_value_blank(self, key: str) -> str:
        return f'"materialForms.{key}" must be a non-blank text.'

    @property
    def material_forms_values_not_distinct(self) -> str:
        return '"materialForms" names the same value for more than one form.'

    # ---- Library names ----

    def sheet_metal_library_name(self, library: str) -> str:
        """The name a library's sheet metal materials are offered under, as a library of their own."""
        return f"{library}_SheetMetal"

    def material_rules_unavailable(self, detail: str | None) -> str:
        return self._with_details("Material rules could not be loaded.", detail)

    # ---- Part material service ----

    def confirm_load_physical_material(self, material: str, library: str) -> str:
        return (
            f"'{material}' is not in this part yet.\n"
            f"Load it from the NX material library '{library}'?\n\n"
            "This can take a while for a large library."
        )

    def apply_aborted(self, detail: str | None) -> str:
        return self._with_details("The material could not be applied; nothing was changed.", detail)

    def clear_aborted(self, detail: str | None) -> str:
        return self._with_details("The material could not be removed; nothing was changed.", detail)

    @property
    def no_target_bodies_resolved(self) -> str:
        """The detail of an abort when none of the target bodies could be found in the part."""
        return "No target bodies could be resolved."

    @property
    def partial_failure(self) -> str:
        return "Some bodies failed. The ones that succeeded were kept; see the Listing Window for details."

    # ---- Per-gesture service: confirmations and per-body reasons ----

    def confirm_bodies(self, count: int, material: str, body_lines: Iterable[str]) -> str:
        """The one question asked for every body of an apply whose rules want confirmation."""
        lines = "\n".join(body_lines)
        return f"{count} body(ies) need confirmation for {material}:\n{lines}\n\nApply to all of them?"

    def body_line(self, body: str, text: str) -> str:
        return f"  [{body}] {text}"

    def blocked(self, rule_message: str | None) -> str:
        return f"blocked: {rule_message if rule_message is not None else ''}"

    @property
    def not_confirmed(self) -> str:
        return "not confirmed"

    @property
    def no_longer_in_part(self) -> str:
        return "no longer in the work part"

    @property
    def has_no_material(self) -> str:
        return "has no material"

    def warning(self, message: str | None) -> str:
        return f"warning: {message if message is not None else ''}"

    @property
    def body_not_resolved(self) -> str:
        return "the body could not be found in the part"

    def material_not_resolved(self, material: str) -> str:
        return f"'{material}' is not in the loaded material libraries"

    def physical_material_load_declined(self, material: str) -> str:
        return f"Loading '{material}' from the NX library was declined."

    def physical_material_not_found(self, material: str, library: str, nx_detail: str) -> str:
        return f"'{material}' was not found in the NX material library '{library}' ({nx_detail})."

    def nx_failed_on_body(self, nx_detail: str) -> str:
        return f"NX failed on this body: {nx_detail}"

    def side_effect_failed(self, detail: str) -> str:
        return f"the material was assigned, but a follow-up step failed: {detail}"

    # ---- Shared ----

    def _with_details(self, text: str, detail: str | None) -> str:
        """A worded sentence with the technical detail that caused it below, or the sentence alone."""
        return text if detail is None or not detail.strip() else f"{text}\n\nDetails: {detail}"


MaterialsText.DEFAULT = MaterialsText()
