# OpenPharmaStability — NEXT_STEPS.md

> **STATUS: v0.5.1 SHIPPED (audit patch).** v0.5.0 shipped the
> advanced-statistics layer — Arrhenius, MKT, reduced-design
> detection, and the opt-in random-effects mixed model. v0.5.1
> closed the v0.5.0 audit: Arrhenius hook now attribute-filtered
> and direction-aware, mixed-model convergence / boundary status
> surfaced at the top level, MKT-without-temp_c now warns
> explicitly. The previous v0.3.0 SHIPPED banner is now a
> footnote in the audit trail. Read `HANDOVER.md` and
> `CHANGELOG.md` first.
>
> §§1–5 are now historical (all shipped). **§6 (Export + UI) is
> the next focus** for v0.6.0 — PDF export plus a Cloudflare Pages
> frontend that calls the existing Python engine. The stats engine
> stays in Python; the UI is a thin client.

**Comprehensive expansion plan: v0.1.0 → v0.5.1 (shipped) → v0.6.0+ (next)**

> **Audience:** the next engineer/agent, starting cold. You have never seen
> the conversation that produced this file. Read **§7 (pycache / env
> integrity)** and **§8 (agent handover protocol)** FIRST, in that order,
> before you touch any code. §6 is the v0.6.0 hot list. §§1–5 are
> historical (shipped — kept as design notes / reference). §10 is the
> ongoing regulatory watch + versioning strategy.

> **Source-of-truth precedence:** `OpenPharmaStability.md` (product
> behavior spec) > `AGENTS.md` (v0.1 execution plan) > this file (forward
> plan). For any NEW feature the math/scope in *this* file governs.
> `contracts.py` is the frozen API seam — see the rules in §8.7 before
> editing it.

> **Repo root referenced throughout:** `E:\STABILITY TOOLKIT` (Windows) /
> the mounted equivalent on Linux. All paths below are relative to that
> root unless absolute.

---

## Table of contents

| § | Title | Ships as |
|---|-------|----------|
| 1 | **IMMEDIATE FIXES (v0.1.1 patch)** | v0.1.1 |
| 2 | Multi-attribute + XLSX | v0.2.0 |
| 3 | Data quality + transforms | v0.3.0 |
| 4 | Regulatory decision tree (ICH Q1A) | v0.4.0 |
| 5 | Advanced statistics | v0.5.0 |
| 6 | Export + UI | v0.6.0 |
| 7 | **PYCACHE / ENV INTEGRITY FIX (pre-work, READ FIRST)** | pre-work |
| 8 | **AGENT HANDOVER PROTOCOL (pre-work, READ FIRST)** | pre-work |
| 9 | Test coverage gaps to fill now | v0.1.1 |
| 10 | Regulatory watch + versioning strategy | ongoing |
| A | Cross-cutting hazards (memorize) | — |
| B | Release checklist (per minor/major) | — |

> **Pre-work reading order for a fresh agent** (sections are numbered
> §1–§10, but the *execution* order on a fresh checkout at v0.5.1 is):
> **§7 → §8 → §6 → §10.** Sections 1–5 are historical design notes
> for releases that have already shipped (kept for reference and for
> any future patch on the relevant subsystem). The env setup and
> handover protocol must happen before any code change; §6 is the
> v0.6.0 hot list (PDF export + Cloudflare Pages UI).

---

## Preamble: Status snapshot & module map

**Current version:** `0.5.1` (declared in three places that must stay in
sync — `openpharmastability/__init__.py`,
`openpharmastability/contracts.py` (`TOOL_VERSION`), and
`pyproject.toml`). v0.5.1 is the audit patch on top of v0.5.0
(advanced statistics). The default analyze path is byte-equivalent
to v0.4.0; v0.5.x added opt-in features only.

**Module map (what exists today at v0.5.1):**

```
openpharmastability/
  __init__.py            # __version__, re-exports of contracts
  contracts.py           # FROZEN dataclasses, enums, constants, signatures
                         #   v0.5.1: model_convergence field on StabilityResult
  cli.py                 # argparse CLI: `analyze` subcommand only
  data/
    io.py                # load_csv() / load_table() — CSV + XLSX dispatch
    xlsx.py              # XLSX loader (v0.2.0)
    metadata.py          # AttributeMetadata loader (v0.2.0)
    schema.py            # validate_and_select() — the contract gate
    conditions.py        # parse_condition() — "25°C/60%RH" -> "25C/60RH"
    bql.py               # apply_bql_policy() — all 5 policies real (v0.3.0)
    quality.py           # audit_data_quality() — 16-check audit (v0.3.0)
    replicates.py        # apply_replicate_policy()
  stats/
    regression.py        # fit_models() -> {POOLED, COMMON_SLOPE, SEPARATE}
                         #   v0.5.0+: optional random-effects mixed model
    poolability.py       # decide_poolability() — 3-step ANCOVA at alpha=0.25
    bounds.py            # confidence_bound(), find_crossing()
    diagnostics.py       # run_diagnostics()
    transforms.py        # assess_transforms() — exploratory (v0.3.0)
    arrhenius.py         # fit_arrhenius() — Ea / A from multi-temp (v0.5.0)
    mkt.py               # mean_kinetic_temperature() — Haynes (v0.5.0)
    MATH_SPEC.md         # the locked math
  models/
    selection.py         # select_model()
  shelf_life/
    engine.py            # analyze() — public single-attribute entry
                         #   v0.5.1: model_convergence surfaced top-level;
                         #   Arrhenius hook now per-attribute + direction-aware
    multi_engine.py      # analyze_many() — multi-attribute orchestration
    limiting.py          # select_limiting() — limiting-attribute selection
    extrapolation.py     # apply_extrapolation_caps() — via dataclasses.replace
  regulatory/
    significant_change.py # evaluate_significant_change() + Q1E table (v0.4.0)
    reduced_design.py    # detect_reduced_design() — ICH Q1D (v0.5.0)
  plots/
    confidence_plot.py   # make_confidence_plot()
  reports/
    html.py              # render_html() — single-attribute
    multi_html.py        # render_multi_html() — multi-attribute
    record.py            # to_decision_record() — single
    multi_record.py      # to_multi_decision_record() — multi
    templates/report.html.j2 + multi_report.html.j2
tools/
  regen_expected.py      # independent numpy/scipy validator (+ --check)
validation/              # 355 pytest tests (testpaths = ["validation"])
  conftest.py            # v0.5 module hard-require fail-fast (v0.5.1)
examples/
  assay_3batch.csv             # golden input
  assay_3batch.expected.json   # golden frozen output
  multi_attribute.csv          # multi-attribute fixture
  multi_attribute_metadata.csv # multi metadata sidecar
  bql_attribute.csv            # BQL fixture
  data_quality_messy.csv       # quality-audit fixture
  assay_long_term.csv          # v0.4 long-term arm
  assay_accelerated_change_lt_3mo.csv   # v0.4 <3mo accelerated change
  assay_accelerated_change_3_6mo.csv    # v0.4 3-6mo accelerated change
  assay_intermediate_no_change.csv      # v0.4 intermediate clean
  assay_intermediate_change.csv         # v0.4 intermediate change
```

**Key contract facts you must not forget:**

- `analyze()` signature lives at `engine.py:115` and is mirrored in
  `contracts.py:238`. Adding params must keep existing ones
  default-compatible.
- `StabilityResult` (`contracts.py:172`) is **single-attribute** today.
  §2 extends it; do it additively (new optional fields with defaults).
- `apply_extrapolation_caps()` manually re-copies every `StabilityResult`
  field (`extrapolation.py:51-69`). **Any new field added to
  `StabilityResult` MUST be added to that copy block** or it will be
  silently dropped. This is the single most common future bug. See §9.9
  for the regression test that catches it. Recommended fix: refactor the
  copy block to `dataclasses.replace(result, ...)`.
- t-quantile selection is centralized in `bounds.py:_quantile_for` (line
  54) and `bounds.py:_bound_multiplier` (line 216). One-sided 95% uses
  `ONE_SIDED_T_QUANTILE = 0.95`; two-sided uses `TWO_SIDED_T_QUANTILE =
  0.975`. These constants are at `contracts.py:39-41`.

---

## SECTION 1: IMMEDIATE FIXES (v0.1.1 patch)

Ship these three before any new feature. Bump version to `0.1.1` in all
three locations (see Preamble). Add a `CHANGELOG.md` entry under
`[0.1.1]`.

### Fix 1.1 — HTML timestamp breaks byte-identical output

**Problem.** `engine._iso_now()` (`engine.py:82-83`) stamps the metadata
with wall-clock time; the template renders it at
`reports/templates/report.html.j2:471` and `:512`. Numbers are identical
run-to-run, but the HTML bytes differ, defeating hash-based audit
trails.

**Files & lines to change:**

- `openpharmastability/engine.py` — `analyze()` signature (`engine.py:115`)
  and `_build_metadata()` (`engine.py:93`).
- `openpharmastability/cli.py` — add the flag in `_build_parser()` around
  line 56.
- `openpharmastability/reports/record.py` — pass the same epoch into
  `to_decision_record()` so JSON is also reproducible.

**Change (real Python).** Make the timestamp injectable and add a
`--source-epoch` / `SOURCE_DATE_EPOCH` path. Honor the reproducible-
builds convention `SOURCE_DATE_EPOCH` (numeric Unix seconds; reproducible
across machines).

```python
# engine.py
import os
from datetime import datetime, timezone

def _iso_now(source_epoch: int | None = None) -> str:
    """Return the report timestamp.

    Resolution order: explicit arg > SOURCE_DATE_EPOCH env > wall clock.
    Honors the reproducible-builds convention (see
    https://reproducible-builds.org/docs/source-date-epoch/).
    """
    if source_epoch is None:
        env = os.environ.get("SOURCE_DATE_EPOCH")
        if env and env.lstrip("-").isdigit():
            source_epoch = int(env)
    if source_epoch is not None:
        return datetime.fromtimestamp(source_epoch, tz=timezone.utc)\
            .strftime("%Y-%m-%dT%H:%M:%SZ")
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _build_metadata(path, df, seed, source_epoch: int | None = None) -> dict:
    return {
        # ...existing keys...
        "timestamp": _iso_now(source_epoch),
    }

def analyze(path, condition, attribute="assay", product_type="product",
            horizon=DEFAULT_HORIZON_MONTHS, replicate_policy="individual",
            seed=None, source_epoch: int | None = None) -> StabilityResult:
    # ...
    metadata=_build_metadata(path, raw_df, seed, source_epoch=source_epoch),
```

```python
# cli.py — in the analyze subparser
a.add_argument("--source-epoch", type=int, default=None,
    help="Fix the report timestamp (Unix epoch seconds) for byte-"
         "reproducible output. Also honored via the SOURCE_DATE_EPOCH "
         "environment variable. Useful for CI diff baselines and audit "
         "trails.")
# pass args.source_epoch into analyze(...)
```

**Test to add** — `validation/test_reporting.py::test_html_byte_identical_with_fixed_epoch`:

```python
def test_html_byte_identical_with_fixed_epoch(tmp_path):
    out1, out2 = tmp_path/"a.html", tmp_path/"b.html"
    plot = tmp_path/"p.png"
    for out in (out1, out2):
        r = analyze(str(CSV_PATH), condition="25C/60RH", attribute="assay",
                    source_epoch=1_700_000_000)
        from openpharmastability.data.io import load_csv
        from openpharmastability.data.schema import validate_and_select
        data = validate_and_select(load_csv(str(CSV_PATH)),
                                   attribute="assay", condition="25C/60RH")
        make_confidence_plot(r, data, str(plot))
        render_html(r, plot_png_path=str(plot.name), out_path=str(out))
    assert out1.read_bytes() == out2.read_bytes()
```

**Acceptance criterion.** Two runs with the same `--source-epoch` (or
same `SOURCE_DATE_EPOCH`) produce byte-identical HTML *and* JSON. Without
the flag, behavior is unchanged (wall-clock timestamp). `173 → 174
passed` minimum. The companion JSON determinism test (§9.2) should be
added in the same commit.

### Fix 1.2 — false-positive direction warning

**Problem.** `schema._resolve_direction` (`schema.py:251`) compares the
declared direction to `_infer_direction_from_spec` (`schema.py:291`).
When **both** spec limits are finite, `_infer_direction_from_spec`
returns `BIDIRECTIONAL` (`schema.py:299-300`). If the user *explicitly
declares* `decreasing` (assay has both a lower and upper spec but
degrades downward), the declared value (`DECREASING`) ≠ inferred
(`BIDIRECTIONAL`), so a spurious mismatch warning fires at
`schema.py:282-287` even though the declaration is perfectly consistent
with hitting the lower limit.

