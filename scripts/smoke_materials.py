"""NX smoke test for BANxOpen Materials. Confirms the [verify] UF call shapes in nx_adapters/uf_disp.py.

Run in NX 2606 with a part open that has bodies (File > Execute > Journal, Alt+F8). Both repos' src folders must be
importable: this script adds them when run from the repo.

Read-only by default:
  1. MaterialEngine.create (library folder, rules file, wiring)
  2. list libraries for the current application; load the first; build its category tree
  3. bodies (kind, volume via UF AskMassProps3d) and current assignments (physical + display material via UF Disp)
  4. plan the first material of the library on every body: verdicts per body

Set BANXOPEN_SMOKE_APPLY=1 to also apply that material to the first body and clear it again, inside an outer undo
scope that is never committed: the part is rolled back afterwards. This exercises the UF display-material calls.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for src in (_REPO / "src", _REPO.parent / "BANxOpen.Foundation" / "src"):
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

import NXOpen  # noqa: E402

from banxopen.foundation.nx import NxSessionContext, UndoScope, install_nx_logging  # noqa: E402
from banxopen.materials.nx import MaterialEngine  # noqa: E402


def main() -> None:
    session = NXOpen.Session.GetSession()
    lw = session.ListingWindow
    lw.Open()
    say = lw.WriteLine
    try:
        install_nx_logging(session)
        started = NxSessionContext.try_initialize()
        if not started.ok or started.value is None:
            say(f"[0] FAILED: {started.message}")
            return
        ctx = started.value

        engine_result = MaterialEngine.create(ctx, confirm_load=lambda _q: True)
        if not engine_result.ok or engine_result.value is None:
            say(f"[1] engine FAILED: {engine_result.error_code}: {engine_result.message}")
            return
        engine = engine_result.value
        service = engine.service
        say(
            f"[1] engine ok: library folder={engine.repository.root_directory} "
            f"sheet metal libraries configured={engine.sheet_metal_libraries.is_configured} "
            f"material forms property={engine.material_forms.property_name} "
            f"validation rules={[r.rule_id for r in engine.rules.validation_rules]}"
        )

        libraries = service.list_libraries()
        say(f"[2] libraries ({len(libraries)}): {[r.display_name for r in libraries]}")
        for reference in libraries:
            if service.is_sheet_metal_library(reference.id):
                sheet_metal = service.load_library(reference)
                say(f"    sheet metal '{reference.display_name}': {[m.name for m in sheet_metal.materials][:10]}")
        if not libraries:
            return
        library = service.load_library(libraries[0])
        tree = service.category_tree(library)
        say(f"    loaded '{library.display_name}': {len(library.materials)} materials, {len(tree)} root categories")

        bodies = service.bodies()
        assignments = service.current_assignments()
        say(f"[3] bodies ({len(bodies)}):")
        for body in bodies[:10]:
            a = assignments.get(body.id)
            display = a.current_display_material if a else None
            say(
                f"      {body.name or body.id}: kind={body.kind.value} volume={body.volume:.6g} m^3 "
                f"material={a.material_name if a else None} "
                f"display={display.name + str(display.rgb) if display else None}"
            )

        if not library.materials or not bodies:
            return
        material = library.materials[0]
        planned = service.plan(material, [b.id for b in bodies])
        say(f"[4] plan '{material.name}':")
        for verdict in planned.verdicts[:10]:
            say(f"      {verdict.body.name}: {verdict.status.value} {verdict.message or ''}")

        if os.environ.get("BANXOPEN_SMOKE_APPLY") == "1":
            target = [bodies[0].id]
            with UndoScope(ctx.session, "BANxOpen materials smoke (rolled back)"):
                applied = service.apply(material, target, confirm_remaining=True)
                say(f"[5] apply: ok={applied.ok} {applied.error_code or ''} {applied.message or ''}")
                for o in applied.value.outcomes if applied.value else ():
                    say(f"      {o.body_name}: {o.status.value} {o.message or ''}")
                after = service.current_assignments().get(bodies[0].id)
                say(f"      now: material={after.material_name if after else None}")
                say(f"      display={after.current_display_material if after else None}")
                cleared = service.clear(target)
                cleared_statuses = [o.status.value for o in cleared.value.outcomes] if cleared.value else []
                say(f"[6] clear: ok={cleared.ok} {cleared_statuses}")
            say("    rolled back.")
        say("Smoke test finished.")
    except Exception:  # report everything: this is a diagnostic journal
        say("Smoke test crashed:\n" + traceback.format_exc())


if __name__ == "__main__":
    main()
