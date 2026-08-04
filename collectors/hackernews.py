"""Hacker News 采集器
使用 hn.algolia.com 免费搜索 API
"""
import requests
from datetime import datetime, timezone
from typing import List, Dict


SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"


def collect(keywords: List[str], since_ts: int) -> List[Dict]:
    """采集 HN 上提及关键词的 posts/comments

    since_ts: Unix 时间戳（秒），只采集这之后的
    """
    results = []
    for kw in keywords:
        params = {
            "query": kw,
            "tags": "(story,comment)",
            "numericFilters": f"created_at_i>{since_ts}",
            "hitsPerPage": 100,
        }
        try:
            r = requests.get(SEARCH_URL, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  [HN] error for '{kw}': {e}")
            continue

        for hit in data.get("hits", []):
            obj_id = hit.get("objectID")
            is_story = hit.get("_tags", []) and "story" in hit["_tags"]
            title = hit.get("title") or hit.get("story_title") or "(comment)"
            url = (
                hit.get("url")
                or f"https://news.ycombinator.com/item?id={obj_id}"
            )
            results.append({
                "source": "hackernews",
                "source_id": str(obj_id),
                "title": title,
                "url": url,
                "author": hit.get("author"),
                "content": (hit.get("comment_text") or hit.get("story_text") or "")[:2000],
                "created_at": datetime.fromtimestamp(
                    hit["created_at_i"], tz=timezone.utc
                ),
                "points": hit.get("points") or 0,
                "comments": hit.get("num_comments") or 0,
                "extra": f"{{\"type\":\"{'story' if is_story else 'comment'}\",\"keyword\":\"{kw}\"}}",
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
