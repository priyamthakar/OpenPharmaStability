# HOSTED_ANALYSIS_BACKEND_PLAN.md

> **Status:** Product / tech decision plan only.  
> **Scope of this document:** decide whether to ship a hosted analysis API, and if so how.  
> **Out of scope here:** implementing FastAPI, Workers, Cloud Run services, or any production code.  
> **Do not treat this file as permission to build** until a go/no-go decision is recorded below.

**Related seams (read-only references):**
- `openpharmastability/ui_service.py` — `analyze_for_ui()`, `UIAnalysisOptions`, `UIAnalysisManifest`
- `openpharmastability/ui_server.py` — local `GET /api/config`, `POST /api/analyze`, `/runs/...` artifacts
- `openpharmastability/api.py` — `analyze_and_artifact()` (engine + report bundle)
- `openpharmastability/contracts.py` — `DISCLAIMER` (verbatim on every response)
- `NEXT_STEPS.md` §6.3 — historical FastAPI async job sketch (reference shape, not a mandate)
- `NEXT_STEPS.md` §11.5 item 2 — hosted backend is a separate product decision
- Public site: `site/` → Cloudflare Pages (static showcase only)

---

## 1. Decision ask

**Question:** Should OpenPharmaStability ship a **hosted analysis backend**, or keep the product as:

1. **Local-only compute** via `openpharmastability-ui` (`ui_server.py` + `ui_service.analyze_for_ui`), and  
2. **Static Cloudflare Pages showcase** for `site/` (docs, sample report, positioning — no server-side analysis)?

| Option | What ships | Compute location | Risk / cost |
|---|---|---|---|
| **A — Local-only + static Pages (status quo)** | CLI, local UI, Pages marketing/docs | User machine | Lowest ops / liability; no multi-user upload surface |
| **B — Hosted analysis (proposed MVP)** | Status quo **plus** a separate Python API origin | Cloud Run / Fly / Containers (not Pages) | Upload, CORS, abuse, ephemeral storage, positioning discipline |
| **C — “Pages runs analyses”** | Attempt to put the engine on Pages/Workers | Cloudflare edge | **Rejected** — Pages cannot run the Python engine; JS reimplementation is a non-goal |

**Default recommendation:** stay on **Option A** until Option B clears the §6 go/no-go checklist. If the checklist passes and there is a clear demo/partner need, ship **Option B** as a thin FastAPI wrap of existing seams — not a rewrite.

**Decision record (fill when decided):**

| Field | Value |
|---|---|
| Decision | `GO` / `NO-GO` / `DEFER` |
| Date | |
| Owner | |
| Rationale (1–3 lines) | |

---

## 2. Recommended architecture (concrete default)

### 2.1 Separation of origins

```text
Browser
  │
  ├─ static assets ──► Cloudflare Pages  (site/ only)
  │                      marketing, docs, sample artifacts
  │                      NEVER claims to run analyses
  │
  └─ analysis API ───► Python compute origin
                         FastAPI wrapping existing Python package
                         Cloud Run | Fly.io | Cloudflare Containers
                         (separate hostname, e.g. api.example.com)
```

**Hard constraint:** Cloudflare Pages is **static-only** for this product. It cannot host `statsmodels` / `scipy` / the shelf-life engine. Do not design a Workers/JS “port” of Q1E math.

### 2.2 Default stack

| Layer | Choice | Why |
|---|---|---|
| HTTP framework | **FastAPI** | Matches `NEXT_STEPS.md` §6.3 direction; clean multipart + JSON |
| Compute entry | **`analyze_for_ui(...)`** | Already returns the UI manifest the local UI consumes |
| Engine / artifacts | **`analyze_and_artifact(...)`** (via `ui_service`) | Single path for CSV/XLSX, plots, HTML, JSON, optional PDF |
| Hosting | **Cloud Run or Fly.io** (or Cloudflare Containers if preferred) | Full Python runtime; scale-to-zero OK for MVP |
| Storage | **Ephemeral disk per request / short-TTL temp dir** | No permanent GxP store in v1 |
| Public site | **Pages stays static** | `site/` deploy path unchanged |

