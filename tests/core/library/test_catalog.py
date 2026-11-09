"""The libraries a user picks from: each file, plus the `_SheetMetal` view of every file holding sheet metal
materials."""

import pytest

from banxopen.materials import (
    MaterialFormClassifier,
    MaterialLibraryCatalog,
    MaterialLibraryId,
    MaterialLibraryReference,
    SheetMetalLibraries,
)
from banxopen.materials.core.rules.sheet_metal import is_sheet_metal_view


def material(name: str, allowed_for: str | None = None) -> str:
    data = f'<PropertyData property="pr1"><Data>{allowed_for}</Data></PropertyData>' if allowed_for else ""
    return f'<Material id="{name}"><BulkDetails><Name>{name}</Name>{data}</BulkDetails></Material>'


def library_xml(*materials: str) -> str:
    metadata = '<Metadata><PropertyDetails id="pr1"><Name>AllowedFor</Name></PropertyDetails></Metadata>'
    return f"<MatML_Doc>{''.join(materials)}{metadata}</MatML_Doc>"


MIXED = library_xml(
    material("Steel"),  # no property: solid only
    material("4010", "SheetMetal"),
    material("5052", "Solid, SheetMetal"),
)
PLAIN = "<MatML_Doc>" + material("Copper") + "</MatML_Doc>"


class FakeRepository:
    def __init__(self, xml_by_name: dict[str, str]) -> None:
        self._xml = {MaterialLibraryId(n): x for n, x in xml_by_name.items()}
        self.reads: list[str] = []

    def list_available_libraries(self):
        return [MaterialLibraryReference(i, i.value, f"C:/MATERIALS/{i.value}.xml") for i in self._xml]

    def read_library_xml(self, library_id):
        self.reads.append(library_id.value)
        if library_id not in self._xml:
            raise FileNotFoundError(library_id.value)
        return self._xml[library_id]


def catalog(repository: FakeRepository, sheet_metal: SheetMetalLibraries | None = None) -> MaterialLibraryCatalog:
    return MaterialLibraryCatalog(repository, sheet_metal, MaterialFormClassifier())


def names(library) -> list[str]:
    return [m.name for m in library.materials]


def test_a_library_with_sheet_metal_materials_is_followed_by_its_sheet_metal_view():
    listed = catalog(FakeRepository({"Metals": MIXED, "Plastics": PLAIN})).list_libraries()

    assert [r.display_name for r in listed] == ["Metals", "Metals_SheetMetal", "Plastics"]
    view = listed[1]
    assert is_sheet_metal_view(view.id)
    assert view.file_path == listed[0].file_path  # NX loads the material from the same file


def test_the_view_holds_the_sheet_metal_materials_and_the_file_the_solid_ones():
    cat = catalog(FakeRepository({"Metals": MIXED}))
    file_ref, view_ref = cat.list_libraries()

    assert names(cat.load(file_ref)) == ["Steel", "5052"]  # 4010 is sheet metal only
    view = cat.load(view_ref)
    assert names(view) == ["4010", "5052"]  # 5052 is in both
    assert view.id == view_ref.id
    assert view.display_name == "Metals_SheetMetal"
    assert view.file_path == file_ref.file_path
    assert {m.library_id for m in view.materials} == {view_ref.id}


def test_views_are_sheet_metal_libraries_whatever_is_configured():
    cat = catalog(FakeRepository({"Metals": MIXED}), SheetMetalLibraries.from_names(["Aero Skins"]))
    file_ref, view_ref = cat.list_libraries()

    assert cat.is_sheet_metal_library(view_ref.id)
    assert not cat.is_sheet_metal_library(file_ref.id)


def test_a_sheet_metal_library_file_is_listed_and_loaded_as_it_is():
    # Legacy: a separate file of sheet metal materials, recognised by name, without the property.
    repository = FakeRepository(
        {"Sheet Metal Materials": library_xml(material("2024"), material("4010", "SheetMetal"))}
    )
    cat = catalog(repository)

    (only,) = cat.list_libraries()
    assert only.display_name == "Sheet Metal Materials"
    assert names(cat.load(only)) == ["2024", "4010"]
    assert cat.is_sheet_metal_library(only.id)


def test_a_file_without_the_property_name_is_not_parsed_to_list_it():
    repository = FakeRepository({"Plastics": PLAIN})
    cat = catalog(repository)

    assert [r.display_name for r in cat.list_libraries()] == ["Plastics"]
    cat.list_libraries()
    assert repository.reads == ["Plastics"]  # read once to check, never again


def test_a_file_that_cannot_be_read_gets_no_view_and_fails_when_opened(caplog):
    cat = catalog(FakeRepository({"Broken": "<MatML_Doc AllowedFor"}))

    (only,) = cat.list_libraries()

    assert "Could not check 'Broken' for sheet metal materials" in caplog.text
    with pytest.raises(ValueError, match="not well formed"):
        cat.load(only)


def test_a_view_can_be_loaded_before_the_libraries_are_listed():
    repository = FakeRepository({"Metals": MIXED})
    view_ref = catalog(repository).list_libraries()[1]

    assert names(catalog(repository).load(view_ref)) == ["4010", "5052"]


def test_loading_returns_the_same_library_each_time():
    cat = catalog(FakeRepository({"Metals": MIXED}))
    file_ref, view_ref = cat.list_libraries()

    assert cat.load(view_ref) is cat.load(view_ref)
    assert cat.load(file_ref) is cat.load(file_ref)
