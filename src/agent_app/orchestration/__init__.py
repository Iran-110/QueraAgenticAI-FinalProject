"""Bounded support workflows; persistence and action execution belong to the tracker."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_app.orchestration.engine import SupportEngine
    from agent_app.orchestration.service import CoreAdapters, CoreTurnOutcome, CoreTurnService

__all__ = ["SupportEngine", "CoreAdapters", "CoreTurnOutcome", "CoreTurnService"]


def __getattr__(name: str) -> object:
    # Leaf ports are also used by reasoning. Eager service imports would load
    # handoff back into a partially initialized reasoning module.
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = "engine" if name == "SupportEngine" else "service"
    value = getattr(import_module(f"{__name__}.{module}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
