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
