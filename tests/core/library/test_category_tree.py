from __future__ import annotations

from banxopen.materials import (
    MaterialCategory,
    MaterialCategoryNode,
    MaterialLibrary,
    MaterialLibraryId,
    build_category_tree,
)

from builders import make_material

LIB = MaterialLibraryId("lib1")


def build(*materials) -> tuple[MaterialCategoryNode, ...]:
    return build_category_tree(MaterialLibrary(LIB, "Lib", tuple(materials)))


def m(name: str, category: MaterialCategory):
    return make_material(name, category=category, library="lib1")


def single(nodes):
    assert len(nodes) == 1
    return nodes[0]


def test_build_nests_categories_by_their_path_segments():
    alloy_steel = MaterialCategory("metal/steel/alloy", "Alloy Steel", ("Metals", "Steel", "Alloy Steel"))

    metals = single(build(m("4140", alloy_steel)))
    steel = single(metals.children)
    alloy = single(steel.children)

    assert (metals.display_name, metals.materials) == ("Metals", ())
    assert (steel.display_name, steel.materials) == ("Steel", ())
    assert alloy.display_name == "Alloy Steel"
    assert alloy.children == ()
    assert [x.name for x in alloy.materials] == ["4140"]


def test_build_merges_categories_that_share_a_path_prefix_into_one_branch():
    steel = MaterialCategory("metal/steel", "Steel", ("Metals", "Steel"))
    aluminum = MaterialCategory("metal/aluminum", "Aluminum", ("Metals", "Aluminum"))

    metals = single(build(m("4140", steel), m("6061", aluminum)))

    assert [c.display_name for c in metals.children] == ["Aluminum", "Steel"]


def test_build_groups_materials_with_equal_but_distinct_category_instances_together():
    steel_a = MaterialCategory("metal/steel", "Steel", ("Metals", "Steel"))
    steel_b = MaterialCategory("metal/steel", "Steel", ("Metals", "Steel"))

    steel = single(single(build(m("Steel A", steel_a), m("Steel B", steel_b))).children)

    assert [x.name for x in steel.materials] == ["Steel A", "Steel B"]


def test_build_treats_path_segments_case_insensitively_so_one_branch_is_produced():
    lower = MaterialCategory("a", "Steel", ("metals", "steel"))
    upper = MaterialCategory("b", "Stainless", ("Metals", "Stainless"))

    assert len(single(build(m("4140", lower), m("316", upper))).children) == 2


def test_build_orders_siblings_by_sort_order_then_display_name():
    second = MaterialCategory("b", "Bravo", ("Bravo",), sort_order=2)
    first = MaterialCategory("a", "Alpha", ("Alpha",), sort_order=1)
    no_sort_order = MaterialCategory("z", "Zulu", ("Zulu",))

    roots = build(m("m-zulu", no_sort_order), m("m-bravo", second), m("m-alpha", first))

    assert [r.display_name for r in roots] == ["Alpha", "Bravo", "Zulu"]


def test_build_sorts_an_intermediate_node_by_the_lowest_sort_order_in_its_subtree():
    plastics = MaterialCategory("p", "Plastics", ("Plastics",), sort_order=5)
    steel = MaterialCategory("s", "Steel", ("Metals", "Steel"), sort_order=1)

    assert [r.display_name for r in build(m("ABS", plastics), m("4140", steel))] == ["Metals", "Plastics"]


def test_build_sorts_materials_within_a_node_by_name_case_insensitively():
    category = MaterialCategory("cat", "Cat", ("Cat",))

    node = single(build(m("charlie", category), m("Alpha", category), m("bravo", category)))

    assert [x.name for x in node.materials] == ["Alpha", "bravo", "charlie"]


def test_build_promotes_a_category_with_no_path_segments_to_its_own_root():
    named = MaterialCategory("named", "Named", ("Named",), sort_order=1)

    roots = build(m("m-uncategorized", MaterialCategory.UNCATEGORIZED), m("m-named", named))

    assert [r.display_name for r in roots] == ["Named", "Uncategorized"]
    assert [x.name for x in roots[1].materials] == ["m-uncategorized"]


def test_build_prefers_the_category_display_name_over_the_raw_segment_on_the_terminating_node():
    category = MaterialCategory("k", "Stainless Steel", ("Metals", "SS"))

    terminating = single(single(build(m("316", category))).children)

    assert terminating.segment == "SS"
    assert terminating.display_name == "Stainless Steel"


def test_build_handles_a_category_terminating_on_an_ancestor_of_another_category():
    metals = MaterialCategory("m", "Metals", ("Metals",))
    steel = MaterialCategory("s", "Steel", ("Metals", "Steel"))

    root = single(build(m("Generic Metal", metals), m("4140", steel)))

    assert [x.name for x in root.materials] == ["Generic Metal"]
    assert [x.name for x in single(root.children).materials] == ["4140"]


def test_build_returns_nothing_for_an_empty_library():
    assert build() == ()
