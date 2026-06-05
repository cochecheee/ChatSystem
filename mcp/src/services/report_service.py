from __future__ import annotations

import html
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import Finding, Project
from ..repositories import FindingRepository
from ..repositories.finding_repo import DAST_TOOLS, DEPS_TOOLS

# ---------------------------------------------------------------------------
# Palette — light theme (báo cáo để in / xuất PDF / đính kèm email).
# ---------------------------------------------------------------------------
_SEV_ORDER = ["critical", "high", "medium", "low", "info"]
_SEV_FG = {
    "critical": "#dc2626", "high": "#ea580c", "medium": "#ca8a04",
    "low": "#16a34a", "info": "#64748b",
}
_SEV_BG = {
    "critical": "#fef2f2", "high": "#fff7ed", "medium": "#fefce8",
    "low": "#f0fdf4", "info": "#f8fafc",
}
_STATUS_LABEL = {
    "pending_review": ("Đang chờ", "#475569", "#f1f5f9"),
    "ai_analyzed": ("AI đã phân tích", "#2563eb", "#eff6ff"),
    "APPROVED": ("Đã duyệt bypass", "#16a34a", "#f0fdf4"),
    "REVOKED": ("Đã thu hồi", "#dc2626", "#fef2f2"),
}
_ACCENT = "#ff6a3d"

# Severity nào render dạng card chi tiết (actionable). Còn lại chỉ vào bảng tổng.
_DETAIL_SEVERITIES = {"critical", "high"}


def _e(value: object) -> str:
    return html.escape(str(value)) if value is not None else ""


def _sev(f: Finding) -> str:
    return (f.severity or "info").lower()


def _category(tool: str) -> str:
    t = (tool or "").lower()
    if t in DEPS_TOOLS:
        return "SCA"
    if t in DAST_TOOLS:
        return "DAST"
    return "SAST"


def _pct(n: int, total: int) -> str:
    return f"{(100 * n / total):.0f}%" if total else "0%"


# ---------------------------------------------------------------------------
# Component renderers
# ---------------------------------------------------------------------------

def _sev_chip(sev: str) -> str:
    fg = _SEV_FG.get(sev, "#64748b")
    return (f"<span class='chip' style='color:{fg};background:{_SEV_BG.get(sev, '#f1f5f9')};"
            f"border-color:{fg}33'>{sev.upper()}</span>")


def _status_chip(status: str) -> str:
    label, fg, bg = _STATUS_LABEL.get(status, (status, "#475569", "#f1f5f9"))
    return f"<span class='chip' style='color:{fg};background:{bg};border-color:{fg}33'>{_e(label)}</span>"


def _bar(counts: dict[str, int], total: int) -> str:
    """Thanh phân bố severity (stacked)."""
    if not total:
        return "<div class='bar empty'></div>"
    segs = ""
    for s in _SEV_ORDER:
        n = counts.get(s, 0)
        if n:
            segs += (f"<span style='width:{100*n/total}%;background:{_SEV_FG[s]}' "
                     f"title='{s}: {n}'></span>")
    return f"<div class='bar'>{segs}</div>"


def _hbar_rows(items: list[tuple[str, int]], total_max: int) -> str:
    rows = ""
    for label, n in items:
        w = (100 * n / total_max) if total_max else 0
        rows += (f"<div class='hbar'><div class='hl'>{_e(label)}</div>"
                 f"<div class='ht'><div class='hf' style='width:{w}%'></div></div>"
                 f"<div class='hv'>{n}</div></div>")
    return rows