**File & lines:** `openpharmastability/data/schema.py`,
`_resolve_direction`, the mismatch branch at lines 277–287.

**Change.** Suppress the warning when the declared direction is
*consistent* with the inferred limits — i.e. when inferred is
`BIDIRECTIONAL` and the declared direction is one of the two single-
sided directions whose limit is present.

```python
# schema.py, inside _resolve_direction, replace the
# `if declared != inferred:` block with:

def _declared_consistent_with_inferred(
    declared: Direction, inferred: Direction
) -> bool:
    """A single-sided declaration is consistent with a both-limits
    ("bidirectional") inferred direction, because the user is telling us
    which limit governs the crossing. A declared UNKNOWN with a
    specific inferred direction is also consistent (the user is
    deferring to inference)."""
    if inferred is Direction.BIDIRECTIONAL and declared in (
        Direction.DECREASING, Direction.INCREASING, Direction.BIDIRECTIONAL
    ):
        return True
    if declared is Direction.UNKNOWN:
        return True
    return declared == inferred

# then in _resolve_direction:
if not _declared_consistent_with_inferred(declared, inferred):
    warnings.append(
        f"declared direction={declared.value!r} differs from the "
        f"inferred direction={inferred.value!r} (inferred from the "
        f"spec limits). Using the declared value per spec; the "
        f"inferred value is recorded for audit."
    )
```

**Test to modify/add** — `validation/test_data_schema.py`:

- Modify any existing test asserting the warning fires for the
  both-specs + declared-decreasing case.
- Add `test_no_direction_warning_when_declared_consistent_with_both_specs`:
  ```python
  def test_no_direction_warning_when_declared_consistent():
      df = _frame_with(lower=90, upper=110, direction="decreasing")
      vd = validate_and_select(df, "assay", "25C/60RH")
      assert vd.direction is Direction.DECREASING
      assert not any("differs from the inferred" in w for w in vd.warnings)
  ```
- Keep a genuine-conflict test: declared `increasing` while only
  `lower_spec` present → warning still fires (`inferred = DECREASING`,
  not bidirectional).

**Acceptance criterion.** No warning when declared ∈ {decreasing,
increasing} and both specs are present; warning still fires for a true
conflict (e.g. declared `increasing` with only a lower spec). UNKNOWN
declared value never warns.

### Fix 1.3 — `regen_expected.py` COMMON_SLOPE not pure-numpy

**Problem.** `tools/regen_expected.py:89` fits the COMMON_SLOPE model
with `statsmodels.formula.api.ols`. The validator's whole purpose is
*independence*; using statsmodels means a statsmodels bug could hide in
both engine and validator. The pooled path (`_pooled_expected`, line 50)
is already pure numpy via `np.linalg.lstsq` — mirror that.

**File & lines:** `tools/regen_expected.py`,
`_common_slope_expected` (lines 85–~140), and remove the
`import statsmodels.formula.api as smf` at line 23.

**Change.** Build the design matrix by hand (treatment coding, reference
= alphabetically-first batch) and solve with `lstsq`; compute
`cov = s^2 (X^T X)^{-1}` directly. Use only `numpy` / `scipy.stats` /
`pandas` / `brentq`.

```python
def _common_slope_expected(df: pd.DataFrame) -> dict:
    batches = sorted(df["batch"].unique())
    ref = batches[0]
    others = batches[1:]
    t = df["time_months"].to_numpy(float)
    y = df["value"].to_numpy(float)
    # Column order MUST match engine's fit_models:
    # [Intercept, time_months, C(batch)[T.b] for b in others (alphabetical)]
    cols = [np.ones_like(t), t]
    for b in others:
        cols.append((df["batch"].to_numpy() == b).astype(float))
    X = np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    n, p = X.shape
    df_resid = n - p
    resid = y - X @ beta
    sse = float((resid**2).sum())
    s = float(np.sqrt(sse / df_resid))
    XtX_inv = np.linalg.inv(X.T @ X)
    cov = (s**2) * XtX_inv
    from scipy.stats import t as student_t
    k_95 = float(student_t.ppf(0.95, df_resid))  # one-sided
    intercept = float(beta[0])
    slope = float(beta[1])
    # per-batch b0: b0_batch = beta[0] + beta[2+i] for i in others; b0_ref = beta[0]
    per_batch_b0 = {b: (intercept + (0 if b == ref else float(beta[2 + others.index(b)])))
                    for b in batches}
    # worst-case (earliest) crossing using the SAME c-vector construction
    # as bounds.py: c has 1.0 in the intercept col, 0 in the time col,
    # 1.0 in this batch's offset col (if any), 0 in the others' offset cols.
    c = np.zeros(p)
    c[0] = 1.0  # intercept always 1
    c[1] = 0.0  # slope coefficient 0 at the SPEC time of crossing
                # (the bound uses yhat(t) and the SE derivative; the
                # engine handles the time term via c[1]=t in the bound
                # function; for the crossing solver it uses the per-t
                # c-vector — match exactly)
    # NOTE: in practice the engine's find_crossing builds c[1]=t at the
    # search time. The validator must do the same. See test below.
    # ...
    return {
        "b1_common": slope,
        "b0_batches": per_batch_b0,
        "df_resid": df_resid,
        "s_resid": s,
        "cov": cov.tolist(),
    }
```

**Test to add** — `validation/test_regen.py::test_regen_does_not_import_statsmodels`:

```python
def test_regen_does_not_import_statsmodels():
    src = SCRIPT.read_text()
    assert "import statsmodels" not in src
    assert "smf." not in src
    assert "statsmodels" not in src   # forbids any reference
```

(Extend the existing
`test_script_does_not_import_project_stats` forbidden tuple to also
include `"statsmodels"`.)

**Acceptance criterion.** `regen_expected.py` imports only
numpy/scipy/pandas (no statsmodels).
`python tools/regen_expected.py --check` still exits 0 against the
committed golden file (values agree to existing tolerance, `rtol=1e-9`
on the existing numerical fields).

---

## SECTION 2: v0.2.0 — MULTI-ATTRIBUTE + XLSX

> v0.2.0 SHIPPED — see CHANGELOG for what actually landed; v0.2.1 hotfix followed.
> v0.3.0 SHIPPED — see CHANGELOG for what actually landed. The data
> quality, BQL, and transform-evidence work was added on top of the
> v0.2.0 multi-attribute + XLSX baseline. The v0.2.1 hotfix that
> followed v0.2.0 (XLSX metadata-sheet detection, multi HTML plot
> paths, bql-policy wiring) is also documented in CHANGELOG.

**Theme:** one analysis call can ingest XLSX, evaluate multiple
attributes (including degradants with upper limits and two-sided
attributes), and report a *limiting* shelf life across them.

### 2.1 XLSX upload

**New function** in `data/io.py`:

```python
from pathlib import Path
import pandas as pd

def load_table(path: str, sheet: str | int | None = None) -> pd.DataFrame:
    """Load CSV or XLSX into a raw DataFrame (no validation).
    Dispatches on extension:
        .csv         -> load_csv()         (back-compat)
        .xlsx/.xlsm  -> pd.read_excel(engine="openpyxl")
        .xls         -> pd.read_excel(engine="xlrd")  # if xlrd installed
    `sheet` selects the worksheet (default: first sheet).
    """
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return load_csv(path)
    if ext in (".xlsx", ".xlsm"):
        return pd.read_excel(
            path, sheet_name=(0 if sheet is None else sheet),
            engine="openpyxl"
        )
    if ext == ".xls":
        return pd.read_excel(
            path, sheet_name=(0 if sheet is None else sheet),
            engine="xlrd"
        )
    raise ValueError(
        f"unsupported input extension {ext!r}; "
        f"use .csv / .xlsx / .xlsm / .xls"
    )
```

Keep `load_csv` as-is (back-compat). `load_table` dispatches as above.

- **`pyproject.toml`:** add `openpyxl>=3.1` to `dependencies`. Add
  `xlrd>=2.0` only if legacy `.xls` is required; otherwise document
  `.xls` as unsupported and drop the branch.
- **`engine.analyze`** and **`cli.py`:** replace internal
  `load_csv(path)` calls with `load_table(path, sheet=args.sheet)`. Add
  CLI flag `--sheet` (str or int, default first sheet).

**CLI additions:**

```
--sheet SHEET          Worksheet name or 0-based index for XLSX input
                       (default: first sheet)
```

**Tests** (`validation/test_data_io.py`):

```python
def test_load_table_csv_backcompat():
    # load_table on a .csv returns the same frame as load_csv
    assert load_table(str(CSV_PATH)).equals(load_csv(str(CSV_PATH)))

def test_load_table_xlsx_roundtrip(tmp_path):
    df = pd.read_csv(CSV_PATH)
    xlsx = tmp_path/"in.xlsx"
    df.to_excel(xlsx, index=False)
    out = load_table(str(xlsx))
    pd.testing.assert_frame_equal(
        out.reset_index(drop=True),
        df.reset_index(drop=True),
        check_dtype=False,   # XLSX round-trip can dtypes-shift
    )

def test_load_table_unsupported_ext(tmp_path):
    f = tmp_path/"data.txt"; f.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="unsupported input extension"):
        load_table(str(f))

def test_load_table_xlsx_sheet_selection(tmp_path):
    df1, df2 = pd.DataFrame({"a":[1]}), pd.DataFrame({"b":[2]})
    xlsx = tmp_path/"s.xlsx"
    with pd.ExcelWriter(xlsx) as w:
        df1.to_excel(w, sheet_name="first", index=False)
        df2.to_excel(w, sheet_name="second", index=False)
    pd.testing.assert_frame_equal(load_table(str(xlsx), sheet="second"),
                                  df2, check_dtype=False)
```

**Acceptance.** `analyze` runs against an `.xlsx` mirror of
`examples/assay_3batch.csv` and produces the same numeric result as the
CSV (subject to dtype tolerance).

### 2.2 Multiple attributes in a single `analyze()` call

**New top-level function** in `shelf_life/engine.py` (keep single-
attribute `analyze` intact; call it internally):

```python
from openpharmastability.contracts import MultiStabilityResult, StabilityResult

def analyze_multi(
    path: str,
    condition: str,
    attributes: list[str] | None = None,    # None -> auto-detect
    product_type: str = "product",
    horizon: float = DEFAULT_HORIZON_MONTHS,
    replicate_policy: str = "individual",
    seed: int | None = None,
    source_epoch: int | None = None,
    sheet: str | int | None = None,
) -> MultiStabilityResult:
    """Run analyze() per attribute and assemble a limiting-shelf-life record.

    Auto-detect attributes (when attributes is None):
        sorted distinct `attribute` values from rows where
        parse_condition(condition) matches the input condition.
    Limiting shelf life = min over non-None
    `supported_shelf_life_months` across attributes.
    """
```

**New contract dataclass** (additive — append to `contracts.py`, do not
modify existing classes):

```python
# openpharmastability/contracts.py — add at the end, before __all__

@dataclass
class MultiStabilityResult:
    """Multi-attribute decision record returned by analyze_multi()."""
    condition: str
    per_attribute: dict[str, StabilityResult]   # keyed by attribute name
    limiting_attribute: Optional[str]           # argmin of supported months
    limiting_shelf_life_months: Optional[int]   # min across attributes
    deliverable_term: str = "shelf life"
    product_type: str = "product"
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

Add `"MultiStabilityResult"` to `contracts.__all__` and to the
`__init__` re-exports.

**Limiting logic.** The limiting shelf life is the **minimum**
`supported_shelf_life_months` across attributes whose value is not
`None`. An attribute with `None` (no crossing within horizon) does
*not* limit. If *all* are `None`,
`limiting_shelf_life_months = None` and a warning notes "not limiting
within horizon for any attribute." `limiting_attribute` is the
attribute achieving that minimum (ties → first alphabetically; record
the tie as a note in `metadata["tie_attributes"]`).

```python
def _limit(per: dict[str, StabilityResult]) -> tuple[Optional[str], Optional[int], list[str]]:
    candidates = [(a, r.supported_shelf_life_months) for a, r in per.items()
                  if r.supported_shelf_life_months is not None]
    if not candidates:
        return None, None, ["not limiting within horizon for any attribute"]
    months = min(m for _, m in candidates)
    winners = sorted(a for a, m in candidates if m == months)
    if len(winners) > 1:
        return winners[0], months, [f"limiting tie between {winners} (alphabetical pick: {winners[0]})"]
    return winners[0], months, []
```

**CLI additions:**

```
--attributes ATTR[,ATTR,...]
                       Comma-separated list of attributes to analyze.
                       If >1, routes to analyze_multi.
