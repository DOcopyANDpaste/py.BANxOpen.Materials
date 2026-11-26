# Changelog

All notable changes to the public API (`banxopen.materials`, `banxopen.materials.nx`). Versioning is semantic, measured on the public API.

## [Unreleased]

### Added
- Sheet metal materials can share a library with the other materials. A material property (`AllowedFor` by default, set by `materialForms` in `material-library-rules.json`) lists what the material may be used for: `Solid`, `SheetMetal`, or both. Without it a material is for solids only.
- `MaterialFormClassifier` and `MaterialForm`: read that property. The body-type rule, the catalog and the engine (`engine.material_forms`) all share one instance.
- `MaterialLibraryCatalog`: offers each library holding sheet metal materials a second time, as `<library>_SheetMetal`, which behaves as a sheet metal library always has. `MaterialAssignmentService` lists and loads libraries through it.
- `MaterialRuleSet.baseline(..., material_forms=)`, `MaterialAssignmentService(..., material_forms=)`, `SheetMetalLibraries.from_rules`, `SheetMetalLibraries.is_sheet_metal_file`.

### Changed
- **Breaking:** targets NX 2606 (Designcenter) and its embedded CPython 3.12. `requires-python` is now `==3.12.*` (was `==3.11.*`), and the code uses 3.12+ syntax (type-parameter generics such as `class OperationResult[T]`), so it no longer runs on NX 2412's Python 3.11.
- Every module starts with `from __future__ import annotations`, enforced by ruff (`required-imports`). Python 3.12 evaluates annotations as soon as the code is run, so a class naming itself in an annotation, or a name imported only under `TYPE_CHECKING`, raised `NameError` on import (for example `from banxopen.foundation.nx import NxSessionContext`). Multi-exception `except` clauses are parenthesised again (`except A, B:` needs Python 3.14).
- An ordinary library lists only the materials allowed for solids, so a sheet-metal-only material appears only in its `_SheetMetal` library.
- `BLOCK_BODY_TYPE_RESTRICTION` also checks the material's `AllowedFor` property, except for materials from a sheet metal library file.
- `material-library-rules.json` no longer requires `sheetMetalLibraries`; the file must have it, `materialForms`, or both.

## [1.0.0] - 2026-10-28

### Added
- Python port of C# BANxOpen.Materials for NX 2412 (CPython 3.11).
- `MaterialAssignmentService` (`MaterialEngine.service`), the per-gesture operations for tools: list/load libraries, category tree, plan with per-body verdicts, apply and clear with per-body reports.
- `PartChangeOutcome`: per-body failure reasons from the part service.
- `MaterialsText` per-body reason wording, part of it moved from the Material Assignment dialog.

### Requires
- banxopen-foundation >= 1.0.1 (typed package marker).
