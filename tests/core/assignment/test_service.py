"""The per-gesture service: what the Material Assignment presenter used to work out itself."""

from __future__ import annotations

import logging

from banxopen.foundation import BodyId, BodyKind, RuleDecision
from banxopen.materials import (
    BodyMaterialAssignment,
    MaterialAssignmentService,
    MaterialLibraryId,
    MaterialLibraryReference,
    MaterialRuleSet,
    MaterialsCodes,
    OutcomeStatus,
    SheetMetalLibraries,
    VerdictStatus,
)

from builders import FakeGateRule, FakeModule, FakePartMaterialService, make_body, make_material


class FakeRepository:
    def __init__(self, *names: str) -> None:
        self.references = [MaterialLibraryReference(MaterialLibraryId(n), n, f"{n}.xml") for n in names]

    def list_available_libraries(self):
        return self.references

    def read_library_xml(self, library_id) -> str:
        return "<MatML_Doc><Material id='m1'><BulkDetails><Name>Steel</Name></BulkDetails></Material></MatML_Doc>"


def service(
    part: FakePartMaterialService,
    *extra_rules: FakeGateRule,
    repository: FakeRepository | None = None,
    sheet_metal_app: bool = False,
) -> MaterialAssignmentService:
    modules = (*MaterialRuleSet.baseline(), FakeModule("TEST", validation_rules=list(extra_rules)))
    return MaterialAssignmentService(
        MaterialRuleSet.from_modules(modules),
        part,
        repository or FakeRepository(),
        SheetMetalLibraries.NAME_HEURISTIC,
        is_sheet_metal_application=sheet_metal_app,
    )


def ids(*names: str) -> list[BodyId]:
    return [BodyId(n) for n in names]


def statuses(report) -> dict[str, OutcomeStatus]:
    return {o.body_id.value: o.status for o in report.outcomes}


# ---- Libraries ----


def test_lists_every_library_outside_the_sheet_metal_application():
    repo = FakeRepository("Metals", "Sheet Metal Materials")

    assert [r.id.value for r in service(FakePartMaterialService([]), repository=repo).list_libraries()] == [
        "Metals",
        "Sheet Metal Materials",
    ]


def test_lists_only_sheet_metal_libraries_in_the_sheet_metal_application():
    repo = FakeRepository("Metals", "Sheet Metal Materials")

    listed = service(FakePartMaterialService([]), repository=repo, sheet_metal_app=True).list_libraries()

    assert [r.id.value for r in listed] == ["Sheet Metal Materials"]


class MixedRepository(FakeRepository):
    """One file holding a solid material and a sheet metal one."""

    def read_library_xml(self, library_id) -> str:
        return (
            "<MatML_Doc>"
            "<Metadata><PropertyDetails id='pr1'><Name>AllowedFor</Name></PropertyDetails></Metadata>"
            "<Material id='m1'><BulkDetails><Name>Steel</Name></BulkDetails></Material>"
            "<Material id='m2'><BulkDetails><Name>4010</Name>"
            "<PropertyData property='pr1'><Data>SheetMetal</Data></PropertyData></BulkDetails></Material>"
            "</MatML_Doc>"
        )


def test_a_library_with_sheet_metal_materials_is_also_offered_as_its_sheet_metal_view():
    svc = service(FakePartMaterialService([]), repository=MixedRepository("Metals"))

    listed = svc.list_libraries()

    assert [r.display_name for r in listed] == ["Metals", "Metals_SheetMetal"]
    assert [svc.is_sheet_metal_library(r.id) for r in listed] == [False, True]
    assert [m.name for m in svc.load_library(listed[0]).materials] == ["Steel"]
    assert [m.name for m in svc.load_library(listed[1]).materials] == ["4010"]


def test_the_sheet_metal_application_offers_the_sheet_metal_view_of_a_mixed_library():
    svc = service(FakePartMaterialService([]), repository=MixedRepository("Metals"), sheet_metal_app=True)

    assert [r.display_name for r in svc.list_libraries()] == ["Metals_SheetMetal"]


def test_a_sheet_metal_view_material_applies_only_to_sheet_metal_bodies():
    part = FakePartMaterialService([make_body("sm", BodyKind.SHEET_METAL), make_body("solid", BodyKind.SOLID)])
    svc = service(part, repository=MixedRepository("Metals"))
    view = svc.list_libraries()[1]
    (sheet_metal_material,) = svc.load_library(view).materials

    planned = svc.plan(sheet_metal_material, ids("sm", "solid"))

    assert {v.body.id.value: v.status for v in planned.verdicts} == {
        "sm": VerdictStatus.OK,
        "solid": VerdictStatus.BLOCKED,
    }


def test_lists_every_library_in_the_sheet_metal_application_when_none_is_sheet_metal(caplog):
    repo = FakeRepository("Metals", "Plastics")

    with caplog.at_level(logging.WARNING, logger="banxopen.materials"):
        listed = service(FakePartMaterialService([]), repository=repo, sheet_metal_app=True).list_libraries()

    assert [r.id.value for r in listed] == ["Metals", "Plastics"]
    assert "no available library is a sheet metal library" in caplog.text