### 2.3 What the FastAPI layer is (and is not)

**Is:** a thin adapter analogous to `ui_server.py` — parse upload + options → call `analyze_for_ui` → return manifest + serve artifact bytes.

**Is not:** a reimplementation of poolability, bounds, diagnostics, GuidanceProfile, or report templates. Those stay in the installed `openpharmastability` package.

### 2.4 Origin / CORS model

- Pages origin (e.g. `https://openpharmastability.pages.dev`) may call the API origin with **explicit CORS allowlist**.
- Local UI (`127.0.0.1:8765`) remains independent and does not require the hosted API.
- API responses must never imply that Pages executed the analysis.

---

## 3. MVP surface

Mirror the **local UI contract** in `ui_server.py`, not the older async-only sketch in §6.3, unless sync timeouts force jobs.

### 3.1 Sync-first endpoints (preferred MVP)

| Method | Path | Behavior | Source of truth |
|---|---|---|---|
| `GET` | `/api/config` | `{ version, disclaimer, guidance_profiles }` | Same shape as `ui_server.py` (`TOOL_VERSION`, `DISCLAIMER`, profiles list) |
| `POST` | `/api/analyze` | multipart `file` + form `options` JSON → `UIAnalysisManifest` dict | `analyze_for_ui` / `UIAnalysisOptions` |
| `GET` | artifact download | Serve files referenced by manifest URLs (HTML, JSON, PNG, optional PDF) | Same idea as `/runs/{run_id}/artifact/...` in `ui_server.py` |

**Request options:** reuse `UIAnalysisOptions` fields (condition, attribute(s), product_type, horizon, policies, guidance, optional Arrhenius/MKT/sensitivity/PDF flags). Do not invent a parallel options schema.

**Response:** reuse `UIAnalysisManifest.to_dict()` including **verbatim** `disclaimer=DISCLAIMER`. Errors still include `disclaimer`.

### 3.2 Optional async job trio (only if needed)

`NEXT_STEPS.md` §6.3 sketches:

| Method | Path | Role |
|---|---|---|
| `POST` | `/analyze` | enqueue → `{ job_id, status }` |
| `GET` | `/status/{id}` | `queued \| running \| done \| error` |
| `GET` | `/report/{id}` | fetch artifact / JSON |

**Rule:** adopt this trio **only** if measured sync requests hit platform HTTP timeouts (or PDF/heavy options routinely exceed budget). Prefer sync for the golden CSV path first; do not build a queue “just because §6.3 sketched one.”

If jobs are required for MVP:

- In-memory dict is acceptable for a **private demo** only (same caveat as §6.3).
- Document that production needs a real queue + TTL eviction.
- Every status/report payload still carries `contracts.DISCLAIMER`.

### 3.3 Explicit non-MVP API surface

- No auth / API keys beyond a possible shared demo token if abuse forces it (still not multi-tenant).
- No streaming progress beyond optional job status.
- No websocket UI.
- No permanent report gallery or user accounts.

---

## 4. GxP / positioning

OpenPharmaStability remains **decision-support / educational**, not a validated GxP or submission system.

### 4.1 Mandatory disclaimer

Every successful and error JSON response (and every HTML report already produced by the engine) must include the **verbatim** string from `contracts.DISCLAIMER`:

> This report is ICH Q1E-inspired and intended for educational, exploratory, and reproducible decision-support use. It is not a substitute for qualified regulatory, statistical, or quality review. The toolkit does not provide 21 CFR Part 11 audit trails, electronic signatures, or data integrity controls, and is not a validated GxP system.

Do not paraphrase, shorten, or “soften” this text on the hosted API or on Pages copy that describes the API.

### 4.2 What hosted v1 must not claim

