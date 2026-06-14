# AGENTS.md — Build Instructions for OpenPharmaStability v0.1

> **STATUS: v0.1.0 COMPLETE.** This file is the archived build plan for v0.1.
> If you are starting fresh, read `HANDOVER.md` first, then `NEXT_STEPS.md`
> for the forward plan. This file is now read-only reference — do not edit it.
> The math in §5 and contracts in §4 remain the authoritative baseline.

> **Read this first, then read `OpenPharmaStability.md` in the same folder.**
> This file tells you (the agent taking over) exactly what to build, how to
> split the work across multiple parallel sub-agents, the precise interface
> contracts so those sub-agents never collide, the exact math, and the
> definition of done. `OpenPharmaStability.md` is the product spec / source of
> truth for behavior; this file is the execution plan. If the two ever
> disagree, the math and scope in **this** file win for v0.1.

---

## 0. Mission

Build **OpenPharmaStability v0.1**: a Python toolkit that ingests a CSV of
pharmaceutical stability data and produces a defensible, ICH Q1E-inspired
shelf-life report (HTML + a machine-readable JSON decision record) for a single
attribute under a single long-term storage condition.

This is a **one-shot build**. By the end, `pytest` passes (including a
golden-file test), and the CLI produces a rendered HTML report from a sample
dataset. Do not stop half-built. Do not invent scope beyond v0.1.

**Hard guardrail (legal/positioning):** this is a *decision-support /
educational* tool. It is NOT a regulatory-approval tool, NOT submission-ready,
NOT a validated GxP/21 CFR Part 11 system. Every report must carry the
disclaimer from the spec. Never write code or copy that claims regulatory
compliance or guaranteed correctness.

---

## 1. v0.1 Scope (build EXACTLY this — no more, no less)

**In scope:**
- CSV input only (no XLSX yet).
- One long-term condition, selected via CLI flag.
- One quantitative attribute (default `assay`, decreasing).
- Three-batch (or N-batch) **fixed-effect** Q1E ANCOVA poolability test at α = 0.25.
- Linear, raw-scale model only (no transforms).
- One-sided **95%** confidence bound on the **mean response**.
- Lower-spec crossing → rounded-down supported shelf life.
- Confidence-bound plot (points by batch, fit, CI band, spec line, crossing
  marker, extrapolation shading).
- HTML report + JSON decision record with assumptions, model choice, p-values,
  shelf-life estimate, warnings, reproducibility metadata.
- Diagnostics (linearity / variance / normality / influence) surfaced as
  warnings, not hard gates.
- Edge-case handling: no-crossing, fail-at-baseline, flat/opposite slope.

**Explicitly OUT of scope for v0.1** (leave clean extension seams, do NOT
implement): XLSX upload, multiple attributes in one run, degradant upper-limit
logic as the primary path (build the seam but default to assay/lower), full
two-sided/bidirectional path, BQL-heavy handling, transform selection,
significant-change-gated extrapolation, Arrhenius, reduced designs
(bracketing/matrixing), MKT, PDF export, web UI.

> Build the *interfaces* so these slot in later, but their bodies can raise
> `NotImplementedError` with a clear message.

---

## 2. Tech stack & environment

- Python 3.11+.
- Runtime deps: `pandas`, `numpy`, `scipy`, `statsmodels`, `matplotlib`,
  `jinja2`.
- Dev deps: `pytest`.
- No network calls at runtime. Deterministic core (no RNG in the analysis path;
  if any randomness is unavoidable, seed it and record the seed).
- Package manager: use a `pyproject.toml` (PEP 621). Installable as
  `pip install -e .` exposing console script `openpharmastability`.

Setup commands the orchestrator runs once before fan-out and once at the end:

```bash
python -m venv .venv && . .venv/bin/activate   # or platform equivalent
pip install -e ".[dev]"
pytest -q
openpharmastability analyze examples/assay_3batch.csv --condition "25C/60RH" --attribute assay --output build/report.html
```

---

## 3. Repository layout (final target)

