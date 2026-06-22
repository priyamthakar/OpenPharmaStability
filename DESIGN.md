# OpenPharmaStability Design System

This design system is for a hiring facing public site and local product UI for OpenPharmaStability. The goal is to present a serious pharma analytics project, not a generic SaaS landing page and not a copied Claude page.

## Position

OpenPharmaStability should read as a local analytical instrument for pharmaceutical stability work.

Use this framing:

- Open source pharmaceutical stability analysis
- ICH Q1E inspired statistical decision support
- Python owned calculations
- Reproducible HTML, JSON, and plot artifacts
- Audit friendly records
- Educational and exploratory use

Avoid this framing:

- Validated GxP system
- 21 CFR Part 11 compliant
- Regulatory approval tool
- Automated compliance
- AI powered product page language
- Cloud enterprise SaaS posture

## Visual Principles

1. Lead with the analytical decision.
   The supported shelf life or retest period is the main number.

2. Show the method, not only the outcome.
   Poolability, model choice, confidence bound, crossing time, warnings, and artifact hashes should be visible.

3. Use editorial restraint.
   Warm neutral surfaces, precise type, and table like information density create credibility.

4. Make the product surface real.
   The UI preview should include setup controls, report preview, artifacts, audit facts, and warnings.

5. No generic card grids.
   Prefer ledgers, specimens, indexes, report sheets, and instrument panels.

## Color

| Token | Hex | Use |
| --- | --- | --- |
| Parchment | `#f4f0e7` | Page background |
| Section neutral | `#efe9dc` | Alternating bands and strips |
| Warm panel | `#fdfbf6` | Local UI panels and report previews |
| White | `#ffffff` | Primary surfaces |
| Charcoal | `#211f1b` | Primary text |
| Warm black | `#26231d` | Code and instrument chrome |
| Stone | `#6f685d` | Secondary text |
| Faint stone | `#938b7d` | Captions and metadata |
| Border | `#e4dbcb` | Hairline divisions |
| Strong border | `#d8cdb8` | Inputs and section rules |
| Terracotta | `#b35a3a` | Primary action, mean line, important labels |
| Sage | `#5e7a56` | Supported state and pass state |
| Ink blue | `#3f5d78` | Data series and JSON artifact |
| Amber | `#b07a32` | Warnings and partial state |

Color should carry meaning. Do not use accent color as decoration.

## Typography

| Role | Family | Guidance |
| --- | --- | --- |
| Display | Newsreader | Product name, editorial headings, large numbers |
| UI and body | IBM Plex Sans | Navigation, controls, body copy, panel labels |
| Mono | IBM Plex Mono | Hashes, code, metadata, run facts, chart labels |

Scale:

- Hero product name: 56 to 64px, Newsreader 500
- Section heading: 32 to 36px, Newsreader 500
- Panel heading: 18 to 24px, IBM Plex Sans 600 or Newsreader 600
- Body: 14 to 16px, IBM Plex Sans 400
- Labels: 10 to 12px, IBM Plex Mono 500, uppercase

## Layout

Use a maximum width of 1180px for the public site and 1280px for the app workspace.

Preferred patterns:

- Masthead rule with metadata
- Asymmetric hero with real product workspace
- Method ledger with numbered rows
- Capability index with table like cells
- Report specimen with chart and decision facts
- Architecture chain with source, engine, result, artifacts, UI
- Compliance boundary panel

Avoid:

- Oversized generic hero copy beside a rounded marketing card
- Repeated equal height feature cards across the whole page
- Decorative blobs, gradients, glassmorphism, and novelty illustration
- Nested cards inside cards

## Components

### Product Workspace Preview

Three columns:

- Setup rail with upload, condition, attribute mode, product type, guidance profile, and BQL policy
- Result and report panel with status, supported decision, model, chart, and report preview
- Artifact and audit rail with HTML, JSON, plot, PDF, input hash, engine version, and limitations

### Report Specimen

Must show:

- Supported shelf life: 17 months
- Statistical crossing: 17.95 months
- Model: common slope plus batch intercepts
- Poolability: partial
- Lower one sided 95% confidence bound
- Warning panel
- Artifact buttons

### Warning Panel

Use amber background and a 3px amber left rule. The copy should be calm and specific.

### Compliance Panel

Use plain language:

OpenPharmaStability is intended for educational, exploratory, and reproducible decision support use. It is not a validated GxP system and does not provide 21 CFR Part 11 audit trails, electronic signatures, or data integrity controls.

## Voice

Precise, calm, scientifically literate, and honest about limitations.

Prefer:

- reproducible
- transparent
- audit friendly
- decision support
- ICH Q1E inspired
- Python owned statistics
- local execution

Avoid:

- revolutionary
- FDA approved
- GxP ready
- validated
- automates compliance
- regulatory approved
- AI powered

## Hiring Focus

The design should help a reviewer see the following without digging:

- This is a statistics heavy product, not a calculator skin.
- The author understands pharma stability concepts and regulatory boundaries.
- The implementation has a real Python engine behind the interface.
- Outputs are reproducible and artifact based.
- The UI is polished enough for portfolio review but still honest about its local first nature.
