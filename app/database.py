"""Database layer supporting both SQLite (dev) and PostgreSQL (production)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from contextlib import contextmanager
from typing import Optional
from .config import config

logger = logging.getLogger("health-api.db")

# ── Connection management ─────────────────────────────────────────────

_pg_pool = None

if config.DB_TYPE == "postgresql":
    import psycopg2
    import psycopg2.pool
    import psycopg2.extras
else:
    import sqlite3


def _init_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=config.pg_url,
        )
        logger.info("PostgreSQL connection pool created")


@contextmanager
def get_db():
    if config.DB_TYPE == "postgresql":
        _init_pg_pool()
        conn = _pg_pool.getconn()
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _pg_pool.putconn(conn)
    else:
        conn = sqlite3.connect(str(config.db_path_resolved))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _execute(conn, sql, params=None):
    """Execute SQL, handling placeholder differences between SQLite (?) and PostgreSQL (%s)."""
    if config.DB_TYPE == "postgresql":
        sql = sql.replace("?", "%s")
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        sql = sql.replace("INSERT OR IGNORE", "INSERT")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur


def _fetchall(conn, sql, params=None) -> list[dict]:
    cur = _execute(conn, sql, params)
    rows = cur.fetchall()
    if config.DB_TYPE == "postgresql":
        return [dict(r) for r in rows]
    else:
        return [dict(r) for r in rows]


def _fetchone(conn, sql, params=None) -> dict | None:
    cur = _execute(conn, sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


# ── Schema initialization ─────────────────────────────────────────────

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    synced_at   TEXT NOT NULL,
    payload     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heart_rate (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    samples     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(device_id, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    count       INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(device_id, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS sleep_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    stages      TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(device_id, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS exercise_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    exercise_type INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(device_id, start_time, end_time)
);

CREATE INDEX IF NOT EXISTS idx_hr_device ON heart_rate(device_id);
CREATE INDEX IF NOT EXISTS idx_steps_device ON steps(device_id);
CREATE INDEX IF NOT EXISTS idx_sleep_device ON sleep_sessions(device_id);
CREATE INDEX IF NOT EXISTS idx_exercise_device ON exercise_sessions(device_id);

CREATE TABLE IF NOT EXISTS watch_sensor_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    watch_id    TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_watch_device ON watch_sensor_data(device_id);
CREATE INDEX IF NOT EXISTS idx_watch_sensor ON watch_sensor_data(sensor_type);
CREATE INDEX IF NOT EXISTS idx_watch_watch_id ON watch_sensor_data(watch_id);

CREATE TABLE IF NOT EXISTS ecg_classifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ecg_record_id INTEGER NOT NULL,
    watch_id    TEXT NOT NULL,
    model_name  TEXT NOT NULL,
    beat_index  INTEGER NOT NULL,
    predicted_class TEXT NOT NULL,
    confidence  REAL NOT NULL,
    all_probabilities TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ecg_class_record ON ecg_classifications(ecg_record_id);
CREATE INDEX IF NOT EXISTS idx_ecg_class_watch ON ecg_classifications(watch_id);
"""

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_log (
    id          SERIAL PRIMARY KEY,
    device_id   TEXT NOT NULL,
    synced_at   TIMESTAMPTZ NOT NULL,
    payload     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heart_rate (
    id          SERIAL PRIMARY KEY,
    device_id   TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    samples     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(device_id, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS steps (
    id          SERIAL PRIMARY KEY,
    device_id   TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    count       INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(device_id, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS sleep_sessions (
    id          SERIAL PRIMARY KEY,
    device_id   TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    stages      TEXT NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(device_id, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS exercise_sessions (
    id          SERIAL PRIMARY KEY,
    device_id   TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    exercise_type INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(device_id, start_time, end_time)
);

CREATE INDEX IF NOT EXISTS idx_hr_device ON heart_rate(device_id);
CREATE INDEX IF NOT EXISTS idx_steps_device ON steps(device_id);
CREATE INDEX IF NOT EXISTS idx_sleep_device ON sleep_sessions(device_id);
CREATE INDEX IF NOT EXISTS idx_exercise_device ON exercise_sessions(device_id);

CREATE TABLE IF NOT EXISTS watch_sensor_data (
    id          SERIAL PRIMARY KEY,
    device_id   TEXT NOT NULL,
    watch_id    TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watch_device ON watch_sensor_data(device_id);
CREATE INDEX IF NOT EXISTS idx_watch_sensor ON watch_sensor_data(sensor_type);
CREATE INDEX IF NOT EXISTS idx_watch_watch_id ON watch_sensor_data(watch_id);

CREATE TABLE IF NOT EXISTS ecg_classifications (
    id          SERIAL PRIMARY KEY,
    ecg_record_id INTEGER NOT NULL,
    watch_id    TEXT NOT NULL,
    model_name  TEXT NOT NULL,
    beat_index  INTEGER NOT NULL,
    predicted_class TEXT NOT NULL,
    confidence  REAL NOT NULL,
    all_probabilities TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ecg_class_record ON ecg_classifications(ecg_record_id);
CREATE INDEX IF NOT EXISTS idx_ecg_class_watch ON ecg_classifications(watch_id);
"""


def init_db():
    with get_db() as conn:
        schema = _PG_SCHEMA if config.DB_TYPE == "postgresql" else _SQLITE_SCHEMA
        if config.DB_TYPE == "postgresql":
            for statement in schema.split(";"):
                s = statement.strip()
                if s:
                    conn.cursor().execute(s)
            conn.commit()
        else:
            conn.executescript(schema)
    logger.info("Database initialized (%s)", config.DB_TYPE)


# ── Write helpers ────────────────────────────────────────────────────

def save_sync(device_id: str, payload_json: str) -> int:
    sql = "INSERT INTO sync_log (device_id, synced_at, payload) VALUES (?, ?, ?)"
    if config.DB_TYPE == "postgresql":
        sql += " RETURNING id"
    with get_db() as conn:
        cur = _execute(conn, sql, (device_id, datetime.utcnow().isoformat(), payload_json))
        if config.DB_TYPE == "postgresql":
            row = cur.fetchone()
            return row["id"] if row else 0
        return cur.lastrowid


def save_heart_rate(device_id: str, records: list[dict]) -> int:
    count = 0
    with get_db() as conn:
        for r in records:
            try:
                if config.DB_TYPE == "postgresql":
                    _execute(conn,
                        "INSERT INTO heart_rate (device_id, start_time, end_time, samples) "
                        "VALUES (?, ?, ?, ?) ON CONFLICT (device_id, start_time, end_time) DO NOTHING",
                        (device_id, r["start_time"], r["end_time"], json.dumps(r["samples"], default=str)))
                else:
                    _execute(conn,
                        "INSERT OR IGNORE INTO heart_rate (device_id, start_time, end_time, samples) VALUES (?, ?, ?, ?)",
                        (device_id, r["start_time"], r["end_time"], json.dumps(r["samples"], default=str)))
                count += 1
            except Exception:
                pass
    return count


def save_steps(device_id: str, records: list[dict]) -> int:
    count = 0
    with get_db() as conn:
        for r in records:
            try:
                if config.DB_TYPE == "postgresql":
                    _execute(conn,
                        "INSERT INTO steps (device_id, start_time, end_time, count) "
                        "VALUES (?, ?, ?, ?) ON CONFLICT (device_id, start_time, end_time) DO NOTHING",
                        (device_id, r["start_time"], r["end_time"], r["count"]))
                else:
                    _execute(conn,
                        "INSERT OR IGNORE INTO steps (device_id, start_time, end_time, count) VALUES (?, ?, ?, ?)",
                        (device_id, r["start_time"], r["end_time"], r["count"]))
                count += 1
            except Exception:
                pass
    return count


def save_sleep_sessions(device_id: str, records: list[dict]) -> int:
    count = 0
    with get_db() as conn:
        for r in records:
            try:
                if config.DB_TYPE == "postgresql":
                    _execute(conn,
                        "INSERT INTO sleep_sessions (device_id, start_time, end_time, stages) "
                        "VALUES (?, ?, ?, ?) ON CONFLICT (device_id, start_time, end_time) DO NOTHING",
                        (device_id, r["start_time"], r["end_time"], json.dumps(r.get("stages", []), default=str)))
                else:
                    _execute(conn,
                        "INSERT OR IGNORE INTO sleep_sessions (device_id, start_time, end_time, stages) VALUES (?, ?, ?, ?)",
                        (device_id, r["start_time"], r["end_time"], json.dumps(r.get("stages", []), default=str)))
                count += 1
            except Exception:
                pass
    return count


def save_exercise_sessions(device_id: str, records: list[dict]) -> int:
    count = 0
    with get_db() as conn:
        for r in records:
            try:
                if config.DB_TYPE == "postgresql":
                    _execute(conn,
                        "INSERT INTO exercise_sessions (device_id, start_time, end_time, exercise_type) "
                        "VALUES (?, ?, ?, ?) ON CONFLICT (device_id, start_time, end_time) DO NOTHING",
                        (device_id, r["start_time"], r["end_time"], r["exercise_type"]))
                else:
                    _execute(conn,
                        "INSERT OR IGNORE INTO exercise_sessions (device_id, start_time, end_time, exercise_type) VALUES (?, ?, ?, ?)",
                        (device_id, r["start_time"], r["end_time"], r["exercise_type"]))
                count += 1
            except Exception:
                pass
    return count


def save_watch_sensor_data(device_id: str, watch_id: str, sensor_type: str, data_json: str) -> int:
    with get_db() as conn:
        _execute(conn,
            "INSERT INTO watch_sensor_data (device_id, watch_id, sensor_type, data_json) VALUES (?, ?, ?, ?)",
            (device_id, watch_id, sensor_type, data_json))
        return 1


def save_ecg_classification(ecg_record_id: int, watch_id: str, model_name: str,
                            beat_index: int, predicted_class: str, confidence: float,
                            all_probabilities: dict) -> int:
    with get_db() as conn:
        _execute(conn,
            "INSERT INTO ecg_classifications (ecg_record_id, watch_id, model_name, beat_index, "
            "predicted_class, confidence, all_probabilities) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ecg_record_id, watch_id, model_name, beat_index, predicted_class, confidence,
             json.dumps(all_probabilities)))
        return 1


# ── Read helpers ─────────────────────────────────────────────────────

ALLOWED_TABLES = {"heart_rate", "steps", "sleep_sessions", "exercise_sessions"}


def get_device_summary(device_id: str) -> dict:
    with get_db() as conn:
        row = _fetchone(conn, "SELECT synced_at FROM sync_log WHERE device_id = ? ORDER BY id DESC LIMIT 1", (device_id,))
        hr = _fetchone(conn, "SELECT COUNT(*) as c FROM heart_rate WHERE device_id = ?", (device_id,))["c"]
        st = _fetchone(conn, "SELECT COUNT(*) as c FROM steps WHERE device_id = ?", (device_id,))["c"]
        sl = _fetchone(conn, "SELECT COUNT(*) as c FROM sleep_sessions WHERE device_id = ?", (device_id,))["c"]
        ex = _fetchone(conn, "SELECT COUNT(*) as c FROM exercise_sessions WHERE device_id = ?", (device_id,))["c"]
    return {
        "device_id": device_id,
        "last_sync": row["synced_at"] if row else None,
        "total_heart_rate_records": hr,
        "total_steps_records": st,
        "total_sleep_sessions": sl,
        "total_exercise_sessions": ex,
    }


def get_latest_records(device_id: str, table: str, limit: int = 50) -> list[dict]:
    """Get latest records from a table. Table name is validated against allowlist."""
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table: {table}")
    with get_db() as conn:
        return _fetchall(conn,
            f"SELECT * FROM {table} WHERE device_id = ? ORDER BY id DESC LIMIT ?",
            (device_id, limit))


def get_watch_sensor_data(watch_id: str, sensor_type: str = None, limit: int = 50) -> list[dict]:
    with get_db() as conn:
        if sensor_type:
            return _fetchall(conn,
                "SELECT * FROM watch_sensor_data WHERE watch_id = ? AND sensor_type = ? ORDER BY id DESC LIMIT ?",
                (watch_id, sensor_type, limit))
        else:
            return _fetchall(conn,
                "SELECT * FROM watch_sensor_data WHERE watch_id = ? ORDER BY id DESC LIMIT ?",
                (watch_id, limit))


def get_watch_summary(watch_id: str) -> dict:
    with get_db() as conn:
        total = _fetchone(conn, "SELECT COUNT(*) as c FROM watch_sensor_data WHERE watch_id = ?", (watch_id,))["c"]
        sensors = _fetchall(conn,
            "SELECT sensor_type, COUNT(*) as count, MAX(created_at) as last_seen "
            "FROM watch_sensor_data WHERE watch_id = ? GROUP BY sensor_type",
            (watch_id,))
    return {"watch_id": watch_id, "total_records": total, "sensors": sensors}


def get_ecg_history(watch_id: str, limit: int = 20) -> list[dict]:
    with get_db() as conn:
        rows = _fetchall(conn,
            "SELECT id, device_id, watch_id, sensor_type, data_json, created_at "
            "FROM watch_sensor_data WHERE watch_id = ? AND sensor_type = 'ecg' "
            "ORDER BY id DESC LIMIT ?",
            (watch_id, limit))
    results = []
    for r in rows:
        try:
            data = json.loads(r["data_json"])
            results.append({
                "id": r["id"],
                "sample_count": len(data.get("samplesMillivolts", [])),
                "sample_rate_hz": data.get("sampleRateHz", 500),
                "start_timestamp": data.get("startTimestamp", 0),
                "duration_ms": data.get("durationMs", 0),
                "lead_off": data.get("leadOff", False),
                "recorded_at": r["created_at"],
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return results


def get_ecg_classifications(ecg_record_id: int) -> list[dict]:
    with get_db() as conn:
        return _fetchall(conn,
            "SELECT * FROM ecg_classifications WHERE ecg_record_id = ? ORDER BY beat_index",
            (ecg_record_id,))


def get_all_watches() -> list[dict]:
    with get_db() as conn:
        return _fetchall(conn,
            "SELECT watch_id, COUNT(*) as total_records, "
            "COUNT(DISTINCT sensor_type) as sensor_count, "
            "MAX(created_at) as last_seen "
            "FROM watch_sensor_data GROUP BY watch_id ORDER BY last_seen DESC")


def get_all_data_for_device(device_id: str) -> dict:
    """Get all data for a device — used for PDF reports and CSV export."""
    with get_db() as conn:
        return {
            "heart_rate": _fetchall(conn, "SELECT * FROM heart_rate WHERE device_id = ? ORDER BY id DESC", (device_id,)),
            "steps": _fetchall(conn, "SELECT * FROM steps WHERE device_id = ? ORDER BY id DESC", (device_id,)),
            "sleep": _fetchall(conn, "SELECT * FROM sleep_sessions WHERE device_id = ? ORDER BY id DESC", (device_id,)),
            "exercise": _fetchall(conn, "SELECT * FROM exercise_sessions WHERE device_id = ? ORDER BY id DESC", (device_id,)),
        }


def get_all_watch_data(watch_id: str) -> dict:
    """Get all watch data grouped by sensor — for export."""
    with get_db() as conn:
        rows = _fetchall(conn,
            "SELECT * FROM watch_sensor_data WHERE watch_id = ? ORDER BY sensor_type, id DESC",
            (watch_id,))
    grouped = {}
    for r in rows:
        st = r["sensor_type"]
        if st not in grouped:
            grouped[st] = []
        grouped[st].append(r)
    return grouped
