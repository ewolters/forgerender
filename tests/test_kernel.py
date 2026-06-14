"""Engine kernel contract (ENGINE.md §7).

The engine's "game loop," sized honestly: discovery + routing only, no math.
The kernel looks up registered solvers, calls them, renders results via the
Result contract, and describes the full catalog for editors — without forgecore
importing a single solver or doing any computation itself.
"""

from dataclasses import dataclass

import pytest

from forgecore import ResultMixin, Scene
from forgecore.kernel import describe, render, run, solvers_for
from forgecore.solver import solver


def test_run_looks_up_and_invokes_the_registered_solver():
    @solver("k_run", consumes={"scene"}, produces=("R",), dialects=set())
    def adder(world, *, bump):
        return ("ran", world, bump)

    s = Scene()
    assert run("k_run", s, bump=3) == ("ran", s, 3)


def test_run_unknown_solver_raises():
    with pytest.raises(KeyError):
        run("does_not_exist", Scene())


def test_render_uses_views_when_present():
    @dataclass
    class KViewsResult(ResultMixin):
        summary: str = "x"

        def to_render(self):
            return "PRIMARY"

    # ResultMixin's default views() wraps to_render() into a list.
    assert render(KViewsResult()) == ["PRIMARY"]


def test_render_falls_back_to_to_render_for_protocol_only_objects():
    class BareResult:  # conforms to Result protocol but is not a ResultMixin
        summary = "x"

        def to_render(self):
            return "BARE"

    assert render(BareResult()) == ["BARE"]


def test_render_returns_empty_for_non_results():
    assert render(object()) == []


def test_describe_catalogs_solvers_results_and_dialects():
    @solver("k_desc", consumes={"dataset"}, produces=("CapResult",),
            dialects={"capability"})
    def cap(world):
        return world

    cat = describe()
    assert "k_desc" in cat["solvers"]
    entry = cat["solvers"]["k_desc"]
    assert entry["consumes"] == ["dataset"]
    assert entry["produces"] == ["CapResult"]
    assert entry["dialects"] == ["capability"]
    assert isinstance(cat["results"], list)
    assert set(cat["dialects"]) == {"spine", "capability", "flow", "behavior"}


def test_solvers_for_is_reexported_from_kernel():
    @solver("k_scene", consumes={"scene"}, produces=("R",), dialects=set())
    def s(world):
        return world

    names = {i.name for i in solvers_for(Scene())}
    assert "k_scene" in names
