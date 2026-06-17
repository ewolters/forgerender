"""The Shingo base model: a process is a network of process-phenomena
(processing / inspection / transport / delay) crossed with operations
(the worker/machine actions). These typed primitives are the engine's
authoring vocabulary; the engine GENERATES a Scene from them, which the
solver modules then run. Canonical units live here (seconds, fractions),
so no downstream layer reinterprets them.
"""

import json

from forgecore import Operation, ProcessModel, Product, Scene, Step, StepKind


def _line() -> ProcessModel:
    return ProcessModel(
        name="Line A",
        steps=[
            Step(id="cnc", name="CNC Turn", kind=StepKind.PROCESSING,
                 operation=Operation(cycle_time_s=60, cycle_time_cv=0.2,
                                     setup_time_s=45, mtbf_s=3600, mttr_s=400)),
            Step(id="move1", kind=StepKind.TRANSPORT, transport_time_s=30, distance_m=12),
            Step(id="weld", name="Weld", kind=StepKind.PROCESSING,
                 operation=Operation(cycle_time_s=95, scrap_fraction=0.02)),
            Step(id="wait1", kind=StepKind.DELAY, delay_s=600, wip=5),
            Step(id="insp", name="Inspect", kind=StepKind.INSPECTION,
                 operation=Operation(cycle_time_s=50)),
        ],
        products=[Product(id="widget", name="Widget", demand_per_day=222)],
    )


def test_processing_and_inspection_steps_become_stations():
    scene = _line().to_scene()
    stations = [n for n in scene.nodes if n.kind == "station"]
    assert [n.id for n in stations] == ["cnc", "weld", "insp"]


def test_scene_has_source_and_sink_boundaries():
    scene = _line().to_scene()
    kinds = [n.kind for n in scene.nodes]
    assert kinds[0] == "source"
    assert kinds[-1] == "sink"


def test_canonical_operation_fields_map_to_scene_attrs():
    scene = _line().to_scene()
    cnc = scene.node("cnc")
    # canonical units: seconds + fractions, named as the solvers read them
    assert cnc.attrs["cycle_time"] == 60
    assert cnc.attrs["cycle_time_cv"] == 0.2
    assert cnc.attrs["changeover_time"] == 45     # setup_time_s, seconds
    assert cnc.attrs["mtbf"] == 3600
    assert cnc.attrs["mttr"] == 400
    assert scene.node("weld").attrs["scrap_rate"] == 0.02  # fraction, not percent


def test_inspection_is_a_step_kind_not_a_separate_primitive():
    scene = _line().to_scene()
    assert scene.node("insp").attrs["step_kind"] == "inspection"


def test_transport_step_becomes_edge_attr_between_operations():
    scene = _line().to_scene()
    # the edge cnc -> weld carries the transport phenomenon
    edge = next(e for e in scene.edges if e.from_id == "cnc" and e.to_id == "weld")
    assert edge.attrs["transport_time_s"] == 30
    assert edge.attrs["distance_m"] == 12


def test_delay_step_becomes_edge_attr_between_operations():
    scene = _line().to_scene()
    edge = next(e for e in scene.edges if e.from_id == "weld" and e.to_id == "insp")
    assert edge.attrs["delay_s"] == 600


def test_transport_edge_carries_trip_count_from_demand():
    scene = _line().to_scene()
    # every unit traverses every edge once, so trips/day == total demand
    edge = next(e for e in scene.edges if e.from_id == "cnc" and e.to_id == "weld")
    assert edge.attrs["frequency"] == 222


def test_non_transport_edge_has_no_trip_count():
    scene = _line().to_scene()
    # weld -> insp carries delay, not transport: no motion, so no trip-count
    edge = next(e for e in scene.edges if e.from_id == "weld" and e.to_id == "insp")
    assert "frequency" not in edge.attrs


def test_demand_sets_source_interarrival_time():
    scene = _line().to_scene()
    src = next(n for n in scene.nodes if n.kind == "source")
    # 28800 s/day / 222 parts/day
    assert abs(src.attrs["interarrival_time"] - 28800 / 222) < 0.01


def test_to_scene_returns_a_serializable_forgecore_scene():
    scene = _line().to_scene()
    assert isinstance(scene, Scene)
    json.dumps(scene.to_dict())  # round-trips through JSON


# --- multi-product routing --------------------------------------------------

def _network() -> ProcessModel:
    # Two products share the cut->weld leg; only B continues to paint.
    return ProcessModel(
        name="Two-Product Cell",
        steps=[
            Step(id="cut", kind=StepKind.PROCESSING, operation=Operation(cycle_time_s=40)),
            Step(id="t1", kind=StepKind.TRANSPORT, distance_m=10, transport_time_s=15),
            Step(id="weld", kind=StepKind.PROCESSING, operation=Operation(cycle_time_s=90)),
            Step(id="t2", kind=StepKind.TRANSPORT, distance_m=5, transport_time_s=8),
            Step(id="paint", kind=StepKind.PROCESSING, operation=Operation(cycle_time_s=60)),
        ],
        products=[
            Product(id="A", demand_per_day=100, route=["cut", "t1", "weld"]),
            Product(id="B", demand_per_day=60, route=["cut", "t1", "weld", "t2", "paint"]),
        ],
    )


def test_stations_are_a_shared_pool_across_products():
    scene = _network().to_scene()
    stations = [n.id for n in scene.nodes if n.kind == "station"]
    assert stations == ["cut", "weld", "paint"]  # each emitted once


def test_shared_edge_sums_trip_count_across_products():
    scene = _network().to_scene()
    # both A (100) and B (60) traverse cut -> weld
    edge = next(e for e in scene.edges if e.from_id == "cut" and e.to_id == "weld")
    assert edge.attrs["frequency"] == 160
    assert edge.attrs["distance_m"] == 10  # physical distance, not summed


def test_divergent_edge_carries_only_its_products_trips():
    scene = _network().to_scene()
    # only B (60) continues weld -> paint
    edge = next(e for e in scene.edges if e.from_id == "weld" and e.to_id == "paint")
    assert edge.attrs["frequency"] == 60


def test_empty_route_visits_all_steps_in_order():
    # a product with no explicit route falls back to the declared step order
    model = ProcessModel(
        steps=[
            Step(id="cut", kind=StepKind.PROCESSING, operation=Operation(cycle_time_s=40)),
            Step(id="t1", kind=StepKind.TRANSPORT, distance_m=7),
            Step(id="weld", kind=StepKind.PROCESSING, operation=Operation(cycle_time_s=90)),
        ],
        products=[Product(id="A", demand_per_day=50)],
    )
    scene = model.to_scene()
    edge = next(e for e in scene.edges if e.from_id == "cut" and e.to_id == "weld")
    assert edge.attrs["frequency"] == 50
