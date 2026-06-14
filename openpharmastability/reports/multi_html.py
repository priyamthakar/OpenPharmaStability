"""Multi-attribute HTML report (v0.2.0).

Renders a :class:`MultiAttributeResult` as a single HTML file with:
- An executive summary at the top.
- An overall decision table.
- One section per analyzed attribute (re-using the existing
  per-attribute plot PNGs saved by the CLI).
- A reproducibility block.
- The verbatim disclaimer.

The template is intentionally simple (no jinja dependency in this
file — the inline string is small and easy to audit). The v0.1
single-attribute report is unchanged; the new
``render_multi_html`` function is the multi-attribute companion.
"""
from __future__ import annotations

import html
import os
from typing import Any

from openpharmastability.contracts import DISCLAIMER, MultiAttributeResult


def _esc(s: Any) -> str:
    return html.escape("" if s is None else str(s))


def _per_attr_block(idx: int, ar, plot_relpath: str | None) -> str:
    r = ar.result
    meta = ar.metadata
    role = ar.metadata.attribute_role.value
    plot_html = (
        f'<img src="{_esc(plot_relpath)}" alt="confidence plot for '
        f'{_esc(ar.metadata.attribute)}" />'
        if plot_relpath
        else '<p><em>No plot available for this attribute.</em></p>'
    )
    # v0.4.0: ICH Q1A significant-change gate verdict for this attribute.
    # Only surface the row when the gate was actually exercised (i.e.
    # the engine populated either the rationale or the per-criterion
    # details). When both are empty (v0.3.x callers), the row is hidden
    # so the report stays quiet about a gate it never ran.
    sc_accel = getattr(r, "significant_change_accelerated", None)
    sc_inter = getattr(r, "significant_change_intermediate", None)
    sc_extrap_allowed = bool(getattr(r, "extrapolation_allowed", True))
    sc_rationale = str(getattr(r, "extrapolation_rationale", "") or "")
    sc_details = getattr(r, "significant_change_details", {}) or {}
    show_sc = bool(sc_rationale) or bool(sc_details)
    if show_sc:
        accel_str = str(sc_accel) if sc_accel is not None else "—"
        inter_str = str(sc_inter) if sc_inter is not None else "—"
        allowed_str = "yes" if sc_extrap_allowed else "NO"
        sc_block = (
            f'<p><strong>ICH Q1A gate:</strong> '
            f'accelerated={_esc(accel_str)} &middot; '
            f'intermediate={_esc(inter_str)} &middot; '
            f'allowed={_esc(allowed_str)} &middot; '
            f'rationale=<code>{_esc(sc_rationale or "—")}</code></p>'
        )
    else:
        sc_block = ""
    # v0.5.0: per-attribute advanced-statistics opt-ins. Each block is
    # rendered only when the corresponding result attribute is
    # populated (Arrhenius / MKT / reduced design) or when the
    # attribute was fit with random-effects / mixed model. ``getattr``
    # keeps this robust against hand-built fixtures that predate the
    # v0.5.0 fields. The model-effects marker is also shown when the
    # attribute used random effects, so the multi-report can surface
    # non-Q1E modeling choices without changing the fixed-effect case.
    model_eff = str(getattr(r, "model_effects", "fixed") or "fixed")
    arr_present = getattr(r, "arrhenius_result", None) is not None
    mkt_present = getattr(r, "mkt_celsius", None) is not None
    rd_present = getattr(r, "reduced_design_report", None) is not None
    v5_bits = ""
    if model_eff != "fixed":
        v5_bits += (
            f'<p><strong>Model effects:</strong> '
            f'<code>{_esc(model_eff)}</code></p>'
        )
        # v0.5.1: mirror the single-attribute "Model convergence" row
        # on the per-attribute block of the multi-attribute report.
        # Gated on ``model_effects == "random"`` so the fixed-effect
        # default pipeline (the v0.4 / v0.5.0 path) stays quiet.
        mc = getattr(r, "model_convergence", None) or {}
        converged = "converged" if mc.get("converged", True) else "NOT converged"
        boundary = " (boundary)" if mc.get("boundary", False) else ""
        v5_bits += (
            f'<p><strong>Mixed-model convergence:</strong> '
            f'{_esc(converged)}{_esc(boundary)}</p>'
        )
    if arr_present:
        ar = r.arrhenius_result
        v5_bits += (
            f'<p><strong>Arrhenius:</strong> '
            f'n_temps={_esc(ar.n_temps)}, '
            f'Ea={_esc(f"{ar.Ea_J_per_mol:.2f}")} J/mol, '
            f'R²={_esc(f"{ar.r_squared:.4f}")}, '
            f'predicted k at {_esc(ar.storage_temp_C)} °C = '
            f'{_esc(f"{ar.predicted_k_at_storage:.4g}")} 1/month</p>'
        )
    # v0.7.0: per-attribute sensitivity report. Mirrors the single-
    # attribute "Sensitivity analysis" section header, but in the
    # multi-attribute compact summary the block is reduced to a
    # single inline paragraph carrying just the summary string.
    # Gated on `getattr(..., default)` so the multi-HTML
    # renderer stays forward-compatible with hand-built fixtures
    # that predate the v0.7.0 field.
    sr = getattr(r, "sensitivity_report", None)
    if sr is not None:
        # v0.8.0: surface the drop mode inline so the multi-attribute
        # report tells the reader whether the row-level or
        # batch-level variant produced the per-attribute rows.
        # Defaults to ``"row"`` when the field is missing
        # (forward-compat against hand-built fixtures).
        sr_mode = str(getattr(sr, "mode", "row") or "row")
        mode_label = "batch-level" if sr_mode == "batch" else "row-level"
        v5_bits += (
            f'<p><strong>Sensitivity:</strong> '
            f'<em>{_esc(getattr(sr, "summary", ""))}</em> '
            f'({_esc(mode_label)})</p>'
        )
    # v0.8.0: per-attribute Arrhenius-driven shelf-life
    # prediction. Mirrors the single-attribute "Arrhenius-driven
    # shelf-life prediction" section in the multi-attribute
    # compact summary. Gated on `getattr(..., default)` so the
    # multi-HTML renderer stays forward-compatible with
    # hand-built fixtures that predate the v0.8.0 field.
    # Exploratory only; the official Q1E shelf-life decision on
    # the per-attribute result above is unchanged.
    asl = getattr(r, "arrhenius_shelf_life", None)
    if asl is not None:
        asl_shelf = getattr(asl, "predicted_shelf_life_months", None)
        asl_cross = getattr(
            asl, "predicted_statistical_crossing_months", None
        )
        v8_bits = (
            f'<p><strong>Arrhenius shelf-life:</strong> '
            f'predicted={_esc(asl_shelf if asl_shelf is not None else "n/a")} mo '
            f'at { _esc(getattr(asl, "storage_temp_C", "?")) } &deg;C '
            f'(crossing={_esc(f"{asl_cross:.2f} mo" if asl_cross is not None else "n/a")})</p>'
        )
        v5_bits += v8_bits
    if mkt_present:
        v5_bits += (
            f'<p><strong>MKT:</strong> '
            f'{_esc(f"{r.mkt_celsius:.2f}")} °C</p>'
        )
    if rd_present:
        rd = r.reduced_design_report
        v5_bits += (
            f'<p><strong>Reduced design:</strong> '
            f'bracketed={_esc("yes" if rd.is_bracketed else "no")}, '
            f'matrixed={_esc("yes" if rd.is_matrixed else "no")}, '
            f'missing_cells={_esc(len(rd.missing_cells))}</p>'
        )
    # v0.6.0: read the per-attribute spec from the AttributeMetadata
    # (which is the authoritative per-attribute spec context, populated
    # from the metadata CSV/XLSX or the per-row data). Reading from
    # ``r.fit.design`` (always empty for the per-attribute StabilityResult)
    # or ``r.metadata.lower_spec`` (a non-existent attribute on
    # StabilityResult — its ``metadata`` is a dict, not a dataclass with
    # ``.lower_spec``) silently produced "lower=None, upper=None" for
    # every attribute. Use ``ar.metadata`` and render missing values as
    # the em-dash placeholder so the report reads correctly.
    lower_spec = ar.metadata.lower_spec
    upper_spec = ar.metadata.upper_spec
    lower_disp = _esc(f"{lower_spec:g}" if lower_spec is not None else "—")
    upper_disp = _esc(f"{upper_spec:g}" if upper_spec is not None else "—")
    return f"""
<section class="attribute" id="attr-{idx}">
  <h2>Attribute: {_esc(meta.attribute)}{' (' + _esc(meta.unit) + ')' if meta.unit else ''}</h2>
  <p><strong>Role:</strong> {_esc(role)} &middot;
     <strong>Direction:</strong> {_esc(r.direction.value)} &middot;
     <strong>Spec:</strong>
     lower={lower_disp},
     upper={upper_disp}</p>
  <p><strong>Model:</strong> {_esc(r.model.value)} &middot;
     <strong>Poolability:</strong> {_esc(r.poolability.decision.value)}
     (p<sub>slopes</sub>={_esc(f'{r.poolability.p_slopes:.3g}')},
      p<sub>intercepts</sub>={_esc(f'{r.poolability.p_intercepts:.3g}') if r.poolability.p_intercepts is not None else 'n/a'})</p>
  <p><strong>Crossing:</strong> {_esc(r.crossing.status.value)} &middot;
     <strong>Statistical:</strong> {_esc(f'{r.statistical_crossing_months:.2f} mo' if r.statistical_crossing_months is not None else 'n/a')} &middot;
     <strong>Governing batch:</strong> {_esc(r.crossing.governing_batch)}</p>
  <p><strong>Supported {r.deliverable_term}:</strong>
     {_esc(f'{r.supported_shelf_life_months} mo' if r.supported_shelf_life_months is not None else 'not limiting within horizon')}
     {' <em>(extrapolation flagged)</em>' if r.extrapolation_flag else ''}</p>
  {sc_block}
  {v5_bits}
  {plot_html}
  {('<h3>Warnings</h3><ul>' + ''.join(f'<li>{_esc(w)}</li>' for w in r.warnings) + '</ul>') if r.warnings else ''}
</section>
"""


