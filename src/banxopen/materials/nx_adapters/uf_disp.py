"""Every NX Open UF call Materials makes, in one place.

NX 2412 ships no Python stubs for `NXOpen.UF`, so neither pyright nor the tests can check these. Each function states
the C# call it ports and the Python return shape it assumes ([verify] until scripts/smoke_materials.py confirms it in
NX). If NX disagrees, only this file changes.
"""

# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportArgumentType=false, reportMissingImports=false

from __future__ import annotations

from typing import Any

import NXOpen
import NXOpen.UF

UfSession = Any  # NXOpen.UF.UFSession: unstubbed


def remove_material_assignment(uf: UfSession, body_tag: int) -> None:
    """UF_DISP_remove_material_assignment: applies "None"; the material stays in the part for other bodies."""
    uf.Disp.RemoveMaterialAssignment(body_tag)


def find_material_in_part(uf: UfSession, part_tag: int, name: str) -> int | None:
    """There is no find-by-name: the part's display materials are listed and matched by name (case-insensitive).

    C#: AskMaterialsInPart(part, MaterialFormatType.ShIrayplus, out count, out tags, out names).
    [verify] Python returns (count, tags, names), and the enum's Python name. If lookups never find anything, the
    format type is the first thing to try changing (the C# note: ShAuthor / ShMax)."""
    try:
        _count, tags, names = uf.Disp.AskMaterialsInPart(part_tag, NXOpen.UF.Disp.MaterialFormatType.SH_IRAYPLUS)
    except NXOpen.NXException:
        return None  # a part with no display materials is a normal state
    for tag, material_name in zip(tags or [], names or [], strict=False):  # NX returns equal-length lists
        if str(material_name).upper() == name.upper():
            return int(tag)
    return None


def create_material(uf: UfSession, name: str) -> int:
    """C#: CreateMaterial(name, out tag, out _). [verify] Python returns (tag, assigned_name). The name NX assigns
    can differ from the one requested, so callers use the returned tag, never a second lookup."""
    tag, _assigned = uf.Disp.CreateMaterial(name)
    return int(tag)


def assign_material(uf: UfSession, material_tag: int, body_tag: int) -> None:
    """Argument order is material first, object second: the reverse of most UF object calls."""
    uf.Disp.AssignMaterial(material_tag, body_tag)


def closest_color(uf: UfSession, unit_rgb: list[float]) -> int:
    """C#: AskClosestColor(UF_DISP_rgb_model, rgb, UF_DISP_CCM_EUCLIDEAN_DISTANCE, out color). [verify] returns the
    colour number."""
    constants = NXOpen.UF.UFConstants
    return int(uf.Disp.AskClosestColor(constants.UF_DISP_rgb_model, unit_rgb, constants.UF_DISP_CCM_EUCLIDEAN_DISTANCE))


def refresh_material_display(uf: UfSession, material_tag: int) -> None:
    """Pushes a new material through to the screen. C#: AskGeometryOfMaterial(tag, out count, out tags), then
    UpdateMaterialDisplayOfGeometry(count, tags). [verify] Python returns (count, tags)."""
    count, tags = uf.Disp.AskGeometryOfMaterial(material_tag)
    if count and tags:
        uf.Disp.UpdateMaterialDisplayOfGeometry(count, tags)


def body_display_material(uf: UfSession, body_tag: int) -> tuple[int, str] | None:
    """C#: AskMaterial(body, out tag, out name). [verify] Python returns (tag, name). None when the body has none."""
    tag, name = uf.Disp.AskMaterial(body_tag)
    return (int(tag), str(name)) if tag and name else None


def color_rgb(uf: UfSession, color_number: int) -> tuple[float, float, float]:
    """C#: AskColor(color, UF_DISP_rgb_model, out name, double[3] values) with values filled in place, 0-1.
    [verify] Python returns (name, values)."""
    _name, values = uf.Disp.AskColor(color_number, NXOpen.UF.UFConstants.UF_DISP_rgb_model)
    return float(values[0]), float(values[1]), float(values[2])


def solid_volume_m3(uf: UfSession, body_tag: int) -> float:
    """C#: AskMassProps3d([body], 1, type 1 = solids, units 4 = kg/m (there is no "part units" option, so volume is in
    m^3), density 0 (the body carries its own), accuracy 1 = use acc_value, acc_value[0] = 0.999, mass_props[47],
    statistics[13]); mass_props[1] is the volume. [verify] Python takes the inputs and returns (mass_props, stats)."""
    accuracy = [0.0] * 11
    accuracy[0] = 0.999
    mass_props, _statistics = uf.Modl.AskMassProps3d([body_tag], 1, 1, 4, 0.0, 1, accuracy)
    return float(mass_props[1])