def test_loading_a_library_makes_it_the_one_assignments_resolve_against():
    part = FakePartMaterialService([])
    repo = FakeRepository("Metals")
    svc = service(part, repository=repo)

    library = svc.load_library(repo.references[0])

    assert part.resolution_libraries == [library]
    assert [m.name for m in library.materials] == ["Steel"]
    assert svc.load_library(repo.references[0]) is library  # cached


# ---- Plan ----


def test_plan_gives_one_verdict_per_body_still_in_the_part():
    part = FakePartMaterialService([make_body("b1"), make_body("b2")])

    planned = service(part).plan(make_material(), ids("b2", "gone", "b1"))

    assert [v.body.id.value for v in planned.verdicts] == ["b2", "b1"]
    assert all(v.status is VerdictStatus.OK for v in planned.verdicts)


def test_plan_flattens_rule_outcomes_into_verdicts_with_their_messages():
    part = FakePartMaterialService(
        [make_body("ok"), make_body("sm", BodyKind.SHEET_METAL), make_body("asks")],
        {BodyId("asks"): BodyMaterialAssignment(BodyId("asks"), "Aluminum", None)},
    )

    planned = service(part).plan(make_material("Steel"), ids("ok", "sm", "asks"))

    by_id = {v.body.id.value: v for v in planned.verdicts}
    assert by_id["sm"].status is VerdictStatus.BLOCKED
    assert by_id["sm"].message == "'Steel' is not available for this body."
    assert by_id["asks"].status is VerdictStatus.NEEDS_CONFIRMATION
    assert by_id["asks"].message is not None and "Replace with 'Steel'?" in by_id["asks"].message
    # Plain steel has no coating data: the display rule warns, and the warning rides on the OK verdict.
    assert by_id["ok"].status is VerdictStatus.OK
    assert by_id["ok"].message is not None and "default display material" in by_id["ok"].message
    assert [v.body.id.value for v in planned.needing_confirmation] == ["asks"]
    assert [v.body.id.value for v in planned.blocked] == ["sm"]


def test_plan_passes_the_variant_to_the_rules():
    seen: list[str | None] = []

    def record(ctx):
        seen.append(ctx.requested_variant)
        return FakeGateRule.always("x", 1).evaluate(ctx)

    service(FakePartMaterialService([make_body("b1")]), FakeGateRule("SEE", 999, record)).plan(
        make_material(), ids("b1"), variant="row-1"
    )

    assert seen == ["row-1"]


# ---- Apply ----


def test_apply_asks_one_question_covering_every_body_that_needs_confirmation_and_changes_nothing():
    part = FakePartMaterialService(
        [make_body("b1"), make_body("b2")],
        {b: BodyMaterialAssignment(b, "Aluminum", None) for b in ids("b1", "b2")},
    )

    result = service(part).apply(make_material("Steel"), ids("b1", "b2"))

    assert result.needs_confirmation
    assert result.question is not None
    assert result.question.startswith("2 body(ies) need confirmation for Steel:\n  [b1] Body already has 'Aluminum'.")
    assert part.applied_plans == []


def test_apply_confirmed_applies_to_every_body():
    part = FakePartMaterialService(
        [make_body("b1")], {BodyId("b1"): BodyMaterialAssignment(BodyId("b1"), "Aluminum", None)}
    )

    result = service(part).apply(make_material("Steel"), ids("b1"), confirm_remaining=True)

    assert result.ok
    assert result.value is not None and statuses(result.value) == {"b1": OutcomeStatus.APPLIED}
    assert [a.body_id.value for a in part.applied_plans[0].assignments] == ["b1"]


def test_apply_declined_skips_those_bodies_and_applies_the_rest():
    part = FakePartMaterialService(
        [make_body("asks"), make_body("clean")],
        {BodyId("asks"): BodyMaterialAssignment(BodyId("asks"), "Aluminum", None)},
    )

    result = service(part).apply(make_material("Steel"), ids("asks", "clean"), confirm_remaining=False)

    assert result.value is not None
    assert statuses(result.value) == {"asks": OutcomeStatus.DECLINED, "clean": OutcomeStatus.APPLIED}
    assert result.value.outcomes[0].message == "not confirmed"


def test_apply_reuses_earlier_confirmations_without_asking_again():
    part = FakePartMaterialService(
        [make_body("b1")], {BodyId("b1"): BodyMaterialAssignment(BodyId("b1"), "Aluminum", None)}
    )

    result = service(part).apply(make_material("Steel"), ids("b1"), confirmed={BodyId("b1")})

    assert not result.needs_confirmation
    assert result.value is not None and result.value.all_applied


def test_apply_reports_blocked_and_vanished_bodies_without_failing():
    part = FakePartMaterialService([make_body("sm", BodyKind.SHEET_METAL), make_body("b1")])

    result = service(part).apply(make_material("Steel"), ids("sm", "gone", "b1"))

    assert result.ok
    assert result.value is not None
    assert statuses(result.value) == {
        "gone": OutcomeStatus.NOT_IN_PART,
        "sm": OutcomeStatus.BLOCKED,
        "b1": OutcomeStatus.APPLIED,
    }
    by_id = {o.body_id.value: o for o in result.value.outcomes}
    assert by_id["sm"].message == "blocked: 'Steel' is not available for this body."
    assert by_id["gone"].message == "no longer in the work part"


