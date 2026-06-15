"""Conformance kit (ENGINE.md §9) — adoption as a checkbox, not artisanal
test-writing. Each solver repo's suite imports these to assert its results and
solvers are engine citizens, and that the pure-stdlib packages stay pure.

Because everything self-registers, everything is checkable — the UObject-
reflection payoff. forgecore still imports no solver; these helpers inspect
whatever the caller has imported.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
from typing import Any

from .dialect import _DIALECTS, Result, result_registry, speaks
from .solver import solver_registry, solvers_for
from .spec import ChartSpec

__all__ = ["assert_result_conforms", "assert_solver_conforms", "assert_pure_stdlib"]


def assert_result_conforms(result: Any) -> None:
    """A result is an engine citizen: it registered, satisfies the Result
    protocol, keeps every dialect view inside its vocabulary, serializes through
    JSON, and draws its complete portrait from its own fields alone."""
    cls = type(result)
    name = cls.__name__

    assert result_registry().get(name) is cls, (
        f"{name} is not registered in result_registry() "
        f"(does it inherit ResultMixin?)"
    )
    assert isinstance(result, Result), (
        f"{name} does not satisfy the Result protocol (needs summary + to_render)"
    )

    for dialect_name, vocab in _DIALECTS:
        view_fn = getattr(result, dialect_name, None)
        if callable(view_fn):
            view = view_fn()
            assert speaks(view, vocab), (
                f"{name}.{dialect_name}() speaks tokens outside {dialect_name}: "
                f"{set(view) - vocab}"
            )

    try:
        json.dumps(result.to_dict())
    except TypeError as e:
        raise AssertionError(f"{name}.to_dict() is not JSON-serializable: {e}")

    views = result.views()  # reads only self — no kwargs supplied
    assert isinstance(views, list) and all(isinstance(v, ChartSpec) for v in views), (
        f"{name}.views() must return list[ChartSpec]"
    )


def assert_solver_conforms(name: str, world: Any) -> None:
    """A solver is an engine citizen: it registered, declares it consumes this
    world type, is discoverable by solvers_for, and actually produces a result
    whose type it declared in `produces`."""
    registry = solver_registry()
    assert name in registry, f"solver {name!r} is not registered in solver_registry()"
    info = registry[name]

    token = type(world).__name__.lower()
    assert token in info.consumes, (
        f"{name} does not declare it consumes {token!r} (consumes={set(info.consumes)})"
    )
    assert info in solvers_for(world), (
        f"solvers_for({type(world).__name__}) does not include {name}"
    )

    result = info.fn(world)
    assert type(result).__name__ in info.produces, (
        f"{name} produced {type(result).__name__}, not in declared "
        f"produces={info.produces}"
    )


def assert_pure_stdlib(package: Any) -> None:
    """An import-guard: every module in the package imports only the standard
    library, forgecore, or itself. Pins the portability card (forgecore,
    forgevsm) and replaces the per-repo grep tests."""
    mod = importlib.import_module(package) if isinstance(package, str) else package
    pkg_name = mod.__name__.split(".")[0]
    allowed = set(sys.stdlib_module_names) | {"forgecore", pkg_name, "__future__"}
    pkg_dir = os.path.dirname(mod.__file__)

    offenders: dict[str, str] = {}
    for root, _dirs, files in os.walk(pkg_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top not in allowed:
                            offenders.setdefault(top, path)
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module:
                        top = node.module.split(".")[0]
                        if top not in allowed:
                            offenders.setdefault(top, path)

    assert not offenders, (
        f"{pkg_name} imports non-stdlib modules (breaks the portability card): "
        f"{offenders}"
    )
