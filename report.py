"""HTML 报告生成器
风格: 极简数据看板，对标 Vercel / Linear / Plausible
支持: EN / 中文双语切换（纯前端 data-i18n 属性驱动）
"""
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict
from collections import defaultdict


# 内联 SVG favicon —— 雷达扫描图标，亮色背景 + 品牌色光束
# 用 base64 编码后塞进 <link rel="icon">，避免外链 404
_FAVICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#F0F6FC"/>
      <stop offset="100%" stop-color="#D6E4F5"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="12" fill="url(#bg)"/>
  <circle cx="32" cy="32" r="22" fill="none" stroke="#3F7FC4" stroke-width="2.5" opacity="0.35"/>
  <circle cx="32" cy="32" r="15" fill="none" stroke="#3F7FC4" stroke-width="2.5" opacity="0.55"/>
  <circle cx="32" cy="32" r="8" fill="none" stroke="#3F7FC4" stroke-width="2.5" opacity="0.75"/>
  <line x1="32" y1="32" x2="50" y2="18" stroke="#3F7FC4" stroke-width="3" stroke-linecap="round"/>
  <circle cx="50" cy="18" r="3" fill="#3F7FC4"/>
  <circle cx="32" cy="32" r="2.5" fill="#3F7FC4"/>
