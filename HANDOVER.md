# HANDOVER.md — OpenPharmaStability cold-start briefing

> **You are picking up OpenPharmaStability v1.1.0 on a fresh machine.**
> Read this file top to bottom, run the verification block, then move on.
> If something in here disagrees with the code, the **code** is wrong —
> but only after you have re-read the relevant contract.

## Current takeover state — 2026-07-17

The statistics engine and local UI are stable at **v1.1.0**. The Graphite Dark
public-site redesign is merged, released, and deployed. Automated Cloudflare
Pages deployment from GitHub Actions is now operational.

| Item | Current state |
|---|---|
| Branch / current release commit | `main` / `406b352` (`ci: update setup actions for Node 24`), tagged `v1.1.0` |
| GitHub release | `v1.1.0`, published 2026-07-17 |
| Production site | https://openpharmastability.pages.dev |
| Latest verified Pages deployment | GitHub Actions run `29590938841`; preview `https://8fdcfa96.openpharmastability.pages.dev`; production branch `main` |
| Production verification | Canonical and preview URLs return HTTP 200; canonical HTML SHA-256 `9348cc241acb58234f570df4ec9ac87b12a8af5c37f0423e776da0adb32b1232` matches LF-normalized `site/index.html` |
| Test state | 483 collected; local full run green with 4 host-dependent PDF skips; GitHub Quality run `29598840371` green on Python 3.11/3.12 plus CLI/site gates |
| Golden validation | `python tools/regen_expected.py --check` passed |
| Site interaction QA | Graphite Dark redesign passed desktop/mobile layout, copy, CTA, console, and sample-artifact checks |
| Visual audit | Side-by-side reference comparison passed; see `design-qa.md` and `qa-output/design-comparison-desktop.png` |
| Immediate priority | No release blocker. Review the revised ICH Q1 draft expected September 2026 and Step 4 expected November 2026 using `Q1_FINAL_GAP_ASSESSMENT_TEMPLATE.md`; a hosted analysis backend remains a separate product decision |

Before adding or promoting a guidance profile, complete the provenance and gap
review gates in `NEXT_STEPS.md` §10. Never overwrite a draft profile or make one
the default.

### Why the public site was redesigned

The previous site was accurate and functional, but it read like an AI-generated
portfolio case study rather than a scientific software product. The audit found
an accumulated pattern of decorative dashboard UI, mono eyebrow labels,
editorial-serif marketing headings, numbered process rows, repeated bordered
panels, public `App UI` / `Design System` routes, and portfolio/process copy such
as “Hiring signal” and “portfolio story.” Mobile turns that system into a very
long stack of micro-panels.

The implemented Graphite Dark direction leads with the real confidence plot and
decision record; make Documentation, Sample report, and GitHub the primary
paths; remove internal design-showcase and hiring-process language; use semantic
HTML and visible focus states; keep the scientific/regulatory boundary explicit.

### Deployment reality

The Cloudflare Pages project is **Direct Upload**. The GitHub workflow at
`.github/workflows/pages-deployment.yml` verifies the deploy-folder sync and
deploys `site/` on relevant pushes to `main`. Repository variable
`CLOUDFLARE_ACCOUNT_ID` and the account-scoped `CLOUDFLARE_API_TOKEN` secret are
configured; workflow run `29590938841` completed the first verified unattended
deployment. Local Wrangler OAuth remains for interactive maintenance only and
must not be copied into GitHub Actions.

---

## 1. Positioning

