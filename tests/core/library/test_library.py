import logging
from dataclasses import replace
from pathlib import Path

import pytest

from banxopen.materials import (
    CachingMaterialLibraryLoader,
    FileSystemMaterialLibraryRepository,
    MaterialCategory,
    MaterialLibrary,
    MaterialLibraryId,
    MaterialLibraryReference,
    MatmlParser,
)

DATA = Path(__file__).parents[2] / "data"
EMPTY_LIBRARY_XML = "<MatML_Doc></MatML_Doc>"


# ---- CachingMaterialLibraryLoaderTests ----


class FakeRepository:
    def __init__(self, xml_by_id: dict[MaterialLibraryId, str]) -> None:
        self._xml_by_id = xml_by_id
        self.read_call_count = 0

    def list_available_libraries(self) -> list[MaterialLibraryReference]:
        return []

    def read_library_xml(self, library_id: MaterialLibraryId) -> str:
        self.read_call_count += 1
        return self._xml_by_id[library_id]


class CountingParser:
    def __init__(self) -> None:
        self._inner = MatmlParser()
        self.parse_call_count = 0

    def parse(self, library_id: MaterialLibraryId, display_name: str, xml_content: str) -> MaterialLibrary:
        self.parse_call_count += 1
        return self._inner.parse(library_id, display_name, xml_content)


def test_get_or_load_parses_on_first_request():
    lib = MaterialLibraryId("lib1")
    repository, parser = FakeRepository({lib: EMPTY_LIBRARY_XML}), CountingParser()

    library = CachingMaterialLibraryLoader(repository, parser).get_or_load(
        MaterialLibraryReference(lib, "Lib 1", "lib1.xml")
    )

    assert library.id == lib
    assert (repository.read_call_count, parser.parse_call_count) == (1, 1)


def test_get_or_load_second_request_for_same_library_returns_cached_instance_without_reparsing():
    lib = MaterialLibraryId("lib1")
    repository, parser = FakeRepository({lib: EMPTY_LIBRARY_XML}), CountingParser()
    loader = CachingMaterialLibraryLoader(repository, parser)
    reference = MaterialLibraryReference(lib, "Lib 1", "lib1.xml")

    assert loader.get_or_load(reference) is loader.get_or_load(reference)
    assert (repository.read_call_count, parser.parse_call_count) == (1, 1)


def test_get_or_load_different_libraries_are_cached_independently():
    a, b = MaterialLibraryId("libA"), MaterialLibraryId("libB")
    repository, parser = FakeRepository({a: EMPTY_LIBRARY_XML, b: EMPTY_LIBRARY_XML}), CountingParser()
    loader = CachingMaterialLibraryLoader(repository, parser)

    loader.get_or_load(MaterialLibraryReference(a, "Lib A", "a.xml"))
    loader.get_or_load(MaterialLibraryReference(b, "Lib B", "b.xml"))
    loader.get_or_load(MaterialLibraryReference(a, "Lib A", "a.xml"))

    assert (repository.read_call_count, parser.parse_call_count) == (2, 2)


def test_get_or_load_points_each_material_at_its_bitmap_or_the_default(tmp_path: Path):
    (tmp_path / "BMPs").mkdir()
    (tmp_path / "BMPs" / "Steel, Mild.bmp").write_bytes(b"")
    lib = MaterialLibraryId("metric")
    repository = FakeRepository({lib: (DATA / "sample-metric-library.xml").read_text(encoding="utf-8")})

    library = CachingMaterialLibraryLoader(repository).get_or_load(
        MaterialLibraryReference(lib, "Metric", str(tmp_path / "metric.xml"))
    )

    images = {m.name: Path(m.image_path or "").name for m in library.materials}
    assert images["Steel, Mild"] == "Steel, Mild.bmp"
    assert images["ABS Plastic"] == "default.bmp"
    assert library.file_path == str(tmp_path / "metric.xml")


# ---- FileSystemMaterialLibraryRepositoryTests ----


def test_list_available_libraries_returns_one_reference_per_xml_file_keyed_by_file_name(tmp_path: Path):
    (tmp_path / "metric.xml").write_text(EMPTY_LIBRARY_XML)
    (tmp_path / "english.xml").write_text(EMPTY_LIBRARY_XML)
    (tmp_path / "notes.txt").write_text("ignored")

    libraries = FileSystemMaterialLibraryRepository(tmp_path).list_available_libraries()

    assert {r.id for r in libraries} == {MaterialLibraryId("metric"), MaterialLibraryId("english")}


def test_read_library_xml_returns_file_content(tmp_path: Path):
    (tmp_path / "metric.xml").write_text("<MatML_Doc><Material/></MatML_Doc>")

    xml = FileSystemMaterialLibraryRepository(tmp_path).read_library_xml(MaterialLibraryId("metric"))

    assert xml == "<MatML_Doc><Material/></MatML_Doc>"


def test_read_library_xml_for_an_unknown_id_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="nope"):
        FileSystemMaterialLibraryRepository(tmp_path).read_library_xml(MaterialLibraryId("nope"))


