# The Forge Engine Specification (v1)

**Status:** APPROVED — drafted 2026-06-11, arbitrated 2026-06-13. This is the
source-of-truth spec, shipped with the forgecore contract package. Draft
history lives at `~/agent_dev/forge-sim-engine/specs/2026-06-11-engine-spec.md`.

**Engine core COMPLETE (2026-06-13):** all six contracts (§2–§6) plus the
kernel (§7) are shipped in forgecore. What remains is *adoption*, not contract:
decorating the real solver entry points (§4 rollout), the conformance kit (§9),
the Ring-2 bridge ports, and the first EventLog consumer.

---

## 1. What the engine is

A composable statistical simulation engine for process improvement. Forge packages
are interchangeable **solvers**; renderers (forgeviz today, JS later) are
interchangeable **views**; one zero-dependency contract package (**forgecore**)
defines every seam. Products (SVEND, Verxted surfaces, consulting tooling) are
built *on* the engine, never *into* it.

### The Unreal mapping (what we're actually copying)

Unreal's architecture, distilled to the five ideas that transfer:

| Unreal | What it does | Forge equivalent | Status |
|---|---|---|---|
| **Core module** | Zero-dep base everything links against; strict one-way dependency layers | forgecore (428 LOC, pure stdlib) | EXISTS |
| **UObject reflection + class registry** | Every class self-registers metadata at startup; editor, serialization, GC all read the registry | `ResultMixin.__init_subclass__` → `result_registry()` | EXISTS (results only — solvers missing) |
| **World / Actors** | The typed scene graph all subsystems read | `Scene` / `Node` / `Edge` | EXISTS |
| **Subsystems** | Self-registering services discovered by the registry, driven by a thin engine loop | `solver` decorator → `solver_registry()` / `solvers_for()` + `kernel.run/render/describe` | EXISTS (registry + kernel shipped 2026-06-13; entry-point rollout pending) |
| **RHI (Render Hardware Interface)** | Neutral command stream; per-backend renderers consume it | `ChartSpec` (+ roles, spec_version) | EXISTS |
| **Unreal Insights / Trace** | Channelized event stream recorded during the run; replay, profiling, analysis built on it | `EventLog` / `Event` (was "Trace") | EXISTS (DES witness; first consumer pending) |

The deepest lesson from Unreal: **the engine's centralization is in discovery,
lifecycle, and routing — never in computation.** UEngine::Tick is small; the work
lives in registered subsystems. Our kernel (§7) follows that: registries plus a
dispatch surface, ~100 LOC, zero math. This preserves the locked decision
"thin contract, NOT a new monolith."

### Dependency law (already enforced, now named)

```
products (SVEND, Verxted, ...)        — may import anything below
renderers (forgeviz, JS)              — import forgecore only
solvers (forgespc, forgesim, forgequeue,
         forgevsm, forgepeople, forgestat) — import forgecore only; NEVER a sibling
forgecore                             — imports NOTHING (pure stdlib)
```

Grep/import-guard tests enforce the bottom two layers (forgesim precedent;
extend to all solvers — see §9 conformance kit).

---

## 2. The six contracts

Two are inputs, one is the run record, two are outputs, one is the actor table:

```
Scene ──┐                       ┌─→ views() → [ChartSpec] → renderer
        ├─→ Solver ─→ (Trace) ─→ Result ─┤
Dataset ┘   (registered)        └─→ dialect() → tokens (SPINE/CAPABILITY/FLOW/BEHAVIOR)
```

| # | Contract | Role | Status |
|---|---|---|---|
| 1 | Scene | world input (graph-shaped solvers) | SHIPPED — pin as-is |
| 2 | Dataset | measurement input (data-shaped solvers) | SHIPPED 2026-06-11 |
| 3 | Solver | registered, self-describing computation | SHIPPED 2026-06-13 (registry; entry-point rollout pending) |
| 4 | EventLog | the run's event record | SHIPPED 2026-06-12 (was "Trace"; renamed on collision) |
| 5 | Result | typed outcome: views + dialect tokens + wire dict | SHIPPED — views() landed 2026-06-11 |
| 6 | ChartSpec | neutral render command stream | SHIPPED — pin as-is |

