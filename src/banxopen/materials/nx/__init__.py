"""BANxOpen Materials: NX API.

Importable without NX: names are resolved lazily on first use, so presenter tests and type checkers can import this.

    started = MaterialEngine.create(ctx, sheet_metal_modules)
    if not started.ok:
        ...                                   # show started.message
    service = started.value.service           # browse, plan, apply, clear
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from banxopen.materials.nx_adapters.display_material_helper import DisplayMaterialHelper
    from banxopen.materials.nx_adapters.engine import MaterialEngine
    from banxopen.materials.nx_adapters.part_material_service import NxPartMaterialService
    from banxopen.materials.nx_adapters.ports import NxMaterialRuleModule, SideEffectExecutor

__all__ = [
    "DisplayMaterialHelper",
    "MaterialEngine",
    "NxMaterialRuleModule",
    "NxPartMaterialService",
    "SideEffectExecutor",
]

_ADAPTERS = "banxopen.materials.nx_adapters"
_LAZY = {
    "DisplayMaterialHelper": "display_material_helper",
    "MaterialEngine": "engine",
    "NxMaterialRuleModule": "ports",
    "NxPartMaterialService": "part_material_service",
    "SideEffectExecutor": "ports",
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f"{_ADAPTERS}.{module}"), name)
