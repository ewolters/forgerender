"""The conformance kit itself is tested here: each assertion passes a
conformant subject and fails a non-conformant one (ENGINE.md §9)."""

import types
from dataclasses import dataclass

import pytest

from forgecore import ChartSpec, Node, ResultMixin, Scene, solver
from forgecore.testing import (
    assert_pure_stdlib,
    assert_result_conforms,
    assert_solver_conforms,
)


# --- subjects ---------------------------------------------------------------

@dataclass
class _GoodResult(ResultMixin):
    summary: str = "ok"
    util: float = 0.5

    def flow(self) -> dict:
        return {"utilization": self.util}

    def to_render(self) -> ChartSpec:
        return ChartSpec(title="good")


@dataclass
class _ForeignDialectResult(ResultMixin):
    summary: str = "bad"

    def flow(self) -> dict:
        return {"not_a_flow_token": 1.0}  # outside FLOW

    def to_render(self) -> ChartSpec:
        return ChartSpec(title="bad")


@dataclass
class _UnregisteredResult:  # does NOT inherit ResultMixin
    summary: str = "orphan"

    def to_render(self) -> ChartSpec:
        return ChartSpec(title="orphan")


@solver("good_test_solver", consumes={"scene"}, produces=("_GoodResult",), dialects={"flow"})
def _good_solver(scene) -> _GoodResult:
    return _GoodResult()


@solver("liar_test_solver", consumes={"scene"}, produces=("WrongName",), dialects={"flow"})
def _liar_solver(scene) -> _GoodResult:
    return _GoodResult()


def _scene() -> Scene:
    return Scene(nodes=[Node(id="a")], edges=[])


# --- assert_result_conforms -------------------------------------------------

def test_conformant_result_passes():
    assert_result_conforms(_GoodResult())


def test_result_with_foreign_dialect_tokens_fails():
    with pytest.raises(AssertionError):
        assert_result_conforms(_ForeignDialectResult())


def test_unregistered_result_fails():
    with pytest.raises(AssertionError):
        assert_result_conforms(_UnregisteredResult())


# --- assert_solver_conforms -------------------------------------------------

def test_conformant_solver_passes():
    assert_solver_conforms("good_test_solver", _scene())


def test_solver_with_wrong_produces_fails():
    with pytest.raises(AssertionError):
        assert_solver_conforms("liar_test_solver", _scene())


def test_unregistered_solver_name_fails():
    with pytest.raises(AssertionError):
        assert_solver_conforms("no_such_solver", _scene())


# --- assert_pure_stdlib -----------------------------------------------------

def test_forgecore_itself_is_pure_stdlib():
    assert_pure_stdlib("forgecore")


def test_allows_stdlib_forgecore_and_intra_package_imports(tmp_path):
    pkg = tmp_path / "purepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "import math\nfrom forgecore import ChartSpec\nfrom . import sub\n")
    (pkg / "sub.py").write_text("import json\n")
    mod = types.ModuleType("purepkg")
    mod.__name__ = "purepkg"
    mod.__file__ = str(pkg / "__init__.py")
    assert_pure_stdlib(mod)


def test_detects_a_non_stdlib_import(tmp_path):
    pkg = tmp_path / "fakepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("import numpy\n")
    mod = types.ModuleType("fakepkg")
    mod.__name__ = "fakepkg"
    mod.__file__ = str(pkg / "__init__.py")
    with pytest.raises(AssertionError):
        assert_pure_stdlib(mod)