Everything below is **additive**. No existing adopter changes; no test breaks.

---

## 3. Dataset — the second input species (SHIPPED 2026-06-11)

**Problem (witnessed):** Half the solvers are not graph-shaped. forgespc entry
points are `cusum_chart(data, target, sigma, ...)`, `gage_rr_crossed(measurements,
parts, operators)`, `bayesian_capability(data, usl, lsl)` — raw arrays + params.
Today that data arrives as ad-hoc kwargs and never reaches the result, which is
the root cause of the blocked Ring-2 data-context families ("forgestat results
don't carry data" is a symptom, not the disease).

**Contract (forgecore/dataset.py, harvested minimal):**

```python
@dataclass
class Series:
    name: str
    values: list[float]
    unit: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)   # subgroup ids, censoring flags, timestamps

@dataclass
class Dataset:
    series: list[Series] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)    # usl/lsl/target, sampling context

    def get(self, name: str) -> Optional[Series]: ...
    def to_dict(self) -> dict:  # stamps spec_version, like Scene
```

Mirrors Scene exactly: generic core fields, solver-specific tokens in
`attrs`/`meta`, `spec_version` on the wire, JSON-serializable, stdlib-only.

**Adoption pattern (mirrors `from_scene`):** module-level `*_from_dataset()`
adapters — `cusum_from_dataset(ds)`, `capability_from_dataset(ds)`. Existing
signatures stay; the adapter extracts and calls. "Dataset in, untouched solver
runs" — same locked principle as Scene.

**Witnesses to build against:** forgespc (capability/CUSUM), forgestat
(t-test/correlation — doubles as its contract adoption), forgepeople
(`Scenario` may stay its typed input the way `PlantLayout` does for Scene;
`scenario_from_dataset` optional).

---

## 4. Solver — the registered subsystem (registry SHIPPED 2026-06-13; rollout pending)

**Problem (witnessed):** forgecore has a first-class *output* side
(`Result`, `result_registry()`) and **no solver side at all**. Every product
hand-wires calls: SVEND's `router.py: dispatch(analysis_type, analysis_id, df,
config)` is a string-keyed, hand-maintained solver registry living in the wrong
layer. The `overhead()` caller manually extracts layer maps. The editor story
("which solvers can run on this Scene?") has nothing to ask.

**Contract (forgecore/solver.py):**

```python
@dataclass(frozen=True)
class SolverInfo:
    name: str                      # "des", "cusum", "jackson_network", ...
    fn: Callable                   # the existing module-level function, unwrapped
    consumes: frozenset[str]       # {"scene"} | {"dataset"} | both
    produces: tuple[str, ...]      # result class names ("VSMResult", ...)
    dialects: frozenset[str]       # {"flow"}, {"capability"}, {"behavior"}
    package: str                   # "forgesim", for provenance/UI grouping

def solver(name, *, consumes, produces, dialects):   # registration decorator
    ...

