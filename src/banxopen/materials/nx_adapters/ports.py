"""How a feature domain registers NX executors for its side effects."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from banxopen.foundation import OperationResult
from banxopen.materials.core.assignment.planning import SideEffectInstruction
from banxopen.materials.core.rules.ports import MaterialRuleModule

if TYPE_CHECKING:
    import NXOpen


class SideEffectExecutor(Protocol):
    """Carries out one kind of side-effect instruction against a resolved body, from inside the part material
    service's per-body undo mark. The domain's core effect rule emits the instruction as plain data; the domain's NX
    layer registers the matching executor beside the rule. They agree on the type and data keys through the rule's
    public constants."""

    @property
    def instruction_type(self) -> str: ...

    def execute(self, instruction: SideEffectInstruction, body: NXOpen.Body) -> OperationResult[None]: ...


class NxMaterialRuleModule(MaterialRuleModule, Protocol):
    """A rule module together with the NX executors for its side effects, registered as one unit so
    `MaterialEngine.create` can refuse a side effect that has no executor."""

    @property
    def side_effect_executors(self) -> Sequence[SideEffectExecutor]:
        """One executor per instruction type the module's side-effect rules emit. Empty when it has none."""
        ...