--all-attributes       Analyze every distinct attribute in the input.
```

When `len(attributes) > 1` or `--all-attributes` is given, route to
`analyze_multi`. Otherwise fall through to single-attribute `analyze`.

**Tests** (`validation/test_engine.py`):

```python
def test_multi_attribute_limiting_is_min():
    # fixture: assay decreasing (crossing ~24mo), degradant increasing
    # (crossing ~12mo). Limiting must be the degradant at 12.
    r = analyze_multi(str(MULTI_CSV), condition="25C/60RH",
                      attributes=["assay", "degradant_A"])
    assert r.limiting_attribute == "degradant_A"
    assert r.limiting_shelf_life_months == 12

def test_multi_attribute_omits_none_from_limiting():
    # one attribute with no crossing (None), one with crossing. None
    # must not be the limiter.
    r = analyze_multi(str(MULTI_CSV), condition="25C/60RH",
                      attributes=["flat_attr", "degradant_A"])
    assert r.limiting_attribute == "degradant_A"
    assert "not limiting" not in " ".join(r.warnings).lower()

def test_multi_attribute_all_none_warns():
    # two attributes that never cross in horizon
    r = analyze_multi(str(MULTI_CSV), condition="25C/60RH",
                      attributes=["flat_a", "flat_b"])
    assert r.limiting_shelf_life_months is None
    assert any("not limiting within horizon" in w for w in r.warnings)

def test_single_attribute_unchanged_in_multi():
    # analyze() called via analyze_multi with one attribute must
    # agree with analyze() called directly.
    a = analyze(str(MULTI_CSV), condition="25C/60RH", attribute="assay")
    m = analyze_multi(str(MULTI_CSV), condition="25C/60RH",
                      attributes=["assay"])
    assert m.per_attribute["assay"].supported_shelf_life_months \
        == a.supported_shelf_life_months
```

**Acceptance.** Multi-attribute run reports correct min and limiting
attribute; single-attribute `analyze` is unchanged (byte-stable against
v0.1).

### 2.3 Degradant upper-limit logic (primary path)

The math already exists: `bounds.find_crossing` handles
`Direction.INCREASING` by using the **upper** one-sided 95% bound vs
`upper_spec` (`bounds.py:245-250`,
`confidence_bound(side="upper")`). v0.2's job is to make this a
*first-class* path, not just reachable.

- Ensure `schema.validate_and_select` correctly sets
  `Direction.INCREASING` for a degradant declared `increasing` with
  only an upper spec (already handled at `schema.py:301-304`). Add a
  degradant fixture.
- `record._confidence_bound_label` already emits
  `upper_one_sided_95_mean` for `INCREASING` (`record.py:41`). No
  change needed; add a test.

**Exact math for degradant upper crossing** (declarative for
documentation):

```
fit is on raw scale: yhat(t) = b0 + b1 * t,  b1 > 0
U(t) = yhat(t) + k_95 * s * sqrt(1/n + (t - tbar)^2 / Sxx)
where k_95 = student_t.ppf(0.95, df_resid)        # ONE-sided
crossing: solve U(t) = upper_spec for t > 0 by brentq on [0, horizon]
```

**Tests:**

```python
def test_degradant_upper_spec_crossing():
    # 3-batch degradant trending up, upper_spec = 1.0
    r = analyze(str(DEGRADANT_CSV), condition="25C/60RH",
                attribute="degradant_A")
    assert r.direction is Direction.INCREASING
    assert r.crossing.status is CrossingStatus.CROSSED
    rec = to_decision_record(r)
    assert rec["fit"]["confidence_bound_label"] == "upper_one_sided_95_mean"
```

**Acceptance.** A degradant-only run produces an upper-bound shelf
life identical to a hand-computed value (add to a new
`degradant.expected.json` golden via a `regen`-style independent calc).

### 2.4 Bidirectional / two-sided crossing

For an attribute with **both** spec limits where neither direction
dominates a priori (declared `bidirectional`), compute **both** a lower
bound vs `lower_spec` and an upper bound vs `upper_spec`, each using
the **two-sided** t-quantile `student_t.ppf(0.975, df)`, and take the
**earliest** crossing of either.

**Exact math.** For each candidate `(spec, side)` in
`[(lower_spec, "lower"), (upper_spec, "upper")]`:

- multiplier `k = student_t.ppf(0.975, df_resid)`  (NOT 0.95 — two
  tails total 5%);
- `lower_bound(t) = yhat(t) − k · SE_mean(t)`; cross when
  `lower_bound(t) == lower_spec`;
- `upper_bound(t) = yhat(t) + k · SE_mean(t)`; cross when
  `upper_bound(t) == upper_spec`;
- `t_cross = min(t_lower_cross, t_upper_cross)` over those that cross
  in `[0, horizon]`;
- governing side/limit recorded.

**Function changes:**

- `bounds.find_crossing` gains a branch for `Direction.BIDIRECTIONAL`
  that calls a new helper `_bidirectional_crossing(fit, data, horizon)`
  which evaluates both sides with the 0.975 multiplier and returns the
  earliest.
- The existing `_bound_multiplier` (hard-coded one-sided,
  `bounds.py:216`) must be made **side/quantile-aware**: pass the
  quantile in, do not hard-code `ONE_SIDED_T_QUANTILE`.
  ```python
  def _bound_multiplier(side: str, direction: Direction,
                        alpha: float = CONFIDENCE) -> float:
      if side == "two-sided":
          return float(student_t.ppf(TWO_SIDED_T_QUANTILE, df_resid))
      return float(student_t.ppf(ONE_SIDED_T_QUANTILE, df_resid))
  ```
- `CrossingResult` (`contracts.py:153`) gains an additive optional
  field `governing_side: Optional[str] = None` (`"lower"`, `"upper"`,
  or `None` for one-sided paths).

**Tests** (`validation/test_stats_crossing.py`):

```python
def test_bidirectional_upper_wins():
    # fixture trending UP faster than DOWN. Both specs finite. Direction
    # declared bidirectional. Crossing must be the upper one and use
    # the 0.975 multiplier.
    r = analyze(str(BIDIR_UP_CSV), condition="25C/60RH",
                attribute="pH")
    assert r.direction is Direction.BIDIRECTIONAL
    assert r.crossing.governing_side == "upper"
    # assert the t-quantile used is provably 0.975 (not 0.95)
    expected_t = student_t.ppf(0.975, r.fit.df_resid)
    # engine records the multiplier it used; add this field
    assert abs(r.fit.quantile_multiplier - expected_t) < 1e-12

def test_bidirectional_lower_wins():
    # mirror of the above
    r = analyze(str(BIDIR_DOWN_CSV), condition="25C/60RH",
                attribute="pH")
    assert r.crossing.governing_side == "lower"
```

**Lock-in test (replaces v0.1 heuristic) — `validation/test_stats_crossing.py::test_bidirectional_uses_two_sided_quantile`**. The
v0.1 heuristic picked `candidates[0]` (lower). The v0.2 implementation
must use the 0.975 multiplier on *both* sides. Pin this in a test that
imports `_bound_multiplier` and asserts the multiplier for
`BIDIRECTIONAL` is `student_t.ppf(0.975, df)`, not 0.95.

**Acceptance.** Bidirectional attribute returns the earliest of the
two two-sided crossings; the multiplier is provably 0.975; the
existing v0.1 one-sided 0.95 path is unchanged.

### 2.5 Limiting shelf life across attributes

Covered in §2.2 (`analyze_multi`). For completeness, the rule:

```
limiting_shelf_life_months = min over attrs of supported_shelf_life_months
                             where the value is not None
limiting_attribute = the attr achieving the min (ties -> first alphabetical)
```

If all attributes are `None`, the record is `None` with a warning. If
*some* are `None` (no crossing), they are *not* the limiter and the
min is taken over the others.

### 2.6 Report: per-attribute breakdown + limiting attribute

- `reports/record.py`: add
  `to_multi_decision_record(multi: MultiStabilityResult) -> dict`
  emitting:
  ```json
  {
    "condition": "25C/60RH",
    "limiting_attribute": "degradant_A",
    "limiting_shelf_life_months": 12,
    "deliverable_term": "shelf life",
    "product_type": "product",
    "per_attribute": { "<attr>": <single decision record>, ... },
    "warnings": [...],
    "metadata": {...},
    "disclaimer": "<verbatim DISCLAIMER>"
  }
  ```
- `reports/html.py` + `templates/report.html.j2`: add a per-attribute
  breakdown table with columns:
  `Attribute | Direction | Model | Poolability | Statistical crossing | Supported months | Limiting?`.
  The limiting row is highlighted (e.g. bold + a `← LIMITING` badge).

**Tests** (`validation/test_reporting.py`):

```python
def test_multi_record_has_every_attribute():
    r = analyze_multi(str(MULTI_CSV), condition="25C/60RH",
                      attributes=["assay", "degradant_A"])
    rec = to_multi_decision_record(r)
    assert set(rec["per_attribute"]) == {"assay", "degradant_A"}
    assert rec["limiting_attribute"] == "degradant_A"

def test_multi_html_has_breakdown_table():
    r = analyze_multi(...)
    html = render_html_multi(r, plot_png_path="p.png", out_path=str(tmp/"h.html"))
    text = Path(tmp/"h.html").read_text()
    assert "assay" in text and "degradant_A" in text
    assert "LIMITING" in text or "←" in text
```

**Acceptance.** HTML/JSON for a multi run shows each attribute and
clearly marks the limiting one; the disclaimer is verbatim in the
JSON (see §9.4).

---

## SECTION 3: v0.3.0 — DATA QUALITY + TRANSFORMS

> **v0.3.0 SHIPPED (2026-06-13).** The data quality audit, real BQL
> policies, and transform-candidate evidence are all live. The
> remaining v0.3.0 work (significant-change gating from §4,
> Arrhenius from §5, etc.) has been moved to v0.4+ plans. See
> `CHANGELOG.md` for the full v0.3.0 entry.

### 3.1 BQL substitution policies

Implement the `SEAM_POLICIES` in `data/bql.py` (currently raise
`NotImplementedError` at `bql.py:88-94`). Final policy set:
`exclude`, `flag`, `substitute_loq`, `substitute_half_loq`, plus new
`manual_review_flag`.

**Data model:** require `loq` (limit of quantitation) and optionally
`lod` columns (already reserved). For a row with `is_bql == True`:

| Policy | Behavior on BQL row |
|---|---|
| `exclude` | drop row (existing). |
| `flag` | keep row; add `"bql_present"` warning (existing). |
| `substitute_loq` | `value := loq`. |
| `substitute_half_loq` (LOQ/2) | `value := loq / 2`. |
| `manual_review_flag` | keep, `value := NaN`; per-row warning + result-level `requires_manual_review = True`. |

Substitution requires `loq` to be finite for the BQL row; if missing,
raise `ValueError` naming the offending row indices (never default to
zero).

```python
# data/bql.py — replace the SEAM_POLICIES branch with:
SUPPORTED_ALL = SUPPORTED_V01 | frozenset({
    "substitute_loq", "substitute_half_loq", "manual_review_flag"
})

def apply_bql_policy(df: pd.DataFrame, policy: str = "exclude", **opts) -> pd.DataFrame:
    if policy == POLICY_EXCLUDE:    return _exclude_bql_rows(df)
    if policy == POLICY_FLAG:        return df.copy()
    if policy == "substitute_loq":  return _substitute(df, factor=1.0)
    if policy == "substitute_half_loq": return _substitute(df, factor=0.5)
    if policy == "manual_review_flag": return _manual_review(df)
    raise ValueError(
        f"unknown BQL policy: {policy!r}. Expected one of {sorted(SUPPORTED_ALL)}."
    )

def _substitute(df: pd.DataFrame, factor: float) -> pd.DataFrame:
    out = df.copy()
    mask = _bql_mask(out)
    if not mask.any():
        return out
    if "loq" not in out.columns or out.loc[mask, "loq"].isna().any():
        bad_idx = out.index[mask & out.get("loq", pd.Series(dtype=float)).isna()].tolist()
        raise ValueError(
            f"substitute_* BQL policy requires a finite 'loq' for every BQL row; "
            f"missing for row indices: {bad_idx[:5]}{'...' if len(bad_idx) > 5 else ''}"
        )
    out.loc[mask, "value"] = out.loc[mask, "loq"] * factor
    return out

