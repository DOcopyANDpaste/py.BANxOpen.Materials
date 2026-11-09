"""Parses NX material library XML (MatML) into domain objects. Pure text in, data out."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from banxopen.materials.model.materials import (
    Material,
    MaterialCategory,
    MaterialId,
    MaterialLibrary,
    MaterialLibraryId,
    MaterialPropertyValue,
)


class MaterialLibraryParser(Protocol):
    def parse(self, library_id: MaterialLibraryId, display_name: str, xml_content: str) -> MaterialLibrary: ...


class MatmlParser:
    """Generic MatML shape: Metadata/PropertyDetails + Metadata/ClassDetails + repeated Material/BulkDetails.

    NOTE (carried from C#): built against the generic MatML schema, not a confirmed NX sample file; expect to adjust
    element names once real library XML is available. Raises ValueError for XML it cannot read.
    """

    def parse(self, library_id: MaterialLibraryId, display_name: str, xml_content: str) -> MaterialLibrary:
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as ex:
            raise ValueError(f"Material library XML is not well formed: {ex}") from ex

        metadata = root.find("Metadata")
        property_details = _build_property_details(metadata)
        categories = _build_categories(metadata)
        materials = tuple(
            _parse_material(element, library_id, property_details, categories, index)
            for index, element in enumerate(root.findall("Material"))
        )
        return MaterialLibrary(library_id, display_name, materials)


@dataclass(frozen=True, slots=True)
class _PropertyDetail:
    name: str
    symbol: str | None
    unit: str | None


def _key(value: str) -> str:
    """Dictionary key for ids looked up case-insensitively, as C#'s OrdinalIgnoreCase dictionaries."""
    return value.upper()


def _text(element: ET.Element | None) -> str | None:
    """XLinq `Element.Value`: all descendant text, or None when there is no element."""
    return None if element is None else "".join(element.itertext())


def _parse_material(
    element: ET.Element,
    library_id: MaterialLibraryId,
    property_details: Mapping[str, _PropertyDetail],
    categories: Mapping[str, MaterialCategory],
    index: int,
) -> Material:
    bulk = element.find("BulkDetails")
    if bulk is None:
        raise ValueError(f"Material at index {index} is missing BulkDetails.")

    raw_name = (_text(bulk.find("Name")) or "").strip()
    name = raw_name or f"Material {index + 1}"
    raw_id = element.get("id")
    material_id = MaterialId(raw_id if raw_id is not None else f"{library_id.value}:{index}")

    class_element = bulk.find("Class")
    class_id = None if class_element is None else class_element.get("ID", class_element.get("idref"))
    matched = categories.get(_key(class_id)) if class_id is not None else None
    category = matched or _inline_category(class_element) or MaterialCategory.UNCATEGORIZED

    properties = tuple(
        value
        for value in (_parse_property_value(p, property_details) for p in bulk.findall("PropertyData"))
        if value is not None
    )
    description = next(
        (
            (_text(a) or "").strip()
            for a in bulk.findall("Annotation")
            if (a.get("name") or "").upper() == "DESCRIPTION"
        ),
        None,
    )
    return Material(
        id=material_id,
        library_id=library_id,
        name=name,
        category=category,
        properties=properties,
        description=description or None,
    )


def _inline_category(class_element: ET.Element | None) -> MaterialCategory | None:
    """Some NX exports give a class inline (`<Class><Name>...</Name></Class>`) rather than as an ID/idref into
    Metadata/ClassDetails. Without a registry match, a category is built from that name so the material isn't dumped
    into Uncategorized."""
    if class_element is None:
        return None
    raw_name = (_text(class_element.find("Name")) or "").strip()
    if not raw_name:
        return None
    return MaterialCategory(raw_name.lower(), raw_name, (raw_name,))


def _parse_property_value(
    property_data: ET.Element, property_details: Mapping[str, _PropertyDetail]
) -> MaterialPropertyValue | None:
    property_id = property_data.get("property")
    if property_id is None:
        return None
    raw_value = (_text(property_data.find("Data")) or "").strip()
    detail = property_details.get(_key(property_id)) or _PropertyDetail(property_id, None, None)
    return MaterialPropertyValue(property_id, detail.name, detail.symbol, raw_value, detail.unit)


def _build_property_details(metadata: ET.Element | None) -> dict[str, _PropertyDetail]:
    result: dict[str, _PropertyDetail] = {}
    if metadata is None:
        return result
    for details in metadata.findall("PropertyDetails"):
        detail_id = details.get("id")
        if detail_id is None:
            continue
        name_element = details.find("Name")
        raw_name = (_text(name_element) or "").strip()
        units = details.find("Units")
        result[_key(detail_id)] = _PropertyDetail(
            raw_name or detail_id,
            None if name_element is None else name_element.get("symbol"),
            None if units is None else units.get("name"),
        )
    return result


def _build_categories(metadata: ET.Element | None) -> dict[str, MaterialCategory]:
    """Flattens the nested Metadata/ClassDetails hierarchy into a lookup from class id to a category carrying the full
    path from root to that class."""
    result: dict[str, MaterialCategory] = {}
    if metadata is None:
        return result

    def walk(class_details: ET.Element, parent_path: tuple[str, ...]) -> None:
        class_id = class_details.get("id")
        raw_name = (_text(class_details.find("Name")) or "").strip()
        name = raw_name or (class_id if class_id is not None else "Unknown")
        path = (*parent_path, name)
        category = MaterialCategory("/".join(path).lower(), name, path)
        if class_id is not None:
            result[_key(class_id)] = category
        for child in class_details.findall("ClassDetails"):
            walk(child, path)

    for root in metadata.findall("ClassDetails"):
        walk(root, ())
    return result
