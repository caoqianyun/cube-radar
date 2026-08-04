"""Cube Radar - 全网传播监测工具

使用:
  python -m cube_radar scan --window 7d     # 抓取过去 7 天数据
  python -m cube_radar report --window 7d   # 生成报告
  python -m cube_radar all --window 7d      # 抓取 + 生成报告（一步到位）
"""
import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from store import Store
from collectors import hackernews, github as gh, reddit, google_news, github_code as gh_code
from collectors.relevance import filter_items, is_relevant
from report import generate_html_report


WINDOW_MAP = {
    "24h": timedelta(hours=24),
    "3d":  timedelta(days=3),
    "7d":  timedelta(days=7),
    "30d": timedelta(days=30),
    "60d":  timedelta(days=60),
    "180d": timedelta(days=180),
}


def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_scan(args, cfg):
    """采集数据"""
    delta = WINDOW_MAP[args.window]
    since_dt = datetime.now(timezone.utc) - delta
    since_ts = int(since_dt.timestamp())

    store = Store("data/radar.db")
    scan_id = store.start_scan(args.window)

    keywords = cfg["keywords"]["primary"]
    repo = cfg["project"]["github_repo"]
    sources = cfg["sources"]
    # token 优先级：环境变量 > config.yaml
    token = os.environ.get("GITHUB_TOKEN") or cfg.get("github_token") or None

    all_results = []
    print(f"\n📡 开始扫描 [{args.window}] 窗口 → since {since_dt.isoformat()}\n")

    if sources.get("hackernews"):
        print("  · Hacker News...")
        all_results += hackernews.collect(keywords, since_ts)

    if sources.get("github"):
        print("  · GitHub (issues/PRs)...")
        all_results += gh.collect(keywords, repo, since_dt, token)

    if sources.get("github_code"):
        print("  · GitHub Code Search (集成指纹)...")
        cs_cfg = cfg.get("code_search", {})
        blacklist = cs_cfg.get("repo_blacklist", "TencentCloud/CubeSandbox")
        custom_fps = cs_cfg.get("fingerprints") or None
        code_results = gh_code.collect(
            fingerprints=custom_fps,
            token=token,
            repo_blacklist=blacklist,
        )
        all_results += code_results
        # 聚合统计：按 repo 看深度集成
        by_repo = gh_code.aggregate_by_repo(code_results)
        if by_repo:
            print(f"     → {len(by_repo)} 个 repo 命中 Cube 集成指纹")
            # 按 star 数降序，打印 top 5
            top_repos = sorted(by_repo.values(), key=lambda x: x.get("stars", 0), reverse=True)[:5]
            for r in top_repos:
                fp_cnt = r.get("fingerprint_count", 0)
                file_cnt = r.get("file_count", 0)
                stars = r.get("stars", 0)
                print(f"       · {r['repo']:40s} ⭐{stars:>5}  指纹{fp_cnt}  文件{file_cnt}")

    if sources.get("reddit"):
        print("  · Reddit...")
        all_results += reddit.collect(keywords, since_dt)

    if sources.get("google_news"):
        print("  · Google News...")
        all_results += google_news.collect(keywords, since_dt)

    # 严格过滤：只保留真实提及 Cube Sandbox 的
    print()
    kept, dropped = filter_items(all_results)
    print(f"  🔍 严格过滤: 保留 {len(kept)} 条, 过滤掉 {len(dropped)} 条不相关内容")
    if dropped:
        print(f"     (被过滤示例: {(dropped[0].get('title') or '')[:60]!r} ...)")
    all_results = kept

    # 写入数据库
    new_count = 0
    for item in all_results:
        is_new = store.upsert_mention(**item)
        if is_new:
            new_count += 1

    store.finish_scan(scan_id, new_count, notes=f"kept={len(all_results)}, dropped={len(dropped)}")
    print(f"\n✓ 完成：入库 {len(all_results)} 条（新增 {new_count} 条）\n")


def cmd_clean(args, cfg):
    """清洗数据库：删除历史入库但不再符合过滤规则的脏数据"""
    store = Store("data/radar.db")
    from datetime import timedelta
    all_mentions = store.query_mentions(datetime.now(timezone.utc) - timedelta(days=3650))
    print(f"\n🧹 清洗数据库中的脏数据...")
    print(f"   现有 {len(all_mentions)} 条")

    to_delete = [m for m in all_mentions if not is_relevant(m)]
    print(f"   将删除 {len(to_delete)} 条不相关记录")
    for m in to_delete[:10]:
        print(f"     × [{m['source']}] {(m['title'] or '')[:70]}")
    if len(to_delete) > 10:
        print(f"     ... and {len(to_delete)-10} more")

    if not to_delete:
        print("   数据库已经是干净的\n")
        return

    for m in to_delete:
        store.conn.execute(
            "DELETE FROM mentions WHERE source = ? AND source_id = ?",
            (m["source"], m["source_id"]),
        )
    store.conn.commit()
    print(f"\n✓ 完成: 删除 {len(to_delete)} 条, 剩余 {len(all_mentions) - len(to_delete)} 条\n")


