"""
report_builder.py — Generate an interactive HTML visual diff report.

Produces diff_summary.html in the patches directory.
Features:
  - Side-by-side red/green diff per page
  - Filter buttons: All, Punctuation, Space fixes, Conjunct, Spelling, No changes
  - Summary statistics bar
"""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Change-type badge colors ─────────────────────────────────────────────────
_BADGE_COLORS: dict[str, str] = {
    "punctuation_clean": "#f59e0b",
    "space_fix":         "#3b82f6",
    "conjunct_fix":      "#8b5cf6",
    "spelling_fix":      "#ef4444",
    "insert":            "#10b981",
    "remove":            "#6b7280",
}
_DEFAULT_BADGE = "#9ca3af"


def _badge(change_type: str) -> str:
    color = _BADGE_COLORS.get(change_type, _DEFAULT_BADGE)
    label = change_type.replace("_", " ").title()
    return (
        f'<span class="badge" style="background:{color}">'
        f'{html.escape(label)}</span>'
    )


def _render_diff_row(ch: dict) -> str:
    orig = html.escape(ch.get("original", ""))
    prop = html.escape(ch.get("proposed", ""))
    reason = html.escape(ch.get("reason", ""))
    line_no = ch.get("line", "?")
    ctype = ch.get("type", "")
    return f"""
        <tr class="change-row" data-type="{html.escape(ctype)}">
          <td class="line-no">L{line_no}</td>
          <td>{_badge(ctype)}</td>
          <td class="diff-old">{orig}</td>
          <td class="diff-new">{prop}</td>
          <td class="reason">{reason}</td>
        </tr>"""


