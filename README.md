# BANxOpen.Materials (Python)

Material libraries (MatML), the material rule engine, and material assignment in NX. It is the Python port of the C# `BANxOpen.Materials` for NX 2606 (Designcenter), whose embedded Python is CPython 3.12 and depends on [BANxOpen.Foundation](https://github.com/DOcopyANDpaste/py.BANxOpen.Foundation).

## Public API

| Package | For | Contents |
|---|---|---|
| `banxopen.materials` (pure) | tools | `MaterialAssignmentService`: `list_libraries`, `load_library`, `category_tree`, `bodies`, `current_assignments`, `plan` → `BodyVerdict`s, `apply` / `clear` → `AssignmentReport` |
| | feature domains | `MaterialRuleModule`, `MaterialValidationRule`, `FeatureMaterialConstraintProvider` + `MaterialConstraint`, `PostAssignmentEffectRule` + `SideEffectInstruction`, `MaterialRuleOrder`, `MaterialRuleSet`, `SheetMetalLibraries`, `MaterialFormClassifier` + `MaterialForm` (what a material may be used for), `MaterialLibraryCatalog` (the libraries offered, including `<library>_SheetMetal`) |
| | everyone | library data (`Material`, `MaterialLibrary`, …), `MaterialsCodes`, `MaterialsText` |
| `banxopen.materials.nx` | entry points, domains | `MaterialEngine.create`, `SideEffectExecutor`, `NxMaterialRuleModule` |

A tool's whole material flow:

```python
from banxopen.materials.nx import MaterialEngine

started = MaterialEngine.create(ctx, sheet_metal_modules, confirm_load=messenger.ask)
service = started.value.service  # after checking started.ok

libraries = service.list_libraries()  # filtered for the NX application
library = service.load_library(libraries[0])
tree = service.category_tree(library)  # render as-is: already grouped and sorted

planned = service.plan(material, selected_ids)  # verdict per body: OK / NEEDS_CONFIRMATION / BLOCKED
result = service.apply(material, selected_ids)
if result.needs_confirmation:  # one question for every body that needs it
    result = service.apply(material, selected_ids, confirm_remaining=messenger.ask(result.question))
report = result.value  # per body: APPLIED / BLOCKED / DECLINED / FAILED / NOT_IN_PART
```

Every business decision sits behind these calls, so a rule change needs no tool change.

## Configuration

Copy `config-samples/material-library-rules.json` beside the library XML files, as described in `config-samples/README.md`. Point `BANXOPEN_MATERIAL_LIBRARY_RULES` at a file elsewhere to override the location.

## Development

```powershell
python -m venv .venv                       # with Python 3.12: the version NX 2606 embeds (the template's .venv works)
.venv\Scripts\python -m pip install -e ..\BANxOpen.Foundation   # sibling repos first, in dependency order: pip does not read [tool.uv.sources]
.venv\Scripts\python -m pip install -e ".[dev]"
New-Item -ItemType Junction -Path .\typings -Target "$env:UGII_BASE_DIR\UGOPEN\pythonStubs"

.venv\Scripts\ruff check . ; .venv\Scripts\pyright ; .venv\Scripts\lint-imports ; .venv\Scripts\python -m pytest --cov
```

The UF calls (NX ships no UF stubs) all live in `nx_adapters/uf_disp.py`. Their Python shapes are confirmed by `scripts/smoke_materials.py` (Alt+F8 in NX; set `BANXOPEN_SMOKE_APPLY=1` to also apply and clear on a rolled-back copy of the part).