def _manual_review(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    mask = _bql_mask(out)
    if mask.any():
        out.loc[mask, "value"] = np.nan
    return out

def _bql_mask(df: pd.DataFrame) -> pd.Series:
    if "is_bql" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["is_bql"].astype("boolean").fillna(False).astype(bool)
```

**Result-level signal:** add `ValidatedData.requires_manual_review: bool
= False` (additive). Schema sets it to `True` when the BQL policy is
`manual_review_flag` AND at least one row was BQL. Also set
`ValidatedData.warnings` with the per-row index list.

**Tests** (`validation/test_data_bql.py`):

```python
def test_substitute_loq_writes_loq_value():
    df = _df_with([{"is_bql": True, "loq": 0.05, "value": np.nan}])
    out = apply_bql_policy(df, "substitute_loq")
    assert out.loc[0, "value"] == 0.05

def test_substitute_half_loq_writes_half():
    df = _df_with([{"is_bql": True, "loq": 0.10, "value": np.nan}])
    out = apply_bql_policy(df, "substitute_half_loq")
    assert out.loc[0, "value"] == 0.05

def test_substitute_missing_loq_raises_with_indices():
    df = _df_with([{"is_bql": True, "value": np.nan}])  # no loq col
    with pytest.raises(ValueError, match="requires a finite 'loq'"):
        apply_bql_policy(df, "substitute_loq")

def test_substitute_never_writes_zero():
    df = _df_with([{"is_bql": True, "loq": 0.0, "value": np.nan}])
    with pytest.raises(ValueError):  # loq=0 is not a valid quantitation limit
        apply_bql_policy(df, "substitute_loq")
    # and verify nothing was written as 0
    assert (df["value"] != 0).all()

def test_manual_review_flag_sets_nan_and_warning():
    df = _df_with([{"is_bql": True, "loq": 0.05, "value": 999.0}])
    out = apply_bql_policy(df, "manual_review_flag")
    assert np.isnan(out.loc[0, "value"])
    # downstream: schema layer sets requires_manual_review=True
```

**Acceptance.** Each substitution policy produces the documented
`value`; missing `loq` raises; no zeros ever written; the result
record carries `requires_manual_review` for the `manual_review_flag`
path.

### 3.2 Replicate policy enforcement

`replicates.py` currently collapses both `mean_by_batch_time` and
`technical_replicates_average` to the same batch/time mean
(`replicates.py:85-86`). v0.3 differentiates the **residual df**
consequence:

- `mean_by_batch_time`: treat each averaged cell as one observation
  (current behavior).
- `technical_replicates_average`: average technical reps within a
  cell but **preserve the count** so the engine can use the correct
  df (true replicates vs technical reps changes the variance
  estimate). Record `n_obs_effective` on the frame / `ValidatedData`
  for the stats layer.

Concretely, return an extra column `n_replicates` (count of rows per
group) and have `schema.validate_and_select` copy it onto
`ValidatedData.n_replicates_per_cell: dict[tuple, int]`. The stats
layer then uses it to inflate the per-cell variance estimate when
`technical_replicates_average` is in effect.

```python
# data/replicates.py
def _aggregate_to_batch_time_means(df: pd.DataFrame) -> pd.DataFrame:
    # ...
    grouped = df.groupby(_GROUP_KEY, as_index=False, sort=True).agg(agg)
    grouped["n_replicates"] = df.groupby(_GROUP_KEY, as_index=False).size()["size"].values
    # ...
```

Add `ValidatedData.replicate_policy: str = "individual"` (additive) and
`ValidatedData.n_replicates_per_cell: dict[tuple[str, float], int] =
field(default_factory=dict)` (additive) so downstream code can
branch.

**Tests:**

```python
def test_replicate_mean_by_batch_time_one_row_per_cell():
    df = _df_with_dupes(2)  # two rows per (batch, time)
    out = apply_replicate_policy(df, "mean_by_batch_time")
    assert len(out) == len(df) // 2
    assert "n_replicates" not in out.columns or (out["n_replicates"] == 2).all()

def test_replicate_tech_avg_records_count():
    df = _df_with_dupes(3)
    out = apply_replicate_policy(df, "technical_replicates_average")
    assert (out["n_replicates"] == 3).all()
    # and the engine's df_resid differs from the mean_by_batch_time path
    a = analyze(..., replicate_policy="mean_by_batch_time")
    b = analyze(..., replicate_policy="technical_replicates_average")
    assert a.fit.df_resid != b.fit.df_resid or a.fit.s_resid != b.fit.s_resid
```

**Acceptance.** Each policy yields the documented row count and the
engine's `df_resid`/`s_resid` differs appropriately between
`individual` and the aggregation policies on a fixture with
replicates.

### 3.3 Log-linear (first-order) transform

**Declare:** new optional column/CLI flag `transform ∈ {none, log}`
(default `none`). `none` = current raw-scale linear. `log` = first-
order kinetics (log-linear).

**Exact math for `transform="log"`:**

1. **Domain check.** Require all `value > 0` for the rows used in the
   fit (raise `ValueError` listing the offending indices — `log`
   undefined).
2. **Fit OLS on the log scale:** `z = a + b·t`, where `z = ln(value)`.
   All model/poolability/SE math from `stats/regression.py` and
   `stats/poolability.py` runs unchanged but on `z`. The fit object
   carries `scale="log"`.
3. **Mean-response bound on the log scale at time `t`:**
   `z_bound(t) = (a + b·t) ∓ k · SE_z(t)` (lower for decreasing, upper
   for increasing; `SE_z` from the log-scale fit's covariance).
4. **Back-transform the bound:** `y_bound(t) = exp(z_bound(t))`.
   Because `exp` is monotonic increasing, the lower bound on `z`
   maps to the lower bound on `y` (and upper → upper) — no extra
   correction is needed for the *bound curve itself* (no lognormal
   bias correction is applied; v0.3 uses the standard Wald-type
   interval on the log scale, which is the convention for
   first-order kinetics shelf-life estimation).
5. **Transform spec limits before crossing.** Compare on the log
   scale: `z_spec_lower = ln(lower_spec)`, `z_spec_upper =
   ln(upper_spec)`. Solve `z_bound(t) == z_spec` for `t` with brentq
   over `[0, horizon]`. (Equivalent to solving
   `exp(z_bound) == spec`; the log-scale form is numerically
   cleaner.)
6. **Report:** `StabilityResult.metadata["transform"] = "log"`. The
   HTML shows back-transformed values for human reading but the
   JSON carries the transform flag and a note: *"bound and crossing
   computed on the log scale; back-transformed via exp() for
   display."*

**Contract additions** (additive, with defaults):

```python
# FitResult
scale: str = "raw"        # "raw" | "log"
z_spec_lower: Optional[float] = None
z_spec_upper: Optional[float] = None

# ValidatedData
transform: str = "none"   # "none" | "log"
```

`confidence_bound` and `find_crossing` branch on `fit.scale`.

**Tests:**

```python
def test_log_transform_recovers_slope_on_synthetic():
    # value = A * exp(-k * t)  =>  ln(value) = ln(A) - k * t
    k_true, A_true = 0.1, 100.0
    t = np.array([0, 3, 6, 9, 12, 18, 24], dtype=float)
    value = A_true * np.exp(-k_true * t) + rng.normal(0, 0.5, size=t.shape)
    df = _df_from_arrays(t=t, value=value, lower_spec=80)
    r = analyze_from_df(df, attribute="assay", condition="25C/60RH",
                        transform="log")
    assert abs(r.fit.params["b1"] - (-k_true)) / k_true < 0.05  # 5% rel

def test_log_transform_value_le_zero_raises():
    df = _df_with_value(0.0)
    with pytest.raises(ValueError, match="log transform requires value > 0"):
        analyze_from_df(df, ..., transform="log")

def test_log_transform_spec_lower_is_logged():
    # crossing on log scale must equal closed-form expectation
    # exp(a + b*t) = lower_spec  =>  t = (ln(lower_spec) - a) / b
    a, b, ls = 5.0, -0.05, 90.0
    expected = (np.log(ls) - a) / b
    r = _synthetic_fit(a=a, b=b, lower_spec=ls, transform="log")
    assert abs(r.statistical_crossing_months - expected) < 1e-6
```

**Acceptance.** Synthetic first-order decay recovers `b ≈ -k`;
back-transformed bound crossing matches a closed-form expectation
within `rtol=1e-6`; `value <= 0` raises; raw-scale path unchanged.

### 3.4 `spec_type` column (release vs shelf-life limits)

New optional column `spec_type ∈ {release, shelf_life}` (default
`shelf_life` if absent). Crossing must use **shelf-life** limits. If
only `release` limits are supplied, **warn**:
`"only release-spec limits supplied; shelf-life limits are usually
wider — crossing computed against release limits, which is
conservative."` Store the spec type used on
`StabilityResult.metadata["spec_type"]` and on
`ValidatedData.spec_type`.

**Implementation:** in `_extract_spec_values` (`schema.py:323`),
filter rows by `spec_type == "shelf_life"` first, then fall back to
`release` only with the warning.

**Tests:**

```python
def test_release_only_data_warns():
    df = _df_with_spec_type("release")
    vd = validate_and_select(df, "assay", "25C/60RH")
    assert any("release-spec limits" in w for w in vd.warnings)
    assert vd.metadata["spec_type"] == "release"

def test_shelf_life_preferred_when_both_present():
    df = _df_with_spec_type("shelf_life")  # also has release rows
    vd = validate_and_select(df, "assay", "25C/60RH")
    assert vd.metadata["spec_type"] == "shelf_life"
    assert not any("release-spec" in w for w in vd.warnings)
```

**Acceptance.** Release-only data emits the warning; `shelf_life`
present is used preferentially; the spec type used is recorded.

### 3.5 Attribute metadata table (separate tab / CSV)

Allow specs/direction/transform to live in a **separate** metadata
table keyed by `attribute`, so the per-row CSV need not repeat them.
For XLSX: a second sheet `attributes` with columns:
`attribute, lower_spec, upper_spec, direction, transform, spec_type,
loq, lod`. For CSV: an optional sidecar `--attributes-meta
path.csv`.

`schema.validate_and_select` merges the metadata onto the observation
frame by `attribute` *before* column-level validation. Per-row
values, if present, win over the table (warn on conflict).

```python
def merge_attribute_metadata(
    df: pd.DataFrame, meta: pd.DataFrame
) -> tuple[pd.DataFrame, list[str]]:
    """Return (merged_df, warnings). Per-row values in df win over meta.
    Conflict = different non-null value in df vs meta for the same
    (attribute, column)."""
    warnings = []
    rows = []
    for _, m in meta.iterrows():
        mask = df["attribute"] == m["attribute"]
        for col in ("lower_spec", "upper_spec", "direction",
                    "transform", "spec_type"):
            if col in m and not pd.isna(m[col]):
                if mask.any() and col in df.columns:
                    conflicting = df.loc[mask, col].dropna().unique()
                    if len(conflicting) and any(
                        not np.isclose(c, m[col]) for c in conflicting
                    ):
                        warnings.append(
                            f"attribute={m['attribute']!r}: per-row "
                            f"{col}={list(conflicting)} overridden by "
                            f"metadata table value {m[col]}"
                        )
                df.loc[mask, col] = m[col]
        rows.append(m["attribute"])
    return df, warnings
```

**CLI addition:**

```
--attributes-meta PATH   Optional metadata table (CSV or XLSX with an
                         "attributes" sheet) keyed by `attribute`.
```

**Tests:**

```python
def test_metadata_sidecar_yields_same_validated_data():
    # per-row CSV vs all-in-one CSV (with metadata sidecar) must
    # produce identical ValidatedData.
    vd1 = validate_and_select(df_inline, "assay", "25C/60RH")
    df_merged, _ = merge_attribute_metadata(df_no_specs, meta_df)
    vd2 = validate_and_select(df_merged, "assay", "25C/60RH")
    assert vd1.lower_spec == vd2.lower_spec
    assert vd1.upper_spec == vd2.upper_spec
    assert vd1.direction == vd2.direction

def test_per_row_wins_over_metadata_with_warning():
    df = _df_with_per_row_spec(91.0)  # contradicts metadata value 90.0
    df_merged, w = merge_attribute_metadata(df, meta_with_90)
    assert any("overridden" in x for x in w)
    # per-row value preserved
    assert df_merged.loc[0, "lower_spec"] == 91.0
```

**Acceptance.** Metadata-tab path yields identical `ValidatedData` to
the all-in-one CSV; conflicting per-row vs table values warn.

---

## SECTION 4: v0.4.0 — REGULATORY DECISION TREE (ICH Q1A integration)

**Theme:** gate extrapolation on the accelerated/intermediate
significant-change evaluation, per ICH Q1A(R2) + Q1E §2.3.

### 4.1 Accelerated condition ingestion (40C/75RH)

Input already carries `condition`; v0.4 just stops treating
non-long-term rows as noise. `analyze` gains:

```python
def analyze(...,                              # existing params
            accelerated_condition: str | None = "40C/75RH",
            intermediate_condition: str | None = "30C/65RH",
            run_accelerated: bool = True) -> StabilityResult:
    """When run_accelerated is True (default), the engine subsets the
    accelerated and intermediate condition rows separately and feeds
    them to the significant-change evaluator (§4.2). The single
    StabilityResult contract is preserved: it still represents the
    long-term condition; the accelerated/intermediate outcomes are
    recorded on the new additive fields below."""
```

The engine subs via `parse_condition`; the existing normalization
already handles `40°C/75%RH` vs `40C/75RH`.

### 4.2 Significant-change checklist

**New module** `openpharmastability/regulatory/significant_change.py`:

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SignificantChange:
    """Result of evaluating the ICH Q1A(R2) §2.2.7 checklist."""
    occurred: bool
    first_change_month: Optional[float]   # earliest time any criterion tripped
    reasons: list[str] = field(default_factory=list)
    per_condition: dict[str, bool] = field(default_factory=dict)
    # Per-criterion details for the report
    details: dict[str, Any] = field(default_factory=dict)

def evaluate_significant_change(
    df: pd.DataFrame,                  # one condition's worth of rows
    attribute_meta: dict[str, Any],    # specs, thresholds
    assay_change_threshold_pct: float = 5.0,
) -> SignificantChange:
    """Evaluate the 5 criteria. df is the filtered long-term (or
    accelerated/intermediate) frame for one attribute. attribute_meta
    carries the spec limits and the column names to look at."""
```

**Criteria (ICH Q1A(R2) §2.2.7 default checklist; all configurable
thresholds):**

1. **Assay:** `|value(t) − value(t=0)| / value(t=0) * 100 ≥
   assay_change_threshold_pct` (default 5%).
2. **Degradant:** any specified degradation product exceeds its
   acceptance criterion (OOS) — i.e. `value(t) > upper_spec` for an
   increasing degradant.
3. **Physical:** failure of appearance/physical attributes
   (configurable boolean column `physical_fail`).
4. **pH:** failure to meet the pH acceptance criterion — i.e.
   `value(t) < ph_spec_low OR value(t) > ph_spec_high`.
5. **Dissolution:** failure for 12 dosage units (configurable boolean
   column `dissolution_fail`).

Each criterion reads optional columns; absent column → that
criterion not evaluated (note it in `details`). Returns earliest
month of first significant change.

```python
# pseudocode
for criterion in criteria:
    if not criterion.has_required_columns(df):
        details[criterion.name] = {"evaluated": False}
        continue
    first_t = criterion.first_trigger_month(df, meta)
    if first_t is not None:
        reasons.append(f"{criterion.name} at t={first_t}: {criterion.evidence}")
        first_change_month = min(first_change_month or inf, first_t)
        details[criterion.name] = {"evaluated": True, "first_t": first_t, ...}
return SignificantChange(
    occurred=(first_change_month is not None),
    first_change_month=first_change_month,
    reasons=reasons,
    per_condition={condition_name: occurred},
    details=details,
)
```

### 4.3 Significant-change gating of extrapolation

Replace/augment `shelf_life/extrapolation.py` logic with the Q1E
decision tree. After computing `SignificantChange` on the
**accelerated** condition (and optionally the intermediate):

| Accelerated result | Allowed extrapolation |
|---|---|
| **No** significant change over 6 mo accelerated | Extrapolation permitted within Q1E caps (current 2× / +12 mo). |
| Significant change at **< 3 mo** | **No extrapolation.** Shelf life ≤ observed long-term data. |
| Significant change at **3–6 mo** | Extrapolation only if **intermediate** (30C/65RH) condition data show no significant change; require intermediate data — if absent, no extrapolation + warning. |
| Significant change at **intermediate** condition | **No extrapolation.** |
| Accelerated change at **> 6 mo** | Extrapolation permitted (informational note: accel change late). |

Encode as a function returning the cap and a rationale string:

```python
def extrapolation_allowance(
    acc: SignificantChange,
    inter: SignificantChange | None,
    observed_months: float,
) -> tuple[bool, float, str]:
    """Returns (allowed, cap_months, rationale)."""
    if not acc.occurred:
        return (True, q1e_cap(observed_months), "no accelerated sig change")
    if acc.first_change_month < 3:
        return (False, observed_months, "accelerated sig change <3mo")
    if 3 <= acc.first_change_month <= 6:
        if inter is None:
            return (False, observed_months,
                    "3-6mo accelerated change; intermediate data required but absent")
        if inter.occurred:
            return (False, observed_months, "intermediate sig change")
        return (True, q1e_cap(observed_months),
                "3-6mo accelerated change; intermediate OK")
    return (True, q1e_cap(observed_months), "accelerated change >6mo")

def q1e_cap(observed: float) -> float:
    """Q1E rule of thumb: min(2 * observed, observed + 12)."""
    return min(2.0 * observed, observed + EXTRAPOLATION_MAX_MONTHS_BEYOND)
```

`apply_extrapolation_caps` consumes this: the binding cap becomes
`min(statistical_crossing_floor, allowance_cap)`; the rationale
appends to `StabilityResult.warnings`.

### 4.4 Intermediate condition data path

`analyze` evaluates the intermediate condition with the same
significant-change checklist; feeds `inter` into §4.3. If
`intermediate_condition` rows are absent but required (3–6 mo
accelerated change), no extrapolation + explicit warning
`"intermediate condition data required for extrapolation decision;
none provided — defaulting to no extrapolation."`.

### 4.5 Updated `extrapolation_flag` + new `StabilityResult` fields

Add (additive, with defaults, **and update the `extrapolation.py`
copy block / switch to `dataclasses.replace`**):

```python
# StabilityResult — additive fields
significant_change_accelerated: Optional[bool] = None
significant_change_intermediate: Optional[bool] = None
extrapolation_allowed: bool = True
extrapolation_rationale: str = ""
significant_change_details: dict[str, Any] = field(default_factory=dict)
```

**New input columns** (all optional):

| Column | Type | Used by |
|---|---|---|
| `physical_fail` | bool | Physical criterion |
| `ph_spec_low`, `ph_spec_high` | float | pH criterion |
| `dissolution_fail` | bool | Dissolution criterion |
| `degradant_oos` | bool | Degradant OOS (or derive from upper_spec) |

**CLI flags:**

```
--accelerated-condition "40C/75RH"
--intermediate-condition "30C/65RH"
--assay-change-threshold 5.0        # percent
--no-significant-change-gate         # opt out, reverts to v0.3 cap-only behavior
```

**Tests:**

```python
@pytest.mark.parametrize("scenario,expected_allowed,rationale_substr", [
    ("no_change",          True,  "no accelerated sig change"),
    ("change_lt_3mo",      False, "<3mo"),
    ("change_3_6_no_inter",False, "intermediate data required"),
    ("change_3_6_inter_ok",True,  "intermediate OK"),
    ("change_at_inter",    False, "intermediate sig change"),
    ("change_gt_6mo",      True,  ">6mo"),
])
def test_extrapolation_allowance_decision_table(scenario, expected_allowed,
                                                rationale_substr):
    acc, inter, observed = SCENARIO_FIXTURES[scenario]
    allowed, cap, why = extrapolation_allowance(acc, inter, observed)
    assert allowed is expected_allowed
    assert rationale_substr in why

def test_no_significant_change_gate_flag_disables_gating():
    r_no_gate = analyze(..., no_significant_change_gate=True, ...)
    r_with_gate = analyze(...)
    # cap is at least as permissive in the no-gate case
    assert r_no_gate.supported_shelf_life_months \
        >= r_with_gate.supported_shelf_life_months
```

**Acceptance.** The extrapolation cap and rationale match the table
for crafted fixtures covering every branch; the CLI opt-out restores
prior (v0.3) behavior; new fields appear in the JSON record and
HTML report.

---

## SECTION 5: v0.5.0 — ADVANCED STATISTICS

### 5.1 Arrhenius module

**New module** `openpharmastability/stats/arrhenius.py`. Model:
`ln(k) = ln(A) − Ea / (R·T)`, where `T` in **Kelvin**, `R = 8.314
J·mol⁻¹·K⁻¹`, `k` is the first-order rate at each stress temperature
(estimated per condition, e.g. from a log-linear fit per §3.3).

```python
# openpharmastability/stats/arrhenius.py
from dataclasses import dataclass
import numpy as np
from scipy.stats import linregress
from scipy.stats import t as student_t

@dataclass
class ArrheniusResult:
    Ea_J_per_mol: float
    ln_A: float
    A: float
    r_squared: float
    predicted_k_at_storage: float
    storage_temp_C: float
    n_temps: int

def fit_arrhenius(
    rate_by_temp_C: dict[float, float],   # {temp_C: k (1/month)}
    storage_temp_C: float,
    R: float = 8.314,                      # J / (mol * K)
) -> ArrheniusResult:
    """Fit ln(k) = ln(A) - Ea/(R*T) to stress-temperature rate data.

    Refuses with NotImplementedError when fewer than 2 temperatures
    are supplied. Emits a loud warning when exactly 2 temperatures are
    supplied (no goodness-of-fit; 3+ recommended).
    """
    temps_C = sorted(rate_by_temp_C)
    if len(temps_C) < 2:
        raise NotImplementedError(
            "Arrhenius requires >= 2 stress temperatures (>= 3 preferred "
            "for a defensible Ea). Got %d. Supply more temperatures or "
            "use a single-temperature shelf-life path." % len(temps_C)
        )
    if len(temps_C) == 2:
        import warnings
        warnings.warn(
            "Arrhenius fit with only 2 temperatures: no goodness-of-fit "
            "available. >= 3 temperatures recommended for a defensible Ea.",
            stacklevel=2,
        )
    T = np.array([c + 273.15 for c in temps_C])          # Kelvin
    lnk = np.log([rate_by_temp_C[c] for c in temps_C])
    # Closed-form OLS: [lnA, -Ea/R] via lstsq
    X = np.column_stack([np.ones_like(T), 1.0 / T])
    beta, *_ = np.linalg.lstsq(X, lnk, rcond=None)
    ln_A = float(beta[0])
    neg_Ea_over_R = float(beta[1])
    Ea = -neg_Ea_over_R * R
    Ts = storage_temp_C + 273.15
    k_pred = float(np.exp(ln_A - Ea / (R * Ts)))
    # r^2 from residuals
    yhat = X @ beta
    ss_res = float(((lnk - yhat) ** 2).sum())
    ss_tot = float(((lnk - lnk.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return ArrheniusResult(
        Ea_J_per_mol=Ea,
        ln_A=ln_A,
        A=float(np.exp(ln_A)),
        r_squared=r2,
        predicted_k_at_storage=k_pred,
        storage_temp_C=storage_temp_C,
        n_temps=len(temps_C),
    )
```

**Tests:**

```python
def test_arrhenius_recovers_known_Ea():
    # synthetic: Ea = 80000 J/mol, A = 1e10
    Ea_true, A_true = 80000.0, 1e10
    R = 8.314
    T_C = np.array([40.0, 50.0, 60.0, 70.0])
    k = A_true * np.exp(-Ea_true / (R * (T_C + 273.15)))
    r = fit_arrhenius({c: k_i for c, k_i in zip(T_C, k)},
                      storage_temp_C=25.0)
    assert abs(r.Ea_J_per_mol - Ea_true) / Ea_true < 1e-6
    assert abs(r.A - A_true) / A_true < 1e-6

def test_arrhenius_two_temps_warns():
    r = fit_arrhenius({40.0: 1e-3, 60.0: 5e-3}, storage_temp_C=25.0)
    assert r.n_temps == 2
    # pytest.warns(UserWarning, match=">= 3 temperatures recommended")

def test_arrhenius_one_temp_raises_not_implemented():
    with pytest.raises(NotImplementedError, match=">= 2 stress temperatures"):
        fit_arrhenius({40.0: 1e-3}, storage_temp_C=25.0)
```

**Acceptance.** 3-temperature synthetic with known `Ea` recovers it
within `rtol=1e-6`; 2-temp warns (no goodness-of-fit); 1-temp raises
`NotImplementedError`.

### 5.2 Reduced designs (bracketing / matrixing) detection

**New module** `openpharmastability/regulatory/reduced_design.py`.
Detect:

- **Bracketing:** only extreme levels of a factor (e.g. strength,
  container size) tested — detect via a `factor`/`level` column where
  intermediate levels are absent.
- **Matrixing:** not every batch×time×condition cell is present
  (sparse).

```python
from dataclasses import dataclass, field

@dataclass
class ReducedDesignReport:
    is_bracketed: bool
    is_matrixed: bool
    missing_cells: list[tuple] = field(default_factory=list)
    note: str = ""

def detect_reduced_design(
    df: pd.DataFrame,
    factor_columns: list[str] | None = None,
) -> ReducedDesignReport:
    """Warn (do not block) when the design is reduced. Returns a
    ReducedDesignReport; caller is responsible for turning it into a
    warning string on the report."""
```

**Tests:**

```python
def test_full_factorial_not_reduced():
    df = _full_factorial_fixture()
    rep = detect_reduced_design(df)
    assert not rep.is_bracketed and not rep.is_matrixed

def test_matrixed_design_warns():
    df = _matrixed_fixture()  # sparse
    rep = detect_reduced_design(df)
    assert rep.is_matrixed
    assert rep.missing_cells  # non-empty

def test_bracketed_design_warns():
    df = _bracketed_fixture()  # only min and max levels
    rep = detect_reduced_design(df, factor_columns=["strength"])
    assert rep.is_bracketed
```

**Acceptance.** Full-factorial → not reduced; sparse → matrixed
warning; extreme-levels-only → bracketed warning; warnings appear in
the JSON record.

### 5.3 Mean kinetic temperature (MKT)

**New function** `stats/mkt.py`:

```
MKT = (Ea/R) / ( −ln( ( Σ exp(−Ea/(R·Ti)) ) / n ) )   [Haynes equation]
```

With `Ti` in Kelvin, `Ea` a default of `83.144 kJ·mol⁻¹` (USP
<1160> common default; configurable), `R = 8.314`.

```python
import numpy as np

DEFAULT_EA_J_PER_MOL = 83.144e3   # USP <1160> common default

def mean_kinetic_temperature(
    temps_C: list[float],
    Ea_J_per_mol: float = DEFAULT_EA_J_PER_MOL,
    R: float = 8.314,
) -> float:
    """Return the Haynes MKT in degrees Celsius."""
    T = np.array([c + 273.15 for c in temps_C])
    mkt_K = (Ea_J_per_mol / R) / (
        -np.log(np.mean(np.exp(-Ea_J_per_mol / (R * T))))
    )
    return float(mkt_K - 273.15)
```

**Input columns:** a `temp_c` column (already aggregated in
`replicates.py`) or a separate temperature-log table. **Output
field:** add `StabilityResult.mkt_celsius: Optional[float] = None`
(additive).

**Tests:**

```python
def test_mkt_constant_temperature_equals_input():
    assert abs(mean_kinetic_temperature([25.0, 25.0, 25.0]) - 25.0) < 1e-9

def test_mkt_handles_excursion():
    # 25C for most of the month, 35C for 4 hours (~0.0056 of the time)
    # Expect MKT slightly above 25C
    temps = [25.0] * 1000 + [35.0] * 6
    mkt = mean_kinetic_temperature(temps)
    assert 25.0 < mkt < 30.0   # excursion lifts MKT
```

**Acceptance.** Constant-temperature input → MKT == that temperature;
a known excursion profile matches a hand-computed MKT within
`rtol=1e-3`.

### 5.4 Random-effects / mixed model (opt-in)

Add `--random-effects` flag routing the fit through a mixed model
(batch as a random effect) via `statsmodels.formula.api.mixedlm`.
**Opt-in only**, with a loud warning:

```
"Random-effects model selected. Confidence bounds and the resulting
shelf life DIFFER from the ICH Q1E fixed-effect (pooled/ANCOVA)
approach and are NOT the Q1E default. Use for exploration only."
```

The default remains fixed-effect. Store
`StabilityResult.metadata["model_effects"] = "random" | "fixed"`.

**CLI addition:**

```
--random-effects        Use a mixed model (batch as random effect)
                        instead of the Q1E default fixed-effect ANCOVA.
                        Not the Q1E default. Exploration only.
```

**Tests:**

```python
def test_random_effects_opt_in_differs_and_warns():
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        r_fixed = analyze(..., random_effects=False)
        r_random = analyze(..., random_effects=True)
    assert any("Random-effects model selected" in str(x.message) for x in w)
    assert r_random.metadata.get("model_effects") == "random"
    # The bound and/or shelf life will almost certainly differ
    assert r_random.fit.s_resid != r_fixed.fit.s_resid \
        or r_random.supported_shelf_life_months != r_fixed.supported_shelf_life_months

def test_default_remains_fixed_effect():
    r = analyze(...)   # no --random-effects
    assert r.metadata.get("model_effects", "fixed") == "fixed"
```

**Acceptance.** Opt-in produces the warning and a (likely) differing
bound; default is unchanged and `metadata["model_effects"] == "fixed"`.

---

## SECTION 6: v0.6.0 — EXPORT + UI

### 6.1 PDF export

`reports/pdf.py`: render the existing HTML to PDF with **weasyprint**
(`HTML(string=html).write_pdf(out_path)`); fall back to **wkhtmltopdf**
(via `pdfkit`) if weasyprint is unavailable.

```python
# openpharmastability/reports/pdf.py
from pathlib import Path

def render_pdf(html_path: str, out_path: str,
               backend: str = "auto") -> str:
    """Render an HTML file to PDF. Returns the path to the written PDF.

    backend='auto' tries weasyprint first, then pdfkit. Raises
    RuntimeError if neither is available.
    """
    html = Path(html_path).read_text(encoding="utf-8")
    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(out_path)
        return out_path
    except ImportError:
        pass
    try:
        import pdfkit
        pdfkit.from_string(html, out_path)
        return out_path
    except ImportError:
        raise RuntimeError(
            "PDF export requires weasyprint (preferred) or pdfkit + "
            "wkhtmltopdf. Install with `pip install openpharmastability[pdf]`."
        )
```

**`pyproject.toml` additions:**

```toml
[project.optional-dependencies]
pdf = ["weasyprint>=60"]
pdf-fallback = ["pdfkit>=1.0"]
ui  = ["streamlit>=1.30"]
api = ["fastapi>=0.110", "uvicorn>=0.27", "python-multipart>=0.0.9"]
all = ["weasyprint>=60", "pdfkit>=1.0", "streamlit>=1.30",
       "fastapi>=0.110", "uvicorn>=0.27", "python-multipart>=0.0.9"]
```

**CLI flag:**

```
--pdf PATH              In addition to --output, also write a PDF copy
                        of the report to PATH.
```

**Tests:**

```python
@pytest.mark.skipif(not _has_weasyprint() and not _has_pdfkit(),
                    reason="no PDF backend installed")
def test_pdf_export_produced(tmp_path):
    # ... run analyze, then render_pdf ...
    assert Path(pdf).stat().st_size > 1024   # non-trivial
    assert Path(pdf).read_bytes()[:4] == b"%PDF"  # PDF magic
```

**Acceptance.** PDF is produced and non-empty (`%PDF` magic); skip
with a clear message if neither backend is installed (xfail-import).

### 6.2 Streamlit MVP

`app/streamlit_app.py`: file uploader (CSV/XLSX) → condition selector
(populated from parsed conditions) → attribute multiselect → run
`analyze` / `analyze_multi` → render the HTML report inline
(`st.components.v1.html`) and a download button for HTML/JSON/PDF. No
persistence; stateless.

```python
# app/streamlit_app.py
import streamlit as st
import pandas as pd
from openpharmastability.contracts import DISCLAIMER
from openpharmastability.shelf_life.engine import analyze, analyze_multi
from openpharmastability.plots.confidence_plot import make_confidence_plot
from openpharmastability.reports.html import render_html
from openpharmastability.reports.record import to_decision_record
from openpharmastability.data.io import load_table
from openpharmastability.data.conditions import parse_condition

st.set_page_config(page_title="OpenPharmaStability", layout="wide")
st.title("OpenPharmaStability — decision-support")

st.warning(DISCLAIMER)   # always shown at the top

uploaded = st.file_uploader("Stability data (CSV or XLSX)", type=["csv","xlsx"])
if not uploaded:
    st.stop()

df = load_table(uploaded.name if hasattr(uploaded, "name") else "/tmp/in")
# ... or save to a temp file and load from there for XLSX dispatch ...

condition = st.selectbox("Long-term condition",
                          sorted(df["condition"].unique()))
attrs = st.multiselect("Attributes", sorted(df["attribute"].unique()))

if st.button("Analyze"):
    if len(attrs) == 1:
        result = analyze(uploaded.name, condition=condition, attribute=attrs[0])
    else:
        result = analyze_multi(uploaded.name, condition=condition, attributes=attrs)
    # render inline
    st.components.v1.html(open("report.html").read(), height=1200, scrolling=True)
    st.download_button("Download JSON", to_decision_record(result))
```

**Run:** `streamlit run app/streamlit_app.py`.

**Acceptance.** Streamlit app launches, accepts the example CSV,
shows the disclaimer at the top, runs the analysis, renders the HTML
inline, and offers a JSON download.

### 6.3 FastAPI backend (for a future React frontend)

`api/main.py` with endpoints:

| Method | Path | Body / params | Returns |
|---|---|---|---|
| `POST` | `/analyze` | multipart file + JSON `{condition, attributes[], product_type, options}` | `{job_id, status: "queued"}` |
| `GET` | `/status/{id}` | — | `{job_id, status: queued\|running\|done\|error, error?}` |
| `GET` | `/report/{id}` | `?format=json\|html\|pdf` | the report artifact |

```python
# api/main.py
from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
import uuid, json, pathlib
from openpharmastability.contracts import DISCLAIMER
from openpharmastability.shelf_life.engine import analyze, analyze_multi
# ...

app = FastAPI(title="OpenPharmaStability API", version="0.6.0")
_JOBS: dict[str, dict] = {}   # in-memory; production needs a real queue

@app.post("/analyze")
async def analyze_endpoint(
    file: UploadFile,
    options: str = Form(...),   # JSON-encoded
):
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {"status": "queued"}
    opts = json.loads(options)
    tmp = pathlib.Path(f"/tmp/{job_id}.csv")
    tmp.write_bytes(await file.read())
    try:
        attrs = opts.get("attributes")
        if not attrs or len(attrs) == 1:
            result = analyze(str(tmp), condition=opts["condition"],
                             attribute=(attrs or ["assay"])[0],
                             product_type=opts.get("product_type", "product"))
        else:
            result = analyze_multi(str(tmp), condition=opts["condition"],
                                    attributes=attrs,
                                    product_type=opts.get("product_type", "product"))
        _JOBS[job_id] = {"status": "done", "result": result}
    except Exception as e:
        _JOBS[job_id] = {"status": "error", "error": str(e)}
    return {"job_id": job_id, "status": "queued"}

@app.get("/status/{job_id}")
def status(job_id: str):
    if job_id not in _JOBS: raise HTTPException(404)
    j = _JOBS[job_id]
    return {"job_id": job_id, "status": j["status"], "error": j.get("error")}

@app.get("/report/{job_id}")
def report(job_id: str, format: str = "json"):
    # ... return the artifact, with the disclaimer always present ...
```

Jobs run in a background task (in-memory dict for MVP; document that
production needs a real queue + the GxP limitations remain). Every
response carries the disclaimer. CORS configured for the future
React origin.

**Tests:**

```python
from fastapi.testclient import TestClient
from api.main import app

def test_api_analyze_flow(tmp_path):
    c = TestClient(app)
    with open("examples/assay_3batch.csv", "rb") as f:
        r = c.post("/analyze", files={"file": ("in.csv", f, "text/csv")},
                   data={"options": json.dumps(
                       {"condition": "25C/60RH",
                        "attributes": ["assay"]})})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    # poll
    s = c.get(f"/status/{jid}").json()
    assert s["status"] == "done"
    rep = c.get(f"/report/{jid}?format=json").json()
    assert rep["disclaimer"] == DISCLAIMER
    assert rep["attribute"] == "assay"
    assert "supported_shelf_life_months" in rep
```

**Acceptance.** `TestClient` posts the example CSV, polls status to
`done`, fetches the JSON report and asserts the limiting shelf life
and the verbatim disclaimer.

---

## SECTION 7: PYCACHE / ENVIRONMENT INTEGRITY FIX — **DO THIS FIRST**

**Why:** the re-audit found stale `.pyc` files from a prior session
(`keen-gracious-feynman`) in `openpharmastability/__pycache__`,
`tools/__pycache__`, and `validation/__pycache__`. Stale bytecode
whose `.py` source mtime looks older (e.g. after a checkout, a file
copy that preserved mtimes, or a clock skew across machines) can be
loaded instead of your edited source, silently defeating fixes.
**You will chase ghosts until you clear this.** Do it before reading
anything else technical.

### 7.1 Delete all caches

**Windows PowerShell (run from repo root `E:\STABILITY TOOLKIT`):**

```powershell
# Remove every __pycache__ dir and stray .pyc/.pyo, but NOT inside .venv
Get-ChildItem -Path . -Recurse -Directory -Filter '__pycache__' |
    Where-Object { $_.FullName -notmatch '\\\.venv\\' } |
    Remove-Item -Recurse -Force

Get-ChildItem -Path . -Recurse -Include *.pyc,*.pyo -File |
    Where-Object { $_.FullName -notmatch '\\\.venv\\' } |
    Remove-Item -Force

# Also clear pytest's cache so collection is fresh
Remove-Item -Recurse -Force .\.pytest_cache -ErrorAction SilentlyContinue
```

**bash / Linux / WSL (run from repo root):**

```bash
find . -path ./.venv -prune -o -type d -name '__pycache__' -print0 | xargs -0 rm -rf
find . -path ./.venv -prune -o -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0 | xargs -0 rm -f
rm -rf .pytest_cache
```

### 7.2 Recompile from current source

```bash
# byte-compile everything fresh; -f forces rewrite, ignoring stale timestamps
python -m compileall -f openpharmastability tools validation
```

A nonzero exit or any `SyntaxError` printed here means a source file
is broken — fix it before proceeding.

### 7.3 Reinstall and verify green

```bash
# from an activated venv (see §8.2)
pip install -e ".[dev]"
python -c "import openpharmastability, sys; print('version', openpharmastability.__version__)"
pytest -q
```

Expected at v0.5.1: `360 passed` (see §8.3 for the exact expectation
and how to treat drift). Earlier releases had different counts —
v0.1.0 = 173, v0.1.1 = 184, v0.3.0 = 254, v0.4.0 = ~280, v0.5.0 = 341.

### 7.4 Permanent guard — Makefile target + pre-commit hook

**Add `Makefile` at repo root** (works under WSL/git-bash; Windows
users invoke the PowerShell block above or `make` via git-bash):

```makefile
.PHONY: clean recompile test fresh
clean:
	find . -path ./.venv -prune -o -type d -name '__pycache__' -print0 | xargs -0 rm -rf
	find . -path ./.venv -prune -o -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0 | xargs -0 rm -f
	rm -rf .pytest_cache

recompile: clean
	python -m compileall -f openpharmastability tools validation

# The canonical "I don't trust my environment" command.
fresh: recompile
	pip install -e ".[dev]"
	pytest -q

test:
	pytest -q
```

**Add `.git/hooks/pre-commit`** (`chmod +x`). It refuses a commit if
tracked `.pyc` files exist and runs a fast import smoke test:

```bash
#!/usr/bin/env bash
set -euo pipefail
# 1. No compiled artifacts should ever be committed.
if git diff --cached --name-only | grep -E '\.py[co]$'; then
  echo "ERROR: attempting to commit .pyc/.pyo files. Add them to .gitignore." >&2
  exit 1
fi
# 2. Source must import cleanly from a fresh interpreter (catches stale-cache masking).
python -B -c "import openpharmastability" || { echo "import failed"; exit 1; }
```

**Add to `.gitignore` (create if missing):**

```
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
build/
*.egg-info/
```

The `python -B` flag (also settable as env
`PYTHONDONTWRITEBYTECODE=1`) tells contributors to run without writing
bytecode while developing, which sidesteps the whole class of
problem. Document it in the README dev section.

**Acceptance criterion for §7:** after running `make fresh` (or the
PowerShell + recompile + reinstall + pytest sequence), `pytest -q`
prints the current expected count (`360 passed` at v0.5.1; see §8.3
for any drift) and `git status` shows no untracked `__pycache__`
directories.

---

## SECTION 8: AGENT HANDOVER PROTOCOL — **READ FIRST**

### 8.1 Read order for docs

1. **This file, §7** — fix the environment before believing any
   test result.
2. **`AGENTS.md`** — the v0.1 build plan; explains the sub-agent
   contract model and the "contracts.py is frozen" rule.
3. **`OpenPharmaStability.md`** — the product behavior spec (source
   of truth for *what the tool should do*).
4. **`openpharmastability/stats/MATH_SPEC.md`** — the locked
   statistical math. Verify any math change against this; if you
   must change it, update it in the same commit.
5. **`openpharmastability/contracts.py`** — read in full. It is the
   API map.
6. **`CHANGELOG.md`** — what already shipped.
7. This file, §1–§10, for whatever release you are executing.

After reading, **verify** the snapshot in the Preamble still matches
reality (`git log --oneline -5`, module list, `__version__`). If they
diverge, trust the code and note the divergence in your first commit
message.

### 8.2 Environment setup (copy-paste ready)

**Windows PowerShell:**

```powershell
cd "E:\STABILITY TOOLKIT"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

**bash / WSL / Linux:**

```bash
cd "/path/to/STABILITY TOOLKIT"
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Python **3.11+** is required (`pyproject.toml`
`requires-python = ">=3.11"`). Runtime deps: `pandas>=2.0`,
`numpy>=1.24`, `scipy>=1.10`, `statsmodels>=0.14`, `matplotlib>=3.7`,
`jinja2>=3.1`. Dev: `pytest>=7.4`.

### 8.3 How to verify current state is healthy

```bash
pytest -q
```

Expected today (v0.5.1): **`360 passed`**. Skips are NOT expected —
`validation/conftest.py` hard-requires the v0.5 modules and exits with
code 2 at collection time if any is missing. Earlier counts: 173
(v0.1.0) → 184 (v0.1.1) → 254 (v0.3.0) → ~280 (v0.4.0) → 341
(v0.5.0). Then run the end-to-end smoke:

```bash
openpharmastability analyze examples/assay_3batch.csv \
    --condition "25C/60RH" --attribute assay --output build/report.html
```

Expected stdout includes `model: common_slope_batch_intercepts`,
`poolability: partial`, a `statistical crossing:` near the value in
`examples/assay_3batch.expected.json` →
`shelf_life.statistical_crossing_months`, and writes
`build/report.html`, `build/report.json`, `build/confidence_plot.png`.

Then run the independent validator:

```bash
python tools/regen_expected.py --check
```

Expected: exit code 0 (prints nothing alarming). This proves the
engine output still matches the independently-computed golden
values.

### 8.4 Known-open warnings vs blockers

| Item | Class | Action |
|---|---|---|
| HTML timestamp makes byte output non-identical run-to-run (numbers identical) | **known-open** (Fix 1.1) | Not a blocker. Numeric determinism holds. |
| `schema._infer_direction_from_spec` false-positive warning when both specs present AND direction declared consistently | **known-open** (Fix 1.2) | Cosmetic; warning noise only. |
| `regen_expected.py` uses statsmodels for COMMON_SLOPE fit (not pure numpy) | **known-open** (Fix 1.3) | Reduces independence claim; not a correctness bug. |
| Stale `.pyc` from prior session | **BLOCKER** | §7 — clear before anything. |
| `pytest` not green / `regen --check` nonzero | **BLOCKER** | Stop and fix before new work. |
| `apply_extrapolation_caps` drops a new `StabilityResult` field | **BLOCKER if introduced** | See Preamble + §9.9 test. |

### 8.5 How to run the regen validator

- **Regenerate** the golden file from the dataset (overwrites
  `examples/assay_3batch.expected.json`):
  ```bash
  python tools/regen_expected.py
  ```
- **Check only** (CI-safe; never writes; exit 0 if engine matches
  golden):
  ```bash
  python tools/regen_expected.py --check
  ```
- **Rule:** never regenerate without first running `--check` and
  understanding *why* it diverged. A divergence is either a real
  regression (fix the code) or an intended math change (then
  regenerate AND bump the changelog AND explain).

### 8.6 Git workflow assumptions

- **Branch per feature**, named
  `feature/<area>-<short>` (e.g. `feature/xlsx-input`,
  `fix/direction-warning`), `fix/<short>` for patches,
  `release/v0.2.0` for release prep.
- **Commit message format** (Conventional Commits):
  `type(scope): summary` where
  `type ∈ {feat, fix, test, docs, refactor, chore, perf}`. Body
  explains *why*. Footer references the section, e.g.
  `Refs NEXT_STEPS §2.1`. Example:
  ```
  feat(io): add XLSX input via openpyxl

  Adds load_table() dispatcher; load_csv kept as thin wrapper for
  back-compat. New tests in validation/test_data_io.py cover .xlsx
  and bad-extension errors.

  Refs NEXT_STEPS §2.1
  ```
- One logical change per commit. Tests land in the **same** commit
  as the code they cover. Never commit with a red `pytest`.
- Tag releases `vMAJOR.MINOR.PATCH` after the version bump in all
  three places (Preamble).

### 8.7 What NOT to do

1. **Do NOT regenerate the golden file**
   (`regen_expected.py` without `--check`) before running `--check`
   and confirming the divergence is intentional.
2. **Do NOT edit `contracts.py` to *change* an existing
   field/enum value/constant.** Additive-only: new optional
   dataclass fields **with defaults**, new enum members, new
   constants. Changing a value (e.g. `POOLABILITY_ALPHA`) is a
   breaking change requiring a major bump and golden regeneration.
3. **Do NOT add a `StabilityResult` field without updating the
   copy block in `extrapolation.py:51-69`.** (Better: refactor
   that to `dataclasses.replace` — see §9.10.)
4. **Do NOT write zeros into the `value` column for BQL/missing
   data.** That is a regulatory landmine; `bql.py` documents this
   explicitly.
5. **Do NOT silently change the t-quantile logic.** It lives in
   two places only (`bounds.py:54` and `bounds.py:216`); changing
   either changes every shelf life. Touch with a test.
6. **Do NOT claim regulatory compliance** in code/copy/reports.
   The disclaimer (`contracts.py:54`, `DISCLAIMER`) is mandatory
   and verbatim.
7. **Do NOT commit `.pyc`, `.venv`, or `build/` artifacts.**
8. **Do NOT introduce RNG into the analysis path.** The core is
   deterministic; `seed` is recorded for metadata only.

---

## SECTION 9: TEST COVERAGE GAPS TO FILL NOW (v0.1.1)

Add all of these alongside the §1 fixes. Target: bring 173 → ~185+.

| # | Test name | File | Missing assertion |
|---|---|---|---|
| 9.1 | `test_regen_does_not_import_statsmodels` | `test_regen.py` | regen uses pure numpy (see Fix 1.3). |
| 9.2 | `test_json_record_deterministic_with_fixed_epoch` | `test_reporting.py` | `to_decision_record` produces byte-identical JSON across two runs given a fixed `source_epoch`. Today only HTML determinism is loosely covered. |
| 9.3 | `test_disclaimer_verbatim_in_html` | `test_reporting.py` | Rendered HTML contains `contracts.DISCLAIMER` **verbatim** (substring check on the exact frozen string). |
| 9.4 | `test_disclaimer_verbatim_in_json` | `test_reporting.py` | The decision record (or its rendered form) carries the verbatim disclaimer. NOTE: `record.py` does **not** currently include the disclaimer — add a `"disclaimer": DISCLAIMER` key to `to_decision_record` and assert it. |
| 9.5 | `test_bql_substitute_loq_raises` | `test_data_io.py` (or a new `test_data_bql.py`) | `apply_bql_policy(df, "substitute_loq")` raises `NotImplementedError`; same for `"substitute_half_loq"`. Asserts the message mentions "seam"/"not implemented". |
| 9.6 | `test_bql_unknown_policy_raises_valueerror` | same | `apply_bql_policy(df, "bogus")` raises `ValueError`. |
| 9.7 | `test_unknown_direction_warns_not_silent` | `test_engine.py` | Data with neither spec finite → `Direction.UNKNOWN`; `analyze` surfaces a warning AND `find_crossing` raises `ValueError` (no spec) rather than returning a bogus shelf life. |
| 9.8 | `test_bidirectional_direction_behavior_explicit` | `test_stats_crossing.py` | With both specs + `BIDIRECTIONAL`, the current heuristic (`bounds._spec_for_direction`, line 251) picks `candidates[0]` (lower). Lock this behavior with an explicit test so the v0.2 bidirectional rewrite (§2.4) is a *deliberate* change, not a silent one. |
| 9.9 | `test_extrapolation_caps_preserves_all_result_fields` | `test_extrapolation.py` | Build a `StabilityResult`, run `apply_extrapolation_caps`, assert **every** field is preserved/copied. This is the regression guard for the Preamble copy-block hazard. |
| 9.10 | `test_dataclasses_replace_refactor` (optional) | `test_extrapolation.py` | After refactoring `extrapolation.py:51-69` to `dataclasses.replace(result, warnings=..., extrapolation_flag=..., supported_shelf_life_months=...)`, assert identical output to the manual copy. **Recommended refactor** — eliminates the copy-block bug class permanently. |
| 9.11 | `test_replicate_unknown_policy_raises` | `test_data_*` | `apply_replicate_policy(df, "bogus")` raises `ValueError`. |
| 9.12 | `test_flat_slope_status` / `test_fail_at_baseline` / `test_no_crossing` | `test_stats_crossing.py` | Confirm all four `CrossingStatus` values are each hit by at least one test (audit found edge-status coverage thin). |
| 9.13 | `test_single_batch_warns` | `test_engine.py` | `n_batches < 3` produces the Q1E warning (`engine.py:214`). |
| 9.14 | `test_engine_handles_single_time_point` | `test_engine.py` | A dataset with one time point (no slope estimable) returns `CrossingStatus.FLAT_OR_OPPOSITE` (or `NO_CROSSING`) without raising. |
| 9.15 | `test_engine_handles_nan_value` | `test_engine.py` | A NaN in the `value` column is either dropped with a warning or raises `ValueError`; assert one or the other explicitly (locks the behavior). |
| 9.16 | `test_engine_handles_negative_time` | `test_engine.py` | A row with `time_months < 0` is either rejected at schema time or filtered out with a warning; no silent inclusion. |
| 9.17 | `test_bql_substitute_half_loq_factor_is_05` | `test_data_bql.py` | After Fix 1.3, assert `substitute_half_loq` writes `value == loq / 2` (locks the 0.5 factor in a test, not just the docstring). |
| 9.18 | `test_bql_no_zero_written_under_any_policy` | `test_data_bql.py` | Across all five policies (`exclude`, `flag`, `substitute_loq`, `substitute_half_loq`, `manual_review_flag`), the function never writes `0.0` into the `value` column for a BQL row. |

**Implementation detail for 9.9** — the regression guard:

```python
import dataclasses
from openpharmastability.contracts import StabilityResult, PoolabilityResult, \
    CrossingResult, DiagnosticsResult, FitResult, Direction, ModelKind, \
    Poolability, CrossingStatus
from openpharmastability.shelf_life.extrapolation import apply_extrapolation_caps

def test_extrapolation_caps_preserves_all_result_fields():
    """Regression guard: every StabilityResult field must be carried
    through apply_extrapolation_caps. If you add a field to the
    contract, add it to this test (or refactor to dataclasses.replace)."""
    base = StabilityResult(
        attribute="assay", condition="25C/60RH",
        direction=Direction.DECREASING,
        model=ModelKind.COMMON_SLOPE,
        poolability=PoolabilityResult(Poolability.PARTIAL, 0.4, 0.3, 0.25, []),
        fit=FitResult(ModelKind.COMMON_SLOPE, {}, 30, 0.5, None,
                      lambda t: 100, {}, []),
        crossing=CrossingResult(18.0, CrossingStatus.CROSSED, "B2", []),
        supported_shelf_life_months=18,
        statistical_crossing_months=18.0,
        observed_data_months=12.0,
        extrapolation_flag=True,
        diagnostics=DiagnosticsResult(True, True, True, [], []),
        warnings=["orig"],
        metadata={"k": "v"},
        deliverable_term="shelf life",
        product_type="product",
        plot_filename="p.png",
    )
    out = apply_extrapolation_caps(base)
    # Every field of `base` must equal the corresponding field of `out`
    # except for the three the function is allowed to change.
    excluded = {"warnings", "extrapolation_flag", "supported_shelf_life_months"}
    for f in dataclasses.fields(StabilityResult):
        if f.name in excluded:
            continue
        assert getattr(out, f.name) == getattr(base, f.name), \
            f"field {f.name!r} dropped or mutated by apply_extrapolation_caps"
```

**Acceptance criterion for §9.** All listed tests present and
passing; `pytest -q` green; `dataclasses.replace` refactor (9.10)
merged so future field additions cannot be dropped; the BQL
"never write zero" guard (9.18) is in place as a hard invariant.

---

## SECTION 10: REGULATORY WATCH + VERSIONING STRATEGY

### 10.1 ICH Q1 consolidated guideline watch

The ICH Q1A–Q1F + Q5C series is being consolidated into a **single
Q1** guideline. Status to track (as of this writing): the
consolidated **ICH Q1** reached **Step 2b in April 2025**; the
**EMA consultation closed July 2025**; it has **not yet reached
Step 4 (final)**. Until Step 4, this toolkit implements
**Q1A(R2) + Q1E** and labels everything "Q1E-inspired."

**Watch checklist (revisit each quarter / on any ICH news):**

- Has consolidated Q1 reached Step 4? (If yes → trigger §10.2
  migration.)
- Did the poolability α (0.25) change? The mean-response one-sided
  95% bound? The 2× / +12-month extrapolation caps? The
  significant-change checklist?
- Any change to retest-period vs shelf-life terminology.

Record findings in `CHANGELOG.md` under a "Regulatory watch"
heading with dates.

### 10.2 Structuring for the Q1A+Q1E → consolidated Q1 switch

Introduce a **guidance-profile abstraction** now (cheap insurance):

```python
# openpharmastability/regulatory/profile.py
from dataclasses import dataclass, field
from openpharmastability.contracts import DISCLAIMER

@dataclass(frozen=True)
class GuidanceProfile:
    name: str                       # "Q1A_R2+Q1E" | "Q1_consolidated"
    poolability_alpha: float
    confidence: float
    one_sided_quantile: float
    two_sided_quantile: float
    extrapolation_max_factor: float
    extrapolation_max_months_beyond: float
    assay_change_threshold_pct: float = 5.0
    significant_change_criteria: tuple[str, ...] = field(default_factory=lambda:
        ("assay", "degradant", "physical", "ph", "dissolution"))
    disclaimer: str = DISCLAIMER

Q1AE = GuidanceProfile(
    name="Q1A_R2+Q1E",
    poolability_alpha=0.25,
    confidence=0.95,
    one_sided_quantile=0.95,
    two_sided_quantile=0.975,
    extrapolation_max_factor=2.0,
    extrapolation_max_months_beyond=12.0,
)
# Q1_CONSOLIDATED = GuidanceProfile(...) defined when Step 4 lands.
```

Migrate the hard-coded constants in `contracts.py`
(`POOLABILITY_ALPHA`, `CONFIDENCE`, the two quantiles, the two
extrapolation caps) to be **sourced from the active profile**,
defaulting to `Q1AE`. Add `analyze(..., profile=Q1AE)`. When
consolidated Q1 ships, add a `Q1_CONSOLIDATED` profile and a
`--guidance q1` flag — no algorithm rewrite, just a new profile +
new golden file. Keep both profiles available for
comparison/audit.

### 10.3 Versioning strategy (SemVer)

- **PATCH (`0.1.x`):** bug fixes, doc/test additions, warning-text
  fixes, no behavior change to numeric output (§1 = `0.1.1`).
- **MINOR (`0.x.0`):** new features that are **additive** and
  backward-compatible — new CLI flags with defaults, new optional
  contract fields, new modules (§§2–6 are minors).
- **MAJOR (`x.0.0`):** any change that alters numeric output for
  the *same* input or breaks the public API/contracts — e.g.
  changing `POOLABILITY_ALPHA`, the default quantile, the
  extrapolation caps, or switching the default guidance profile
  to consolidated Q1. **Major bumps require regenerating the
  golden file** and a migration note.
- Version lives in **three** places (Preamble) — bump all three
  in one commit.

**Version-bump decision table:**

| Change | Bump |
|---|---|
| Fix 1.1, 1.2, 1.3 (§1) — *shipped in v0.1.1* | PATCH → 0.1.1 |
| Add XLSX input, multi-attribute, degradant upper, bidirectional (§2) — *shipped in v0.2.0* | MINOR → 0.2.0 |
| Hotfix on v0.2.0 (XLSX metadata, multi HTML plot paths, bql-policy wiring) — *shipped in v0.2.1* | PATCH → 0.2.1 |
| Add BQL substitution, log transform, spec_type, attribute metadata (§3) — *shipped in v0.3.0* | MINOR → 0.3.0 |
| Hotfix on v0.3.0 (CLI version + bql-policy choice, dataclass field, plot bug) — *shipped in v0.3.1* | PATCH → 0.3.1 |
| Add ICH Q1A significant-change gating (§4) — *shipped in v0.4.0* | MINOR → 0.4.0 |
| Add Arrhenius, MKT, reduced designs, random effects opt-in (§5) — *shipped in v0.5.0* | MINOR → 0.5.0 |
| Audit patch on v0.5.0 (Arrhenius hook filter + direction, mixed-model convergence surfacing, MKT-without-temp_c warning, docs sync, hard-require v0.5 modules) — *shipped in v0.5.1* | PATCH → 0.5.1 |
| Add PDF, Streamlit/Cloudflare Pages UI, FastAPI (§6) | MINOR → 0.6.0 |
| Switch default profile to consolidated Q1 | MAJOR → 1.0.0 |
| Change `POOLABILITY_ALPHA` from 0.25 to anything else | MAJOR |

### 10.4 Disclaimer update checklist

When regulatory guidance changes, before editing
`contracts.DISCLAIMER` (`contracts.py:54`):

1. Confirm the new guidance reference (e.g. "ICH Q1E" → "ICH Q1
   (2026)") and update the "...-inspired" wording.
2. Re-confirm the tool is still **not** a validated GxP / 21 CFR
   Part 11 system — keep that clause verbatim unless legal review
   says otherwise.
3. Update every place the disclaimer is asserted verbatim: tests
   9.3/9.4, the HTML template, the JSON record (after adding it
   per 9.4), the CLI footer (`cli.py:140`).
4. Because tests assert the disclaimer **verbatim**, a disclaimer
   change is a deliberate test update — land them together.
5. A disclaimer wording change that reflects a guidance switch
   is at least a MINOR bump; if it accompanies an algorithm
   change, MAJOR.

---

## Appendix A — Cross-cutting hazards (memorize)

1. **`extrapolation.py` copy block** — every `StabilityResult`
   field added in §§2/4/5 must be copied there, or refactor to
   `dataclasses.replace` (§9.10). This is the #1 silent-bug
   source.
2. **t-quantile** — only `bounds.py:54` (`_quantile_for`) and
   `bounds.py:216` (`_bound_multiplier`) decide 0.95 vs 0.975.
   The bidirectional work (§2.4) must make `_bound_multiplier`
   quantile-aware instead of hard-coding one-sided.
3. **Version triple-sync** — `__init__.py`,
   `contracts.py:TOOL_VERSION`, `pyproject.toml`.
4. **Never write zeros for BQL/missing.**
5. **Golden file discipline** — `--check` before regenerate;
   regenerate only on *intended* numeric change; major bump on
   numeric change.
6. **`contracts.py` is additive-only** — see §8.7.
7. **Stale `__pycache__`** — see §7.
8. **Rounding shelf life** — `supported_shelf_life_months` is
   `floor()`, never `round()` or `ceil()`. A shelf life that is
   too long is a patient-safety issue.

---

## Appendix B — Release checklist (per minor/major)

```
[ ] make fresh                                  # clean caches, recompile, reinstall, pytest green
[ ] python tools/regen_expected.py --check       # 0 (or regenerate if intended)
[ ] new tests added in same commits as features
[ ] version bumped in all three locations
[ ] CHANGELOG.md updated (incl. Regulatory watch if relevant)
[ ] disclaimer verbatim everywhere (tests 9.3/9.4 green)
[ ] CLI --help reflects new flags
[ ] end-to-end smoke run produces HTML+JSON+PNG
[ ] git tag vX.Y.Z
```

**Per-section reminders for the checklist:**

- **v0.1.1 (§1, §9):** confirm `regen_expected.py` no longer
  imports statsmodels; confirm `--source-epoch` and
  `SOURCE_DATE_EPOCH` both work; confirm the JSON carries the
  disclaimer (test 9.4).
- **v0.2.0 (§2):** confirm `analyze_multi` end-to-end; the
  degradant upper bound matches a hand-computed value; the
  bidirectional path uses 0.975 (test 2.4).
- **v0.3.0 (§3):** confirm BQL substitution never writes zero
  (test 9.18); confirm log transform handles `value <= 0` and
  recovers a known slope.
- **v0.4.0 (§4):** confirm all six branches of the
  `extrapolation_allowance` decision table.
- **v0.5.0 (§5):** confirm Arrhenius 1-temp raises
  `NotImplementedError`; confirm MKT constant-input ==
  constant-output.
- **v0.6.0 (§6):** confirm PDF magic bytes (`%PDF`) when
  backend installed; confirm Streamlit boots; confirm API
  `TestClient` flow.

---

*End of NEXT_STEPS.md. Bump this file (not just the code) whenever
guidance, scope, or contracts change. Pin a CHANGELOG entry.*