def _render_page_section(diff_data: dict) -> str:
    page = diff_data.get("page", "?")
    changes = diff_data.get("changes", [])
    count = diff_data.get("changes_count", len(changes))

    if not changes:
        return f"""
      <details class="page-section no-changes">
        <summary>Page {page} <span class="count-badge zero">0 changes</span></summary>
        <p class="no-change-msg">✅ No OCR corrections proposed for this page.</p>
      </details>"""

    rows = "".join(_render_diff_row(ch) for ch in changes)
    return f"""
      <details class="page-section" open>
        <summary>Page {page} <span class="count-badge">{count} change(s)</span></summary>
        <table class="diff-table">
          <thead>
            <tr>
              <th>Line</th><th>Type</th>
              <th>Original (raw OCR)</th><th>Proposed (corrected)</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>{rows}
          </tbody>
        </table>
      </details>"""


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="gu">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — OCR Diff Report</title>
  <style>
    :root {{
      --bg: #0f172a; --surface: #1e293b; --border: #334155;
      --text: #e2e8f0; --muted: #94a3b8;
      --del: #450a0a; --del-text: #fca5a5;
      --add: #052e16; --add-text: #86efac;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif;
            font-size: 14px; line-height: 1.6; padding: 20px; }}
    h1 {{ font-size: 1.6rem; margin-bottom: 4px; }}
    .subtitle {{ color: var(--muted); margin-bottom: 16px; }}
    .stats-bar {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
    .stat {{ background: var(--surface); border: 1px solid var(--border);
             border-radius: 8px; padding: 8px 16px; }}
    .stat .num {{ font-size: 1.4rem; font-weight: 700; }}
    .filters {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }}
    .filter-btn {{ background: var(--surface); border: 1px solid var(--border);
                   color: var(--text); padding: 6px 14px; border-radius: 20px;
                   cursor: pointer; font-size: 13px; transition: all 0.2s; }}
    .filter-btn:hover, .filter-btn.active {{ background: #3b82f6; border-color: #3b82f6; }}
    .page-section {{ background: var(--surface); border: 1px solid var(--border);
                     border-radius: 10px; margin-bottom: 12px; overflow: hidden; }}
    .page-section > summary {{ padding: 12px 16px; cursor: pointer; font-weight: 600;
                                display: flex; align-items: center; gap: 10px;
                                list-style: none; }}
    .page-section > summary:hover {{ background: rgba(255,255,255,0.04); }}
    .count-badge {{ background: #3b82f6; color: #fff; font-size: 12px;
                    padding: 2px 8px; border-radius: 12px; }}
    .count-badge.zero {{ background: #1e3a5f; }}
    .no-change-msg {{ padding: 12px 16px; color: var(--muted); }}
    .diff-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    .diff-table th {{ background: #0f172a; text-align: left; padding: 8px 10px;
                       border-bottom: 1px solid var(--border); color: var(--muted); }}
    .diff-table td {{ padding: 7px 10px; border-bottom: 1px solid var(--border);
                       vertical-align: top; }}
    .diff-old {{ background: var(--del); color: var(--del-text);
                 font-family: 'Noto Sans Gujarati', monospace; white-space: pre-wrap; }}
    .diff-new {{ background: var(--add); color: var(--add-text);
                 font-family: 'Noto Sans Gujarati', monospace; white-space: pre-wrap; }}
    .line-no {{ color: var(--muted); font-size: 12px; white-space: nowrap; }}
    .reason {{ color: var(--muted); font-size: 12px; }}
    .badge {{ color: #fff; font-size: 11px; padding: 1px 7px; border-radius: 10px;
              white-space: nowrap; }}
    .no-changes {{ opacity: 0.55; }}
    .hidden {{ display: none !important; }}
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Gujarati&display=swap');
  </style>
</head>
<body>
  <h1>📄 OCR Diff Report</h1>
  <div class="subtitle">{book_slug} — Generated by Phase 3 LLM Verification</div>

  <div class="stats-bar">
    <div class="stat"><div class="num">{total_pages}</div><div>Pages</div></div>
    <div class="stat"><div class="num">{pages_with_changes}</div><div>Pages with changes</div></div>
    <div class="stat"><div class="num">{total_changes}</div><div>Total changes</div></div>
    <div class="stat" style="border-color:#f59e0b">
      <div class="num">{punct_count}</div><div>Punctuation</div></div>
    <div class="stat" style="border-color:#3b82f6">
      <div class="num">{space_count}</div><div>Space fixes</div></div>
    <div class="stat" style="border-color:#8b5cf6">
      <div class="num">{conjunct_count}</div><div>Conjunct fixes</div></div>
    <div class="stat" style="border-color:#ef4444">
      <div class="num">{spelling_count}</div><div>Spelling fixes</div></div>
  </div>

  <div class="filters">
    <button class="filter-btn active" onclick="filterChanges('all')">All</button>
    <button class="filter-btn" onclick="filterChanges('punctuation_clean')">Punctuation</button>
    <button class="filter-btn" onclick="filterChanges('space_fix')">Space Fixes</button>
    <button class="filter-btn" onclick="filterChanges('conjunct_fix')">Conjunct Fixes</button>
    <button class="filter-btn" onclick="filterChanges('spelling_fix')">Spelling Fixes</button>
    <button class="filter-btn" onclick="filterChanges('no-changes')">No Changes</button>
  </div>

  <div id="pages">
    {page_sections}
  </div>

  <script>
    function filterChanges(type) {{
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');

      document.querySelectorAll('.page-section').forEach(sec => {{
        if (type === 'all') {{ sec.classList.remove('hidden'); return; }}
        if (type === 'no-changes') {{
          sec.classList.toggle('hidden', !sec.classList.contains('no-changes'));
          return;
        }}
        const rows = sec.querySelectorAll('.change-row[data-type="' + type + '"]');
        sec.querySelectorAll('.change-row').forEach(r => r.classList.add('hidden'));
        rows.forEach(r => r.classList.remove('hidden'));
        sec.classList.toggle('hidden', rows.length === 0);
      }});
    }}
  </script>
</body>
</html>
"""


def build_report(
    book_slug: str,
    patches_dir: Path,
    output_html: Path | None = None,
) -> Path:
    """
    Read all *_diff.json files in patches_dir and produce diff_summary.html.

    Parameters
    ----------
    output_html : defaults to patches_dir/diff_summary.html
    """
    if output_html is None:
        output_html = patches_dir / "diff_summary.html"

    json_files = sorted(patches_dir.glob("page_*_diff.json"))
    if not json_files:
        logger.warning("No *_diff.json files found in %s", patches_dir)
        output_html.write_text("<p>No diff data found.</p>", encoding="utf-8")
        return output_html

    all_diffs: list[dict] = []
    for jf in json_files:
        try:
            all_diffs.append(json.loads(jf.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("Could not parse %s: %s", jf, exc)

    # ── statistics ───────────────────────────────────────────────────────────
    total_pages = len(all_diffs)
    pages_with_changes = sum(1 for d in all_diffs if d.get("changes_count", 0) > 0)
    all_changes = [ch for d in all_diffs for ch in d.get("changes", [])]
    total_changes = len(all_changes)
    punct_count = sum(1 for c in all_changes if c["type"] == "punctuation_clean")
    space_count = sum(1 for c in all_changes if c["type"] == "space_fix")
    conjunct_count = sum(1 for c in all_changes if c["type"] == "conjunct_fix")
    spelling_count = sum(1 for c in all_changes if c["type"] == "spelling_fix")

    page_sections = "".join(_render_page_section(d) for d in all_diffs)

    html_content = _HTML_TEMPLATE.format(
        title=book_slug,
        book_slug=book_slug,
        total_pages=total_pages,
        pages_with_changes=pages_with_changes,
        total_changes=total_changes,
        punct_count=punct_count,
        space_count=space_count,
        conjunct_count=conjunct_count,
        spelling_count=spelling_count,
        page_sections=page_sections,
    )

    output_html.write_text(html_content, encoding="utf-8")
    logger.info("HTML report written → %s", output_html)
    return output_html
