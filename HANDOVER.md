# HANDOVER.md — OpenPharmaStability cold-start briefing

> **You are picking up OpenPharmaStability v0.5.1 on a fresh machine.**
> Read this file top to bottom, run the verification block, then move on.
> If something in here disagrees with the code, the **code** is wrong —
> but only after you have re-read the relevant contract.

---

## 1. Positioning

**OpenPharmaStability v0.5.1** is an ICH Q1E-inspired Python toolkit
that ingests a CSV or XLSX of pharmaceutical stability data and
produces a shelf-life estimate, a confidence-bound plot, an HTML
report, and a machine-readable JSON decision record. The v0.1
baseline (one attribute, one long-term condition) has been extended
through v0.2 (multi-attribute + XLSX), v0.3 (data quality + BQL +
transform evidence), v0.4 (ICH Q1A significant-change gating), and
v0.5 (Arrhenius / MKT / reduced designs / random-effects opt-in,
plus the v0.5.1 audit patch). It is a **decision-support /
educational** tool: not a regulatory submission tool, not
submission-ready, and **not** a validated GxP / 21 CFR Part 11
system. The mandatory disclaimer lives at
`openpharmastability/contracts.py::DISCLAIMER` and is rendered
verbatim in every HTML report.

---

## 2. Quick facts

| Item | Value |
|---|---|
| Tool name | `openpharmastability` |
| Version | `0.5.1` (declared in `__init__.py`, `contracts.py::TOOL_VERSION`, and `pyproject.toml` — keep in sync) |
| Python | `3.11+` (developed on 3.12) |
| Install (editable, with dev deps) | `pip install -e ".[dev]"` |
| CLI entry point | `openpharmastability` (console script) |
| CLI invocation | `openpharmastability analyze <csv> --condition "25C/60RH" --attribute assay --output report.html` |
| Golden CSV | `examples/assay_3batch.csv` (42 rows, 3 batches, 7 time points) |
| Golden expected | `examples/assay_3batch.expected.json` |
| Regeneration script | `tools/regen_expected.py` (independent numpy + scipy.stats.t + brentq; no project imports) |
| Test count | **360** pytest tests across the files in `validation/` (count via `pytest --collect-only`) |
| Reported shelf life on the golden dataset | **17 months** (statistical crossing 17.955 mo, B2, COMMON_SLOPE) |
| Frozen contracts | `openpharmastability/contracts.py` (read-only after release) |
| Multi-attribute fixture | `examples/multi_attribute.csv` (48 rows, 2 attributes) + `examples/multi_attribute_metadata.csv` — limiting impurity_a at 7 months |
| BQL fixture | `examples/bql_attribute.csv` (30 rows, 1 BQL row with loq=88.0) — supports `exclude` / `flag` / `substitute_loq` / `substitute_half_loq` / `manual_review` |
| Data quality fixture | `examples/data_quality_messy.csv` (16 rows; 1 ERROR no-spec + 2 WARNINGS + 1 INFO) |
| Significant-change fixtures (v0.4) | `examples/assay_long_term.csv` + `assay_accelerated_change_lt_3mo.csv` + `assay_accelerated_change_3_6mo.csv` + `assay_intermediate_no_change.csv` + `assay_intermediate_change.csv` |
| v0.5 modules | `stats/arrhenius.py`, `stats/mkt.py`, `regulatory/reduced_design.py`, `regulatory/significant_change.py` — hard-required by `validation/conftest.py` |

### Recent releases

| Version | Theme | What it added |
|---|---|---|
| `0.5.1` (current) | Audit patch on v0.5.0 | Arrhenius hook filtered to selected attribute + direction-aware; mixed-model convergence / boundary status surfaced at `StabilityResult.model_convergence` + warnings + HTML; explicit "no temp_c" warning when `--mkt` is requested without temperature data; docs synced; v0.5 tests now hard-require the v0.5 modules. |
| `0.5.0` | Advanced statistics | Arrhenius (`stats/arrhenius.py`), MKT (`stats/mkt.py`), reduced-design detection (`regulatory/reduced_design.py`), opt-in random-effects mixed model. All opt-in; default path unchanged. |
| `0.4.0` | ICH Q1A significant-change gating | `regulatory/significant_change.py`; Q1E extrapolation decision tree; new `StabilityResult` fields for accelerated/intermediate flags + rationale; `--accelerated-condition`, `--intermediate-condition`, `--no-significant-change-gate` CLI flags. |
| `0.3.0` | Data quality + BQL + transform evidence | `data/quality.py` 16-check audit; real BQL policies (`substitute_loq`, `substitute_half_loq`, `manual_review`); `stats/transforms.py` exploratory transform-candidate evidence. |
| `0.2.0` | Multi-attribute + XLSX | `data/xlsx.py`, `data/metadata.py`, `shelf_life/multi_engine.py`, `shelf_life/limiting.py`; per-attribute analysis + limiting-attribute selection. |
| `0.1.x` | Initial baseline | Single attribute, single long-term condition, fixed-effect ANCOVA, one-sided 95% bound, lower-spec crossing, HTML+JSON report. |

