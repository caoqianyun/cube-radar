"""GitHub 采集器
- 搜索代码 / issue / 讨论中提及关键词
- 抓取仓库自身的 stargazers / forks / referrer 趋势
"""
import requests
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional


GH_API = "https://api.github.com"


def _headers(token: Optional[str] = None):
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def collect(
    keywords: List[str],
    repo: str,
    since_dt: datetime,
    token: Optional[str] = None,
) -> List[Dict]:
    """采集 GitHub 上的提及

    1) 搜索 issues/PRs 中提及关键词
    2) 抓取本仓库的最新 stargazers（暗示讨论度）
    3) 抓取本仓库的最新 PRs / Issues 时间线
    """
    results = []

    # 1) 搜索 issues 提及（跨全 github）
    for kw in keywords:
        q = f'"{kw}" in:title,body'
        try:
            r = requests.get(
                f"{GH_API}/search/issues",
                params={"q": q, "sort": "created", "order": "desc", "per_page": 30},
                headers=_headers(token),
                timeout=10,
            )
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception as e:
            print(f"  [GH] search error '{kw}': {e}")
            continue

        for item in data.get("items", []):
            created = datetime.fromisoformat(
                item["created_at"].replace("Z", "+00:00")
            )
            if created < since_dt:
                continue
            # 跳过来自本仓库自己的 issue/PR（避免自己讨论自己被计入）
            if repo in item.get("repository_url", ""):
                continue
            results.append({
                "source": "github",
                "source_id": f"issue-{item['id']}",
                "title": item.get("title", ""),
                "url": item["html_url"],
                "author": item.get("user", {}).get("login"),
                "content": (item.get("body") or "")[:2000],
                "created_at": created,
                "points": item.get("reactions", {}).get("total_count", 0),
                "comments": item.get("comments", 0),
                "extra": json.dumps({
                    "type": "issue" if "pull_request" not in item else "pr",
                    "repo": item.get("repository_url", "").split("/repos/")[-1],
                    "keyword": kw,
                }),
            })

    # 2) 抓本仓库新增的 stargazers（最近 N 个）
    try:
        r = requests.get(
            f"{GH_API}/repos/{repo}/stargazers",
            params={"per_page": 100},
            headers={**_headers(token), "Accept": "application/vnd.github.star+json"},
            timeout=10,
        )
        if r.status_code == 200:
            for s in r.json():
                starred_at = datetime.fromisoformat(
                    s["starred_at"].replace("Z", "+00:00")
                )
                if starred_at < since_dt:
                    continue
                user = s.get("user", {})
                results.append({
                    "source": "github",
                    "source_id": f"star-{user.get('id')}-{int(starred_at.timestamp())}",
                    "title": f"⭐ {user.get('login')} starred {repo}",
                    "url": user.get("html_url", ""),
                    "author": user.get("login"),
                    "content": "",
                    "created_at": starred_at,
                    "points": 1,
                    "comments": 0,
                    "extra": json.dumps({"type": "star"}),
                })
    except Exception as e:
        print(f"  [GH] stargazers error: {e}")

    # 3) 本仓库最近的 PRs（开源参与度信号）
    try:
        r = requests.get(
            f"{GH_API}/repos/{repo}/pulls",
            params={"state": "all", "per_page": 30, "sort": "created", "direction": "desc"},
            headers=_headers(token),
            timeout=10,
        )
        if r.status_code == 200:
            for pr in r.json():
                created = datetime.fromisoformat(
                    pr["created_at"].replace("Z", "+00:00")
                )
                if created < since_dt:
                    continue
                results.append({
                    "source": "github",
                    "source_id": f"pr-{pr['id']}",
                    "title": f"PR: {pr['title']}",
                    "url": pr["html_url"],
                    "author": pr.get("user", {}).get("login"),
                    "content": (pr.get("body") or "")[:1000],
                    "created_at": created,
                    "points": 0,
                    "comments": pr.get("comments", 0),
                "extra": json.dumps({
                    "type": "pr",
                    "repo": repo,  # 本仓库的 PR
                    "state": pr.get("state"),
                    "merged": pr.get("merged_at") is not None,
                }),
                })
    except Exception as e:
        print(f"  [GH] PRs error: {e}")

    return _dedupe(results)


def _dedupe(items):
    seen = set()
    out = []
    for x in items:
        key = (x["source"], x["source_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out
