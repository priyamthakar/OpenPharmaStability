# CMC Analytics Positioning

## Target Track

OpenPharmaStability should be positioned for:

- CMC Data Scientist
- Pharmaceutical Development Scientist
- Drug Product Analytics
- Stability Data Analyst
- CMC Digitalization / Pharma Analytics roles

Recruiter-facing title:

**ICH-style stability analytics engine for shelf-life estimation and CMC reporting**

## Why This Project Fits CMC Analytics

The project turns pharmaceutical stability data into a reproducible analytical workflow:

- validates structured stability data from CSV/XLSX,
- analyzes assay, impurity, degradant, and other CQA trends,
- checks batch poolability using an ICH Q1E-inspired approach,
- estimates supported shelf life from confidence-bound/specification crossing,
- identifies limiting attributes and limiting batches,
- flags data-quality and model-assumption risks,
- produces HTML/PDF/report artifacts and JSON decision records.

This is the kind of work CMC analytics teams need when they convert spreadsheet-heavy stability review into a traceable data product.

## Resume Bullets

- Built **OpenPharmaStability**, a Python-first stability analytics toolkit for pharmaceutical development that estimates supported shelf life from ICH Q1E-inspired confidence-bound/specification crossing.
- Implemented multi-batch stability regression, batch poolability logic, multi-attribute limiting shelf-life selection, data-quality checks, and report-ready HTML/PDF/JSON outputs.
- Designed the workflow around CMC reviewer needs: assay/degradant trends, OOS/OOT risk flags, shelf-life vs retest-period terminology, reproducibility metadata, and explicit decision-support limitations.
- Shipped a tested engine (**483** collected tests; decision-support only — not GxP validated) with a golden assay case study (**17 months**, governing batch **B2**, common-slope model) and a public sample site.

## Portfolio Case Study Structure

Use this structure on GitHub, LinkedIn, or a portfolio page:

1. **Problem**  
   Stability review is often fragmented across spreadsheets, plots, and manual justification. CMC teams need reproducible, audit-friendly shelf-life analytics.

2. **Input**  
   Tidy stability data with batch, condition, time, attribute, value, units, and shelf-life specification limits.

3. **Analysis**  
   Fixed-effect stability regression, poolability checks, confidence bounds, limiting attribute selection, and data-quality warnings.

4. **Output**  
   Shelf-life recommendation, limiting attribute/batch, plots, assumptions, warnings, and report artifacts for qualified CMC review.

5. **Boundary**  
   Decision-support and educational software only; not a validated GxP or 21 CFR Part 11 system.

## Interview Pitch

> I built OpenPharmaStability to show how CMC stability review can move from spreadsheet-based interpretation to a reproducible Python workflow. It validates stability data, fits ICH Q1E-inspired trend models, checks whether batches can be pooled, estimates supported shelf life from confidence-bound crossing of shelf-life specifications, and exports reviewer-facing reports and JSON decision records. On the golden three-batch assay dataset it selects a common-slope model, identifies batch B2 as governing, and reports a 17-month supported shelf life from a one-sided 95% mean-response bound. I framed it as decision support rather than a validated regulatory system, which keeps the technical claims honest.

## Role Mapping

| Target role | Evidence in OpenPharmaStability |
|---|---|
| CMC Data Scientist | Stability regression, batch analytics, report automation, JSON decision records |
| Pharmaceutical Development Scientist | Shelf-life reasoning, CQA trend interpretation, product-quality risk flags |
| Drug Product Analytics | Multi-attribute limiting shelf life, assay/degradant monitoring, OOT/OOS warnings |
| CMC Digitalization Analyst | Spreadsheet-to-workflow conversion, reproducible CLI/API/UI, audit metadata |
| Pharma Analytics Consultant | Structured stakeholder-facing reports and clear limitations |

## Skills To Highlight

- Python, pandas, scipy/statsmodels-style modeling
- Stability data analysis
- ICH Q1E-inspired shelf-life reasoning
- Batch poolability
- CQA and specification-limit interpretation
- HTML/PDF/JSON report generation
- CLI/API/UI productization
- Testable scientific software

## Live references

| Asset | Path / URL |
|---|---|
| Golden case study + CMC walkthrough | README.md § "Case study: the golden assay dataset" + "For CMC reviewers" |
| Golden numbers | **17 months** supported shelf life; statistical crossing ~17.955 mo; governing batch **B2**; model `common_slope_batch_intercepts` |
| Sample HTML / JSON / plot | `site-sample/` (`sample-report.html`, `sample-report.json`, `confidence_plot.png`) |
| Local UI screenshot | `site-sample/ui-workspace.png` (also linked from README § Local UI) |
| Multi-attribute sample | `site-sample/multi/` (limiting CQA = impurity_a at **7 months**; assay 16 months) |
| Public site | https://openpharmastability.pages.dev |
| Test suite | **483** collected (`pytest --collect-only -q`); decision-support only — not GxP validated |
| Engine version | **v1.0.4** |

## What To Build Next For This Career Track

Done:

1. Short visual case study in the README using the golden assay dataset (plot + 17-month table, governing batch B2, common slope).
2. "For CMC reviewers" walkthrough: input → poolability → bound/crossing → decision record → report.
3. Local UI screenshot in portfolio materials (`site-sample/ui-workspace.png`).
4. Multi-attribute limiting-attribute sample story (`site-sample/multi/` + README multi-attribute section; limiting CQA = impurity_a @ 7 months).
5. Public-site link to the multi-attribute report (`site-sample/multi/multi-report.html`).

Highest-value remaining improvements for job applications:

1. **Sample PDF (optional)** — one compact sample report PDF on the public portfolio (browser Save as PDF from the local UI, or server-side PDF if a backend is installed). Not a release blocker.
2. Keep the validation/test count visible (**483** collected), but do not overclaim regulatory validation.
3. When extending portfolio copy: keep the disclaimer boundary explicit (decision-support / educational only — not GxP, not 21 CFR Part 11, not submission-ready).
