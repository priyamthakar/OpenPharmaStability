# Public-site UI/UX audit — 2026-07-17

> **Historical audit.** Its redesign recommendations were implemented and
> verified in the Graphite Dark public site. For the living implementation
> contract, read `DESIGN.md`, `design-qa.md`, and `NEXT_STEPS.md` §11.

Surface: https://openpharmastability.pages.dev  
Evidence folder: `qa-output/`  
Detailed working report: `qa-output/ui-ux-audit.md`

## Verdict

The public site is accurate, responsive, and functionally healthy, but its
presentation reads like an AI-generated portfolio case study rather than
scientific software. The problem is cumulative: a decorative dashboard hero,
mono uppercase eyebrow labels, oversized editorial-serif headings, numbered
process rows, repeated bordered panels, status pills, a feature matrix, and a
public design-system showcase all use familiar generated-site conventions.

The right response is subtraction. The real confidence plot, supported
shelf-life decision, model selection, warnings, decision record, and install
command already provide a distinctive visual and content system.

## Captured flow

| Step | Screenshot | Health | Main finding |
|---|---|---|---|
| Desktop overview | `qa-output/desktop-home.png` | Needs substantial revision | Attractive at a glance, but over-authored and templated; the mock dashboard and portfolio/process language dominate. |
| Desktop app preview | `qa-output/desktop-app.png` | Structurally healthy | Clear workflow, but looks operational despite being a static preview; retain only as an honestly captioned screenshot. |
| Desktop design system | `qa-output/desktop-design.png` | Remove publicly | Useful internal reference, irrelevant to scientists and the strongest portfolio-showcase signal. |
| Desktop report section | `qa-output/desktop-sample-report.png` | Strong evidence, poor placement | The real plot/result is persuasive but appears too late. |
| Mobile overview | `qa-output/mobile-home.png` | Functional, excessively long | Reflows without overlap but becomes a long stack of labels, cards, micro-grids, and repeated explanations. |
| Mobile app preview | `qa-output/mobile-app.png` | Mostly healthy | Decision flow survives; secondary artifacts and audit facts should collapse. |
| Mobile design system | `qa-output/mobile-design.png` | Unhealthy public experience | Dense component catalogue with little value to the intended audience. |

The automated production QA also confirmed that navigation, warnings/JSON
states, truth copy, and all sample HTML/JSON/plot links work. No layout
regressions or console errors were reported.

## Highest-impact changes

1. Replace `Overview / App UI / Design System` with
   `Documentation / Sample report / GitHub`.
2. Replace the hero's decorative workspace with the real confidence plot and
   17-month example decision.
3. Delete public-facing process language: “Public face,” “Hiring signal,”
   “portfolio story,” architecture self-commentary, and `DESIGN.md` display.
4. Move real sample evidence directly below the hero.
5. Collapse Method, Capability, Technical case study, Architecture, and
   Positioning into one concise method/scope section.
6. Use plain tables/lists instead of feature cells and repeated cards.
7. Reserve mono type for code, p-values, hashes, and filenames.
8. Use the sans face for public headings; keep editorial serif use restrained.
9. Remove most enclosing cards, pills, decorative status dots, and shadows.
10. Add semantic structure, focus-visible styling, reduced-motion behavior,
    explicit button types, and safe new-tab link relations.

## Source-level risks

The audited `site/index.html` contained:

- 467 `div` elements;
- 628 inline `style` attributes;
- no explicit `:focus` rules;
- no `prefers-reduced-motion` rule;
- no ARIA attributes;
- 11 buttons without explicit `type`;
- 11 new-tab links without `rel`;
- no `h3` elements despite visually implied subsections.

These observations are implementation risks, not a claim of WCAG failure or
conformance. Keyboard, screen-reader, measured contrast, and 200–400% zoom
checks remain part of redesign acceptance.

## Research grounding

- [Impeccable's slop catalogue](https://impeccable.style/slop/) identifies
  nested cards, oversized editorial-serif heroes, uppercase eyebrow labels,
  copy-paste layouts, and motion without meaning as recurring generated-design
  tells.
- [Slopless Design](https://www.slopless.design/) emphasizes that generic copy,
  repeated boxes, and decorative dashboard complexity compound into sameness.
- [W3C page-structure guidance](https://www.w3.org/WAI/tutorials/page-structure/)
  recommends meaningful landmarks and logical headings for navigation and
  orientation.
- [web.dev accessible responsive design](https://web.dev/articles/accessible-responsive-design)
  explains that responsive layouts should remain readable and functional under
  substantial zoom, not only avoid horizontal overflow.

## Design contract

`DESIGN.md` is the implementation contract derived from this audit.
`NEXT_STEPS.md` §11 contains the execution order and acceptance checklist.

