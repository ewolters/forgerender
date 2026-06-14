"""Kernel — centralized routing (ENGINE.md §7).

The engine's "game loop," sized honestly: discovery + routing only, no math.
The work lives in the registered solvers (the Unreal lesson — UEngine::Tick is
small). The kernel looks up a solver and calls it, renders a result through the
Result contract, lists what can run on a world, and describes the full catalog
for editors. forgecore still imports nothing: the registries fill when the
caller imports solver packages.
"""

from __future__ import annotations

from typing import Any

from .dialect import BEHAVIOR, CAPABILITY, FLOW, SPINE, result_registry
from .solver import solver_registry, solvers_for

__all__ = ["run", "render", "describe", "solvers_for"]


def run(solver_name: str, world: Any, **params: Any) -> Any:
    """Look up a registered solver by name and call it on the world.

    Raises KeyError if no solver is registered under that name — completeness
    is the caller's job (import the solver package first)."""
    return solver_registry()[solver_name].fn(world, **params)


def render(result: Any) -> list:
    """Render a result into its ChartSpec views via the Result contract.

    Prefers views() (the complete portrait); falls back to to_render() for
    bare protocol conformers; returns [] for anything that is not a result."""
    views = getattr(result, "views", None)
    if callable(views):
        return views()
    to_render = getattr(result, "to_render", None)
    if callable(to_render):
        return [to_render()]
    return []


def describe() -> dict:
    """The full engine catalog, for editors: registered solvers (with their
    consume/produce/dialect metadata), result types, and dialect vocabularies.
    JSON-serializable — frozensets become sorted lists."""
    return {
        "solvers": {
            name: {
                "consumes": sorted(info.consumes),
                "produces": list(info.produces),
                "dialects": sorted(info.dialects),
                "package": info.package,
            }
            for name, info in solver_registry().items()
        },
        "results": sorted(result_registry()),
        "dialects": {
            "spine": sorted(SPINE),
            "capability": sorted(CAPABILITY),
            "flow": sorted(FLOW),
            "behavior": sorted(BEHAVIOR),
        },
    }