**OpenPharmaStability v1.1.0** is an ICH Q1E-inspired Python toolkit
that ingests a CSV or XLSX of pharmaceutical stability data and
produces a shelf-life estimate, a confidence-bound plot, an HTML
report, a machine-readable JSON decision record, an optional PDF
copy, a self-contained `ReportArtifact` bundle, an optional
sensitivity report (row-level or batch-level leave-one-out), an
optional acceptance-criteria CSV, an optional Arrhenius-driven
shelf-life prediction, and (v0.9.0) optional per-batch Arrhenius
rate diagnostics with outlier flagging + Holm-corrected poolability
p-values + v0.10.0 GuidanceProfile abstraction, bidirectional
two-sided quantile fix, and §9 test sweep. The v0.1 baseline has
been extended through v0.2
(multi-attribute + XLSX), v0.3 (data quality + BQL + transform
evidence), v0.4 (ICH Q1A significant-change gating), v0.5
(Arrhenius / MKT / reduced designs / random-effects opt-in, plus
the v0.5.1 audit patch), v0.6 (export + API foundation), v0.7
(backend features: pure-numpy regen, multi-attribute metadata
spec override honored, sensitivity analysis, acceptance-criteria
CSV, direct XLSX support), v0.8 (more backend features: Arrhenius-
driven shelf-life prediction, leave-one-batch-out sensitivity,
cross-platform `Makefile`), and v0.9 (more backend features:
Holm-corrected poolability p-values, multi-engine XLSX dispatch,
per-batch Arrhenius rate diagnostic with outlier flagging, multi-
attribute `unit` + `report_order` surfacing), v0.10/v0.11
(GuidanceProfile + profile audit), and v1.0.0 (local UI workspace
and UI service manifest). It is a **decision-support /
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
| Version | `1.1.0` (declared in `__init__.py`, `contracts.py::TOOL_VERSION`, and `pyproject.toml` — keep in sync) |
| Python | `3.11+` (developed on 3.12) |
| Install (editable, with dev deps) | `pip install -e ".[dev]"` |
| Install (with PDF backend) | `pip install -e ".[pdf]"` (weasyprint) or `".[pdf-fallback]"` (pdfkit + wkhtmltopdf) |
| Build (cross-platform) | `make fresh` (Linux / macOS / WSL / git-bash) or the PowerShell script in `NEXT_STEPS.md` §7.1 (native Windows) |
| CLI entry point | `openpharmastability` (console script) |
| Local UI entry point | `openpharmastability-ui --host 127.0.0.1 --port 8765` |
| CLI invocation | `openpharmastability analyze <csv-or-xlsx> --condition "25C/60RH" --attribute assay --output report.html [--pdf report.pdf] [--artifact-dir build/bundle] [--sensitivity --sensitivity-mode {row,batch}] [--acceptance-csv acceptance.csv] [--arrhenius-shelf-life] [--arrhenius-per-batch] [--quiet]` |
| Golden CSV | `examples/assay_3batch.csv` (42 rows, 3 batches, 7 time points) |
| Golden expected | `examples/assay_3batch.expected.json` |
| Regeneration script | `tools/regen_expected.py` (pure numpy + scipy.stats.t + brentq; no statsmodels, no project imports) |
| Test count | **483 collected tests** (confirm via `pytest --collect-only -q`); expect ~479 passed + 4 host-dependent PDF skips without weasyprint/pdfkit |
| Reported shelf life on the golden dataset | **17 months** (statistical crossing 17.955 mo, B2, COMMON_SLOPE) |
| Frozen contracts | `openpharmastability/contracts.py` (read-only after release) |
| Python API | `openpharmastability.api` — `analyze_csv`, `analyze_xlsx`, `analyze_path`, `analyze_multi`, `make_artifact`, `analyze_and_artifact`, `compute_sensitivity_for`, `predict_arrhenius_shelf_life_for`; v1 adds `openpharmastability.ui_service.analyze_for_ui` |
| Report artifact | `contracts.ReportArtifact` — self-contained bundle (HTML with inlined plot, JSON, plots, optional PDF) with SHA-256 digests and byte sizes |
| Sensitivity report | `contracts.SensitivityReport` — leave-one-out (row-level or batch-level, via `--sensitivity-mode`) over Cook's-distance outliers, attached when `--sensitivity` is set |
| Acceptance-criteria CSV | `--acceptance-csv PATH` flag emits a flat CSV (one row per analyzed attribute) for LIMS / regulatory-tracking ingestion |
| Arrhenius-driven shelf-life | `--arrhenius-shelf-life` flag fits Arrhenius on multi-temperature rate data and predicts the long-term shelf life; attached as `StabilityResult.arrhenius_shelf_life` |
| Per-batch Arrhenius rate | `--arrhenius-per-batch` flag fits per-(batch × temperature) rates and flags outlier batches via robust z-score; attached as `ArrheniusResult.per_batch_rate_by_temp` and `ArrheniusResult.outlier_batches` |
| Poolability | `PoolabilityResult` carries the raw `p_slopes` / `p_intercepts` and the v0.9.0 Holm-corrected `p_slopes_holm` / `p_intercepts_holm` |

