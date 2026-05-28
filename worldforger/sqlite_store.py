"""SQLite-backed storage for frequently read/written story sub-data.

Provides ACID guarantees, concurrent-read safety (WAL mode), and
zero-dependency implementation using Python's built-in sqlite3.

Tables:
  summary_cards      — chapter summary cards (read before each generation)
  consistency_reports — per-chapter consistency audit results
  sentiment_logs     — per-chapter sentiment analysis logs
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from worldforger.world_store import world_root

_DB_FILE_NAME = "story_data.db"


def _db_path(world_id: str) -> Path:
    return world_root(world_id) / _DB_FILE_NAME


# Per-world connection cache (thread-safe).  Connections are opened lazily
# and kept alive for the process lifetime.  WAL mode means concurrent
# reads from multiple threads / async tasks are fine.
_conns: dict[str, sqlite3.Connection] = {}
_lock = threading.Lock()


def _get_conn(world_id: str) -> sqlite3.Connection:
    with _lock:
        conn = _conns.get(world_id)
        if conn is not None:
            return conn
    dbp = _db_path(world_id)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(dbp), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    _ensure_tables(conn)
    with _lock:
        _conns[world_id] = conn
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS summary_cards (
            chapter_id TEXT PRIMARY KEY,
            card_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS consistency_reports (
            chapter_id TEXT PRIMARY KEY,
            report_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sentiment_logs (
            chapter_id TEXT PRIMARY KEY,
            log_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)


def close_world(world_id: str) -> None:
    """Close and remove the cached connection for *world_id* (if any)."""
    with _lock:
        conn = _conns.pop(world_id, None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


# ── summary_cards ──────────────────────────────────────────────

def read_summary_card(world_id: str, chapter_id: str) -> dict | None:
    conn = _get_conn(world_id)
    row = conn.execute(
        "SELECT card_json FROM summary_cards WHERE chapter_id = ?",
        (chapter_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["card_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def write_summary_card(world_id: str, chapter_id: str, data: dict) -> None:
    conn = _get_conn(world_id)
    conn.execute(
        "INSERT OR REPLACE INTO summary_cards (chapter_id, card_json, updated_at) VALUES (?, ?, ?)",
        (chapter_id, json.dumps(data, ensure_ascii=False), _now()),
    )
    conn.commit()


# ── consistency_reports ────────────────────────────────────────

def read_consistency_report(world_id: str, chapter_id: str) -> dict | None:
    conn = _get_conn(world_id)
    row = conn.execute(
        "SELECT report_json FROM consistency_reports WHERE chapter_id = ?",
        (chapter_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["report_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def write_consistency_report(world_id: str, chapter_id: str, data: dict) -> None:
    conn = _get_conn(world_id)
    conn.execute(
        "INSERT OR REPLACE INTO consistency_reports (chapter_id, report_json, updated_at) VALUES (?, ?, ?)",
        (chapter_id, json.dumps(data, ensure_ascii=False), _now()),
    )
    conn.commit()


# ── sentiment_logs ─────────────────────────────────────────────

def read_sentiment_log(world_id: str, chapter_id: str) -> dict | None:
    conn = _get_conn(world_id)
    row = conn.execute(
        "SELECT log_json FROM sentiment_logs WHERE chapter_id = ?",
        (chapter_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["log_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def write_sentiment_log(world_id: str, chapter_id: str, data: dict) -> None:
    conn = _get_conn(world_id)
    conn.execute(
        "INSERT OR REPLACE INTO sentiment_logs (chapter_id, log_json, updated_at) VALUES (?, ?, ?)",
        (chapter_id, json.dumps(data, ensure_ascii=False), _now()),
    )
    conn.commit()


# ── migration from legacy JSON files ───────────────────────────

def migrate_json_files(world_id: str) -> int:
    """One-shot: scan existing JSON files and import into SQLite.

    Returns the number of rows migrated.  Idempotent — existing rows are
    left untouched (INSERT OR IGNORE).
    """
    from worldforger.story_store import (
        consistency_dir,
        consistency_path,
        sentiment_dir,
        sentiment_path,
        story_summaries_dir,
        summary_path,
    )

    conn = _get_conn(world_id)
    migrated = 0

    # Summary cards
    sd = story_summaries_dir(world_id)
    if sd.is_dir():
        for f in sorted(sd.glob("*.json")):
            ch_id = f.stem
            existing = conn.execute(
                "SELECT 1 FROM summary_cards WHERE chapter_id = ?", (ch_id,)
            ).fetchone()
            if existing:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT OR IGNORE INTO summary_cards (chapter_id, card_json, updated_at) VALUES (?, ?, ?)",
                    (ch_id, json.dumps(data, ensure_ascii=False), _now()),
                )
                migrated += 1
            except (json.JSONDecodeError, OSError):
                pass

    # Consistency reports
    cd = consistency_dir(world_id)
    if cd.is_dir():
        for f in sorted(cd.glob("*.json")):
            ch_id = f.stem
            existing = conn.execute(
                "SELECT 1 FROM consistency_reports WHERE chapter_id = ?", (ch_id,)
            ).fetchone()
            if existing:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT OR IGNORE INTO consistency_reports (chapter_id, report_json, updated_at) VALUES (?, ?, ?)",
                    (ch_id, json.dumps(data, ensure_ascii=False), _now()),
                )
                migrated += 1
            except (json.JSONDecodeError, OSError):
                pass

    # Sentiment logs
    sd2 = sentiment_dir(world_id)
    if sd2.is_dir():
        for f in sorted(sd2.glob("*.json")):
            ch_id = f.stem
            existing = conn.execute(
                "SELECT 1 FROM sentiment_logs WHERE chapter_id = ?", (ch_id,)
            ).fetchone()
            if existing:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT OR IGNORE INTO sentiment_logs (chapter_id, log_json, updated_at) VALUES (?, ?, ?)",
                    (ch_id, json.dumps(data, ensure_ascii=False), _now()),
                )
                migrated += 1
            except (json.JSONDecodeError, OSError):
                pass

    if migrated:
        conn.commit()
    return migrated


# ── helpers ────────────────────────────────────────────────────

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
