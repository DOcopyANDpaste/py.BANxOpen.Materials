import pytest

from banxopen.materials import MaterialCategory, MaterialId, MaterialPropertyValue


def make(raw_value: str) -> MaterialPropertyValue:
    return MaterialPropertyValue("pr1", "Test Property", None, raw_value, None)


# ---- IdsTests ----


def test_material_id_str_returns_value():
    assert str(MaterialId("steel-1")) == "steel-1"


def test_material_id_equality_is_by_value():
    assert MaterialId("a") == MaterialId("a")
    assert MaterialId("a") != MaterialId("b")


# ---- MaterialPropertyValueTests ----


def test_as_string_returns_raw_value_unchanged():
    assert make("Matte").as_string() == "Matte"


def test_as_number_parses_a_single_numeric_raw_value():
    assert make("7.872").as_number() == 7.872


@pytest.mark.parametrize("raw_value", ["Matte", "10,20,30", "", "1_000"])
def test_as_number_returns_none_for_non_numeric_raw_value(raw_value):
    assert make(raw_value).as_number() is None


def test_as_array_splits_comma_separated_raw_value_and_trims_each_entry():
    assert make("10, 20 ,30").as_array() == ("10", "20", "30")


def test_as_array_single_value_with_no_commas_returns_one_element():
    assert make("7.872").as_array() == ("7.872",)


def test_as_array_drops_empty_entries_from_trailing_or_repeated_commas():
    assert make("10,,20,").as_array() == ("10", "20")


def test_uncategorized_sorts_last_and_has_no_path():
    assert MaterialCategory.UNCATEGORIZED.path_segments == ()
    assert MaterialCategory.UNCATEGORIZED.sort_order == 2_147_483_647