```text
openpharmastability/
  __init__.py
  contracts.py        # ALL shared dataclasses, enums, type aliases (Wave 0)
  data/
    __init__.py
    io.py             # load_csv -> raw DataFrame
    schema.py         # validate + normalize required/optional columns
    conditions.py     # parse_condition() string normalizer
    bql.py            # BQL policy application (v0.1: minimal, flag-only)
    replicates.py     # replicate_policy application
  stats/
    __init__.py
    regression.py     # fit models, return FitResult
    poolability.py    # 3-step ANCOVA, return PoolabilityResult
    bounds.py         # mean-response CI bound + crossing solver
    diagnostics.py    # linearity/variance/normality/influence
  models/
    __init__.py
    selection.py      # choose model from poolability -> ModelChoice
  shelf_life/
    __init__.py
    engine.py         # orchestrate: data->fit->pool->select->bound->crossing->StabilityResult
    extrapolation.py  # caps + flags
  reports/
    __init__.py
    html.py           # render StabilityResult -> HTML (jinja2)
    record.py         # StabilityResult -> JSON decision record
    templates/
      report.html.j2
  plots/
    __init__.py
    confidence_plot.py
  cli.py              # argparse/console entrypoint
examples/
  assay_3batch.csv
  assay_3batch.expected.json   # hand/independently-computed golden values
validation/
  __init__.py
  test_golden.py      # asserts engine output == expected.json within tol
  test_contracts.py   # smoke tests on each module's contract
  test_edge_cases.py  # no-crossing, fail-at-baseline, flat-slope
pyproject.toml
README.md
AGENTS.md             # this file
OpenPharmaStability.md # the spec
```

---

## 4. THE CONTRACTS (Wave 0 — build these FIRST, then freeze)

These are the seams that let sub-agents work in parallel without reading each
other's code. The orchestrator writes `contracts.py` **completely** before any
fan-out, commits it, and tells every sub-agent: *import from `contracts`, do not
modify it.* If a sub-agent thinks a contract is wrong, it must STOP and report
to the orchestrator — not edit it unilaterally.

```python
# contracts.py  (authoritative shapes — fill in with real dataclasses)
from dataclasses import dataclass, field
from enum import Enum

class Direction(str, Enum):
    DECREASING = "decreasing"
    INCREASING = "increasing"
    BIDIRECTIONAL = "bidirectional"
    UNKNOWN = "unknown"

class ModelKind(str, Enum):
    POOLED = "pooled"
    COMMON_SLOPE = "common_slope_batch_intercepts"
    SEPARATE = "batch_specific"

class Poolability(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"

REQUIRED_COLUMNS = ["batch", "condition", "time_months", "attribute", "value"]
# plus at least one of: lower_spec, upper_spec
POOLABILITY_ALPHA = 0.25
CONFIDENCE = 0.95

@dataclass
class ValidatedData:
    df: "pandas.DataFrame"      # normalized, one attribute, one condition
    attribute: str
    condition: str
    direction: Direction
    lower_spec: float | None
    upper_spec: float | None
    n_batches: int
    time_points: list[float]
    warnings: list[str] = field(default_factory=list)

@dataclass
class FitResult:
    kind: ModelKind
    params: dict          # b0, b1 (and per-batch where relevant)
    df_resid: int
    s_resid: float        # residual standard error
    cov: "numpy.ndarray"  # parameter covariance (s^2 * (X'X)^-1)
    fitted_fn: object     # callable batch->(t->yhat) OR t->yhat for pooled
    design: dict          # tbar, Sxx, n, per-batch where needed

@dataclass
class PoolabilityResult:
    decision: Poolability
    p_slopes: float
    p_intercepts: float | None
    alpha: float

@dataclass
class CrossingResult:
    crossing_months: float | None   # None if no crossing in horizon
    status: str                     # "crossed" | "no_crossing" | "fail_at_baseline" | "flat_or_opposite"
    governing_batch: str | None

@dataclass
class DiagnosticsResult:
    linearity_ok: bool
    homoscedastic_ok: bool
    normal_resid_ok: bool
    influential_points: list[int]
    notes: list[str] = field(default_factory=list)

@dataclass
class StabilityResult:
    attribute: str
    condition: str
    direction: Direction
    model: ModelKind
    poolability: PoolabilityResult
    fit: FitResult
    crossing: CrossingResult
    supported_shelf_life_months: int | None
    statistical_crossing_months: float | None
    observed_data_months: float
    extrapolation_flag: bool
    diagnostics: DiagnosticsResult
    warnings: list[str]
    metadata: dict          # file hash, lib versions, timestamp, tool version
```

**Function signatures every sub-agent must honor:**

