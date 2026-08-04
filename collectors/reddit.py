"""Reddit 采集器
使用 reddit.com/search.json 公开端点（无需登录）
"""
import requests
from datetime import datetime, timezone
from typing import List, Dict


# Reddit 对默认 UA 全部 403，必须用真实浏览器 UA
SEARCH_URL = "https://old.reddit.com/search.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def collect(keywords: List[str], since_dt: datetime) -> List[Dict]:
    results = []
    for kw in keywords:
        params = {
            "q": kw,
            "sort": "new",
            "limit": 50,
            "t": "month",  # 最近一个月范围（reddit 时间过滤粒度）
        }
        try:
            r = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  [Reddit] error '{kw}': {e}")
            continue

        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            created = datetime.fromtimestamp(
                d.get("created_utc", 0), tz=timezone.utc
            )
            if created < since_dt:
                continue
            results.append({
                "source": "reddit",
                "source_id": d.get("id"),
                "title": d.get("title", ""),
                "url": "https://reddit.com" + d.get("permalink", ""),
                "author": d.get("author"),
                "content": (d.get("selftext") or "")[:2000],
                "created_at": created,
                "points": d.get("ups", 0),
                "comments": d.get("num_comments", 0),
                "extra": f'{{"subreddit":"{d.get("subreddit","")}","keyword":"{kw}"}}',
            })

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