---

## 3. Environment setup (copy-paste ready)

> **Clear `__pycache__` first.** Stale `.pyc` files on a Linux mount
> have already masked a v0.1 audit fix. This is the #1 cause of
> mysterious test mismatches.

### Windows PowerShell

```powershell
Get-ChildItem -Path "E:\STABILITY TOOLKIT" -Recurse -Filter "__pycache__" |
    Remove-Item -Recurse -Force
Get-ChildItem -Path "E:\STABILITY TOOLKIT" -Recurse -Include "*.pyc" |
    Remove-Item -Force

cd "E:\STABILITY TOOLKIT"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

pytest -q
```

### bash (git-bash on Windows, or Linux/WSL mount of the same folder)

```bash
BASE="E:/STABILITY TOOLKIT"            # on Windows; on Linux use the mounted path
find "$BASE" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
find "$BASE" -name "*.pyc" -delete 2>/dev/null; true

cd "$BASE"
python -m venv .venv
source .venv/Scripts/activate          # Windows git-bash
# source .venv/bin/activate           # Linux/WSL
pip install -e ".[dev]"

pytest -q
```

---

## 4. Healthy state verification

A healthy v0.5.1 install is fully characterised by these four
commands. All four must succeed.

### 4.1 `pytest -q` — exact expected output

```text
360 passed in <Xs>
```

Pass criteria:

- The exact count is **360** (the per-file collection map is in
  the `pytest --collect-only -q` output; ~33 test files under
  `validation/`).
- `validation/conftest.py` must import cleanly. If any of the v0.5
  modules (`stats.arrhenius`, `stats.mkt`,
  `regulatory.reduced_design`, `regulatory.significant_change`)
  is missing, the conftest exits with code 2 at collection time
  ("Missing v0.5.0 modules"). Reinstall the package
  (`pip install -e .[dev]`) to fix.
- The golden test
  `validation/test_golden.py::test_engine_common_slope_matches_golden`
  must pass — primary integrity gate.
- The cross-check test
  `validation/test_stats_bounds.py::test_common_slope_bound_uses_full_cov`
  must pass — independent math verification (it builds the c-vector
  from the parameter name list and asserts agreement with `bounds.py`).
- `0 failed`, `0 errors`. Statsmodels deprecation warnings and a
  handful of NumPy `RuntimeWarning`s from the MKT empty-input
  test are tolerated.

### 4.2 CLI run — exact expected artifact

```bash
cd "E:/STABILITY TOOLKIT"
source .venv/Scripts/activate
openpharmastability analyze examples/assay_3batch.csv \
    --condition "25C/60RH" --attribute assay --output build/report.html
```

Pass criteria:

- Exit code `0`.
- Artifacts written: `build/report.html`, `build/report.json`,
  `build/confidence_plot.png`.
- `report.json` and the HTML body contain a line of the form:

  ```text
  supported shelf life: 17 months
  ```

  (or `Retest period: 17 months` with `--product-type substance`).
- `report.json` carries a top-level `model_convergence` dict
  (v0.5.1+). For the default OLS / fixed-effect path it is
  `{"converged": true, "boundary": false, "message": "OLS"}`.
- The HTML contains the verbatim string from `contracts.DISCLAIMER`
  and explicitly uses **"shelf life"** (product) or **"retest
  period"** (substance).
- Numbers in `report.json` and the HTML body match `expected.json` to
  `rtol=1e-9`. Only the ISO-8601 timestamp in the metadata block
  differs between runs unless `--source-epoch` is used (v0.1.1+).

### 4.3 Golden regeneration check — exact expected exit

```bash
python tools/regen_expected.py --check
```

Pass criteria:

- Exit code `0`. Stdout ends with a one-line OK message.
- Exit code `1` means the committed golden file diverges from the
  independent recomputation. **Do not run `--write`** until you
  understand why — the divergence is almost always either a real
  source bug or a stale `__pycache__`.

### 4.4 v0.5 module import — fail-fast guard

```bash
python -c "from openpharmastability.stats.arrhenius import fit_arrhenius; \
            from openpharmastability.stats.mkt import mean_kinetic_temperature; \
            from openpharmastability.regulatory.reduced_design import detect_reduced_design; \
            from openpharmastability.regulatory.significant_change import evaluate_significant_change; \
            print('v0.5 modules OK')"
```