```python
# data
def load_csv(path: str) -> "pandas.DataFrame"
def validate_and_select(df, attribute: str, condition: str,
                        replicate_policy: str = "individual") -> ValidatedData
def parse_condition(raw: str) -> str          # "25°C/60%RH" -> "25C/60RH"

# stats
def fit_models(data: ValidatedData) -> dict[ModelKind, FitResult]
def test_poolability(fits: dict[ModelKind, FitResult],
                     data: ValidatedData) -> PoolabilityResult
def confidence_bound(fit: FitResult, t: float, side: str, conf: float = CONFIDENCE) -> float
def find_crossing(fit: FitResult, data: ValidatedData, horizon: float) -> CrossingResult
def run_diagnostics(fit: FitResult, data: ValidatedData) -> DiagnosticsResult

# models
def select_model(pool: PoolabilityResult, fits: dict) -> tuple[ModelKind, FitResult]

# shelf_life
def analyze(path: str, condition: str, attribute: str = "assay",
            product_type: str = "product") -> StabilityResult

# reports / plots
def render_html(result: StabilityResult, plot_png_path: str, out_path: str) -> None
def to_decision_record(result: StabilityResult) -> dict           # JSON-serializable
def make_confidence_plot(result: StabilityResult, data: ValidatedData,
                         out_path: str) -> None
```

---

## 5. THE MATH (implement exactly — this is the validation target)

For a fitted linear model `value = b0 + b1 * time`:

```text
yhat(t)    = b0 + b1 * t
SE_mean(t) = s * sqrt( 1/n + (t - tbar)^2 / Sxx )
  s    = sqrt( SSE / df ),  df = n - p  (p = # estimated params in chosen model)
  n    = observations used in the fit
  tbar = mean of time values
  Sxx  = sum( (time_i - tbar)^2 )
```

One-sided 95% bounds — **use the 0.95 t-quantile (5% in ONE tail). NOT 0.975.**
This is the single most common bug; get it right and assert it in a test.

```text
Lower L(t) = yhat(t) - t_(0.95, df) * SE_mean(t)
Upper U(t) = yhat(t) + t_(0.95, df) * SE_mean(t)
```

Two-sided / unknown direction (NOT in v0.1, but document): use 0.975.

**Crossing** (decreasing attribute, lower spec): smallest `t > 0` with
`L(t) = lower_spec`. The bound is curved (SE grows away from `tbar`), so solve
numerically with bisection/Brent over `[0, horizon]`. Do not invert a straight
line.

**For multi-batch models** (common-slope or separate): evaluate each batch's
own curve, take the **earliest (worst-case)** crossing; record `governing_batch`.
Standard errors must come from the chosen model's covariance matrix
`s^2 * (X'X)^-1`, so `df`/`Sxx` reflect the real design — not a single-batch
shortcut.

**Poolability (3-step nested ANCOVA, α = 0.25):**
1. Test `time:batch` interaction (slopes). If p < 0.25 → SEPARATE, stop.
2. Else refit `value ~ time + batch`, test `batch` (intercepts). If p < 0.25 →
   COMMON_SLOPE.
3. Else → POOLED.
Each test uses the pooled MSE from the relevant nested model.

**Shelf-life constraints:** round DOWN to whole month; may not exceed observed
data length unless extrapolation is flagged; RT extrapolation cap ≈ 2× and
≤ 12 months beyond long-term data — hard-flag beyond it.

**Edge cases the solver must return (not crash):**
- No crossing within horizon → `status="no_crossing"`, shelf life =
  "≥ horizon, not limiting in evaluated range".
- `L(0)` already past spec → `status="fail_at_baseline"`, shelf life = 0 + warn.
- Slope ≈ 0 or opposite to declared direction → `status="flat_or_opposite"`,
  no positive crossing claimed + warn.

---

## 6. PARALLEL EXECUTION PLAN (use max agents)

Spawn sub-agents in **waves**. Within a wave, run them **concurrently**. Each
sub-agent owns a disjoint set of files (listed below) so there are zero write
conflicts. Every sub-agent: (a) imports only from `contracts.py`, (b) writes its
own files + its own unit tests, (c) must leave `pytest` green for its module
against stub inputs, (d) reports back a one-line status.

### Wave 0 — Foundation (orchestrator, SERIAL, do alone)
Owns: `pyproject.toml`, `openpharmastability/__init__.py`, `contracts.py`,
empty package `__init__.py` files, `README.md` skeleton.
Deliverable: installable skeleton, frozen contracts, `pytest` collects 0 real
tests but runs clean. **Do not fan out until this is committed.**

### Wave 1 — Build modules (PARALLEL — spawn all at once)