def render_multi_html(
    result: MultiAttributeResult,
    plot_dir: str,
    out_path: str,
) -> None:
    """Render a multi-attribute HTML report to ``out_path``.

    Parameters
    ----------
    result:
        The :class:`MultiAttributeResult` to render.
    plot_dir:
        Directory where per-attribute plot PNGs were saved (absolute
        or relative). The HTML embeds the **relative path from the
        HTML file's directory to each plot** so the report renders
        correctly whether plots live in a sub-directory (the default
        ``<out_dir>/plots``) or alongside the HTML itself.
    out_path:
        Destination path for the HTML. The directory is created
        if missing.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    # The HTML is the anchor for resolving relative image paths in the
    # browser. Compute its absolute directory once and pass it down so
    # per-attribute plot references point at the right location, whether
    # the plots live in a sub-directory (the default ``<out_dir>/plots``)
    # or in the same directory as the report itself.
    html_dir = os.path.dirname(os.path.abspath(out_path)) or "."

    n_total = len(result.attributes)
    n_lim = sum(1 for a in result.attributes if a.included_in_limiting_decision)
    overview_table_rows = "".join(
        f"<tr>"
        f"<td>{_esc(ar.metadata.attribute)}</td>"
        f"<td>{_esc(ar.metadata.attribute_role.value)}</td>"
        f"<td>{_esc(ar.result.model.value)}</td>"
        f"<td>{_esc(ar.result.poolability.decision.value)}</td>"
        f"<td>{_esc(ar.result.crossing.status.value)}</td>"
        f"<td>{_esc(f'{ar.result.statistical_crossing_months:.2f}' if ar.result.statistical_crossing_months is not None else 'n/a')}</td>"
        f"<td>{_esc(ar.result.supported_shelf_life_months if ar.result.supported_shelf_life_months is not None else 'n/a')}</td>"
        f"<td>{'yes' if ar.included_in_limiting_decision else f'no ({_esc(ar.exclusion_reason)})'}</td>"
        f"</tr>"
        for ar in result.attributes
    )

    attr_sections = "".join(
        _per_attr_block(i, ar, _rel_plot(plot_dir, ar.metadata.attribute, html_dir))
        for i, ar in enumerate(result.attributes)
    )

    md = result.metadata
    meta_rows = "".join(
        f"<tr><th>{_esc(k)}</th><td><code class='mono'>{_esc(v)}</code></td></tr>"
        for k, v in md.items()
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OpenPharmaStability multi-attribute report — {_esc(result.condition)}</title>
<base href="{_esc(_to_file_url(html_dir))}">
<style>
  body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; max-width: 1100px; margin: 2em auto; padding: 0 1em; color: #222; }}
  h1, h2, h3 {{ color: #1a365d; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4em 0.6em; text-align: left; vertical-align: top; }}
  th {{ background: #f3f4f6; }}
  code.mono {{ font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 0.92em; }}
  .disclaimer {{ background: #fef3c7; border-left: 4px solid #d97706; padding: 0.8em 1em; margin: 1.5em 0; }}
  img {{ max-width: 100%; height: auto; border: 1px solid #ddd; margin: 0.5em 0; }}
  .muted {{ color: #666; font-size: 0.92em; }}
  section.attribute {{ border-top: 1px solid #e5e7eb; margin-top: 1.5em; padding-top: 1em; }}
</style>
</head>
<body>

<h1>OpenPharmaStability multi-attribute report</h1>
<p class="muted">Tool version {_esc(md.get('tool_version', '?'))} &middot;
   Python {_esc(md.get('library_versions', {}).get('python', '?'))} &middot;
   pandas {_esc(md.get('library_versions', {}).get('pandas', '?'))}</p>

<div class="disclaimer">
  <strong>Disclaimer.</strong> {_esc(DISCLAIMER)}
</div>

<h2>Executive summary</h2>
<table>
  <tr><th>Condition</th><td>{_esc(result.condition)}</td></tr>
  <tr><th>Product type</th><td>{_esc(result.product_type)}</td></tr>
  <tr><th>Deliverable term</th><td>{_esc(result.deliverable_term)}</td></tr>
  <tr><th>Overall supported {result.deliverable_term}</th>
      <td><strong>{_esc(result.supported_shelf_life_months if result.supported_shelf_life_months is not None else 'not limiting within horizon')}</strong>
          {' <em>(extrapolation flagged)</em>' if any(ar.result.extrapolation_flag for ar in result.attributes) else ''}</td></tr>
  <tr><th>Limiting attribute</th><td>{_esc(result.limiting_attribute if result.limiting_attribute is not None else 'none (no attribute eligible)')}</td></tr>
  <tr><th>Attributes analyzed</th><td>{n_total} ({n_lim} eligible for limiting decision)</td></tr>
  <tr><th>Observed data length</th><td>{_esc(result.observed_data_months)} mo</td></tr>
</table>

<h2>Overall decision</h2>
<table>
  <tr>
    <th>Attribute</th><th>Role</th><th>Model</th><th>Poolability</th>
    <th>Crossing</th><th>Statistical (mo)</th><th>Supported (mo)</th><th>Limiting?</th>
  </tr>
  {overview_table_rows}
</table>

<h2>Per-attribute details</h2>
{attr_sections if attr_sections else '<p><em>No attributes analyzed.</em></p>'}

{('<h2>Top-level warnings</h2><ul>' + ''.join(f'<li>{_esc(w)}</li>' for w in result.warnings) + '</ul>') if result.warnings else ''}

<h2>Reproducibility</h2>
<table>
{meta_rows}
</table>

<p class="muted">End of report.</p>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)


def _rel_plot(plot_dir: str, attribute: str, html_dir: str) -> str | None:
    """Return the relative path from the HTML report's directory
    to the per-attribute plot PNG. Returns None if the file does
    not exist.
    """
    if not plot_dir:
        return None
    filename = f"{attribute}_confidence_plot.png"
    # Resolve plot_dir to an absolute path.
    if not os.path.isabs(plot_dir):
        plot_dir = os.path.abspath(os.path.join(html_dir, plot_dir))
    plot_file = os.path.join(plot_dir, filename)
    if not os.path.exists(plot_file):
        return None
    # Compute relative path from HTML dir to plot file.
    rel = os.path.relpath(plot_file, start=html_dir)
    return rel.replace(os.sep, "/")


def _to_file_url(html_dir: str) -> str:
    """Convert an absolute filesystem path to a file:// URL for use
    in a ``<base href>`` tag. Uses forward slashes and percent-encodes
    characters that are unsafe in URLs.
    """
    abs_dir = os.path.abspath(html_dir)
    # Make sure the path ends with a separator so the base resolves
    # relative to the directory, not to a sibling file.
    if not abs_dir.endswith(os.sep):
        abs_dir = abs_dir + os.sep
    posix = abs_dir.replace(os.sep, "/")
    return "file://" + posix


__all__ = ["render_multi_html"]