def test_apply_says_exactly_which_bodies_nx_failed_on():
    part = FakePartMaterialService(
        [make_body("b1"), make_body("b2")], fail_on={BodyId("b2"): "NX failed on this body: 42"}
    )

    result = service(part).apply(make_material("Steel"), ids("b1", "b2"))

    assert not result.ok
    assert result.error_code == MaterialsCodes.PARTIAL_FAILURE
    assert result.value is not None
    assert statuses(result.value) == {"b1": OutcomeStatus.APPLIED, "b2": OutcomeStatus.FAILED}
    assert result.value.outcomes[1].message == "NX failed on this body: 42"


def test_apply_puts_warnings_on_the_bodies_that_took():
    part = FakePartMaterialService([make_body("b1")])

    result = service(part, FakeGateRule.always("CAREFUL", 250, RuleDecision.WARN)).apply(
        make_material("Steel"), ids("b1")
    )

    assert result.value is not None
    (outcome,) = result.value.outcomes
    assert outcome.status is OutcomeStatus.APPLIED
    assert outcome.message is not None and outcome.message.startswith("warning: ")
    assert "careful" in outcome.message


def test_apply_with_nothing_left_to_apply_does_not_touch_the_part():
    part = FakePartMaterialService([make_body("sm", BodyKind.SHEET_METAL)])

    result = service(part).apply(make_material("Steel"), ids("sm"))

    assert result.ok
    assert part.applied_plans == []


# ---- Clear ----


def test_clear_skips_bodies_with_no_material_and_reports_them():
    part = FakePartMaterialService(
        [make_body("has"), make_body("none")], {BodyId("has"): BodyMaterialAssignment(BodyId("has"), "Steel", None)}
    )

    result = service(part).clear(ids("has", "none", "gone"))

    assert part.cleared == [ids("has")]
    assert result.value is not None
    assert statuses(result.value) == {
        "gone": OutcomeStatus.NOT_IN_PART,
        "has": OutcomeStatus.APPLIED,
        "none": OutcomeStatus.NO_MATERIAL,
    }


def test_clear_says_exactly_which_bodies_nx_failed_on():
    part = FakePartMaterialService(
        [make_body("b1"), make_body("b2")],
        {b: BodyMaterialAssignment(b, "Steel", None) for b in ids("b1", "b2")},
        fail_on={BodyId("b1"): "nope"},
    )

    result = service(part).clear(ids("b1", "b2"))

    assert not result.ok
    assert result.value is not None
    assert statuses(result.value) == {"b1": OutcomeStatus.FAILED, "b2": OutcomeStatus.APPLIED}


def test_bodies_and_assignments_are_read_fresh_from_the_part():
    part = FakePartMaterialService([make_body("b1")])
    svc = service(part)
    part.bodies.append(make_body("b2"))
    part.assignments[BodyId("b2")] = BodyMaterialAssignment(BodyId("b2"), "Steel", None)

    assert [b.id.value for b in svc.bodies()] == ["b1", "b2"]
    assert svc.current_assignments()[BodyId("b2")].material_name == "Steel"


# ---- Preferred material ----


def test_reads_the_preferred_material_trimmed():
    part = FakePartMaterialService([], preferred="  S235JR ")

    assert service(part).preferred_material() == "S235JR"


def test_a_blank_preferred_material_reads_as_none():
    assert service(FakePartMaterialService([], preferred="   ")).preferred_material() is None
    assert service(FakePartMaterialService([])).preferred_material() is None


def test_writes_the_preferred_material_trimmed():
    part = FakePartMaterialService([], preferred="S235JR")

    result = service(part).set_preferred_material(" AlMg3 ")

    assert result.ok
    assert part.preferred_writes == ["AlMg3"]


def test_any_material_may_be_preferred_even_one_on_no_body():
    part = FakePartMaterialService([make_body("B1")])

    assert service(part).set_preferred_material("NotOnAnyBody").ok
    assert part.preferred == "NotOnAnyBody"


def test_writing_the_value_the_part_has_changes_nothing():
    part = FakePartMaterialService([], preferred="S235JR")

    result = service(part).set_preferred_material("s235jr")

    assert result.ok
    assert part.preferred_writes == []


def test_a_blank_preferred_material_is_refused():
    part = FakePartMaterialService([])

    result = service(part).set_preferred_material("  ")

    assert not result.ok
    assert result.error_code == MaterialsCodes.PREFERRED_MATERIAL_BLANK
    assert part.preferred_writes == []


def test_a_failed_preferred_material_write_is_passed_through():
    part = FakePartMaterialService([], fail_preferred_write="NX said no")

    result = service(part).set_preferred_material("S235JR")

    assert not result.ok
    assert result.message == "NX said no"
