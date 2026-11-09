"""The nested, sorted category tree a material browser renders. The UI makes no grouping or sorting decisions."""

from __future__ import annotations

from dataclasses import dataclass, field

from banxopen.materials.model.materials import SORT_LAST, Material, MaterialLibrary


@dataclass(frozen=True, slots=True)
class MaterialCategoryNode:
    """One node of the category tree.

    `segment` is the raw class-hierarchy segment the node was created from and identifies it among its siblings;
    `display_name` is what the user sees: the same for intermediate nodes, but the owning category's curated name for
    a node that terminates a category's path. `materials` is non-empty only on nodes that terminate a category path.
    Both tuples are already in render order.
    """

    segment: str
    display_name: str
    children: tuple[MaterialCategoryNode, ...]
    materials: tuple[Material, ...]


def build_category_tree(library: MaterialLibrary) -> tuple[MaterialCategoryNode, ...]:
    """The root nodes, in render order."""
    roots: list[_Node] = []

    groups: dict[str, list[Material]] = {}
    for material in library.materials:
        groups.setdefault(material.category.key, []).append(material)

    for members in groups.values():
        category = members[0].category
        # A category with no class hierarchy still needs somewhere to live, so it becomes a root named after itself.
        # That is what puts Uncategorized (no path, sorted last) at the top level, last.
        path = category.path_segments or (category.display_name,)
        node = _descend(roots, path)
        # The curated label wins over the raw segment on the terminating node; intermediate nodes keep their segment.
        node.display_name = category.display_name
        node.materials.extend(members)
        node.sort_order = min(node.sort_order, category.sort_order if category.sort_order is not None else SORT_LAST)

    for root in roots:
        _effective_sort_order(root)
    return _freeze(roots)


@dataclass(slots=True, eq=False)
class _Node:
    segment: str
    display_name: str
    children: list[_Node] = field(default_factory=list["_Node"])
    materials: list[Material] = field(default_factory=list[Material])
    sort_order: int = SORT_LAST
    effective_sort_order: int = SORT_LAST


def _descend(roots: list[_Node], path: tuple[str, ...]) -> _Node:
    """Walks `path`, creating nodes as needed. Segments match case-insensitively, so a library that spells the same
    class differently across entries still produces one branch."""
    siblings = roots
    node: _Node | None = None
    for segment in path:
        node = next((n for n in siblings if n.segment.upper() == segment.upper()), None)
        if node is None:
            node = _Node(segment, segment)
            siblings.append(node)
        siblings = node.children
    assert node is not None  # callers always pass at least one segment
    return node


def _effective_sort_order(node: _Node) -> int:
    """A node sorts by the lowest sort order anywhere in its subtree, so an explicitly ordered category pulls its
    ancestors up with it instead of every intermediate node tying and falling back to alphabetical."""
    order = node.sort_order
    for child in node.children:
        order = min(order, _effective_sort_order(child))
    node.effective_sort_order = order
    return order


def _freeze(nodes: list[_Node]) -> tuple[MaterialCategoryNode, ...]:
    ordered = sorted(nodes, key=lambda n: (n.effective_sort_order, n.display_name.upper()))
    return tuple(
        MaterialCategoryNode(
            n.segment,
            n.display_name,
            _freeze(n.children),
            tuple(sorted(n.materials, key=lambda m: m.name.upper())),
        )
        for n in ordered
    )