def cmd_report(args, cfg):
    """生成 HTML 报告"""
    delta = WINDOW_MAP[args.window]
    since_dt = datetime.now(timezone.utc) - delta

    store = Store("data/radar.db")

    mentions = store.query_mentions(since_dt)
    by_day = store.stats_by_day(since_dt)
    by_source = store.stats_by_source(since_dt)
    top = store.top_mentions(since_dt, limit=15)

    # 构建应用集成数据（github_code 源聚合成 repo 维度）
    code_integrations = _build_code_integrations(mentions)

    # 构建 PR/Issue 提及数据（github 源里的 issue/PR，排除 star）
    pr_issue_mentions = _build_pr_issue_mentions(mentions)

    out_dir = Path(cfg.get("output_dir", "reports"))
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"report-{args.window}-{timestamp}.html"

    generate_html_report(
        out_path=out_path,
        project_name=cfg["project"]["name"],
        window=args.window,
        since=since_dt,
        until=datetime.now(timezone.utc),
        mentions=mentions,
        by_day=by_day,
        by_source=by_source,
        top=top,
        code_integrations=code_integrations,
        pr_issue_mentions=pr_issue_mentions,
    )

    print(f"\n📄 报告已生成: {out_path.resolve()}\n")


def _build_code_integrations(mentions):
    """把 github_code 源的 mention 聚合成 repo 维度的集成列表

    返回 list，每项包含：
      repo, stars, fingerprint_count, file_count, files, repo_url, signal_value
    """
    import json as _json
    by_repo = {}
    for m in mentions:
        if m.get("source") != "github_code":
            continue
        try:
            extra = _json.loads(m.get("extra") or "{}")
        except Exception:
            continue
        repo = extra.get("repo", "")
        if not repo:
            continue
        if repo not in by_repo:
            by_repo[repo] = {
                "repo": repo,
                "stars": extra.get("repo_stars", 0),
                "repo_url": extra.get("repo_url", f"https://github.com/{repo}"),
                "fingerprints": set(),
                "files": {},
            }
        fp = extra.get("fingerprint", "")
        if fp:
            by_repo[repo]["fingerprints"].add(fp)
        path = extra.get("path", "")
        if path and path not in by_repo[repo]["files"]:
            by_repo[repo]["files"][path] = {
                "path": path,
                "url": m.get("url", ""),
            }
        # 取最大 star 数
        by_repo[repo]["stars"] = max(by_repo[repo]["stars"], extra.get("repo_stars", 0))

    # 转成 list 并计算信号价值
    result = []
    for repo, info in by_repo.items():
        fp_count = len(info["fingerprints"])
        file_count = len(info["files"])
        stars = info["stars"]

        # 信号价值算法（1-5 星）：
        # - 指纹数 >= 4 或 文件数 >= 8：5 星（深度集成）
        # - 指纹数 >= 3 或 文件数 >= 5：4 星（中度集成）
        # - 指纹数 >= 2 或 文件数 >= 3：3 星（明确集成）
        # - star > 500 或 指纹数 >= 2：2 星（有影响力但需确认）
        # - 其他：1 星（浅集成 / 待确认）
        if fp_count >= 4 or file_count >= 8:
            signal = 5
        elif fp_count >= 3 or file_count >= 5:
            signal = 4
        elif fp_count >= 2 or file_count >= 3:
            signal = 3
        elif stars > 500:
            signal = 2
        else:
            signal = 1

        result.append({
            "repo": repo,
            "stars": stars,
            "fingerprint_count": fp_count,
            "file_count": file_count,
            "files": list(info["files"].values()),
            "repo_url": info["repo_url"],
            "signal_value": signal,
        })

    # 排序：先按信号价值降序，再按 star 降序
    result.sort(key=lambda x: (x["signal_value"], x["stars"]), reverse=True)
    return result


def _build_pr_issue_mentions(mentions):
    """从 github 源的 mention 里提取 issue/PR（排除 star 类）

    返回 list，每项包含：title, url, author, comments, created_at, extra(含 type/repo)
    """
    import json as _json
    result = []
    for m in mentions:
        if m.get("source") != "github":
            continue
        try:
            extra = _json.loads(m.get("extra") or "{}")
        except Exception:
            continue
        item_type = extra.get("type", "")
        # 只要 issue 和 pr，排除 star
        if item_type not in ("issue", "pr"):
            continue
        result.append({
            "title": m.get("title", ""),
            "url": m.get("url", ""),
            "author": m.get("author", ""),
            "comments": m.get("comments", 0),
            "points": m.get("points", 0),
            "created_at": m.get("created_at", ""),
            "extra": m.get("extra", "{}"),
        })

    # 按时间降序
    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result


def cmd_all(args, cfg):
    """采集 + 生成报告"""
    cmd_scan(args, cfg)
    cmd_report(args, cfg)


def main():
    parser = argparse.ArgumentParser(
        prog="cube-radar",
        description="Cube Sandbox 全网传播监测",
    )
    sub = parser.add_subparsers(dest="cmd")

    for name, func in [("scan", cmd_scan), ("report", cmd_report), ("all", cmd_all), ("clean", cmd_clean)]:
        p = sub.add_parser(name)
        p.add_argument(
            "--window",
            choices=list(WINDOW_MAP.keys()),
            default="7d",
            help="时间窗口（默认 7d）",
        )
        p.set_defaults(func=func)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    cfg = load_config()
    args.func(args, cfg)


if __name__ == "__main__":
    main()