</svg>'''
_FAVICON_B64 = base64.b64encode(_FAVICON_SVG.encode("utf-8")).decode("ascii")


SOURCE_LABELS = {
    "hackernews": "Hacker News",
    "github": "GitHub",
    "github_code": "GitHub Code",
    "reddit": "Reddit",
    "google_news": "Google News",
    "twitter": "X / Twitter",
}

SOURCE_COLORS = {
    "hackernews": "#FF6600",
    "github": "#8B5CF6",
    "github_code": "#10B981",
    "reddit": "#FF4500",
    "google_news": "#4285F4",
    "twitter": "#1DA1F2",
}


def _relative_time(dt_str, lang="en"):
    try:
        if isinstance(dt_str, str):
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        else:
            dt = dt_str
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = now - dt
        secs = diff.total_seconds()
        if secs < 3600:
            return f"{int(secs/60)}m ago" if lang == "en" else f"{int(secs/60)} 分钟前"
        if secs < 86400:
            return f"{int(secs/3600)}h ago" if lang == "en" else f"{int(secs/3600)} 小时前"
        return f"{int(secs/86400)}d ago" if lang == "en" else f"{int(secs/86400)} 天前"
    except Exception:
        return ""


def _build_daily_series(by_day, since, until):
    by_day_map = defaultdict(lambda: defaultdict(int))
    for row in by_day:
        by_day_map[row["day"]][row["source"]] = row["cnt"]
    days = []
    cur = since.date()
    end = until.date()
    while cur <= end:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    sources = sorted({r["source"] for r in by_day})
    datasets = []
    for s in sources:
        datasets.append({
            "label": SOURCE_LABELS.get(s, s),
            "data": [by_day_map[d].get(s, 0) for d in days],
            "borderColor": SOURCE_COLORS.get(s, "#888"),
            "backgroundColor": SOURCE_COLORS.get(s, "#888") + "33",
            "tension": 0.35,
            "fill": True,
            "borderWidth": 2,
            "pointRadius": 3,
            "pointHoverRadius": 6,
        })
    return days, datasets


def generate_html_report(
    out_path: Path,
    project_name: str,
    window: str,
    since: datetime,
    until: datetime,
    mentions: List[Dict],
    by_day: List[Dict],
    by_source: List[Dict],
    top: List[Dict],
    code_integrations: List[Dict] = None,
    pr_issue_mentions: List[Dict] = None,
):
    days, datasets = _build_daily_series(by_day, since, until)

    total_mentions = len(mentions)
    unique_authors = len({m.get("author") for m in mentions if m.get("author")})
    total_engagement = sum(
        (m.get("points") or 0) + (m.get("comments") or 0) for m in mentions
    )
    peak = max(
        ((d, sum(ds["data"][i] for ds in datasets)) for i, d in enumerate(days)),
        key=lambda x: x[1],
        default=("-", 0),
    )
    by_source_total = sum(s["cnt"] for s in by_source) or 1

    html = TEMPLATE.format(
        project_name=project_name,
        window=window,
        since_str=since.strftime("%Y-%m-%d %H:%M UTC"),
        until_str=until.strftime("%Y-%m-%d %H:%M UTC"),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_mentions=total_mentions,
        unique_authors=unique_authors,
        total_engagement=total_engagement,
        peak_day=peak[0] if peak[1] else "-",
        peak_count=peak[1],
        days_json=json.dumps(days),
        datasets_json=json.dumps(datasets),
        source_labels_json=json.dumps([SOURCE_LABELS.get(s["source"], s["source"]) for s in by_source]),
        source_data_json=json.dumps([s["cnt"] for s in by_source]),
        source_colors_json=json.dumps([SOURCE_COLORS.get(s["source"], "#888") for s in by_source]),
        source_rows=_render_source_rows(by_source, by_source_total),
        top_rows=_render_top_rows(top),
        all_rows=_render_all_rows(mentions[:50]),
        code_integration_rows=_render_code_integration_rows(code_integrations or []),
        code_integration_count=len(code_integrations) if code_integrations else 0,
        pr_issue_rows=_render_pr_issue_rows(pr_issue_mentions or []),
        pr_issue_count=len(pr_issue_mentions) if pr_issue_mentions else 0,
        _favicon_b64=_FAVICON_B64,
    )
    out_path.write_text(html, encoding="utf-8")


def _render_source_rows(by_source, total):
    rows = []
    for s in by_source:
        label = SOURCE_LABELS.get(s["source"], s["source"])
        color = SOURCE_COLORS.get(s["source"], "#888")
        pct = (s["cnt"] / total) * 100 if total else 0
        rows.append(f'''
        <tr>
          <td><span class="dot" style="background:{color}"></span>{label}</td>
          <td class="num">{s["cnt"]}</td>
          <td class="num">{s.get("total_points") or 0}</td>
          <td class="num">{s.get("total_comments") or 0}</td>
          <td>
            <div class="bar-wrap">
              <div class="bar" style="width:{pct:.1f}%;background:{color}"></div>
              <span class="bar-pct">{pct:.1f}%</span>
            </div>
          </td>
        </tr>
        ''')
    return "\n".join(rows) or '<tr><td colspan="5" class="empty" data-i18n="empty_none">No data</td></tr>'


def _render_top_rows(top):
    if not top:
        return '<div class="empty" data-i18n="empty_top">No mentions yet in this window.</div>'
    rows = []
    for i, m in enumerate(top, 1):
        label = SOURCE_LABELS.get(m["source"], m["source"])
        color = SOURCE_COLORS.get(m["source"], "#888")
        title = (m.get("title") or "")[:160]
        url = m.get("url") or "#"
        author = m.get("author") or "—"
        points = m.get("points") or 0
        comments = m.get("comments") or 0
        score = m.get("score") or 0
        rel_en = _relative_time(m.get("created_at", ""), "en")
        rel_zh = _relative_time(m.get("created_at", ""), "zh")
        rows.append(f'''
        <a class="top-card" href="{url}" target="_blank" rel="noopener">
          <div class="top-rank">#{i}</div>
          <div class="top-body">
            <div class="top-meta">
              <span class="chip" style="--c:{color}">{label}</span>
              <span class="muted">@{author}</span>
              <span class="muted">· <span data-en="{rel_en}" data-zh="{rel_zh}">{rel_en}</span></span>
            </div>
            <div class="top-title">{title}</div>
            <div class="top-stats">
              <span>↑ {points}</span>
              <span>💬 {comments}</span>
              <span class="score" data-en="score {score}" data-zh="热度 {score}">score {score}</span>
            </div>
          </div>
        </a>
        ''')
    return "\n".join(rows)


def _render_all_rows(mentions):
    if not mentions:
        return '<tr><td colspan="5" class="empty" data-i18n="empty_all">No mentions yet.</td></tr>'
    rows = []
    for m in mentions:
        label = SOURCE_LABELS.get(m["source"], m["source"])
        color = SOURCE_COLORS.get(m["source"], "#888")
        title = (m.get("title") or "")[:120]
        url = m.get("url") or "#"
        author = m.get("author") or "—"
        rel_en = _relative_time(m.get("created_at", ""), "en")
        rel_zh = _relative_time(m.get("created_at", ""), "zh")
        rows.append(f'''
        <tr>
          <td><span class="chip" style="--c:{color}">{label}</span></td>
          <td><a href="{url}" target="_blank" rel="noopener" class="ml">{title}</a></td>
          <td>@{author}</td>
          <td class="num">{m.get("points") or 0}</td>
          <td class="muted"><span data-en="{rel_en}" data-zh="{rel_zh}">{rel_en}</span></td>
        </tr>
        ''')
    return "\n".join(rows)


def _render_code_integration_rows(integrations):
    """渲染"应用集成情况"表格

    integrations 是已经聚合好的 list，每项包含：
      repo, stars, fingerprint_count, file_count, files, repo_url, integration_note, signal_value
    """
    if not integrations:
        return '<tr><td colspan="6" class="empty" data-i18n="empty_code">No code integrations found.</td></tr>'
    rows = []
    for it in integrations:
        repo = it.get("repo", "")
        stars = it.get("stars", 0)
        fp_count = it.get("fingerprint_count", 0)
        file_count = it.get("file_count", 0)
        files = it.get("files", [])
        repo_url = it.get("repo_url", "")
        note = it.get("integration_note", "")
        signal = it.get("signal_value", "")

        # 信号价值用星级表示（1-5）
        signal_stars = "★" * signal + "☆" * (5 - signal) if isinstance(signal, int) else str(signal)

        # 文件列表渲染成可点击链接
        file_links = []
        for f in files[:3]:
            path = f.get("path", "")
            url = f.get("url", "")
            short = path if len(path) <= 50 else "..." + path[-47:]
            file_links.append(f'<a href="{url}" target="_blank" rel="noopener" class="ml file-link">{short}</a>')
        if len(files) > 3:
            file_links.append(f'<span class="muted">+{len(files)-3} more</span>')
        files_html = "<br>".join(file_links) if file_links else "—"

        # 星级格式化
        stars_display = f"{stars:,}" if stars >= 1000 else str(stars)

        rows.append(f'''
        <tr>
          <td><a href="{repo_url}" target="_blank" rel="noopener" class="ml repo-link">{repo}</a></td>
          <td class="num">{stars_display}</td>
          <td class="num">{fp_count}</td>
          <td class="num">{file_count}</td>
          <td class="files-cell">{files_html}</td>
          <td class="signal-cell">{signal_stars}</td>
        </tr>
        ''')
    return "\n".join(rows)


def _render_pr_issue_rows(pr_issues):
    """渲染"PR/Issue 提及"表格"""
    if not pr_issues:
        return '<tr><td colspan="6" class="empty" data-i18n="empty_pr">No PR/Issue mentions found.</td></tr>'
    rows = []
    for m in pr_issues:
        title = (m.get("title") or "")[:100]
        url = m.get("url") or "#"
        author = m.get("author") or "—"
        repo = m.get("repo", "")
        # 从 extra JSON 里取 type（issue 或 pr）
        import json as _json
        try:
            extra = _json.loads(m.get("extra") or "{}")
            item_type = extra.get("type", "issue")
            item_repo = extra.get("repo", repo)
        except Exception:
            item_type = "issue"
            item_repo = repo

        type_label = "PR" if item_type == "pr" else "Issue"
        type_color = "#8B5CF6" if item_type == "pr" else "#3F7FC4"

        points = m.get("points") or 0
        comments = m.get("comments") or 0
        rel_en = _relative_time(m.get("created_at", ""), "en")
        rel_zh = _relative_time(m.get("created_at", ""), "zh")

        rows.append(f'''
        <tr>
          <td><span class="chip" style="--c:{type_color}">{type_label}</span></td>
          <td class="repo-cell"><a href="https://github.com/{item_repo}" target="_blank" rel="noopener" class="ml">{item_repo}</a></td>
          <td><a href="{url}" target="_blank" rel="noopener" class="ml">{title}</a></td>
          <td>@{author}</td>
          <td class="num">{comments}</td>
          <td class="muted"><span data-en="{rel_en}" data-zh="{rel_zh}">{rel_en}</span></td>
        </tr>
        ''')
    return "\n".join(rows)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project_name} · Radar Report</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,{_favicon_b64}">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0A0E14;
    --bg-card: #11161D;
    --bg-card-hover: #161C24;
    --border: #1F2630;
    --text: #E6EDF3;
    --text-muted: #7D8590;
    --text-dim: #4B535D;
    --brand: #3F7FC4;
    --brand-light: #6BA7DC;
    --accent: #27476F;
  }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', 'PingFang SC', system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
    background-image:
      radial-gradient(circle at 20% 0%, rgba(63,127,196,0.08), transparent 50%),
      radial-gradient(circle at 80% 100%, rgba(39,71,111,0.06), transparent 50%);
  }}
  .container {{
    max-width: 1280px;
    margin: 0 auto;
    padding: 48px 32px 80px;
  }}

  /* Language toggle */
  .lang-toggle {{
    position: fixed;
    top: 20px;
    right: 24px;
    z-index: 100;
    display: inline-flex;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 3px;
    backdrop-filter: blur(12px);
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  }}
  .lang-btn {{
    padding: 6px 14px;
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-family: inherit;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.03em;
    cursor: pointer;
    border-radius: 999px;
    transition: all 0.2s;
  }}
  .lang-btn:hover {{ color: var(--text); }}
  .lang-btn.active {{
    background: var(--brand);
    color: #fff;
    box-shadow: 0 2px 8px rgba(63,127,196,0.4);
  }}

  /* Header */
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 40px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--border);
  }}
  .header h1 {{
    font-size: 28px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }}
  .header h1 .brand {{ color: var(--brand-light); }}
  .header .sub {{
    color: var(--text-muted);
    margin-top: 6px;
    font-size: 13px;
  }}
  .window-badge {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    color: var(--brand-light);
  }}
  .window-badge::before {{
    content: "";
    width: 6px; height: 6px;
    background: var(--brand-light);
    border-radius: 50%;
    box-shadow: 0 0 8px var(--brand-light);
    animation: pulse 2s ease-in-out infinite;
  }}
  @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}

  /* KPI cards */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 32px;
  }}
  .kpi-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 22px;
    transition: all 0.2s;
  }}
  .kpi-card:hover {{
    border-color: var(--brand);
    transform: translateY(-2px);
  }}
  .kpi-label {{
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }}
  .kpi-value {{
    font-size: 32px;
    font-weight: 600;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
  }}
  .kpi-hint {{
    color: var(--text-dim);
    font-size: 11px;
    margin-top: 6px;
  }}

  .section {{ margin-bottom: 32px; }}
  .section-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }}
  .section-title {{
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
  }}
  .section-title .num {{
    color: var(--text-muted);
    font-weight: 400;
    margin-left: 6px;
  }}

  .chart-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
  }}
  .chart-wrap {{ position: relative; height: 320px; }}

  .two-col {{
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 20px;
  }}
  @media (max-width: 900px) {{
    .two-col {{ grid-template-columns: 1fr; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{
    text-align: left;
    color: var(--text-muted);
    font-weight: 500;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
  }}
  td {{ padding: 12px; border-bottom: 1px solid var(--border); }}
  tr:last-child td {{ border-bottom: none; }}
  td.num {{ font-variant-numeric: tabular-nums; color: var(--text); }}
  td.muted {{ color: var(--text-dim); font-size: 12px; }}
  td a.ml {{ color: var(--text); text-decoration: none; }}
  td a.ml:hover {{ color: var(--brand-light); }}
  .empty {{ color: var(--text-dim); text-align: center; padding: 28px !important; font-style: italic; }}

  .dot {{
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 8px;
    vertical-align: middle;
  }}

  .bar-wrap {{ display: flex; align-items: center; gap: 8px; }}
  .bar {{ height: 6px; border-radius: 3px; background: var(--brand); min-width: 4px; }}
  .bar-pct {{ color: var(--text-muted); font-size: 11px; font-variant-numeric: tabular-nums; min-width: 36px; }}

  .top-grid {{ display: grid; grid-template-columns: 1fr; gap: 8px; }}
  .top-card {{
    display: flex;
    gap: 16px;
    padding: 16px 20px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    text-decoration: none;
    color: inherit;
    transition: all 0.15s;
  }}
  .top-card:hover {{
    background: var(--bg-card-hover);
    border-color: var(--brand);
    transform: translateX(4px);
  }}
  .top-rank {{
    font-size: 14px;
    font-weight: 600;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
    min-width: 32px;
    padding-top: 2px;
  }}
  .top-body {{ flex: 1; min-width: 0; }}
  .top-meta {{
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 4px;
    font-size: 12px;
  }}
  .top-title {{
    font-size: 14px;
    font-weight: 500;
    line-height: 1.5;
    margin: 4px 0 6px;
  }}
  .top-stats {{
    display: flex;
    gap: 14px;
    font-size: 12px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }}
  .top-stats .score {{
    margin-left: auto;
    color: var(--brand-light);
    font-weight: 500;
  }}

  .chip {{
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    background: color-mix(in srgb, var(--c) 18%, transparent);
    color: var(--c);
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.02em;
  }}
  .muted {{ color: var(--text-muted); }}

  /* Section hint (subtitle on the right) */
  .section-hint {{
    color: var(--text-dim);
    font-size: 12px;
    font-weight: 400;
  }}

  /* Integration table specific styles */
  .integration-table td {{
    vertical-align: top;
  }}
  .integration-table .repo-link {{
    font-weight: 500;
    font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Consolas', monospace;
    font-size: 12px;
  }}
  .integration-table .files-cell {{
    max-width: 320px;
    line-height: 1.8;
  }}
  .integration-table .file-link {{
    font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Consolas', monospace;
    font-size: 11px;
    color: var(--text-muted);
  }}
  .integration-table .file-link:hover {{
    color: var(--brand-light);
  }}
  .integration-table .signal-cell {{
    color: #F5C518;
    letter-spacing: 1px;
    font-size: 12px;
  }}
  .repo-cell a {{
    font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Consolas', monospace;
    font-size: 12px;
  }}

  .footer {{
    margin-top: 60px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    color: var(--text-dim);
    font-size: 12px;
    text-align: center;
  }}
  .footer a {{ color: var(--brand-light); text-decoration: none; }}
</style>
</head>
<body>

<!-- Language Toggle -->
<div class="lang-toggle" role="tablist">
  <button class="lang-btn active" data-lang="en" role="tab">EN</button>
  <button class="lang-btn" data-lang="zh" role="tab">中文</button>
</div>

<div class="container">

  <!-- Header -->
  <div class="header">
    <div>
      <h1>
        <span class="brand">●</span> {project_name}
        <span style="color:var(--text-muted);font-weight:400" data-i18n="header_suffix">· Radar Report</span>
      </h1>
      <div class="sub">
        <span data-i18n="period_label">Period</span>: {since_str} → {until_str} ·
        <span data-i18n="generated_label">Generated</span> {generated_at}
      </div>
    </div>
    <div class="window-badge">
      <span data-i18n="window_label">Window</span>: {window}
    </div>
  </div>

  <!-- KPI -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label" data-i18n="kpi_total">Total Mentions</div>
      <div class="kpi-value">{total_mentions}</div>
      <div class="kpi-hint" data-i18n="kpi_total_hint">Across HN / GitHub / Reddit / Google News</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label" data-i18n="kpi_authors">Unique Authors</div>
      <div class="kpi-value">{unique_authors}</div>
      <div class="kpi-hint" data-i18n="kpi_authors_hint">Distinct accounts mentioning the project</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label" data-i18n="kpi_engagement">Total Engagement</div>
      <div class="kpi-value">{total_engagement}</div>
      <div class="kpi-hint" data-i18n="kpi_engagement_hint">Upvotes + comments combined</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label" data-i18n="kpi_peak">Peak Day</div>
      <div class="kpi-value" style="font-size:20px">{peak_day}</div>
      <div class="kpi-hint">
        {peak_count} <span data-i18n="kpi_peak_hint">mentions on this day</span>
      </div>
    </div>
  </div>

  <!-- Trend chart -->
  <div class="section">
    <div class="section-header">
      <div class="section-title">
        <span data-i18n="sec_trend">Volume Trend</span>
        <span class="num" data-i18n="sec_trend_hint">· daily mentions by source</span>
      </div>
    </div>
    <div class="chart-card">
      <div class="chart-wrap"><canvas id="trendChart"></canvas></div>
    </div>
  </div>

  <div class="two-col">
    <div class="section">
      <div class="section-header">
        <div class="section-title" data-i18n="sec_source">Source Breakdown</div>
      </div>
      <div class="chart-card" style="padding:0">
        <table>
          <thead>
            <tr>
              <th data-i18n="th_source">Source</th>
              <th data-i18n="th_mentions">Mentions</th>
              <th data-i18n="th_points">Points</th>
              <th data-i18n="th_comments">Comments</th>
              <th data-i18n="th_share">Share</th>
            </tr>
          </thead>
          <tbody>
            {source_rows}
          </tbody>
        </table>
      </div>
    </div>

    <div class="section">
      <div class="section-header">
        <div class="section-title" data-i18n="sec_dist">Distribution</div>
      </div>
      <div class="chart-card">
        <div class="chart-wrap" style="height:260px"><canvas id="pieChart"></canvas></div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <div class="section-title">
        <span data-i18n="sec_top">Top Mentions</span>
        <span class="num" data-i18n="sec_top_hint">· ranked by engagement</span>
      </div>
    </div>
    <div class="top-grid">
      {top_rows}
    </div>
  </div>

  <!-- 应用集成情况 -->
  <div class="section">
    <div class="section-header">
      <div class="section-title">
        <span data-i18n="sec_code">App Integrations</span>
        <span class="num">· {code_integration_count} repos</span>
      </div>
      <div class="section-hint" data-i18n="sec_code_hint">Code-level Cube integration detected via API fingerprints</div>
    </div>
    <div class="chart-card" style="padding:0">
      <table class="integration-table">
        <thead>
          <tr>
            <th data-i18n="th_repo">Repo</th>
            <th data-i18n="th_stars">Stars</th>
            <th data-i18n="th_fps">Fingerprints</th>
            <th data-i18n="th_files">Files</th>
            <th data-i18n="th_evidence">Integration Evidence (code paths)</th>
            <th data-i18n="th_signal">Signal</th>
          </tr>
        </thead>
        <tbody>
          {code_integration_rows}
        </tbody>
      </table>
    </div>
  </div>

  <!-- PR/Issue 提及 -->
  <div class="section">
    <div class="section-header">
      <div class="section-title">
        <span data-i18n="sec_pr">PR / Issue Mentions</span>
        <span class="num">· {pr_issue_count} items</span>
      </div>
      <div class="section-hint" data-i18n="sec_pr_hint">Issues & PRs across GitHub mentioning Cube</div>
    </div>
    <div class="chart-card" style="padding:0">
      <table>
        <thead>
          <tr>
            <th data-i18n="th_type">Type</th>
            <th data-i18n="th_repo">Repo</th>
            <th data-i18n="th_title">Title</th>
            <th data-i18n="th_author">Author</th>
            <th data-i18n="th_comments">Comments</th>
            <th data-i18n="th_when">When</th>
          </tr>
        </thead>
        <tbody>
          {pr_issue_rows}
        </tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <div class="section-title">
        <span data-i18n="sec_all">All Mentions</span>
        <span class="num" data-i18n="sec_all_hint">· latest 50</span>
      </div>
    </div>
    <div class="chart-card" style="padding:0">
      <table>
        <thead>
          <tr>
            <th data-i18n="th_source">Source</th>
            <th data-i18n="th_title">Title</th>
            <th data-i18n="th_author">Author</th>
            <th data-i18n="th_points">Points</th>
            <th data-i18n="th_when">When</th>
          </tr>
        </thead>
        <tbody>
          {all_rows}
        </tbody>
      </table>
    </div>
  </div>

  <div class="footer">
    <span data-i18n="footer_powered">Cube Radar · Powered by HN Algolia, GitHub API, Reddit JSON, Google News RSS</span><br>
    <a href="https://github.com/TencentCloud/CubeSandbox">github.com/TencentCloud/CubeSandbox</a>
  </div>
</div>

<script>
  // ============ i18n dictionary ============
  const I18N = {{
    en: {{
      header_suffix: "· Radar Report",
      period_label: "Period",
      generated_label: "Generated",
      window_label: "Window",
      kpi_total: "Total Mentions",
      kpi_total_hint: "Across HN / GitHub / Reddit / Google News",
      kpi_authors: "Unique Authors",
      kpi_authors_hint: "Distinct accounts mentioning the project",
      kpi_engagement: "Total Engagement",
      kpi_engagement_hint: "Upvotes + comments combined",
      kpi_peak: "Peak Day",
      kpi_peak_hint: "mentions on this day",
      sec_trend: "Volume Trend",
      sec_trend_hint: "· daily mentions by source",
      sec_source: "Source Breakdown",
      sec_dist: "Distribution",
      sec_top: "Top Mentions",
      sec_top_hint: "· ranked by engagement",
      sec_code: "App Integrations",
      sec_code_hint: "Code-level Cube integration detected via API fingerprints",
      sec_pr: "PR / Issue Mentions",
      sec_pr_hint: "Issues & PRs across GitHub mentioning Cube",
      sec_all: "All Mentions",
      sec_all_hint: "· latest 50",
      th_source: "Source",
      th_mentions: "Mentions",
      th_points: "Points",
      th_comments: "Comments",
      th_share: "Share",
      th_title: "Title",
      th_author: "Author",
      th_when: "When",
      th_repo: "Repo",
      th_stars: "Stars",
      th_fps: "Fingerprints",
      th_files: "Files",
      th_evidence: "Integration Evidence (code paths)",
      th_signal: "Signal",
      th_type: "Type",
      empty_none: "No data",
      empty_top: "No mentions yet in this window.",
      empty_all: "No mentions yet.",
      empty_code: "No code integrations found.",
      empty_pr: "No PR/Issue mentions found.",
      footer_powered: "Cube Radar · Powered by HN Algolia, GitHub API, Reddit JSON, Google News RSS",
    }},
    zh: {{
      header_suffix: "· 传播监测报告",
      period_label: "监测周期",
      generated_label: "生成时间",
      window_label: "窗口",
      kpi_total: "总提及数",
      kpi_total_hint: "覆盖 HN / GitHub / Reddit / Google News",
      kpi_authors: "独立作者数",
      kpi_authors_hint: "提及项目的不同账号数量",
      kpi_engagement: "总互动量",
      kpi_engagement_hint: "点赞 + 评论合计",
      kpi_peak: "峰值日",
      kpi_peak_hint: "条提及",
      sec_trend: "声量趋势",
      sec_trend_hint: "· 按来源分层的每日提及数",
      sec_source: "来源分布",
      sec_dist: "占比",
      sec_top: "热门提及",
      sec_top_hint: "· 按互动量排序",
      sec_code: "应用集成情况",
      sec_code_hint: "通过 API 指纹检测到的代码级 Cube 集成",
      sec_pr: "PR / Issue 提及",
      sec_pr_hint: "GitHub 上提及 Cube 的 Issue 和 PR",
      sec_all: "全部提及",
      sec_all_hint: "· 最近 50 条",
      th_source: "来源",
      th_mentions: "提及数",
      th_points: "点赞",
      th_comments: "评论",
      th_share: "占比",
      th_title: "标题",
      th_author: "作者",
      th_when: "时间",
      th_repo: "仓库",
      th_stars: "星级",
      th_fps: "指纹数",
      th_files: "文件数",
      th_evidence: "集成情况（代码路径）",
      th_signal: "信号价值",
      th_type: "类型",
      empty_none: "暂无数据",
      empty_top: "该时间窗口内暂无提及",
      empty_all: "暂无提及记录",
      empty_code: "暂未发现代码集成",
      empty_pr: "暂无 PR/Issue 提及",
      footer_powered: "Cube Radar · 数据来源：HN Algolia、GitHub API、Reddit JSON、Google News RSS",
    }}
  }};

  function applyLang(lang) {{
    document.documentElement.setAttribute('lang', lang === 'zh' ? 'zh-CN' : 'en');
    // 常规 i18n 属性
    document.querySelectorAll('[data-i18n]').forEach(el => {{
      const key = el.getAttribute('data-i18n');
      const val = I18N[lang]?.[key];
      if (val !== undefined) el.textContent = val;
    }});
    // 双语数据 (data-en / data-zh) — 用于时间戳、score 等含数字的动态字段
    document.querySelectorAll('[data-en][data-zh]').forEach(el => {{
      el.textContent = el.getAttribute(lang === 'zh' ? 'data-zh' : 'data-en');
    }});
    // 按钮激活态
    document.querySelectorAll('.lang-btn').forEach(b => {{
      b.classList.toggle('active', b.dataset.lang === lang);
    }});
    // 记住偏好
    try {{ localStorage.setItem('cube-radar-lang', lang); }} catch(e) {{}}
  }}

  document.querySelectorAll('.lang-btn').forEach(btn => {{
    btn.addEventListener('click', () => applyLang(btn.dataset.lang));
  }});

  // 页面加载时恢复偏好（默认英文）
  try {{
    const saved = localStorage.getItem('cube-radar-lang');
    if (saved === 'zh') applyLang('zh');
  }} catch(e) {{}}

  // ============ Charts ============
  Chart.defaults.color = '#7D8590';
  Chart.defaults.borderColor = '#1F2630';
  Chart.defaults.font.family = "'Inter', -apple-system, system-ui, 'PingFang SC', sans-serif";

  new Chart(document.getElementById('trendChart'), {{
    type: 'line',
    data: {{
      labels: {days_json},
      datasets: {datasets_json}
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{
          position: 'top', align: 'end',
          labels: {{ boxWidth: 8, boxHeight: 8, usePointStyle: true, pointStyle: 'circle', padding: 16 }}
        }},
        tooltip: {{
          backgroundColor: '#11161D',
          borderColor: '#1F2630', borderWidth: 1,
          padding: 12, cornerRadius: 8, displayColors: true,
          titleColor: '#E6EDF3', bodyColor: '#E6EDF3',
        }}
      }},
      scales: {{
        x: {{ grid: {{ display: false }}, ticks: {{ maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }} }},
        y: {{ grid: {{ color: '#1F2630', drawBorder: false }}, beginAtZero: true, ticks: {{ precision: 0 }} }}
      }}
    }}
  }});

  new Chart(document.getElementById('pieChart'), {{
    type: 'doughnut',
    data: {{
      labels: {source_labels_json},
      datasets: [{{
        data: {source_data_json},
        backgroundColor: {source_colors_json},
        borderColor: '#11161D', borderWidth: 2,
        hoverOffset: 8,
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {{
        legend: {{
          position: 'right',
          labels: {{ boxWidth: 8, boxHeight: 8, usePointStyle: true, pointStyle: 'circle', padding: 12 }}
        }},
        tooltip: {{
          backgroundColor: '#11161D',
          borderColor: '#1F2630', borderWidth: 1,
          padding: 12, cornerRadius: 8
        }}
      }}
    }}
  }});
</script>
</body>
</html>
"""
