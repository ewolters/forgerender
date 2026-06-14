"""Solver registry contract (ENGINE.md §4).

The output side of the engine (Result/result_registry) has a mirror on the
input side: solvers self-register metadata at import time so the kernel and
editors can discover what can run on a given world. Same discovery model as
results — import-time registration, caller owns completeness, collisions raise.
"""

import pytest

from forgecore import Dataset, Scene
from forgecore.solver import SolverInfo, solver, solver_registry, solvers_for


def test_decorator_registers_and_returns_the_function_unchanged():
    @solver("echo", consumes={"scene"}, produces=("EchoResult",), dialects={"flow"})
    def echo(scene):
        return scene

    # The decorated function is still callable and returns its value.
    s = Scene()
    assert echo(s) is s
    # ...and it registered.
    assert "echo" in solver_registry()


def test_solverinfo_normalizes_fields_and_infers_package():
    def cap(ds):
        return ds

    cap.__module__ = "forgespc.capability"
    solver("cap_demo", consumes={"dataset"}, produces=("ProcessCapability",),
           dialects={"capability"})(cap)

    info = solver_registry()["cap_demo"]
    assert isinstance(info, SolverInfo)
    assert info.name == "cap_demo"
    assert info.fn is cap
    assert info.consumes == frozenset({"dataset"})
    assert isinstance(info.consumes, frozenset)
    assert info.produces == ("ProcessCapability",)
    assert info.dialects == frozenset({"capability"})
    assert info.package == "forgespc"


def test_solvers_for_scene_returns_scene_consumers_only():
    @solver("scene_only", consumes={"scene"}, produces=("A",), dialects=set())
    def s_only(scene):
        return scene

    @solver("data_only", consumes={"dataset"}, produces=("B",), dialects=set())
    def d_only(ds):
        return ds

    names = {i.name for i in solvers_for(Scene())}
    assert "scene_only" in names
    assert "data_only" not in names


def test_solvers_for_dataset_returns_dataset_consumers_only():
    @solver("scene_only2", consumes={"scene"}, produces=("A",), dialects=set())
    def s_only(scene):
        return scene

    @solver("data_only2", consumes={"dataset"}, produces=("B",), dialects=set())
    def d_only(ds):
        return ds

    names = {i.name for i in solvers_for(Dataset())}
    assert "data_only2" in names
    assert "scene_only2" not in names


def test_cross_module_name_collision_raises():
    def f():
        pass

    f.__module__ = "pkg_a"
    solver("collide", consumes={"scene"}, produces=("R",), dialects=set())(f)

    def g():
        pass

    g.__module__ = "pkg_b"
    with pytest.raises(TypeError):
        solver("collide", consumes={"scene"}, produces=("R",), dialects=set())(g)


def test_same_module_redefinition_is_allowed():
    def f():
        pass

    f.__module__ = "pkg_same"
    solver("redef", consumes={"scene"}, produces=("R",), dialects=set())(f)

    def f2():
        pass

    f2.__module__ = "pkg_same"
    solver("redef", consumes={"scene"}, produces=("R",), dialects=set())(f2)
    assert solver_registry()["redef"].fn is f2


def test_solver_registry_returns_a_copy():
    @solver("copy_probe", consumes={"scene"}, produces=("R",), dialects=set())
    def f(scene):
        return scene

    reg = solver_registry()
    reg.clear()
    assert "copy_probe" in solver_registry()
