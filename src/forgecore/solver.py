"""Solver registry — the engine's input-side discovery seam (ENGINE.md §4).

The mirror of `result_registry()`: solvers self-register metadata at import
time so the kernel and editors can ask "what can run on this world?" without
forgecore importing a single solver. The decorator wraps an existing
module-level function without modifying it — the function stays callable; only
the registration is new.

Same discovery model as results: import-time registration, the caller owns
registry completeness (no entry-point machinery, YAGNI), and a cross-module
name collision raises rather than silently overwriting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class SolverInfo:
    """Declarative metadata about one registered solver entry point."""

    name: str
    fn: Callable
    consumes: frozenset[str]  # {"scene"} | {"dataset"} | both
    produces: tuple[str, ...]  # result class names this solver yields
    dialects: frozenset[str]  # {"flow"}, {"capability"}, {"behavior"}
    package: str  # top-level package, for provenance / UI grouping


_REGISTRY: dict[str, SolverInfo] = {}


def solver(
    name: str,
    *,
    consumes: Iterable[str],
    produces: Iterable[str],
    dialects: Iterable[str],
) -> Callable[[Callable], Callable]:
    """Register a module-level function as a solver; return it unchanged.

    Collisions across modules raise (same rule as ResultMixin); re-registering
    the same name from the same module is allowed (module reload).
    """

    def register(fn: Callable) -> Callable:
        existing = _REGISTRY.get(name)
        if existing is not None and existing.fn.__module__ != fn.__module__:
            raise TypeError(
                f"solver name collision: {name} is already registered by "
                f"{existing.fn.__module__}; refusing to overwrite from "
                f"{fn.__module__}"
            )
        _REGISTRY[name] = SolverInfo(
            name=name,
            fn=fn,
            consumes=frozenset(consumes),
            produces=tuple(produces),
            dialects=frozenset(dialects),
            package=fn.__module__.split(".")[0],
        )
        return fn

    return register


def solver_registry() -> dict[str, SolverInfo]:
    """Catalog of registered solvers. Completeness depends on the caller having
    imported the relevant solver packages — forgecore imports none of them."""
    return dict(_REGISTRY)


def solvers_for(world: Any) -> list[SolverInfo]:
    """Every solver that can run on this world, matched by world type.

    The match token is the world's class name lowercased (Scene -> "scene",
    Dataset -> "dataset"); a solver runs if it declares that token in
    `consumes`."""
    token = type(world).__name__.lower()
    return [info for info in _REGISTRY.values() if token in info.consumes]
