"""SQLite 存储层"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,           -- hn / github / reddit / google_news
    source_id TEXT NOT NULL,        -- 平台内唯一 ID（防重复）
    title TEXT,
    url TEXT,
    author TEXT,
    content TEXT,
    created_at TIMESTAMP NOT NULL,  -- 内容发布时间
    fetched_at TIMESTAMP NOT NULL,  -- 抓取时间
    points INTEGER DEFAULT 0,       -- 点赞/upvotes/stars
    comments INTEGER DEFAULT 0,     -- 评论数
    extra TEXT,                     -- JSON 字段，存平台特有字段
    UNIQUE(source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_mentions_created ON mentions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mentions_source  ON mentions(source);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    window TEXT,
    new_mentions INTEGER DEFAULT 0,
    notes TEXT
);
"""


class Store:
    def __init__(self, db_path: str = "data/radar.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_mention(
        self,
        source: str,
        source_id: str,
        title: str,
        url: str,
        author: Optional[str],
        content: Optional[str],
        created_at: datetime,
        points: int = 0,
        comments: int = 0,
        extra: Optional[str] = None,
    ) -> bool:
        """插入或更新一条 mention，返回 True 如果是新增"""
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO mentions
                  (source, source_id, title, url, author, content,
                   created_at, fetched_at, points, comments, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source, source_id, title, url, author, content,
                 created_at.isoformat(), datetime.utcnow().isoformat(),
                 points, comments, extra),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # 已存在，更新 points/comments（这些指标可能涨）
            cur.execute(
                """
                UPDATE mentions SET points = ?, comments = ?, fetched_at = ?
                WHERE source = ? AND source_id = ?
                """,
                (points, comments, datetime.utcnow().isoformat(),
                 source, source_id),
            )
            self.conn.commit()
            return False

    def start_scan(self, window: str) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO scans (started_at, window) VALUES (?, ?)",
            (datetime.utcnow().isoformat(), window),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_scan(self, scan_id: int, new_mentions: int, notes: str = ""):
        self.conn.execute(
            "UPDATE scans SET finished_at = ?, new_mentions = ?, notes = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), new_mentions, notes, scan_id),
        )
        self.conn.commit()

    def query_mentions(self, since: datetime, source: Optional[str] = None):
        sql = "SELECT * FROM mentions WHERE created_at >= ?"
        params = [since.isoformat()]
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def stats_by_day(self, since: datetime):
        rows = self.conn.execute(
            """
            SELECT DATE(created_at) AS day, source, COUNT(*) AS cnt
            FROM mentions
            WHERE created_at >= ?
            GROUP BY day, source
            ORDER BY day
            """,
            (since.isoformat(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats_by_source(self, since: datetime):
        rows = self.conn.execute(
            """
            SELECT source, COUNT(*) AS cnt,
                   SUM(points) AS total_points,
                   SUM(comments) AS total_comments
            FROM mentions
            WHERE created_at >= ?
            GROUP BY source
            ORDER BY cnt DESC
            """,
            (since.isoformat(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def top_mentions(self, since: datetime, limit: int = 10):
        """按互动量（points + comments）排序的热门提及"""
        rows = self.conn.execute(
            """
            SELECT *, (COALESCE(points,0) + COALESCE(comments,0)*2) AS score
            FROM mentions
            WHERE created_at >= ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (since.isoformat(), limit),
        ).fetchall()
        return [dict(r) for r in rows]
