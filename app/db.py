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
                priced INTEGER NOT NULL,
                requested_model TEXT NOT NULL DEFAULT '',
                routing_saved_usd REAL NOT NULL DEFAULT 0,
                streamed INTEGER NOT NULL DEFAULT 0,
                reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                upstream TEXT NOT NULL DEFAULT 'primary'
            );
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        # Upgrade databases created by v0.1
        existing = {r["name"] for r in _db().execute("PRAGMA table_info(calls)")}
        for col, ddl in [
            ("requested_model", "TEXT NOT NULL DEFAULT ''"),
            ("routing_saved_usd", "REAL NOT NULL DEFAULT 0"),
            ("streamed", "INTEGER NOT NULL DEFAULT 0"),
            ("reasoning_tokens", "INTEGER NOT NULL DEFAULT 0"),
            ("upstream", "TEXT NOT NULL DEFAULT 'primary'"),
        ]:
            if col not in existing:
                _db().execute(f"ALTER TABLE calls ADD COLUMN {col} {ddl}")
        _db().execute("CREATE INDEX IF NOT EXISTS idx_calls_team_ts ON calls (team, ts)")
        _db().commit()


def _start_of_today_utc() -> float:
    now = time.time()
    return now - (now % 86400)


def spent_today(team: str) -> float:
    with _lock:
        r = _db().execute("SELECT COALESCE(SUM(cost_usd), 0) AS s FROM calls WHERE team = ? AND ts >= ?",
                          (team, _start_of_today_utc())).fetchone()
    return float(r["s"])


def spent_today_by_team() -> dict:
    with _lock:
        rows = _db().execute("SELECT team, SUM(cost_usd) AS s FROM calls WHERE ts >= ? GROUP BY team",
                             (_start_of_today_utc(),)).fetchall()
    return {r["team"]: float(r["s"]) for r in rows}


CALL_COLUMNS = frozenset({
    "ts", "provider", "model", "team", "feature", "input_tokens", "output_tokens", "cost_usd",
    "saved_usd", "latency_ms", "cache_hit", "status", "priced", "requested_model",
    "routing_saved_usd", "streamed", "reasoning_tokens", "upstream",
})
GROUP_COLUMNS = frozenset({"team", "feature", "model"})


def log_call(**row) -> None:
    row.setdefault("ts", time.time())
    unknown = set(row) - CALL_COLUMNS
    if unknown:
        raise ValueError(f"Unknown columns: {sorted(unknown)}")
    cols = ", ".join(row)  # only names from CALL_COLUMNS; values are bound parameters
    marks = ", ".join("?" for _ in row)
    with _lock:
        _db().execute(f"INSERT INTO calls ({cols}) VALUES ({marks})", tuple(row.values()))  # nosec B608
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
        # col is checked against an allowlist, so it is safe to put in the query
        if col not in GROUP_COLUMNS:
            raise ValueError(f"Can't group by {col}")
        with _lock:
            rows = _db().execute(
                f"""SELECT {col} AS name, COUNT(*) AS calls,
                           SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
                           SUM(reasoning_tokens) AS reasoning_tokens,
                           ROUND(SUM(cost_usd), 6) AS cost_usd, ROUND(SUM(saved_usd), 6) AS saved_usd,
                           ROUND(SUM(routing_saved_usd), 6) AS routing_saved_usd
                    FROM calls GROUP BY {col} ORDER BY cost_usd DESC"""  # nosec B608
            ).fetchall()
        return [dict(r) for r in rows]

    with _lock:
        t = _db().execute(
            """SELECT COUNT(*) AS calls,
                      COALESCE(SUM(cache_hit), 0) AS cache_hits,
                      ROUND(COALESCE(SUM(cost_usd), 0), 6) AS cost_usd,
                      ROUND(COALESCE(SUM(saved_usd), 0), 6) AS saved_usd,
                      ROUND(COALESCE(SUM(routing_saved_usd), 0), 6) AS routing_saved_usd,
                      COALESCE(SUM(CASE WHEN requested_model = 'auto' THEN 1 ELSE 0 END), 0) AS routed_calls,
                      COALESCE(SUM(streamed), 0) AS streamed_calls,
                      COALESCE(SUM(output_tokens), 0) AS output_tokens,
                      COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                      COALESCE(SUM(CASE WHEN upstream != 'primary' THEN 1 ELSE 0 END), 0) AS fallback_calls,
                      ROUND(COALESCE(AVG(latency_ms), 0), 1) AS avg_latency_ms,
                      COALESCE(SUM(CASE WHEN priced = 0 THEN 1 ELSE 0 END), 0) AS unpriced_calls
               FROM calls"""
        ).fetchone()
    return {"totals": dict(t), "by_team": group("team"), "by_feature": group("feature"), "by_model": group("model")}