def _finding_card(f: Finding) -> str:
    sev = _sev(f)
    rd = f.raw_data or {}
    cwe_name = rd.get("cwe_name")
    owasp = rd.get("owasp_category")
    pkg = rd.get("pkg_name")
    inst = rd.get("installed_version")
    fixed = rd.get("fixed_version")
    uri = rd.get("uri")
    solution = rd.get("solution")
    run_id = None
    try:
        run_id = f.artifact.github_run_id if f.artifact else None
    except Exception:
        run_id = None

    meta = []
    loc = _e(f.file_path) + (f" : {f.line_number}" if f.line_number else "")
    meta.append(("Vị trí", f"<span class='mono'>{loc}</span>"))
    meta.append(("Công cụ", f"<span class='tool'>{_e(f.tool)}</span> · {_category(f.tool)}"))
    if f.cwe_id:
        meta.append(("CWE", f"<span class='mono'>{_e(f.cwe_id)}</span>" + (f" — {_e(cwe_name)}" if cwe_name else "")))
    if owasp:
        meta.append(("OWASP", _e(owasp)))
    if f.cvss_score:
        meta.append(("CVSS", f"{f.cvss_score:g}"))
    if pkg:
        ver = _e(inst or "?")
        if fixed:
            ver += f" → <b style='color:#16a34a'>{_e(fixed)}</b> (đã có bản vá)"
        meta.append(("Gói", f"<span class='mono'>{_e(pkg)}</span> @ {ver}"))
    if uri:
        meta.append(("URL", f"<span class='mono'>{_e(uri)}</span>"))
    if run_id:
        meta.append(("Run", f"<span class='mono'>#{_e(run_id)}</span>"))

    meta_html = "".join(
        f"<div class='m'><span class='mk'>{k}</span><span class='mv'>{v}</span></div>"
        for k, v in meta
    )

    # Triage trail
    triage = ""
    if f.status == "APPROVED" and f.approved_by:
        triage = (f"<div class='triage ok'><b>Duyệt bypass</b> bởi {_e(f.approved_by)}"
                  + (f" — {_e(f.justification)}" if f.justification else "") + "</div>")
    elif f.status == "REVOKED" and f.revoked_by:
        triage = (f"<div class='triage no'><b>Thu hồi (false-positive)</b> bởi {_e(f.revoked_by)}"
                  + (f" — {_e(f.revoke_justification)}" if f.revoke_justification else "") + "</div>")

    if solution:
        triage += f"<div class='sol'><b>Khắc phục đề xuất:</b> {_e(solution)}</div>"

    # AI analysis
    ai_html = ""
    if f.ai_analysis:
        a = f.ai_analysis
        diff = _e(a.get("remediation_diff", "")).replace("\n", "<br>")
        parts = []
        if a.get("explanation_vi"):
            parts.append(f"<p><b>Giải thích:</b> {_e(a['explanation_vi'])}</p>")
        if a.get("impact_vi"):
            parts.append(f"<p><b>Tác động:</b> {_e(a['impact_vi'])}</p>")
        if a.get("confidence"):
            parts.append(f"<p><b>Độ tin cậy AI:</b> {_e(a['confidence'])}</p>")
        if diff.strip():
            parts.append(f"<details><summary>Diff khắc phục (AI)</summary><pre>{diff}</pre></details>")
        if parts:
            ai_html = f"<div class='ai'><div class='ai-h'>✦ Phân tích AI</div>{''.join(parts)}</div>"

    return f"""<div class='fcard' style='border-left-color:{_SEV_FG.get(sev, '#64748b')}'>
      <div class='fc-head'>
        {_sev_chip(sev)} {_status_chip(f.status)}
        <span class='fc-rule mono'>{_e(f.rule_id)}</span>
        <span class='fc-id'>#{_e(f.id)}</span>
      </div>
      <div class='fc-msg'>{_e(f.message)}</div>
      <div class='fc-meta'>{meta_html}</div>
      {triage}
      {ai_html}
    </div>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def generate_html(
    db: AsyncSession,
    project_name: str = "Tất cả dự án",
    project_id: int | None = None,
    severity: str | None = None,
) -> str:
    """Render báo cáo bảo mật chi tiết (HTML, light theme, in/PDF-friendly)."""
    findings: list[Finding] = await FindingRepository(db).list_for_report(
        project_id=project_id, severity=severity,
    )

    # Tên project (nếu lọc theo 1 project).
    if project_id is not None:
        proj = (await db.execute(select(Project).where(Project.id == project_id))).scalars().first()
        if proj is not None:
            project_name = proj.name

    total = len(findings)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # --- aggregations ---
    by_sev = Counter(_sev(f) for f in findings)
    by_status = Counter(f.status for f in findings)
    by_tool = Counter(f.tool for f in findings)
    by_cat = Counter(_category(f.tool) for f in findings)
    by_owasp = Counter((f.raw_data or {}).get("owasp_category") for f in findings if (f.raw_data or {}).get("owasp_category"))
    by_cwe = Counter(
        (f.cwe_id, (f.raw_data or {}).get("cwe_name"))
        for f in findings if f.cwe_id
    )
    open_n = sum(1 for f in findings if f.status not in ("REVOKED", "APPROVED"))
    approved_n = by_status.get("APPROVED", 0)
    revoked_n = by_status.get("REVOKED", 0)
    crit, high = by_sev.get("critical", 0), by_sev.get("high", 0)

    # --- KPI cards ---
    def kpi(label, value, color="#0f172a"):
        return (f"<div class='kpi'><div class='kpi-v' style='color:{color}'>{value}</div>"
                f"<div class='kpi-l'>{label}</div></div>")
    kpis = (
        kpi("Tổng findings", total)
        + kpi("Critical", crit, _SEV_FG["critical"])
        + kpi("High", high, _SEV_FG["high"])
        + kpi("Đang mở", open_n)
        + kpi("Đã thu hồi (FP)", revoked_n, "#dc2626")
        + kpi("Nhóm OWASP", len(by_owasp), _ACCENT)
    )

    # --- severity table ---
    sev_rows = "".join(
        f"<tr><td>{_sev_chip(s)}</td><td class='num'>{by_sev.get(s,0)}</td>"
        f"<td class='num muted'>{_pct(by_sev.get(s,0), total)}</td></tr>"
        for s in _SEV_ORDER if by_sev.get(s, 0)
    )

    # --- category / tool / owasp / cwe ---
    cat_rows = "".join(
        f"<tr><td><b>{_e(c)}</b></td><td class='num'>{by_cat.get(c,0)}</td>"
        f"<td class='muted'>{ {'SAST':'Quét mã nguồn tĩnh','SCA':'Quét thư viện/dependency','DAST':'Quét runtime (ZAP)'}.get(c,'') }</td></tr>"
        for c in ("SAST", "SCA", "DAST") if by_cat.get(c, 0)
    )
    tool_max = max(by_tool.values()) if by_tool else 1
    tool_bars = _hbar_rows(by_tool.most_common(), tool_max)
    owasp_rows = "".join(
        f"<tr><td>{_e(cat)}</td><td class='num'>{n}</td></tr>"
        for cat, n in sorted(by_owasp.items())
    ) or "<tr><td class='muted' colspan='2'>Không có finding nào ánh xạ được OWASP.</td></tr>"
    cwe_rows = "".join(
        f"<tr><td class='mono'>{_e(cid)}</td><td>{_e(cname or '')}</td><td class='num'>{n}</td></tr>"
        for (cid, cname), n in by_cwe.most_common(10)
    ) or "<tr><td class='muted' colspan='3'>—</td></tr>"

    # --- executive summary prose ---
    top_owasp = ", ".join(c.split(" - ")[-1] for c, _ in by_owasp.most_common(3)) or "không xác định"
    posture = ("nghiêm trọng" if crit else ("cần chú ý" if high else "tương đối ổn định"))
    summary = (
        f"Phạm vi báo cáo: <b>{_e(project_name)}</b>"
        + (f", lọc severity = <b>{_e(severity)}</b>" if severity else "")
        + f". Tổng cộng <b>{total}</b> lỗ hổng được ghi nhận, trong đó "
        f"<b style='color:{_SEV_FG['critical']}'>{crit} critical</b> và "
        f"<b style='color:{_SEV_FG['high']}'>{high} high</b>. "
        f"<b>{open_n}</b> đang mở chờ xử lý, <b>{approved_n}</b> đã được duyệt bypass, "
        f"<b>{revoked_n}</b> đã đánh dấu false-positive. "
        f"Nhóm rủi ro OWASP phổ biến nhất: {_e(top_owasp)}. "
        f"Tổng quan tư thế bảo mật: <b>{posture}</b>."
    )

    # --- detailed cards (critical/high/medium) + full table (all) ---
    findings_sorted = sorted(
        findings,
        key=lambda f: (_SEV_ORDER.index(_sev(f)) if _sev(f) in _SEV_ORDER else 99, -(f.cvss_score or 0)),
    )
    detail_html = ""
    detail_count = 0
    for s in _SEV_ORDER:
        if s not in _DETAIL_SEVERITIES:
            continue
        group = [f for f in findings_sorted if _sev(f) == s and f.status != "REVOKED"]
        if not group:
            continue
        detail_count += len(group)
        detail_html += (f"<h3 class='grp'>{_sev_chip(s)} {len(group)} finding "
                        f"mức {s.upper()}</h3>")
        detail_html += "".join(_finding_card(f) for f in group)
    if not detail_html:
        detail_html = "<p class='muted'>Không có finding critical/high/medium đang mở.</p>"

    # full compact table (mọi finding)
    table_rows = ""
    for f in findings_sorted:
        loc = _e((f.file_path or "").split("/")[-1]) + (f":{f.line_number}" if f.line_number else "")
        table_rows += (
            f"<tr><td class='num muted'>{_e(f.id)}</td>"
            f"<td>{_sev_chip(_sev(f))}</td>"
            f"<td><span class='tool'>{_e(f.tool)}</span></td>"
            f"<td class='mono ell' title='{_e(f.rule_id)}'>{_e(f.rule_id)}</td>"
            f"<td class='mono ell' title='{_e(f.file_path)}'>{loc}</td>"
            f"<td class='mono'>{_e(f.cwe_id or '')}</td>"
            f"<td>{_status_chip(f.status)}</td></tr>"
        )

    # revoked appendix
    revoked = [f for f in findings_sorted if f.status == "REVOKED"]
    revoked_html = ""
    if revoked:
        rrows = "".join(
            f"<tr><td class='num muted'>{_e(f.id)}</td><td class='mono ell'>{_e(f.rule_id)}</td>"
            f"<td>{_e(f.revoked_by or '')}</td><td>{_e(f.revoke_justification or '')}</td></tr>"
            for f in revoked
        )
        revoked_html = f"""<h2>Phụ lục — Findings đã thu hồi (false-positive)</h2>
        <div class='card'><table><thead><tr><th>#</th><th>Rule</th><th>Bởi</th><th>Lý do</th></tr></thead>
        <tbody>{rrows}</tbody></table></div>"""

    detail_note = (f"<p class='muted'>Hiển thị chi tiết {detail_count} finding mức "
                   f"critical/high đang mở (ưu tiên xử lý). Toàn bộ {total} finding liệt kê ở bảng bên dưới.</p>")

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shiftwall — Báo cáo bảo mật — {_e(project_name)}</title>
<style>
  :root {{ --acc:{_ACCENT}; --fg:#0f172a; --fg2:#334155; --muted:#64748b; --line:#e5e7eb; --card:#fafafa; }}
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:var(--fg);
        background:#fff;margin:0;line-height:1.6;font-size:14px}}
  .page{{max-width:980px;margin:0 auto;padding:40px 44px 80px}}
  .mono{{font-family:'SF Mono',ui-monospace,Consolas,monospace;font-size:.9em}}
  .muted{{color:var(--muted)}}
  .num{{text-align:right;font-variant-numeric:tabular-nums}}
  .ell{{max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}

  header.cover{{display:flex;align-items:center;gap:16px;border-bottom:3px solid var(--acc);padding-bottom:20px;margin-bottom:8px}}
  .logo{{width:46px;height:46px;border-radius:11px;background:var(--acc);display:flex;align-items:center;justify-content:center;flex:0 0 auto}}
  header.cover h1{{font-size:25px;margin:0;letter-spacing:-.02em}}
  header.cover .sub{{color:var(--muted);font-size:13px;margin-top:2px}}
  .badge{{margin-left:auto;text-align:right}}
  .badge .big{{font-size:30px;font-weight:800;color:var(--acc);line-height:1}}
  .badge .lbl{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}

  h2{{font-size:16px;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line);
      text-transform:uppercase;letter-spacing:.04em;color:var(--fg2)}}
  h3.grp{{font-size:14px;margin:22px 0 10px;display:flex;align-items:center;gap:8px}}

  .summary{{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--acc);
            border-radius:8px;padding:14px 18px;font-size:14px}}
  .kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:14px 0}}
  .kpi{{border:1px solid var(--line);border-radius:10px;padding:12px;text-align:center;background:#fff}}
  .kpi-v{{font-size:24px;font-weight:800;line-height:1}}
  .kpi-l{{font-size:10.5px;color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.03em}}

  .bar{{display:flex;height:14px;border-radius:7px;overflow:hidden;background:#f1f5f9;margin:6px 0 14px}}
  .bar span{{display:block;height:100%}} .bar.empty{{background:#f1f5f9}}

  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  .card{{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:#fff;overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;font-size:12.5px}}
  th{{text-align:left;padding:7px 9px;color:var(--muted);border-bottom:2px solid var(--line);
      font-size:10.5px;text-transform:uppercase;letter-spacing:.04em}}
  td{{padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}}

  .chip{{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 8px;border-radius:20px;
         border:1px solid;letter-spacing:.02em}}
  .tool{{font-family:'SF Mono',Consolas,monospace;font-size:11px;background:#f1f5f9;border:1px solid var(--line);
         border-radius:5px;padding:1px 6px;color:var(--fg2)}}

  .hbar{{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:12px}}
  .hbar .hl{{flex:0 0 150px;font-family:'SF Mono',Consolas,monospace;font-size:11px}}
  .hbar .ht{{flex:1;height:9px;background:#f1f5f9;border-radius:5px;overflow:hidden}}
  .hbar .hf{{height:100%;background:var(--acc);border-radius:5px}}
  .hbar .hv{{flex:0 0 36px;text-align:right;font-variant-numeric:tabular-nums}}

  .fcard{{border:1px solid var(--line);border-left:3px solid #ccc;border-radius:8px;padding:12px 15px;margin:9px 0;background:#fff}}
  .fc-head{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
  .fc-rule{{font-size:12px;color:var(--fg2)}}
  .fc-id{{margin-left:auto;color:var(--muted);font-size:11px;font-family:'SF Mono',Consolas,monospace}}
  .fc-msg{{margin:8px 0;font-size:13.5px}}
  .fc-meta{{display:grid;grid-template-columns:1fr 1fr;gap:3px 18px;font-size:12px;margin-top:6px}}
  .fc-meta .m{{display:flex;gap:8px}} .fc-meta .mk{{flex:0 0 64px;color:var(--muted);font-size:11px}}
  .fc-meta .mv{{flex:1;min-width:0;word-break:break-word}}
  .triage{{margin-top:9px;font-size:12px;padding:7px 11px;border-radius:6px;background:#f8fafc;border:1px solid var(--line)}}
  .triage.ok{{background:#f0fdf4;border-color:#bbf7d0}} .triage.no{{background:#fef2f2;border-color:#fecaca}}
  .sol{{margin-top:7px;font-size:12px;padding:7px 11px;border-radius:6px;background:#eff6ff;border:1px solid #bfdbfe}}
  .ai{{margin-top:9px;font-size:12.5px;padding:9px 12px;border-radius:6px;background:#fbf7f4;border:1px solid #f3e2d8}}
  .ai-h{{font-weight:700;color:var(--acc);margin-bottom:4px}}
  .ai pre{{background:#0f172a;color:#e2e8f0;padding:9px;border-radius:6px;font-size:11px;overflow-x:auto;white-space:pre-wrap}}
  details summary{{cursor:pointer;color:var(--acc);font-size:12px;margin-top:5px}}

  footer{{margin-top:46px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);
          font-size:11.5px;display:flex;justify-content:space-between}}

  @media print {{
    .page{{max-width:none;padding:0}}
    .fcard,.kpi,.card{{break-inside:avoid}}
    h2,h3{{break-after:avoid}}
    a{{color:inherit;text-decoration:none}}
  }}
</style>
</head>
<body>
<div class="page">

  <header class="cover">
    <div class="logo">
      <svg width="26" height="26" viewBox="0 0 64 64" fill="none" stroke="#fff" stroke-width="4"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M24 16 H18 V48 H24"/><path d="M40 16 H46 V48 H40"/>
        <path d="M39 32 H27"/><path d="M31 27 L26 32 L31 37"/>
      </svg>
    </div>
    <div>
      <h1>Báo cáo bảo mật</h1>
      <div class="sub">Shiftwall · Secure CI/CD &nbsp;—&nbsp; {_e(project_name)} &nbsp;·&nbsp; {now}</div>
    </div>
    <div class="badge"><div class="big">{total}</div><div class="lbl">findings</div></div>
  </header>

  <h2>Tóm tắt điều hành</h2>
  <div class="summary">{summary}</div>

  <div class="kpis">{kpis}</div>

  <h2>Phân bố mức độ</h2>
  {_bar(by_sev, total)}
  <div class="grid2">
    <div class="card"><table>
      <thead><tr><th>Mức độ</th><th class='num'>Số lượng</th><th class='num'>Tỷ lệ</th></tr></thead>
      <tbody>{sev_rows or "<tr><td class='muted' colspan='3'>—</td></tr>"}</tbody>
    </table></div>
    <div class="card"><table>
      <thead><tr><th>Loại quét</th><th class='num'>Số lượng</th><th>Mô tả</th></tr></thead>
      <tbody>{cat_rows or "<tr><td class='muted' colspan='3'>—</td></tr>"}</tbody>
    </table></div>
  </div>

  <h2>Theo công cụ</h2>
  <div class="card">{tool_bars or "<span class='muted'>—</span>"}</div>

  <h2>Ánh xạ OWASP Top 10 (2021) &amp; CWE phổ biến</h2>
  <div class="grid2">
    <div class="card"><table>
      <thead><tr><th>Nhóm OWASP</th><th class='num'>Số lượng</th></tr></thead>
      <tbody>{owasp_rows}</tbody>
    </table></div>
    <div class="card"><table>
      <thead><tr><th>CWE</th><th>Tên</th><th class='num'>Số lượng</th></tr></thead>
      <tbody>{cwe_rows}</tbody>
    </table></div>
  </div>

  <h2>Chi tiết findings ưu tiên</h2>
  {detail_note}
  {detail_html}

  <h2>Toàn bộ findings ({total})</h2>
  <div class="card"><table>
    <thead><tr><th>#</th><th>Mức</th><th>Tool</th><th>Rule</th><th>File</th><th>CWE</th><th>Trạng thái</th></tr></thead>
    <tbody>{table_rows or "<tr><td class='muted' colspan='7'>Không có finding.</td></tr>"}</tbody>
  </table></div>

  {revoked_html}

  <h2>Phương pháp</h2>
  <div class="card muted" style="font-size:12.5px;line-height:1.7">
    Báo cáo tổng hợp từ pipeline DevSecOps shift-left: <b>SAST</b> (Semgrep, CodeQL, Bandit, SpotBugs…),
    <b>SCA</b> (Trivy, OWASP Dependency-Check) và <b>DAST</b> (OWASP ZAP). Severity phân giải theo
    security-severity (CVSS), <code>defaultConfiguration.level</code> và chuẩn SARIF; ánh xạ CWE → OWASP Top 10 2021.
    Finding đánh dấu <i>thu hồi</i> là false-positive đã được kỹ sư bảo mật xác nhận và sẽ không chặn CI ở các lần quét sau.
  </div>

  <footer>
    <span>🛡 Shiftwall — Secure CI/CD · {_e(project_name)}</span>
    <span>Tạo lúc {now}</span>
  </footer>
</div>
</body>
</html>"""
