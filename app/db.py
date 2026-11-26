"""SQLite storage for call logs and the response cache."""
import json
import os
import sqlite3
import threading
import time

DB_PATH = os.getenv("DB_PATH", "data/costguard.db")
_lock = threading.Lock()
_conn = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db() -> None:
    with _lock:
        _db().executescript(
            """
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                team TEXT NOT NULL,
                feature TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                saved_usd REAL NOT NULL,
                latency_ms REAL NOT NULL,
                cache_hit INTEGER NOT NULL,
                status INTEGER NOT NULL,
                priced INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        _db().commit()


def log_call(**row) -> None:
    row.setdefault("ts", time.time())
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    with _lock:
        _db().execute(f"INSERT INTO calls ({cols}) VALUES ({marks})", tuple(row.values()))
        _db().commit()


def get_cached(key: str, ttl_seconds: float):
    with _lock:
        r = _db().execute("SELECT response, created_at FROM cache WHERE key = ?", (key,)).fetchone()
    if r is None or (ttl_seconds > 0 and time.time() - r["created_at"] > ttl_seconds):
        return None
    return json.loads(r["response"])


def put_cache(key: str, response: dict) -> None:
    with _lock:
        _db().execute(
            "INSERT OR REPLACE INTO cache (key, response, created_at) VALUES (?, ?, ?)",
            (key, json.dumps(response), time.time()),
        )
        _db().commit()


def stats() -> dict:
    def group(col: str):
        with _lock:
            rows = _db().execute(
                f"""SELECT {col} AS name, COUNT(*) AS calls,
                           SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
                           ROUND(SUM(cost_usd), 6) AS cost_usd, ROUND(SUM(saved_usd), 6) AS saved_usd
                    FROM calls GROUP BY {col} ORDER BY cost_usd DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    with _lock:
        t = _db().execute(
            """SELECT COUNT(*) AS calls,
                      COALESCE(SUM(cache_hit), 0) AS cache_hits,
                      ROUND(COALESCE(SUM(cost_usd), 0), 6) AS cost_usd,
                      ROUND(COALESCE(SUM(saved_usd), 0), 6) AS saved_usd,
                      ROUND(COALESCE(AVG(latency_ms), 0), 1) AS avg_latency_ms,
                      COALESCE(SUM(CASE WHEN priced = 0 THEN 1 ELSE 0 END), 0) AS unpriced_calls
               FROM calls"""
        ).fetchone()
    return {"totals": dict(t), "by_team": group("team"), "by_feature": group("feature"), "by_model": group("model")}