Pass criteria:

- Exit code `0`. Stdout prints `v0.5 modules OK`.
- An `ImportError` here means the package is partially installed;
  `validation/conftest.py` will exit with code 2 the next time you
  run `pytest`.

---

## 5. Hard rules (do not violate)

These invariants are enforced by a contract constant, a test, or a
code review check. Do not relax any of them.

1. **One-sided 95% t-quantile is `student_t.ppf(0.95, df)`, not 0.975.**
   Constant at `contracts.ONE_SIDED_T_QUANTILE = 0.95`. The two-sided
   0.975 lives separately at `contracts.TWO_SIDED_T_QUANTILE`. The
   cross-check test
   `test_stats_bounds.py::test_common_slope_bound_uses_full_cov`
   guards this.

2. **Supported shelf life is rounded DOWN to whole months, never up.**
   Implemented in `shelf_life/engine.py` when materialising
   `StabilityResult.supported_shelf_life_months`. A wrong shelf life
   that is too long is a patient-safety issue; rounding up is never
   acceptable.

3. **Multi-batch crossing solver takes the worst-case (earliest)
   batch.** For COMMON_SLOPE and SEPARATE models, evaluate each
   batch's own lower bound, then take the smallest positive `t` at
   which any batch's bound crosses the spec. Record
   `CrossingResult.governing_batch` (e.g. `B2` on the golden dataset).

4. **Batches are a FIXED EFFECT (ICH Q1E).** A random-effects /
   mixed-model treatment is opt-in only and would change the
   confidence bounds. Poolability is the 3-step nested ANCOVA at
   `alpha = contracts.POOLABILITY_ALPHA = 0.25`. See
   `stats/poolability.py`.

5. **`contracts.py` is FROZEN after a release.** Propose changes via
   the orchestrator / handover conversation; do not edit it
   unilaterally. If you must touch it, every caller has to be updated
   atomically. The dataclasses and enums in this file are the public
   API every other module imports.

6. **Regenerate `expected.json` ONLY via `tools/regen_expected.py`.**
   The script is independent (no `openpharmastability` imports —
   only `numpy`, `scipy.stats.t`, `pandas`, `brentq`) so the golden
   file is verifiable by anyone with the dataset and a Python
   interpreter. After any regeneration, immediately run
   `python tools/regen_expected.py --check` to confirm the on-disk
   file still matches.

7. **The HTML report must contain the verbatim disclaimer from
   `contracts.DISCLAIMER`** and must use the correct deliverable
   term: **"shelf life"** for a drug product (default) and **"retest
   period"** for a drug substance. The engine sets this from
   `product_type` into `StabilityResult.deliverable_term`; the report
   template must render the matching phrase.

---

## 6. Open warnings (v0.5.1 status)

All three v0.1.1 known-open items are now **resolved**:

- HTML timestamp determinism — fixed in v0.1.1 via `--source-epoch` /
  `SOURCE_DATE_EPOCH`. Two runs with the same epoch produce byte-
  identical JSON.
- `schema._infer_direction_from_spec` false-positive warning — fixed
  in v0.1.1; declaring `decreasing` or `increasing` on a dataset with
  both spec limits no longer warns.
- `tools/regen_expected.py` independence — fixed in v0.1.1; the
  script is pure numpy + scipy.stats.t + pandas + brentq with no
  statsmodels or project imports.

The v0.5.1 release closed the three v0.5.0 audit items below.
There are currently **no open known warnings**.

### 6.1 Arrhenius hook now attribute-filtered and direction-aware (resolved in v0.5.1)

**What it was.** The v0.5.0 `_compute_arrhenius` helper in the
engine read the raw DataFrame to derive per-temperature rates and
implicitly assumed a decreasing degradation (`rate = -slope`). On
a mixed-attribute file the rates were contaminated by rows from
other attributes, and on an increasing degradant the sign of the
rate was wrong. The Arrhenius parameters silently flipped.

**Resolution in v0.5.1.** The helper now accepts the
`ValidatedData` (which knows the active attribute and the declared
direction) and computes `rate = sign(direction) * (-slope)` per
temperature on the per-attribute, per-direction-filtered rows.
The exploration-only caveat in the report is unchanged; the fix
prevents the silent contamination. Covered by new direction tests
in `validation/test_arrhenius.py` and `validation/test_engine_v050.py`.

### 6.2 Mixed-model convergence / boundary status now surfaced (resolved in v0.5.1)