| Agent | Owns (files) | Builds | Depends on |
|---|---|---|---|
| **A — Data** | `data/io.py`, `data/schema.py`, `data/conditions.py`, `data/bql.py`, `data/replicates.py` + their tests | CSV load, validation/normalization, condition parser, replicate policy, minimal BQL flag pass-through | contracts |
| **B — Stats core** | `stats/regression.py`, `stats/poolability.py`, `stats/bounds.py` + tests | model fits via statsmodels, 3-step ANCOVA, mean-response bound + crossing solver (the §5 math) | contracts |
| **C — Diagnostics** | `stats/diagnostics.py` + tests | linearity/variance/normality/influence per spec §"Assumptions and Diagnostics" | contracts |
| **D — Plot** | `plots/confidence_plot.py` + test | matplotlib plot per spec, saves PNG | contracts |
| **E — Reporting** | `reports/html.py`, `reports/record.py`, `reports/templates/report.html.j2` + tests | HTML via jinja2 + JSON decision record, against a hand-built `StabilityResult` fixture | contracts |
| **F — Fixtures/Golden** | `examples/assay_3batch.csv`, `examples/assay_3batch.expected.json`, `validation/test_golden.py`, `validation/test_edge_cases.py` | realistic 3-batch assay dataset; compute expected slope/intercept/SE/bound/crossing/shelf-life **independently** (plain numpy + scipy.stats.t, separate from Agent B's code) and freeze them; write golden + edge tests | contracts, §5 math |

> Agents E and F build against the `StabilityResult` contract using their own
> hand-made fixtures, so they do NOT need B finished. That's the point of Wave 0.

### Wave 2 — Integration (orchestrator + 1 helper, after Wave 1 joins)
Owns: `models/selection.py`, `shelf_life/engine.py`, `shelf_life/extrapolation.py`,
`cli.py`. Wire data → fit → poolability → select → bound → crossing →
extrapolation → `StabilityResult` → report + plot. Then run the FULL suite and
the CLI end-to-end. Fix any contract mismatches **by adjusting module internals,
never by loosening the golden test**.

### Coordination rules (state explicitly to every sub-agent)
- One agent = one file set. Never edit another agent's files.
- `contracts.py` is read-only after Wave 0; propose changes via the orchestrator.
- Each module ships with its own `pytest` tests and a stub/fixture so it's
  independently runnable.
- Status report format: `AGENT <X>: done | files: [...] | tests: N passed | notes: ...`.
- If blocked > one attempt on a contract ambiguity, STOP and surface it; do not
  guess and diverge.

---

## 7. Reproducibility metadata (Agent E + engine)

Every report and JSON record embeds: input file **SHA-256**, row/column counts,
library versions (`pandas numpy scipy statsmodels`), tool version, random seed
if any, and an **ISO-8601** timestamp. The HTML must contain the spec's
disclaimer verbatim and state product_type → retest period (substance) vs shelf
life (product), defaulting to shelf life + warning if unspecified.

---

## 8. DEFINITION OF DONE (the baseline — all must hold)

1. `pip install -e ".[dev]"` succeeds; console script `openpharmastability` exists.
2. `pytest -q` is green, including:
   - **Golden test**: `analyze(examples/assay_3batch.csv, ...)` reproduces the
     frozen slope, intercept, residual SE, one-sided 95% bound, statistical
     crossing time, and rounded shelf life in `assay_3batch.expected.json`
     within tight tolerance (e.g. `rtol=1e-6` for fit stats, exact for rounded
     months).
   - **Cross-check test**: Agent F's independent numpy/scipy computation agrees
     with Agent B's `bounds.py` output (guards the t-quantile bug).
   - **Edge-case tests**: no-crossing, fail-at-baseline, flat/opposite slope
     return the specified statuses, not exceptions.
3. CLI produces `build/report.html` with the plot, model choice, p-values,
   shelf-life estimate, warnings, disclaimer, and reproducibility metadata.
4. Determinism: running the CLI twice yields identical numbers.
5. Out-of-scope features either absent or raising clear `NotImplementedError`.
6. No claim of regulatory compliance anywhere in code, output, or README.

When all six hold, **stop**: that is v0.1 baseline. Report the supported
shelf-life number and the path to the rendered report.

---

## 9. Suggested commit checkpoints

`chore: scaffold + contracts` → `feat: data layer` / `feat: stats core` /
`feat: diagnostics` / `feat: plot` / `feat: reporting` / `test: golden fixtures`
(Wave 1, parallel) → `feat: engine + cli integration` → `test: full suite green`
→ `docs: README usage`.

---

## 10. Quick reference — one-shot order for the orchestrator

1. Read `OpenPharmaStability.md` fully.
2. Wave 0: scaffold repo, write & freeze `contracts.py`, confirm clean install.
3. Spawn Wave 1 agents A–F **in parallel**, each on its own file set.
4. Join; resolve any reported contract issues centrally.
5. Wave 2: build `selection`, `engine`, `extrapolation`, `cli`; integrate.
6. Run full `pytest` + CLI end-to-end; fix internals until DoD §8 passes.
7. Report shelf-life result + report path. Done.