### Recent releases

| Version | Theme | What it added |
|---|---|---|
| `1.0.4` | Local UI Save as PDF + site polish | Browser-native **Save as PDF** button in the local UI report preview (`window.print()` + print CSS); public site showcase accuracy fixes (engine badge 1.0.4, real guidance/BQL options); sample artifacts refreshed to `tool_version` 1.0.4. No analysis-math change. |
| `1.1.0` (current) | Guidance provenance + release quality | Effective/draft guidance provenance is explicit and consistently threaded across single/multi reports, no-data paths, samples, and the UI; Quality CI verifies the package, golden values, installed CLI, and static-site sync. No analysis-math change. |
| `1.0.3` | Toolchain-robust validation | `tools/regen_expected.py --check` compares golden values with `rtol=1e-9` / `atol=1e-12` (last-ULP drift on modern numpy/scipy/BLAS); random-effects 2-batch boundary test accepts `converged=False` as well as `boundary=True`. Suite green on a clean modern install (479 passed / 4 host-dependent PDF skips). |
| `1.0.2` | Handover + roadmap orientation sync | Current-version docs now match the live package markers; `NEXT_STEPS.md` no longer describes the completed `dataclasses.replace` extrapolation refactor as open work. |
| `1.0.1` | Release documentation truth sync | README/HANDOVER/NEXT_STEPS synchronized after the local UI shipment; expected test collection corrected to 483. |
| `1.0.0` | Local v1 UI + service manifest | `openpharmastability-ui` local workspace, packaged static UI, `ui_service.analyze_for_ui()` manifest, artifact preview/download flow. Python engine remains authoritative; UI does not reimplement statistics. |
| `0.11.0` | Guidance profile completion | `--guidance`, profile registry/resolver, `StabilityResult.profile_name`, JSON + HTML guidance audit, non-default-profile threading tests. |
| `0.10.0` | GuidanceProfile abstraction + bidirectional fix | `GuidanceProfile`, two-sided bidirectional 0.975 quantile, `CrossingResult.governing_side`, additional §9 tests. |
| `0.9.0` | Backend features (no UI) | `PoolabilityResult.p_slopes_holm` / `p_intercepts_holm` (Holm-Bonferroni corrected p-values for the two-step poolability test); `analyze_many` now accepts XLSX / XLSM directly via the v0.7.0 `load_table` dispatcher (symmetry with the single-attribute path); `--arrhenius-per-batch` flag + per-batch Arrhenius rate dict + outlier-batches list with robust z-score detection; multi-attribute `unit` + `report_order` surfaced in the per-attribute HTML block, the overview table, and a new top-level `attribute_order` key in the multi JSON record. |
| `0.8.0` | Backend features (no UI) | `stats.arrhenius_shelf_life.predict_arrhenius_shelf_life` (Arrhenius-driven shelf-life prediction; `--arrhenius-shelf-life` flag); `compute_sensitivity` now accepts `mode={row,batch}` for leave-one-batch-out (`--sensitivity-mode {row,batch}` flag); cross-platform `Makefile` (`make fresh / test / regen-check`). |
| `0.7.0` | Backend features (no UI) | `stats.sensitivity.compute_sensitivity` (leave-one-out over Cook's-distance outliers, `--sensitivity` flag); `to_acceptance_criteria` + `--acceptance-csv PATH` (LIMS-friendly flat CSV); `StabilityResult.lower_spec` / `upper_spec` (the spec limits the engine used); `load_table` dispatcher in `data/io.py` so `engine.analyze()` accepts CSV / XLSX / XLSM directly; multi-attribute metadata `lower_spec` / `upper_spec` override now actually applied (v0.2.1 CHANGELOG claim honored at last); `tools/regen_expected.py` is now pure-numpy (the v0.1.1 "regen uses statsmodels" known-open item is finally closed). |
| `0.6.0` | Export + API foundation | `reports/pdf.py` (weasyprint primary, pdfkit fallback); `reports/artifacts.py` (`make_report_artifact` with inlined plot); `api.py` thin programmatic surface; new CLI flags `--pdf`, `--no-html`, `--json-only`, `--artifact-dir`, `--quiet`; improved error messages + non-zero exit codes; multi-attribute HTML spec display fix. |
| `0.5.1` | Audit patch on v0.5.0 | Arrhenius hook filtered to selected attribute + direction-aware; mixed-model convergence / boundary status surfaced at `StabilityResult.model_convergence` + warnings + HTML; explicit "no temp_c" warning when `--mkt` is requested without temperature data; docs synced; v0.5 tests now hard-require the v0.5 modules. |
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
483 passed, <N> skipped in <Xs>  (PDF-backend skips are host-dependent)
```

Pass criteria:

- The expected collection count is **483** after v1.0.0 (the per-file collection map is in
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

## 6. Open warnings (v0.10.0 status)

All v0.1.1, v0.3.1, and v0.5.1 known-open items are now **resolved**
(documented below under "Recent releases" history).

There are currently **no open known warnings**. The v0.7.0 release
introduced two new optional analytical surfaces: the
`SensitivityReport` (leave-one-out over Cook's-distance outliers,
opt-in via `--sensitivity`) and the acceptance-criteria CSV
(`--acceptance-csv PATH`, designed for LIMS / regulatory-tracking
ingestion). See §2 and the `openpharmastability.api` module for
the programmatic surface.

### 6.1 v0.1.1 known-open items (all resolved)

- HTML timestamp determinism — fixed in v0.1.1 via `--source-epoch` /
  `SOURCE_DATE_EPOCH`. Two runs with the same epoch produce byte-
  identical JSON.
- `schema._infer_direction_from_spec` false-positive warning — fixed
  in v0.1.1; declaring `decreasing` or `increasing` on a dataset with
  both spec limits no longer warns.
- `tools/regen_expected.py` independence — **finally closed in
  v0.7.0**. The COMMON_SLOPE fit is now pure-numpy
  (`np.linalg.lstsq` + `np.linalg.inv`); the validator no longer
  shares an OLS backend with the engine.

### 6.2 v0.3.0 / v0.3.1 cleanup (all resolved)

- `bql_summary` was a hack via `object.__setattr__` on the result; v0.3.1
  made it a proper `StabilityResult` field and refactored
  `apply_extrapolation_caps` to `dataclasses.replace`.
- Single-attribute JSON record omitted the disclaimer; v0.3.1 added
  it (matches the multi-attribute record).
- `audit_data_quality` existed but was not wired in; v0.3.1 calls it
  from `engine.analyze()` and surfaces findings via warnings + JSON
  `metadata.data_quality`.
- `plots/confidence_plot.py` drew misleading per-batch bands and
  hard-coded "lower" regardless of `Direction.INCREASING`; v0.3.1
  draws a single worst-case band and respects direction.
- `data/quality.py` condition check normalized via `parse_condition`
  in v0.3.1; `data/metadata.py` accepts `transform="log"` in v0.3.1.

### 6.3 v0.5.0 / v0.5.1 audit items (all resolved)

- Arrhenius engine hook now filters to the selected attribute and
  respects the declared direction (was reading the raw DataFrame and
  assuming decreasing degradation via `rate = -slope`). Resolved in
  v0.5.1.
- Mixed-model convergence / boundary status now surfaced at
  `StabilityResult.model_convergence` + warnings + HTML (was only
  inside `fit.design`). Resolved in v0.5.1.
- MKT-without-`temp_c` now emits an explicit warning. Resolved in
  v0.5.1.

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
hard-require v0.5 modules. v0.6.0 — PDF export, report artifacts
(self-contained HTML bundle with inlined plot), Python API, CLI
polish (--pdf, --no-html, --json-only, --artifact-dir, --quiet),
multi-attribute HTML spec display fix. v0.7.0 — backend
features only (per user "features first, website last" reshape):
pure-numpy regen (v0.1.1 "regen uses statsmodels" known-open
item finally closed), multi-attribute metadata `lower_spec` /
`upper_spec` override now actually applied (v0.2.1 CHANGELOG
claim finally honored), `engine.analyze()` accepts XLSX / XLSM
directly via the `load_table` dispatcher, sensitivity analysis
(`--sensitivity`, leave-one-out over Cook's-distance outliers),
acceptance-criteria CSV export (`--acceptance-csv PATH`).
v0.8.0 — more backend features (no UI): Arrhenius-driven
shelf-life prediction (`--arrhenius-shelf-life`; predicts the
long-term shelf life from stress-temperature rate data and the
v0.5.0 Arrhenius module), leave-one-batch-out sensitivity
(`--sensitivity-mode batch`; the v0.7.0 row-level mode is the
default), cross-platform `Makefile` (`make fresh / test /
regen-check`). v0.10.0 — GuidanceProfile + bidirectional fix + §9 tests:
Holm-Bonferroni corrected poolability p-values
(`PoolabilityResult.p_slopes_holm` / `p_intercepts_holm`),
multi-engine `analyze_many` accepts XLSX / XLSM directly via
the v0.7.0 `load_table` dispatcher, per-batch Arrhenius rate
diagnostic (`--arrhenius-per-batch`; flags outlier batches via
robust z-score), multi-attribute `unit` + `report_order`
surfaced in the per-attribute HTML block and a new top-level
`attribute_order` key in the multi JSON record. **No frontend
in v0.6, v0.7, v0.8, or v0.9** — the UI pass (Cloudflare Pages
+ Claude Design) is deferred to a future release (v1.0).

The three v0.1 audit fixes that mattered most:

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
   v0.6.0; what each minor/patch added; backward-compatibility notes.
3. **`NEXT_STEPS.md`** — the forward plan. v1.0.4 is the current
   release; the local UI pass has shipped (including Save as PDF),
   and the active UI work is the audited anti-slop redesign of the static
   public site over the existing Python-owned stats engine. Read §7 (pycache/env integrity) and §8 (agent handover
   protocol) first, before touching any code.
4. **`AGENTS.md`** — the v0.1 build plan, wave structure, and the
   authoritative math in §5. Read-only reference now.
5. **`OpenPharmaStability.md`** — the product spec / source of truth
   for behaviour.
6. **`openpharmastability/contracts.py`** — the frozen dataclasses,
   enums, constants, and public function signatures. The public API
   every module imports from. Do not edit unilaterally; additive
   only.

If you are picking up **post-v1 UI work** (public-site redesign, hosted
deployment, browser polish, or workflow hardening), read
`UI_UX_AUDIT.md`, `SESSION_SUMMARY_2026-07-17.md`, and
`NEXT_STEPS.md` §11 in full and
the v1.0.0 / v1.0.4 entries in `CHANGELOG.md` before opening an editor.
The Python stats engine is the authoritative implementation; the UI is a
thin client that posts CSV/XLSX to a thin API and renders the HTML
report inline. Do not reimplement the statistical core in JavaScript /
TypeScript.

For **CMC / hiring-facing portfolio work**, also read
`CMC_ANALYTICS_POSITIONING.md` and the README case study section
("Case study: the golden assay dataset"). The live public site is
https://openpharmastability.pages.dev (static `site/` on Cloudflare Pages).
