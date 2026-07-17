# OpenPharmaStability public design contract

> **Status: revised 2026-07-17 after desktop/mobile audit.** This file governs
> the public static site. It does not replace the local UI's product controls or
> the report template. Read `UI_UX_AUDIT.md` before changing the site.

## Product impression

OpenPharmaStability should look like carefully maintained scientific software:
calm, exact, inspectable, and useful. It must not look like a generated SaaS
landing page, a design-system showcase, or a hiring portfolio exercise.

The visual identity comes from the actual work product:

- confidence-bound plots;
- supported shelf-life or retest-period decisions;
- model and poolability evidence;
- warnings and assumptions;
- reproducibility metadata and decision records.

Do not invent decorative product UI when a real report, plot, table, command, or
record can carry the message.

## Primary audience and task

Primary audience: stability scientists, CMC reviewers, pharmaceutical
development scientists, and technical evaluators.

The page must let a first-time visitor answer, in order:

1. What decision does this tool support?
2. What statistical evidence is preserved?
3. Can I inspect a real result?
4. How do I install and run it?
5. What does it explicitly not claim to do?

## Public information architecture

The public header contains only:

- Documentation
- Sample report
- GitHub

The page contains no public `App UI` or `Design System` route. A single honest
image of the local workspace may appear as supporting evidence, clearly labeled
as a local-interface preview.

Recommended page order:

1. Outcome-focused hero with install command and sample-report action
2. Real golden-result evidence: plot, 17-month decision, B2, common-slope model
3. Compact method sequence: input → poolability → bound → decision record
4. Supported / not-supported scope table
5. Reproducibility and local-execution evidence
6. Installation and documentation links
7. Plain disclaimer and compact footer

## Anti-slop rules

### Never use

- a centered generic hero with a badge or pill above it;
- a miniature fake dashboard as hero decoration;
- gradients, glows, glassmorphism, blobs, floating ornaments, or novelty art;
- rows of equal feature cards or boxes nested inside boxes;
- a mono uppercase eyebrow above every heading;
- numbered `01 / 02 / 03` rows used only as visual decoration;
- oversized editorial-serif marketing copy;
- status pills, dots, hashes, or code typography as ornament;
- “public face,” “hiring signal,” “portfolio story,” “design system,” or
  behind-the-scenes design language in user-facing copy;
- vague headlines such as “A better way to...” or “Built for modern teams.”

### Prefer

- direct statements that only this product can truthfully make;
- real plots, decision values, model names, warnings, and files;
- whitespace, alignment, typographic hierarchy, and simple horizontal rules;
- plain tables and lists when the content is tabular or sequential;
- one primary action and one supporting action per section;
- captions that distinguish sample evidence from live computation.

## Voice

Use concise, scientifically literate language.

Preferred terms:

- reproducible
- inspectable
- decision support
- ICH Q1E-inspired
- one-sided 95% mean-response bound
- governing batch
- decision record
- local execution

Avoid:

- revolutionary
- AI-powered
- compliance automation
- GxP-ready
- regulatory approved
- validated
- enterprise platform
- audit-proof

## Typography

Use no more than two families on the public site.

- Body, navigation, controls, and marketing headings: `IBM Plex Sans`.
- Code, p-values, hashes, filenames, and commands only: `IBM Plex Mono`.

`Newsreader` may remain inside generated reports or as a restrained product-name
detail, but it must not drive oversized public-site hero and section headings.

Minimum guidance:

- body: 16px desktop, at least 15px mobile;
- supporting text: at least 14px;
- navigation and buttons: at least 14px;
- comfortable prose width: approximately 55–70 characters;
- no letter-spaced uppercase prose.

## Color and surfaces

The selected public direction is **Graphite Dark**. It uses a restrained
instrument-panel palette without glow, gradients, or decorative dashboard UI.

| Token | Hex | Public-site use |
|---|---|---|
| Graphite | `#0e171f` | base page |
| Surface | `#111d27` | restrained secondary band or command field |
| Raised surface | `#14222d` | exceptional inset surface |
| White | `#f4f7f9` | primary text; real plot field remains white |
| Muted blue-grey | `#aab8c2` | secondary text |
| Rule | `#314453` | simple separators |
| Action red | `#dc6256` | primary action and limiting result only |
| Evidence blue | `#58a8ce` | links and observed-data meaning |
| Supported green | `#69b487` | supported/pass meaning only |
| Amber | `#d8a75b` | warnings only |

The page should mostly be one continuous surface. Use a subtle tint or border
only when spacing and alignment are insufficient. Shadows are exceptional.

## Layout

- Maximum content width: approximately 1120px.
- Use an asymmetric evidence-led hero only when the right side contains the real
  plot or report evidence—not a fabricated dashboard.
- Avoid more than two columns for meaningful content.
- On mobile, preserve reading order and remove secondary metadata rather than
  squeezing it into micro-grids.
- Keep the complete public page to roughly five to seven substantive sections.

## Accessibility baseline

Every redesign must include:

- semantic `header`, `nav`, `main`, `section`, and `footer` landmarks;
- one logical heading outline per rendered page state;
- visible `:focus-visible` treatment;
- keyboard-operable navigation and actions;
- `prefers-reduced-motion` handling for any nonessential motion;
- explicit `type="button"` on non-submit buttons;
- `rel="noopener noreferrer"` on new-tab links;
- descriptive link text and captions;
- mobile reflow and zoom resilience;
- measured color contrast before release.

Do not claim WCAG conformance from screenshots or automated checks alone.

## Scientific and legal boundary

The public page must state plainly that OpenPharmaStability is educational and
decision-support software. It is not a validated GxP system, does not provide
21 CFR Part 11 controls, and is not submission-ready or a regulatory-approval
tool. Do not paraphrase away the stronger disclaimer in generated reports.

## Acceptance test for a public-site revision

- A scientist can identify the supported decision within the first viewport.
- The hero contains real evidence or no visual—not a decorative dashboard.
- Documentation, Sample report, and GitHub are immediately available.
- There is no public design-system showcase or hiring-process language.
- Desktop and mobile screenshots have been inspected, not merely generated.
- Keyboard focus, reduced motion, semantic structure, links, and responsive
  behavior have been checked.
- Site copy matches the golden data and current engine version.
- Python tests and golden regeneration still pass.
- `site/` is synchronized, production is deployed, and canonical HTML matches
  the local deploy artifact.
