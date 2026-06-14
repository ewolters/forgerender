"""forgecore — the forge render contract (ChartSpec schema)."""

from .spec import (
    ROLE_CENTERLINE,
    ROLE_CONTROL_LIMIT,
    ROLE_DATA,
    ROLE_OUT_OF_CONTROL,
    ROLE_RUN_RULE,
    ROLE_SIGMA_ZONE,
    ROLE_SPEC_LIMIT,
    ROLES,
    SPEC_VERSION,
    Annotation,
    Axis,
    ChartSpec,
    Marker,
    ReferenceLine,
    Trace,
    Zone,
)
from .scene import Edge, Node, Scene
from .dataset import Dataset, Series
from .trace import Event, EventLog
from .dialect import (
    BEHAVIOR,
    CAPABILITY,
    FLOW,
    SPINE,
    Result,
    ResultMixin,
    result_registry,
    speaks,
)
from .solver import SolverInfo, solver, solver_registry, solvers_for
from .kernel import describe, render, run

__version__ = "0.1.0"

__all__ = [
    "Annotation",
    "Axis",
    "ChartSpec",
    "Marker",
    "ReferenceLine",
    "Trace",
    "Zone",
    "ROLES",
    "ROLE_DATA",
    "ROLE_CENTERLINE",
    "ROLE_CONTROL_LIMIT",
    "ROLE_OUT_OF_CONTROL",
    "ROLE_SPEC_LIMIT",
    "ROLE_RUN_RULE",
    "ROLE_SIGMA_ZONE",
    "SPEC_VERSION",
    "SPINE",
    "CAPABILITY",
    "FLOW",
    "BEHAVIOR",
    "Result",
    "ResultMixin",
    "result_registry",
    "speaks",
    "SolverInfo",
    "solver",
    "solver_registry",
    "solvers_for",
    "run",
    "render",
    "describe",
    "Scene",
    "Node",
    "Edge",
    "Dataset",
    "Series",
    "Event",
    "EventLog",
]
