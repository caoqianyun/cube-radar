"""Google News RSS 采集器
Google News 提供免费 RSS 订阅，可按关键词搜索
"""
import requests
import xml.etree.ElementTree as ET
import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict
from urllib.parse import quote


def collect(keywords: List[str], since_dt: datetime) -> List[Dict]:
    results = []
    for kw in keywords:
        # Google News RSS 端点
        url = f"https://news.google.com/rss/search?q={quote(kw)}&hl=en-US&gl=US&ceid=US:en"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            print(f"  [GoogleNews] error '{kw}': {e}")
            continue

        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub = item.findtext("pubDate", "")
            source = item.find("source")
            source_name = source.text if source is not None else "unknown"

            try:
                created = parsedate_to_datetime(pub).astimezone(timezone.utc)
            except Exception:
                continue
            if created < since_dt:
                continue

            sid = hashlib.md5(link.encode()).hexdigest()[:16]
            results.append({
                "source": "google_news",
                "source_id": sid,
                "title": title,
                "url": link,
                "author": source_name,
                "content": item.findtext("description", "")[:2000],
                "created_at": created,
                "points": 0,
                "comments": 0,
                "extra": f'{{"news_source":"{source_name}","keyword":"{kw}"}}',
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
