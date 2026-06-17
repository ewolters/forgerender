"""The Shingo base model — process × operation, the engine's authoring layer.

Shingo's structure of production: a process (the flow of the *object* through
space and time) crosses operations (the actions of the *subject* — worker or
machine). The process is made of four phenomena, and only the first adds value:

    processing  — transformation (value-adding)
    inspection  — comparison to a standard
    transport   — change of location  (lean "motion")
    delay       — storage / waiting

An Operation is the worker/machine action that realizes a processing or
inspection step; changeover is its setup cost on a product switch.

These typed primitives are the engine's vocabulary. `ProcessModel.to_scene()`
GENERATES a forgecore.Scene from them — the way a game engine instantiates a
level from assets — which the solver modules (forgevsm, forgesim, forgequeue)
then run. Canonical units are defined HERE, once: seconds and fractions. The
Scene attrs are named as the solver adapters read them, so no layer
reinterprets a value (the scrap_rate percent-vs-fraction class of bug).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .scene import Edge, Node, Scene


class StepKind(str, Enum):
    """Shingo's four process phenomena — what happens to the product."""

    PROCESSING = "processing"
    INSPECTION = "inspection"
    TRANSPORT = "transport"
    DELAY = "delay"


# Only processing transforms the product; the rest are non-value-adding by
# Shingo's definition. The engine and layers read this, never re-decide it.
VALUE_ADDING = frozenset({StepKind.PROCESSING})

# The phenomena realized by a worker/machine action (an Operation); the others
# happen *between* operations and ride the connecting edge.
_OPERATION_KINDS = frozenset({StepKind.PROCESSING, StepKind.INSPECTION})


@dataclass
class Operation:
    """A subject (worker/machine) action realizing a process step.

    Canonical units: SECONDS and FRACTIONS (0-1). Every layer reads these as-is.
    """

    cycle_time_s: float = 0.0
    cycle_time_cv: float = 0.0  # variability; 0 = deterministic
    setup_time_s: float = 0.0  # changeover, paid on a product switch
    scrap_fraction: float = 0.0  # 0-1
    mtbf_s: float = 0.0  # mean time between failures; 0 = never fails
    mttr_s: float = 0.0  # mean time to repair
    capacity: int = 1  # parallel units at this operation
    resource: str = ""  # id of the Resource this operation consumes


@dataclass
class Step:
    """One node in the product's process flow (a Shingo phenomenon).

    Processing/inspection steps carry an Operation; transport/delay steps carry
    their own duration and happen between operations.
    """

    id: str
    name: str = ""
    kind: StepKind = StepKind.PROCESSING
    operation: Optional[Operation] = None
    transport_time_s: float = 0.0  # TRANSPORT
    distance_m: float = 0.0  # TRANSPORT
    delay_s: float = 0.0  # DELAY
    wip: int = 0  # DELAY — units waiting


@dataclass
class Product:
    """A thing that flows through the process; its type drives changeover."""

    id: str
    name: str = ""
    demand_per_day: float = 0.0


@dataclass
class Resource:
    """Finite shared capacity an operation consumes (operators, tools)."""

    id: str
    name: str = ""
    count: int = 1


@dataclass
class ProcessModel:
    """A Shingo process × operation network — the base model.

    `to_scene()` generates the forgecore.Scene that the solver modules run.
    """

    steps: list[Step] = field(default_factory=list)
    products: list[Product] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    available_s_per_day: float = 28800.0  # 8h shift
    name: str = ""

    def total_demand_per_day(self) -> float:
        return sum(p.demand_per_day for p in self.products)

    def to_scene(self) -> Scene:
        """Generate the runnable Scene: a source boundary, the operations as
        station nodes carrying canonical attrs, the transport/delay phenomena
        folded onto the connecting edges, and a sink boundary."""
        nodes: list[Node] = []
        edges: list[Edge] = []

        demand = self.total_demand_per_day()
        interarrival = self.available_s_per_day / demand if demand > 0 else 0.0
        nodes.append(Node(id="__source__", name="Customer Demand", kind="source",
                          attrs={"interarrival_time": interarrival}))

        prev_id = "__source__"
        pending: dict = {}  # transport/delay phenomena accumulating onto the next edge

        def edge_attrs(p: dict) -> dict:
            # A transport edge carries a trip-count: in a single route every unit
            # traverses it once, so trips/day == demand. Movement-waste (the motion
            # layer) is frequency x distance; without this it renders zero.
            attrs = dict(p)
            if attrs.get("distance_m", 0.0) > 0:
                attrs["frequency"] = demand
            return attrs

        for step in self.steps:
            if step.kind in _OPERATION_KINDS:
                op = step.operation or Operation()
                attrs = {
                    "step_kind": step.kind.value,
                    "cycle_time": op.cycle_time_s,
                    "cycle_time_cv": op.cycle_time_cv,
                    "changeover_time": op.setup_time_s,
                    "scrap_rate": op.scrap_fraction,
                    "mtbf": op.mtbf_s,
                    "mttr": op.mttr_s,
                    "operators": op.capacity,
                }
                nodes.append(Node(id=step.id, name=step.name or step.id,
                                  kind="station", attrs=attrs))
                edges.append(Edge(from_id=prev_id, to_id=step.id, attrs=edge_attrs(pending)))
                pending = {}
                prev_id = step.id
            elif step.kind is StepKind.TRANSPORT:
                pending["transport_time_s"] = pending.get("transport_time_s", 0.0) + step.transport_time_s
                pending["distance_m"] = pending.get("distance_m", 0.0) + step.distance_m
            elif step.kind is StepKind.DELAY:
                pending["delay_s"] = pending.get("delay_s", 0.0) + step.delay_s
                pending["wip"] = pending.get("wip", 0) + step.wip

        nodes.append(Node(id="__sink__", name="Shipping", kind="sink"))
        edges.append(Edge(from_id=prev_id, to_id="__sink__", attrs=edge_attrs(pending)))

        return Scene(nodes=nodes, edges=edges, meta={"name": self.name})