**What it was.** The v0.5.0 `random_effects=True` path stored a
`convergence` sub-block inside `fit.design`. Nothing in the JSON
record, the HTML report, or the warnings list mentioned it, so a
mixed-model run that hit a boundary (random-effect variance → 0)
or failed to converge looked indistinguishable from a healthy one.

**Resolution in v0.5.1.** The `StabilityResult.model_convergence`
field is now a top-level dict (default
`{"converged": true, "boundary": false, "message": ""}` — populated
on every result for both OLS and mixed paths). A warning is appended
when the mixed model hits a boundary or fails to converge, and the
single-attribute HTML report renders a status line. Covered by
tests in `validation/test_reporting.py`,
`validation/test_multi_reporting.py`, and
`validation/test_stats_regression.py`.

### 6.3 MKT-without-temp_c now warns (resolved in v0.5.1)

**What it was.** Requesting `--mkt` on an input with no `temp_c`
column silently set `mkt_celsius = None` with no surface signal in
the warnings list.

**Resolution in v0.5.1.** The engine now appends
`"MKT requested but no temp_c column in the input; mkt_celsius is None."`
to the warnings list so the report is honest about why MKT is
missing. Covered by a new test in `validation/test_engine_v050.py`.

---

## 7. Audit trail

The complete history is in **`CHANGELOG.md`**. Summary of releases:
v0.2.1 (hotfix) — XLSX metadata-sheet detection, multi HTML plot
paths, XLSX file handle closure, bql-policy wiring, multi metadata
merge. v0.3.0 — data quality audit, real BQL policies, transform-
candidate evidence, diagnostics detail, report upgrade. v0.3.1 —
CLI version + bql-policy choice fix, `BQLSummary` as a proper
field, `apply_extrapolation_caps` via `dataclasses.replace`,
disclaimer in single-attribute JSON, quality wiring into
`engine.analyze`, plot-bound bugfix. v0.4.0 — ICH Q1A
significant-change checklist, Q1E extrapolation decision tree,
new `StabilityResult` fields + CLI flags. v0.5.0 — Arrhenius, MKT,
reduced-design detection, opt-in random-effects mixed model.
v0.5.1 — Arrhenius hook filter + direction, mixed-model
convergence surfacing, MKT-without-temp_c warning, docs sync,
hard-require v0.5 modules. The three v0.1 audit fixes that
mattered most:

1. **COMMON_SLOPE c-vector bug** in `stats/regression.py` — a single
   shared per-batch linear-combination vector with `1.0` in every
   offset column was reused for every batch, under-estimating the SE
   and biasing the lower bound (B2 at t=12 was 92.823 instead of
   92.932). Fixed by building a per-batch c-vector from the parameter
   name list.
2. **Tautological COMMON_SLOPE cross-check test** in
   `validation/test_stats_bounds.py` — the test read the c-vector
   from `fit.design` (the engine's own storage) and compared the
   function to itself. Rewrote to build the c-vector independently
   from the parameter names.
3. **Missing COMMON_SLOPE golden entry** in
   `examples/assay_3batch.expected.json` — only POOLED values were
   frozen, but the engine selects COMMON_SLOPE on the golden dataset,
   so the golden test was not actually cross-checking the model in
   use. Added a full `common_slope_fit` block with per-batch
   intercepts, the common slope, `s_resid`, per-batch crossings, and
   the worst-case batch/crossing.

A fresh `tools/regen_expected.py` was added at the same time, so the
golden file is regenerable from scratch with no project imports.

---

## 8. Where to read next

Read these in order. Stop at the first one that fully answers your
question.

1. **`HANDOVER.md`** (this file) — orientation, env setup, healthy
   state, hard rules, open warnings.
2. **`CHANGELOG.md`** — every release entry from v0.1.0 through
   v0.5.1; what each minor/patch added; backward-compatibility notes.
3. **`NEXT_STEPS.md`** — the forward plan. §6 (PDF export + UI) is
   the next focus for v0.6.0; §§1–5 are now historical (shipped).
   Read §7 (pycache/env integrity) and §8 (agent handover protocol)
   first, before touching any code.
4. **`AGENTS.md`** — the v0.1 build plan, wave structure, and the
   authoritative math in §5. Read-only reference now.
5. **`OpenPharmaStability.md`** — the product spec / source of truth
   for behaviour.
6. **`openpharmastability/contracts.py`** — the frozen dataclasses,
   enums, constants, and public function signatures. The public API
   every module imports from. Do not edit unilaterally; additive
   only.

If you are picking up **v0.6.0 work** (PDF export + Cloudflare Pages
UI), read `NEXT_STEPS.md` §6 in full and the v0.5.1 entry in
`CHANGELOG.md` before opening an editor. The Python stats engine
is the authoritative implementation; the UI is a thin client.