def solver_registry() -> dict[str, SolverInfo]: ...
def solvers_for(world) -> list[SolverInfo]:          # match on type(world)
```

Same discovery model as results: **import-time registration, caller owns
registry completeness** (locked decision — no entry-point machinery, YAGNI).
The decorator wraps *existing module-level functions without modifying them*:

```python
# forgevsm/scene.py — the only change is the decorator line
@solver("vsm", consumes={"scene"}, produces=("VSMResult",), dialects={"flow"})
def vsm_from_scene(scene) -> list[ProcessStep]: ...
```

Registration metadata is declarative; forgecore never imports a solver.

---

## 5. Result — completing the existing contract

Two known open questions are both "the Result protocol is underspecified."
Settle them here, once.

### 5a. Multi-view: `views()`

**Problem (witnessed):** `_charts_from_control_chart` renders an I+MR **pair**
via `from_spc_result_pair`; `to_render() -> ChartSpec` is single-by-contract.
The richest result in the fleet can't leave the bridge.

**Decision:** add `views() -> list[ChartSpec]` to ResultMixin with default
`[self.to_render()]`. `to_render()` keeps its meaning: *the* primary
self-portrait. Results with richer composition override `views()`
(ControlChartResult → I + MR). The bridge contract fallback calls `views()`.
Renderers accept lists already (`charts_from_result` returns a list).

Wire impact: none (`to_dict()` unchanged) → SPEC_VERSION stays "1".

### 5b. Data-carrying policy

**Problem (witnessed):** `_charts_from_capability` composes a histogram from
`data=` kwargs the result never sees; same for distributions, correlation,
Weibull, KM, ML-cluster.

**Decision:** a Result **owns every field its views need** — that is the
definition of a complete result, not an option. Concretely:
- Results MAY declare data fields (`data: list[float] | None = None`);
  solvers populate them when the input is available.
- `views()` may only read `self`. If a portrait needs data the result lacks,
  the *result type* is incomplete — fix the dataclass, not the bridge.
- Dialect views (`capability()`, `flow()`, ...) remain summary-token-only;
  raw data never enters dialect dicts.
- `to_dict()` includes data fields when present (it's `asdict`; large payloads
  are the caller's serialization concern, same as today).

This is the forgestat adoption decision, made deliberately as spec policy:
when forgestat results adopt ResultMixin they gain the fields their portraits
need, fed by Dataset (§3).

---

## 6. EventLog — the run record (SHIPPED 2026-06-12)

> **Naming resolved by collision:** the contract is `EventLog`, not `Trace` —
> `forgecore.Trace` was already the ChartSpec series type (Pyright caught the
> clash before the first test ran). Same rule as the registry: rename, don't
> suppress. Everywhere this spec says "Trace seam," read EventLog.

**Witness:** `forgesim/des.py` already runs on
`_Event(time, seq, evt_type, station_id, job)` in a heapq, with event kinds
(`arrival`, `end_process`, `changeover_end`, `breakdown`, ...) and
`_update_state()` state transitions. The contract is the *recorded* mirror of
that internal queue — exactly how Unreal Insights mirrors the frame loop.

**Contract (forgecore/trace.py):**

```python
@dataclass
class Event:
    t: float                 # simulation time
    kind: str                # "arrival", "start_process", "breakdown", "state_change", ...
    subject: str = ""        # node id / job id / actor id
    attrs: dict[str, Any] = field(default_factory=dict)

@dataclass
class EventLog:
    events: list[Event] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)   # seed, run_time, warmup, scene ref
    def add(self, t, kind, subject="", **attrs): ...      # emitter convenience
    def for_subject(self, subject) -> list[Event]: ...    # every event about one actor
    def to_dict(self) -> dict:  # stamps spec_version