| Claim | Allowed? |
|---|---|
| “Runs the same engine as the local UI / CLI” | Yes (if true) |
| “Decision-support / educational” | Yes |
| “21 CFR Part 11 / validated GxP / audit trail / e-sign” | **No** |
| “Cloudflare Pages runs your analysis” | **No** |
| “Submission-ready / regulatory approval” | **No** |

### 4.3 Site / Pages copy constraints

- `site/` may link to a hosted demo **only** with clear language that analysis runs on a **separate Python service**.
- Keep the existing redesign rule: no implication that the static showcase is a hosted analysis application (`NEXT_STEPS.md` §11 / public IA notes).
- Prefer CTAs: Documentation, Sample report, GitHub, and (if GO) “Try hosted demo (experimental)” with disclaimer adjacent.

---

## 5. Non-goals for v1 hosted

Do **not** include in the first hosted release:

1. **Multi-tenant authentication** (OAuth, org accounts, RBAC, per-user quotas as a product feature).
2. **Permanent GxP storage** (audit logs, immutable report retention, e-sign, Part 11 controls).
3. **Reimplementing stats in Workers / JavaScript** (or any edge rewrite of ANCOVA / bounds / poolability).
4. Replacing or forking `ui_service` / `api.analyze_and_artifact` with a second engine path.
5. Expanding beyond the local UI option set without a separate product decision.
6. Using Pages Functions as the compute host for the engine.

---

## 6. Go / no-go checklist

Complete before any implementation PR. A single **No** on a hard gate → **NO-GO** or **DEFER**.

### 6.1 Product / positioning (hard)

| # | Check | Pass? |
|---|---|---|
| P1 | Decision owner accepts decision-support-only positioning for a public/demo API | ☐ |
| P2 | Pages copy plan does **not** imply Pages runs analyses | ☐ |
| P3 | Verbatim `DISCLAIMER` on every API response is accepted as non-negotiable | ☐ |
| P4 | No Part 11 / audit / e-sign roadmap is implied by shipping hosted v1 | ☐ |

### 6.2 Security / abuse (hard)

| # | Check | Pass? |
|---|---|---|
| S1 | Upload size limit defined (recommend ≤ 5–10 MB for MVP) | ☐ |
| S2 | Allowed types limited (CSV / XLSX); reject executables / archives | ☐ |
| S3 | Path traversal blocked for artifact URLs (same resolve-under-root pattern as `ui_server.py`) | ☐ |
| S4 | Rate limit / IP throttle plan for public demo (or private allowlist only) | ☐ |
| S5 | No secrets in client; CORS allowlist restricted to known Pages (+ localhost if needed) | ☐ |
| S6 | Temp inputs/artifacts deleted on TTL or after response (no unbounded disk) | ☐ |

### 6.3 Size / time limits (hard)

| # | Check | Pass? |
|---|---|---|
| T1 | Sync timeout budget measured on golden + worst expected XLSX (recommend target ≤ 30–60 s) | ☐ |
| T2 | PDF / sensitivity / Arrhenius-heavy flags either disabled by default or forced onto async | ☐ |
| T3 | Platform request timeout (Cloud Run / Fly / proxy) documented and compatible with T1 | ☐ |
| T4 | If T1 fails → either strip heavy options or adopt §6.3 job trio; do not ship hanging sync | ☐ |

### 6.4 Storage model (hard)

| # | Check | Pass? |
|---|---|---|
| E1 | Ephemeral-only: run dirs under `/tmp` (or equivalent) with UUID isolation | ☐ |
| E2 | TTL eviction (e.g. 15–60 minutes) for artifact download URLs | ☐ |
| E3 | Explicit statement: hosted v1 is **not** a records-retention system | ☐ |
| E4 | No customer data written to durable object storage without a later decision | ☐ |

### 6.5 Architecture fit (hard)

