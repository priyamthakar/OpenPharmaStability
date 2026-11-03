# CLAUDE.md

Project instructions for coding agents live in the repository docs. Read, in order:

1. `HANDOVER.md` — current state and verification block.
2. `NEXT_STEPS.md` — §7 (env integrity) and §8 (handover protocol) before any code change.
3. `AGENTS.md` and `OpenPharmaStability.md` — execution plan and product spec.

Key rules: the Python statistics engine is authoritative (do not reimplement it in JS/TS);
`openpharmastability/contracts.py` is a frozen API seam; do not change `DEFAULT_PROFILE`,
guidance-profile values, or goldens without the gates in `NEXT_STEPS.md` §10.
Verify with `make test` and `make regen-check`.
