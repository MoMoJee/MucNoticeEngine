"""SQLite 存储 + 去重层。

去重规则：以 Notice.id 为主键，`INSERT OR IGNORE` 的 rowcount 判定「是否新条目」。
所有方法都是 async：内部用 `asyncio.to_thread` 包装阻塞的 sqlite3 调用，
调用方（engine / API）无需关心线程问题。
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .fetcher import CHINA_TZ
from .models import Notice

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notices (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    link         TEXT NOT NULL,
    source       TEXT NOT NULL,
    source_key   TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT '',
    date         TEXT NOT NULL DEFAULT '',
    pub_date     TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    pushed       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_notices_source    ON notices(source_key);
CREATE INDEX IF NOT EXISTS idx_notices_published ON notices(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_notices_category  ON notices(category);
"""

_COLUMNS = (
    "id, title, link, source, source_key, category, date, pub_date, "
    "published_at, summary, content"
)


class NoticeStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # ---------------- 写入 / 去重 ----------------

    async def upsert_notices(self, notices: list[Notice]) -> list[Notice]:
        """写入通知，返回其中此前未出现过（即新）的那些。"""
        return await asyncio.to_thread(self._upsert, notices)

    def _upsert(self, notices: list[Notice]) -> list[Notice]:
        now = datetime.now(CHINA_TZ).isoformat()
        new_items: list[Notice] = []
        with self._lock, self._conn:
            for n in notices:
                cur = self._conn.execute(
                    f"INSERT OR IGNORE INTO notices ({_COLUMNS}, first_seen_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        n.id,
                        n.title,
                        n.link,
                        n.source,
                        n.source_key,
                        n.category,
                        n.date,
                        n.pub_date,
                        n.published_at.isoformat(),
                        n.summary,
                        n.content,
                        now,
                    ),
                )
                if cur.rowcount == 1:
                    new_items.append(n)
        return new_items

    async def mark_pushed(self, notice_ids: list[str]) -> None:
        if not notice_ids:
            return
        await asyncio.to_thread(self._mark_pushed, notice_ids)

    def _mark_pushed(self, notice_ids: list[str]) -> None:
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE notices SET pushed = 1 WHERE id = ?",
                [(nid,) for nid in notice_ids],
            )

    # ---------------- 查询 ----------------

    async def get(self, notice_id: str) -> Notice | None:
        return await asyncio.to_thread(self._get, notice_id)

    def _get(self, notice_id: str) -> Notice | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM notices WHERE id = ?", (notice_id,)
        ).fetchone()
        return _row_to_notice(row) if row else None

    async def query(
        self,
        source_keys: list[str] | None = None,
        category: str | None = None,
        since: datetime | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notice]:
        return await asyncio.to_thread(
            self._query, source_keys, category, since, q, limit, offset
        )

    def _query(self, source_keys, category, since, q, limit, offset) -> list[Notice]:
        clauses: list[str] = []
        params: list[object] = []
        if source_keys:
            placeholders = ",".join("?" for _ in source_keys)
            clauses.append(f"source_key IN ({placeholders})")
            params.extend(source_keys)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if since is not None:
            clauses.append("published_at >= ?")
            params.append(since.isoformat())
        if q:
            clauses.append("title LIKE ?")
            params.append(f"%{q}%")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([max(1, min(limit, 500)), max(0, offset)])
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM notices {where} "
            "ORDER BY published_at DESC, source ASC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [_row_to_notice(r) for r in rows]

    async def stats(self) -> list[dict]:
        return await asyncio.to_thread(self._stats)

    def _stats(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT source_key, source, COUNT(*) AS total, "
            "SUM(pushed) AS pushed, MAX(published_at) AS latest "
            "FROM notices GROUP BY source_key, source ORDER BY source_key"
        ).fetchall()
        return [dict(r) for r in rows]

    async def count(self) -> int:
        return await asyncio.to_thread(
            lambda: self._conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
        )

    # ---------------- 维护 ----------------

    async def purge_older_than_days(self, days: int) -> int:
        """删除 published_at 早于 N 天的记录，返回删除条数。days<=0 时不清理。"""
        if days <= 0:
            return 0
        return await asyncio.to_thread(self._purge, days)

    def _purge(self, days: int) -> int:
        cutoff = datetime.now(CHINA_TZ).timestamp() - days * 86400
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=CHINA_TZ).isoformat()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM notices WHERE published_at < ?", (cutoff_iso,)
            )
            return cur.rowcount

    def close(self) -> None:
        self._conn.close()


def _row_to_notice(row: sqlite3.Row) -> Notice:
    return Notice(
        id=row["id"],
        title=row["title"],
        link=row["link"],
        source=row["source"],
        source_key=row["source_key"],
        category=row["category"],
        date=row["date"],
        pub_date=row["pub_date"],
        published_at=datetime.fromisoformat(row["published_at"]),
        summary=row["summary"],
        content=row["content"],
    )