| # | Check | Pass? |
|---|---|---|
| A1 | FastAPI calls `analyze_for_ui` / `analyze_and_artifact` only — no parallel math | ☐ |
| A2 | Pages remains static deploy of `site/` only | ☐ |
| A3 | Compute on separate origin (Cloud Run / Fly / Containers) | ☐ |
| A4 | Manifest shape compatible with local UI expectations (or documented deltas) | ☐ |

### 6.6 Soft / nice-to-have

| # | Check | Pass? |
|---|---|---|
| N1 | Health endpoint for uptime checks | ☐ |
| N2 | Structured logging without storing uploaded CSV contents | ☐ |
| N3 | Same `TOOL_VERSION` surfaced in `/api/config` as package | ☐ |

**Gate rule:** all hard checks (P/S/T/E/A) must be ☐→☑ before coding. Soft checks do not block the decision but should be tracked.

---

## 7. Existing seams to wrap (do not reinvent)

### 7.1 `ui_service.py`

- **`UIAnalysisOptions`** — accepted option surface for local UI; reuse for hosted form JSON.
- **`analyze_for_ui(input_path, output_dir, options, url_prefix=...)`** — preferred hosted entrypoint; already embeds `DISCLAIMER` and builds artifact URL list.
- **`UIAnalysisManifest`** — stable JSON shape for clients.

Docstring intent (already in tree): *“The local web UI and any future HTTP layer should consume this manifest instead of reimplementing shelf-life logic.”*

### 7.2 `ui_server.py`

Reference implementation of the MVP HTTP surface:

- `GET /api/config` → version + `DISCLAIMER` + guidance profiles  
- `POST /api/analyze` → temp run dir + `analyze_for_ui` → JSON manifest  
- `GET /runs/{run_id}/...` → artifact download with path-safety checks  
- Error JSON includes `disclaimer: DISCLAIMER`

Hosted FastAPI should behave like a production-hardened cousin of this adapter, not a new product.

### 7.3 `api.py`

- **`analyze_and_artifact(...)`** — one-shot analyze + `ReportArtifact` (HTML/JSON/plots/optional PDF).  
- Called by `analyze_for_ui`; keep this as the sole artifact-generation path.

### 7.4 `NEXT_STEPS.md` §6.3

Use as **historical design notes** for:

- FastAPI as the HTTP framework  
- Disclaimer on every response  
- CORS for a browser frontend  
- Optional async job trio when sync is insufficient  
- Explicit warning that in-memory jobs are not production-grade  

Do **not** treat §6.3’s direct `analyze` / `analyze_multi` calls as the preferred entry once `ui_service` exists — prefer `analyze_for_ui` so hosted and local stay aligned.

### 7.5 Positioning already recorded

`NEXT_STEPS.md` §11.5: *“Hosted analysis backend — out of scope and requires a separate product decision.”*  
This plan is that decision artifact. Implementation starts only after §1 records **GO**.

---

## 8. Suggested decision outcomes

### NO-GO / DEFER (recommended until checklist clears)

Keep:

- Local `openpharmastability-ui`  
- Static Pages for `site/`  
- CLI / Python API for power users  

Communicate: analysis is run locally; the public site is documentation and samples.

### GO (only after §6)

Implement in a **later** change set (not this plan):

1. New service package or `api/` FastAPI app wrapping `analyze_for_ui`  
2. Deploy to Cloud Run / Fly / Containers  
3. CORS to Pages origin  
4. Ephemeral storage + limits  
5. Pages copy update: separate-origin demo language + disclaimer  
6. Tests mirroring local config/analyze/disclaimer assertions (and §6.3’s TestClient idea if async)

---

## 9. One-line summary

**Ship hosted analysis only as a separate Python FastAPI origin wrapping `analyze_for_ui` / `analyze_and_artifact`; keep Cloudflare Pages static; never imply Pages runs Q1E math; every response carries verbatim `contracts.DISCLAIMER`; defer async jobs until sync timeouts force them.**