```

Solvers that simulate over time MAY emit an EventLog (`run_des(layout,
record_trace=True) -> result` with `result.trace`); analytic solvers
(queueing formulas, capability) never will — the log is optional by design,
like `position` on Node. Animation, replay, what-if scrubbing, and
digital-twin products consume the EventLog; they never reach into solver
internals. The log rides `result.trace` as a plain attribute, OUTSIDE the
`to_dict()` wire payload.

Sequencing unchanged from the 2026-06-09 decision: **shape is spec'd now so
Ring-2 work can't drift past it; implementation lands after Ring-2.**

---

## 7. Kernel — centralized routing (SHIPPED 2026-06-13)

The engine's "game loop," sized honestly: discovery + routing only, no math.

```python
# forgecore/kernel.py  (~100 LOC, stdlib only)
def solvers_for(world: Scene | Dataset) -> list[SolverInfo]
def run(solver_name: str, world, **params) -> Any        # looks up, calls fn
def render(result) -> list[ChartSpec]                     # views() if Result, else []
def describe() -> dict                                    # full catalog: solvers + results + dialects, for editors
```

What this buys, concretely:
- **SVEND canvas:** user draws a Scene → `solvers_for(scene)` lists VSM /
  Jackson / DES / transport as runnable layers → `run()` → `render()`. The
  editor story becomes three kernel calls.
- **`svend/analysis/router.py` shrinks by attrition** exactly like the bridge:
  its string-keyed dispatch migrates to `kernel.run()` family-by-family as
  solvers register. Handlers keep doing what recon proved they do (input prep,
  forgenarr stats) — routing stops being their job.
- **New products** (Verxted surfaces, consulting scripts, WASM builds) get the
  whole catalog from `describe()` with zero per-product wiring.

forgecore still imports nothing: registries fill when the caller imports solver
packages (the locked completeness rule). A convenience meta-package
(`forge-engine` that just imports all public solvers) can come later; not v1.

---

## 8. Versioning

- `SPEC_VERSION` ("1") covers the **wire shapes**: ChartSpec, Scene, Dataset,
  EventLog `to_dict()`. Bump on any serialized-shape change; additive Python API
  (views, registries) does not bump it.
- forgecore package version signals API additions (0.2.0 = Dataset + views +
  EventLog, shipped; Solver registry + kernel land next).

---

## 9. Conformance kit — `forgecore.testing`

Adoption becomes a checkbox, not artisanal test-writing. One module, importable
by every solver repo's test suite:

```python
from forgecore.testing import (
    assert_result_conforms,    # registers cleanly; speaks() its declared dialects;
                               # to_dict round-trips through json; views() -> [ChartSpec];
                               # views() reads only self (no kwargs)
    assert_solver_conforms,    # registered; consumes/produces accurate (run a sample world,
                               # check result type names match `produces`)
    assert_pure_stdlib,        # import-guard: package imports nothing outside stdlib
                               # + forgecore (replaces per-repo grep tests; pins the
                               # portability card for forgecore/forgevsm)
)
```

Kills the duplicated drift-guard tests across six repos and makes "is X an
engine citizen?" a one-line assertion. This is the UObject-reflection payoff:
because everything registers, everything is checkable.

---

## 10. Build order (each step ships green and alone)

1. **`views()` on ResultMixin** + ControlChartResult override (I+MR pair) +
   bridge fallback upgraded to `views()`. *Unblocks the biggest Ring-2 family;
   smallest diff.* ✓ SHIPPED 2026-06-11
2. **Dataset** + first `from_dataset` witnesses (forgespc capability + CUSUM).
   ✓ SHIPPED 2026-06-11
3. **Data-carrying retrofit** of capability/distribution result types per §5b;
   delete their bridge builders. *(Ring-2 attrition continues underneath, now
   spec-governed.)* — in progress (capability done)
4. **Solver registry** + decorate the ~10 public entry points across 5 repos.
   ✓ registry contract SHIPPED 2026-06-13 (`forgecore/solver.py`); decorating
   the entry points across the solver repos is the remaining rollout.
5. **Kernel** + `describe()`; SVEND canvas + router migration become possible.
   ✓ SHIPPED 2026-06-13 (`forgecore/kernel.py`: run / render / describe /
   solvers_for). SVEND canvas routing + router.py attrition now unblocked.
6. **Conformance kit**; swap per-repo drift-guards for it.
7. **EventLog consumer** (post-Ring-2, per standing decision): the EventLog
   contract + DES witness shipped 2026-06-12; first consumer = animation layer
   or `wip_over_time(log)` view.
8. forgestat adoption (ResultMixin + Dataset + data fields) — closes the last
   blocked Ring-2 families.

Steps 1–3 are this workstream's current Ring-2 thread, re-grounded in the spec.
Steps 4–5 are the "centralized routing" ask. Nothing existing is rewritten at
any step.

---

## Arbitrated decisions (resolved 2026-06-13)

All three draft open points were settled by the slices that shipped between
2026-06-11 and 2026-06-12; arbitration confirmed the proposals as-built.

1. **Naming → `Dataset/Series`.** Chosen and shipped (forgecore `0e823a4`).
   Plain, matches consulting vocabulary; PCL "measures with meaning" layers on
   top rather than being baked in now.
2. **`to_render()` survives — keep both.** Shipped: `to_render()` = the
   primary portrait (single-chart consumers); `views()` = the complete
   portrait (forgecore `aaca3f3`). No deprecation.
3. **EventLog `kind` is free-form for v1.** Shipped (forgecore `32c94ae`);
   `kind` mirrors `Node.kind`. Promote to a frozenset dialect once 2+ solvers
   emit logs — the same harvest discipline that produced subset-semantics.
   (The contract was also renamed `Trace` → `EventLog` on a name collision
   with the ChartSpec series type; see §6.)
