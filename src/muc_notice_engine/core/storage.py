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
    external_id  TEXT NOT NULL DEFAULT '',
    summary      TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    pushed       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_notices_source    ON notices(source_key);
CREATE INDEX IF NOT EXISTS idx_notices_published ON notices(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_notices_category  ON notices(category);

CREATE TABLE IF NOT EXISTS assets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_id         TEXT NOT NULL,
    kind              TEXT NOT NULL,
    filename          TEXT NOT NULL,
    local_path        TEXT NOT NULL,
    size              INTEGER NOT NULL DEFAULT 0,
    sha1              TEXT NOT NULL DEFAULT '',
    first_download_at TEXT NOT NULL,
    last_access_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_notice ON assets(notice_id);
CREATE INDEX IF NOT EXISTS idx_assets_access ON assets(last_access_at);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_COLUMNS = (
    "id, title, link, source, source_key, category, date, pub_date, "
    "published_at, external_id, summary, content"
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
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                        n.external_id,
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
            escaped = _escape_like(q)
            pattern = f"%{escaped}%"
            clauses.append(
                "(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' "
                "OR content LIKE ? ESCAPE '\\')"
            )
            params.extend([pattern, pattern, pattern])

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

    # ---------------- 落盘文件表 ----------------

    async def add_assets(self, notice_id: str, records: list[dict]) -> None:
        if not records:
            return
        await asyncio.to_thread(self._add_assets, notice_id, records)

    def _add_assets(self, notice_id: str, records: list[dict]) -> None:
        now = datetime.now(CHINA_TZ).isoformat()
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT INTO assets (notice_id, kind, filename, local_path, size, sha1, "
                "first_download_at, last_access_at) VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        notice_id,
                        r.get("kind", ""),
                        r.get("filename", ""),
                        r.get("local_path", ""),
                        int(r.get("size", 0)),
                        r.get("sha1", ""),
                        now,
                        now,
                    )
                    for r in records
                ],
            )

    async def clear_assets(self, notice_id: str) -> None:
        await asyncio.to_thread(self._clear_assets, notice_id)

    def _clear_assets(self, notice_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM assets WHERE notice_id = ?", (notice_id,))

    async def replace_assets(self, notice_id: str, records: list[dict]) -> None:
        """原子替换一条通知的落盘文件记录（先删后插）。"""
        await asyncio.to_thread(self._replace_assets, notice_id, records)

    def _replace_assets(self, notice_id: str, records: list[dict]) -> None:
        now = datetime.now(CHINA_TZ).isoformat()
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM assets WHERE notice_id = ?", (notice_id,))
            self._conn.executemany(
                "INSERT INTO assets (notice_id, kind, filename, local_path, size, sha1, "
                "first_download_at, last_access_at) VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        notice_id,
                        r.get("kind", ""),
                        r.get("filename", ""),
                        r.get("local_path", ""),
                        int(r.get("size", 0)),
                        r.get("sha1", ""),
                        now,
                        now,
                    )
                    for r in records
                ],
            )

    async def get_assets(self, notice_id: str) -> list[dict]:
        return await asyncio.to_thread(self._get_assets, notice_id)

    def _get_assets(self, notice_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM assets WHERE notice_id = ? ORDER BY id", (notice_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    async def touch_assets(self, notice_id: str) -> None:
        await asyncio.to_thread(self._touch_assets, notice_id)

    def _touch_assets(self, notice_id: str) -> None:
        now = datetime.now(CHINA_TZ).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE assets SET last_access_at = ? WHERE notice_id = ?",
                (now, notice_id),
            )

    async def total_asset_size(self) -> int:
        return await asyncio.to_thread(
            lambda: self._conn.execute(
                "SELECT COALESCE(SUM(size), 0) FROM assets"
            ).fetchone()[0]
        )

    async def list_assets_oldest(self, limit: int = 500) -> list[dict]:
        return await asyncio.to_thread(self._list_assets_oldest, limit)

    def _list_assets_oldest(self, limit: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM assets ORDER BY last_access_at ASC, id ASC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    async def delete_asset(self, asset_id: int) -> None:
        await asyncio.to_thread(self._delete_asset, asset_id)

    def _delete_asset(self, asset_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))

    async def fill_content_preview(self, notice_id: str, content: str) -> None:
        """仅在 content 为空时写入预览文本（不覆盖列表接口已有内容）。"""
        text = (content or "").strip()[:2000]
        if not text:
            return
        await asyncio.to_thread(self._fill_content_preview, notice_id, text)

    def _fill_content_preview(self, notice_id: str, text: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE notices SET content = ? WHERE id = ? AND content = ''",
                (text, notice_id),
            )

    # ---------------- 键值状态（回填标记等）----------------

    async def get_meta(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get_meta, key)

    def _get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    async def set_meta(self, key: str, value: str) -> None:
        await asyncio.to_thread(self._set_meta, key, value)

    def _set_meta(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
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


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符，配合 ESCAPE '\\' 使用。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
        external_id=row["external_id"],
        summary=row["summary"],
        content=row["content"],
    )
