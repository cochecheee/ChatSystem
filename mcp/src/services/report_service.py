from __future__ import annotations

import html
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import Finding

_SEV_COLOR = {
    "critical": "#ef4444",
    "high":     "#f97316",
    "medium":   "#eab308",
    "low":      "#22c55e",
    "info":     "#6b7280",
    "CRITICAL": "#ef4444",
    "HIGH":     "#f97316",
    "MEDIUM":   "#eab308",
    "LOW":      "#22c55e",
    "INFO":     "#6b7280",
}

_STATUS_COLOR = {
    "APPROVED":        "#22c55e",
    "REVOKED":         "#ef4444",
    "ai_analyzed":     "#3b82f6",
    "pending_review":  "#6b7280",
}


def _e(value: object) -> str:
    return html.escape(str(value)) if value is not None else ""


async def generate_html(db: AsyncSession, project_name: str = "Security Report") -> str:
    result = await db.execute(select(Finding))
    findings: list[Finding] = list(result.scalars().all())

    counts: dict[str, int] = {}
    for f in findings:
        sev = (f.severity or "info").lower()
        counts[sev] = counts.get(sev, 0) + 1

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    total = len(findings)

    severity_rows = "".join(
        f"<tr><td style='color:{_SEV_COLOR.get(s, '#888')}'><b>{s.upper()}</b></td><td>{c}</td></tr>"
        for s, c in sorted(counts.items(), key=lambda x: ["critical","high","medium","low","info"].index(x[0]) if x[0] in ["critical","high","medium","low","info"] else 99)
    )

    finding_rows = ""
    for f in findings:
        sev_color = _SEV_COLOR.get((f.severity or "info").lower(), "#888")
        status_color = _STATUS_COLOR.get(f.status, "#888")
        ai_badge = "✓ AI" if f.ai_analysis else ""
        finding_rows += (
            f"<tr>"
            f"<td class='mono'>{_e(f.id)}</td>"
            f"<td class='mono' style='max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{_e(f.rule_id)}</td>"
            f"<td style='max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{_e(f.file_path)}"
            f"{' : ' + str(f.line_number) if f.line_number else ''}</td>"
            f"<td><span style='color:{sev_color};font-weight:600'>{_e(f.severity)}</span></td>"
            f"<td class='mono'>{_e(f.cwe_id)}</td>"
            f"<td><span style='color:{status_color}'>{_e(f.status)}</span></td>"
            f"<td style='color:#3b82f6'>{ai_badge}</td>"
            f"</tr>"
        )

    ai_sections = ""
    for f in findings:
        if not f.ai_analysis:
            continue
        a = f.ai_analysis
        diff_html = _e(a.get("remediation_diff", "")).replace("\n", "<br>")
        ai_sections += f"""
        <div class='ai-block'>
          <h4>Finding #{_e(f.id)} — {_e(f.rule_id)}</h4>
          <p><b>Confidence:</b> {_e(a.get('confidence'))}</p>
          <p><b>Giải thích:</b> {_e(a.get('explanation_vi'))}</p>
          <p><b>Tác động:</b> {_e(a.get('impact_vi'))}</p>
          <p><b>CWE:</b> {_e(a.get('cwe_reference'))}</p>
          <details>
            <summary>Remediation diff</summary>
            <pre class='diff'>{diff_html}</pre>
          </details>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sentinel SAST — {_e(project_name)}</title>
<style>
  :root {{ --bg: #0f1117; --card: #1a1d27; --border: #2d3148; --text: #e2e8f0; --muted: #6b7280; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background: var(--bg); color: var(--text); padding: 32px; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  h2 {{ font-size: 15px; margin: 24px 0 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: .05em; }}
  h4 {{ font-size: 13px; margin-bottom: 8px; }}
  .meta {{ color: var(--muted); font-size: 12px; margin-bottom: 24px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; padding: 6px 10px; color: var(--muted); border-bottom: 1px solid var(--border); white-space: nowrap; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  .mono {{ font-family: 'SF Mono',Consolas,monospace; }}
  .ai-block {{ background: #131820; border: 1px solid #2d3148; border-radius: 6px; padding: 14px; margin-bottom: 12px; font-size: 12.5px; line-height: 1.6; }}
  .ai-block p {{ margin-bottom: 6px; }}
  pre.diff {{ font-family: monospace; font-size: 11px; white-space: pre-wrap; background: #0a0d14; padding: 10px; border-radius: 4px; margin-top: 8px; }}
  .badge-total {{ display: inline-block; background: #3b82f6; color: #fff; border-radius: 4px; padding: 2px 8px; font-size: 12px; margin-left: 8px; }}
  footer {{ color: var(--muted); font-size: 11px; margin-top: 32px; text-align: center; }}
</style>
</head>
<body>
<h1>🛡 Sentinel SAST Report <span class='badge-total'>{total} findings</span></h1>
<div class='meta'>Generated {now}</div>

<h2>Summary by Severity</h2>
<div class='card'>
  <table>
    <thead><tr><th>Severity</th><th>Count</th></tr></thead>
    <tbody>{severity_rows}</tbody>
  </table>
</div>

<h2>All Findings</h2>
<div class='card'>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Rule</th><th>File</th><th>Severity</th><th>CWE</th><th>Status</th><th>AI</th>
      </tr>
    </thead>
    <tbody>{finding_rows}</tbody>
  </table>
</div>

<h2>AI Analysis</h2>
{ai_sections or "<div class='card'><p style='color:var(--muted)'>Chưa có finding nào được phân tích bởi AI.</p></div>"}

<footer>Sentinel SAST &mdash; DevSecOps Integration &mdash; {_e(project_name)}</footer>
</body>
</html>"""
