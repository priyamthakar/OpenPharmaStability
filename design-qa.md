# Design QA — Graphite Dark public site

## Comparison

- Selected reference: `design-concepts/revised-theme-2-graphite-dark.png`
- Implemented capture: `qa-output/desktop-home.png`
- Combined comparison: `qa-output/design-comparison-desktop.png`
- Desktop viewport: 1440 × 900, full page
- Mobile viewport: 375 × 812, full page

## Findings and fixes

1. The first implementation preserved the selected graphite palette,
   evidence-first hierarchy, compact ledger, red decision accent, blue links,
   IBM Plex typography, and rule-led layout.
2. The reference's illustrative dark chart was replaced intentionally with the
   real engine-generated confidence plot. This creates a white scientific
   evidence field while preserving result integrity.
3. Initial mobile QA found 127 px of horizontal overflow from intrinsic code
   block sizing. Grid children were allowed to shrink and code fields were
   constrained to their containers. The repeated mobile run measured zero
   overflow.
4. Desktop and mobile checks confirm semantic landmarks, the exact headline,
   required scientific facts, working evidence CTA, clean console, and HTTP 200
   sample report, multi-attribute report, and plot assets.
5. Public portfolio/design-system language and the previous mock application
   views are absent.

## Final result

final result: passed

## 2026-07-24 a11y re-check (Agent C)

**Outcome: no change required.** Spot-check of `DESIGN.md` §Accessibility baseline / `NEXT_STEPS.md` §11.6 against current Graphite Dark public site and local UI. No CSS or token edits; no `sync-site` run.

### Checked

**Public site** (`site/index.html`, source `OpenPharmaStability.dc.html`):

- Landmarks: `header`, `nav` (aria-label Primary), `main#main`, `section`s, `footer`
- Skip link to `#main`
- Global `:focus-visible` outline (`3px` Evidence blue `--blue`)
- `@media (prefers-reduced-motion: reduce)` disables smooth scroll / animations / transitions
- Nav preserved: Documentation / Sample report / GitHub
- New-tab links use `rel="noopener noreferrer"`
- Disclaimer / educational boundary copy intact (footer legal + assurance section)

**Local UI** (`openpharmastability/ui/static/{index.html,styles.css,app.js}`):

- Landmarks: `header.topbar`, `main.workspace`, labeled `aside`s, `section`s
- `:focus-visible` on buttons and links; form controls use visible `:focus` rings
- Non-submit controls use `type="button"`; submit uses `type="submit"`
- No CSS/JS transitions or animations → reduced-motion rule not applicable (no nonessential motion)
- Disclaimer panel remains; JS only injects server-provided disclaimer text (no stats in JS)

### Not changed

- Color tokens / Graphite Dark palette
- Public nav labels or IA
- Engine, profiles, goldens, hosted-backend plan, Q1 worksheets

Acceptance notes from the prior Graphite Dark QA pass above remain in force.