def test_list_available_libraries_missing_directory_warns_and_returns_empty(tmp_path: Path, caplog):
    with caplog.at_level(logging.WARNING, logger="banxopen.materials"):
        libraries = FileSystemMaterialLibraryRepository(tmp_path / "does-not-exist").list_available_libraries()

    assert libraries == []
    assert "not found" in caplog.text


def test_default_root_prefers_the_customer_materials_folder(tmp_path: Path, monkeypatch):
    (tmp_path / "customer" / "MATERIALS").mkdir(parents=True)
    monkeypatch.setenv("UGII_CUSTOMER_DIR", str(tmp_path / "customer"))
    monkeypatch.setenv("UGII_BASE_DIR", str(tmp_path / "base"))

    assert FileSystemMaterialLibraryRepository().root_directory == tmp_path / "customer" / "MATERIALS"


def test_default_root_falls_back_to_the_base_materials_folder(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UGII_CUSTOMER_DIR", str(tmp_path / "no-materials-here"))
    monkeypatch.setenv("UGII_BASE_DIR", str(tmp_path / "base"))

    assert FileSystemMaterialLibraryRepository().root_directory == tmp_path / "base" / "MATERIALS"


# ---- MaterialLibraryParserTests ----


def parse_fixture(name: str = "sample-metric-library.xml", library: str = "metric") -> MaterialLibrary:
    return MatmlParser().parse(MaterialLibraryId(library), library, (DATA / name).read_text(encoding="utf-8"))


def material(library: MaterialLibrary, name: str):
    (found,) = [m for m in library.materials if m.name == name]
    return found


def test_parse_reads_all_materials_in_document_order():
    assert [m.name for m in parse_fixture().materials] == ["Steel, Mild", "ABS Plastic", "Unclassified Sample"]


def test_parse_uses_explicit_material_id_when_present():
    assert material(parse_fixture(), "Steel, Mild").id.value == "mat_steel_mild"


def test_parse_generates_fallback_id_when_material_has_no_id_attribute():
    assert material(parse_fixture(), "Unclassified Sample").id.value == "metric:2"


def test_parse_resolves_nested_class_hierarchy_into_category_path():
    category = material(parse_fixture(), "Steel, Mild").category

    assert category.key == "metal/ferrous/steel"
    assert category.path_segments == ("Metal", "Ferrous", "Steel")
    assert category.display_name == "Steel"


def test_parse_falls_back_to_uncategorized_when_material_has_no_class():
    assert material(parse_fixture(), "Unclassified Sample").category == MaterialCategory.UNCATEGORIZED


def test_parse_uses_inline_class_name_when_no_registry_match():
    xml = """<?xml version="1.0" encoding="utf-8"?>
        <MatML_Doc>
          <Material>
            <BulkDetails>
              <Name>TestMaterial</Name>
              <Class>
                <Name>Testing Only Material</Name>
              </Class>
              <PropertyData property="Density">
                <Data format="exponential">0.000000e+00</Data>
              </PropertyData>
            </BulkDetails>
          </Material>
        </MatML_Doc>"""

    (only,) = MatmlParser().parse(MaterialLibraryId("inline"), "Inline Library", xml).materials

    assert only.category.display_name == "Testing Only Material"
    assert only.category != MaterialCategory.UNCATEGORIZED


def test_parse_reads_numeric_property_value_with_unit_and_symbol():
    (density,) = [p for p in material(parse_fixture(), "Steel, Mild").properties if p.name == "Density"]

    assert density.as_number() == 7.872
    assert density.raw_value == "7.872"
    assert density.unit == "g/cm^3"
    assert density.symbol == "rho"


def test_parse_reads_description_annotation_when_present():
    library = parse_fixture()

    assert material(library, "Steel, Mild").description == "General purpose mild steel."
    assert material(library, "ABS Plastic").description is None


def test_parse_passes_through_english_units_without_conversion():
    (aluminum,) = parse_fixture("sample-english-library.xml", "english").materials
    (density,) = [p for p in aluminum.properties if p.name == "Density"]

    assert density.unit == "lbm/in^3"
    assert density.as_number() == 0.0975


def test_parse_rejects_a_material_without_bulk_details():
    with pytest.raises(ValueError, match="index 0 is missing BulkDetails"):
        MatmlParser().parse(MaterialLibraryId("x"), "x", "<MatML_Doc><Material/></MatML_Doc>")


def test_parse_rejects_malformed_xml():
    with pytest.raises(ValueError, match="not well formed"):
        MatmlParser().parse(MaterialLibraryId("x"), "x", "<MatML_Doc>")


def test_parse_matches_class_ids_case_insensitively():
    xml = """<MatML_Doc><Metadata><ClassDetails id="CL_A"><Name>Alloys</Name></ClassDetails></Metadata>
        <Material><BulkDetails><Name>M</Name><Class idref="cl_a"/></BulkDetails></Material></MatML_Doc>"""

    (only,) = MatmlParser().parse(MaterialLibraryId("x"), "x", xml).materials

    assert only.category.display_name == "Alloys"


def test_parsed_materials_have_value_equality():
    first, second = parse_fixture(), parse_fixture()

    assert first.materials == second.materials
    assert replace(first.materials[0], name="other") != second.materials[0]
