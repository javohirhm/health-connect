"""Database layer supporting both SQLite (dev) and PostgreSQL (production)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
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

CREATE TABLE IF NOT EXISTS ai_insights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id    TEXT NOT NULL,
    date        TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    ai_text     TEXT NOT NULL,
    model       TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(watch_id, date)
);

CREATE INDEX IF NOT EXISTS idx_ai_insights_watch ON ai_insights(watch_id, date);
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

CREATE TABLE IF NOT EXISTS ai_insights (
    id          SERIAL PRIMARY KEY,
    watch_id    TEXT NOT NULL,
    date        TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    ai_text     TEXT NOT NULL,
    model       TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(watch_id, date)
);

CREATE INDEX IF NOT EXISTS idx_ai_insights_watch ON ai_insights(watch_id, date);
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
    """Insert a watch sensor row and return the new row id (so the caller can
    schedule per-row work like ECG classification)."""
    sql = "INSERT INTO watch_sensor_data (device_id, watch_id, sensor_type, data_json) VALUES (?, ?, ?, ?)"
    if config.DB_TYPE == "postgresql":
        sql += " RETURNING id"
    with get_db() as conn:
        cur = _execute(conn, sql, (device_id, watch_id, sensor_type, data_json))
        if config.DB_TYPE == "postgresql":
            row = cur.fetchone()
            return row["id"] if row else 0
        return cur.lastrowid or 0


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


def get_today_summary(watch_id: str) -> dict:
    """Roll up today's metrics for a watch (UTC day boundary).

    Aggregates HR samples across all batches today, accel batch count as a
    wear-time proxy, latest SpO2, ECG count + latest classification, and the
    most recent sleep session for the device that owns this watch. Each
    section is `null` when no data exists for that sensor today.
    """
    today_start = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        # ── Heart rate ───────────────────────────────────────────────
        hr_rows = _fetchall(conn,
            "SELECT data_json FROM watch_sensor_data "
            "WHERE watch_id = ? AND sensor_type = 'heart_rate' AND created_at >= ?",
            (watch_id, today_start))

        all_bpms: list[int] = []
        all_ibis: list[int] = []
        for r in hr_rows:
            try:
                payload = json.loads(r["data_json"])
                for s in payload.get("samples", []):
                    bpm = s.get("bpm")
                    if isinstance(bpm, (int, float)) and bpm > 0:
                        all_bpms.append(int(bpm))
                    # Inter-beat intervals — accept both "ibi_ms" (snake_case)
                    # and "ibiMs" (camelCase, default Gson on the watch).
                    ibis = s.get("ibi_ms") or s.get("ibiMs")
                    if isinstance(ibis, list):
                        for ibi in ibis:
                            if isinstance(ibi, (int, float)) and 300 < ibi < 2000:
                                all_ibis.append(int(ibi))
                    elif isinstance(ibis, (int, float)) and 300 < ibis < 2000:
                        all_ibis.append(int(ibis))
            except (json.JSONDecodeError, TypeError):
                continue

        hr_summary = None
        if all_bpms:
            sorted_bpms = sorted(all_bpms)
            resting_n = max(1, len(sorted_bpms) // 10)
            resting = sum(sorted_bpms[:resting_n]) // resting_n

            # HRV — RMSSD: root mean square of successive IBI differences.
            # Higher RMSSD generally indicates better recovery / parasympathetic tone.
            hrv_rmssd = None
            if len(all_ibis) >= 2:
                diffs = [all_ibis[i + 1] - all_ibis[i] for i in range(len(all_ibis) - 1)]
                if diffs:
                    hrv_rmssd = round((sum(d * d for d in diffs) / len(diffs)) ** 0.5, 1)

            hr_summary = {
                "avg_bpm": sum(all_bpms) // len(all_bpms),
                "min_bpm": min(all_bpms),
                "max_bpm": max(all_bpms),
                "resting_bpm": resting,
                "samples": len(all_bpms),
                "hrv_rmssd_ms": hrv_rmssd,
            }

        # ── Activity classification (still/walking/running/active) ───
        accel_rows = _fetchall(conn,
            "SELECT data_json FROM watch_sensor_data "
            "WHERE watch_id = ? AND sensor_type = 'accelerometer' AND created_at >= ?",
            (watch_id, today_start))
        activity_summary = None
        if accel_rows:
            from .signal_analysis import aggregate_activity
            activity_minutes = aggregate_activity(accel_rows) or {}
            batches = len(accel_rows)
            activity_summary = {
                "accel_batches": batches,
                "wear_time_estimate_min": round(batches * 5 / 60),
                "activity_minutes": activity_minutes,
            }

        # ── Latest SpO2 ──────────────────────────────────────────────
        spo2_row = _fetchone(conn,
            "SELECT data_json, created_at FROM watch_sensor_data "
            "WHERE watch_id = ? AND sensor_type = 'spo2' AND created_at >= ? "
            "ORDER BY id DESC LIMIT 1",
            (watch_id, today_start))
        spo2_summary = None
        if spo2_row:
            try:
                data = json.loads(spo2_row["data_json"])
                spo2_summary = {
                    "latest_percent": data.get("spO2Percent", 0),
                    "recorded_at": spo2_row["created_at"],
                }
            except json.JSONDecodeError:
                pass

        # ── ECG count + latest classification ────────────────────────
        ecg_count_row = _fetchone(conn,
            "SELECT COUNT(*) as c FROM watch_sensor_data "
            "WHERE watch_id = ? AND sensor_type = 'ecg' AND created_at >= ?",
            (watch_id, today_start))
        ecg_summary = None
        if ecg_count_row and ecg_count_row["c"] > 0:
            latest = _fetchone(conn,
                "SELECT id FROM watch_sensor_data "
                "WHERE watch_id = ? AND sensor_type = 'ecg' AND created_at >= ? "
                "ORDER BY id DESC LIMIT 1",
                (watch_id, today_start))
            label = None
            if latest:
                cls_row = _fetchone(conn,
                    "SELECT predicted_class FROM ecg_classifications "
                    "WHERE ecg_record_id = ? ORDER BY id DESC LIMIT 1",
                    (latest["id"],))
                label = cls_row["predicted_class"] if cls_row else None
            ecg_summary = {
                "recordings": ecg_count_row["c"],
                "latest_status": label or "Not analyzed",
            }

        # ── Last sleep session (Health Connect, keyed by device_id) ──
        dev_row = _fetchone(conn,
            "SELECT device_id FROM watch_sensor_data WHERE watch_id = ? ORDER BY id DESC LIMIT 1",
            (watch_id,))
        sleep_summary = None
        if dev_row:
            sleep_row = _fetchone(conn,
                "SELECT start_time, end_time FROM sleep_sessions "
                "WHERE device_id = ? ORDER BY id DESC LIMIT 1",
                (dev_row["device_id"],))
            if sleep_row:
                try:
                    start = datetime.fromisoformat(sleep_row["start_time"].replace("Z", "+00:00"))
                    end = datetime.fromisoformat(sleep_row["end_time"].replace("Z", "+00:00"))
                    duration_h = round((end - start).total_seconds() / 3600, 1)
                    sleep_summary = {
                        "duration_hours": duration_h,
                        "started_at": sleep_row["start_time"],
                    }

                    # Restlessness: re-use accelerometer rows that fall inside
                    # this sleep window. Watch_sensor_data.created_at uses
                    # 'YYYY-MM-DD HH:MM:SS' (UTC) — convert the sleep bounds
                    # to the same shape for the SQL comparison.
                    sleep_start_sql = start.astimezone().strftime("%Y-%m-%d %H:%M:%S") \
                        if start.tzinfo else start.strftime("%Y-%m-%d %H:%M:%S")
                    sleep_end_sql = end.astimezone().strftime("%Y-%m-%d %H:%M:%S") \
                        if end.tzinfo else end.strftime("%Y-%m-%d %H:%M:%S")
                    overnight_accel = _fetchall(conn,
                        "SELECT data_json FROM watch_sensor_data "
                        "WHERE watch_id = ? AND sensor_type = 'accelerometer' "
                        "AND created_at >= ? AND created_at <= ?",
                        (watch_id, sleep_start_sql, sleep_end_sql))
                    if overnight_accel:
                        from .signal_analysis import analyze_sleep_restlessness
                        restlessness = analyze_sleep_restlessness(overnight_accel)
                        if restlessness:
                            sleep_summary["restlessness"] = restlessness
                except (ValueError, AttributeError):
                    pass

        # ── Rhythm screen (AFib heuristic) ───────────────────────────
        rhythm_screen = None
        if all_ibis:
            from .ml_classifier import detect_afib
            # Pull today's beat classifications (if any) to enrich the screen.
            cls_rows = _fetchall(conn,
                "SELECT predicted_class FROM ecg_classifications "
                "WHERE watch_id = ? AND created_at >= ? LIMIT 500",
                (watch_id, today_start))
            beat_classes = [r["predicted_class"] for r in cls_rows] if cls_rows else None
            rhythm_screen = detect_afib(all_ibis, beat_classes)

    return {
        "watch_id": watch_id,
        "date": today_start[:10],
        "heart_rate": hr_summary,
        "rhythm_screen": rhythm_screen,
        "activity": activity_summary,
        "spo2": spo2_summary,
        "ecg": ecg_summary,
        "sleep": sleep_summary,
    }


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


# ── History summary (last N days) — used as Gemini chat context ───────

def get_history_summary(watch_id: str, days: int = 30) -> dict:
    """Compact aggregate of the last `days` of data for this watch.

    Used as background context in `/insights/total` and `/chat` so Gemini can
    answer trend questions ("how's my HRV been this month?"). Compact dict —
    not every sample, just averages.
    """
    start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        # ── HR + HRV across the window ───────────────────────────────
        hr_rows = _fetchall(conn,
            "SELECT data_json FROM watch_sensor_data "
            "WHERE watch_id = ? AND sensor_type = 'heart_rate' AND created_at >= ?",
            (watch_id, start))

        all_bpms: list[int] = []
        all_ibis: list[int] = []
        for r in hr_rows:
            try:
                payload = json.loads(r["data_json"])
                for s in payload.get("samples", []):
                    bpm = s.get("bpm")
                    if isinstance(bpm, (int, float)) and bpm > 0:
                        all_bpms.append(int(bpm))
                    ibis = s.get("ibi_ms") or s.get("ibiMs")
                    if isinstance(ibis, list):
                        for ibi in ibis:
                            if isinstance(ibi, (int, float)) and 300 < ibi < 2000:
                                all_ibis.append(int(ibi))
                    elif isinstance(ibis, (int, float)) and 300 < ibis < 2000:
                        all_ibis.append(int(ibis))
            except (json.JSONDecodeError, TypeError):
                continue

        avg_hr = sum(all_bpms) // len(all_bpms) if all_bpms else None

        avg_hrv = None
        if len(all_ibis) >= 2:
            diffs = [all_ibis[i + 1] - all_ibis[i] for i in range(len(all_ibis) - 1)]
            if diffs:
                avg_hrv = round((sum(d * d for d in diffs) / len(diffs)) ** 0.5, 1)

        # ── Wear-time proxy (accel batch count) ──────────────────────
        accel_count = _fetchone(conn,
            "SELECT COUNT(*) as c FROM watch_sensor_data "
            "WHERE watch_id = ? AND sensor_type = 'accelerometer' AND created_at >= ?",
            (watch_id, start))["c"]
        avg_wear_min_per_day = round(accel_count * 5 / 60 / max(1, days)) if accel_count else 0

        # ── ECG counts + classification distribution ─────────────────
        ecg_count = _fetchone(conn,
            "SELECT COUNT(*) as c FROM watch_sensor_data "
            "WHERE watch_id = ? AND sensor_type = 'ecg' AND created_at >= ?",
            (watch_id, start))["c"]

        ecg_classes: dict = {}
        if ecg_count > 0:
            class_rows = _fetchall(conn,
                "SELECT predicted_class, COUNT(*) as c FROM ecg_classifications "
                "WHERE watch_id = ? AND created_at >= ? GROUP BY predicted_class",
                (watch_id, start))
            for r in class_rows:
                ecg_classes[r["predicted_class"]] = r["c"]

        # ── Sleep history ────────────────────────────────────────────
        dev_row = _fetchone(conn,
            "SELECT device_id FROM watch_sensor_data WHERE watch_id = ? ORDER BY id DESC LIMIT 1",
            (watch_id,))
        avg_sleep = None
        sleep_count = 0
        if dev_row:
            sleep_rows = _fetchall(conn,
                "SELECT start_time, end_time FROM sleep_sessions "
                "WHERE device_id = ? AND start_time >= ?",
                (dev_row["device_id"], start.split()[0]))
            durations = []
            for r in sleep_rows:
                try:
                    s = datetime.fromisoformat(r["start_time"].replace("Z", "+00:00"))
                    e = datetime.fromisoformat(r["end_time"].replace("Z", "+00:00"))
                    h = (e - s).total_seconds() / 3600
                    if 0 < h < 24:
                        durations.append(h)
                except (ValueError, AttributeError):
                    continue
            if durations:
                avg_sleep = round(sum(durations) / len(durations), 1)
                sleep_count = len(durations)

        # ── Latest SpO2 in the window ────────────────────────────────
        spo2_row = _fetchone(conn,
            "SELECT data_json FROM watch_sensor_data "
            "WHERE watch_id = ? AND sensor_type = 'spo2' AND created_at >= ? "
            "ORDER BY id DESC LIMIT 1",
            (watch_id, start))
        latest_spo2 = None
        if spo2_row:
            try:
                latest_spo2 = json.loads(spo2_row["data_json"]).get("spO2Percent")
            except (json.JSONDecodeError, TypeError):
                pass

    # Aggregate AFib screen across all of the window's IBIs
    rhythm_screen = None
    if all_ibis:
        from .ml_classifier import detect_afib
        rhythm_screen = detect_afib(all_ibis, None)

    return {
        "watch_id": watch_id,
        "days_covered": days,
        "avg_hr_bpm": avg_hr,
        "avg_hrv_rmssd_ms": avg_hrv,
        "avg_wear_min_per_day": avg_wear_min_per_day,
        "ecg_recordings": ecg_count,
        "ecg_classifications": ecg_classes,
        "avg_sleep_hours": avg_sleep,
        "sleep_sessions_logged": sleep_count,
        "latest_spo2_percent": latest_spo2,
        "rhythm_screen": rhythm_screen,
    }


# ── AI insights cache ─────────────────────────────────────────────────

def get_sleep_history(watch_id: str, limit: int = 14) -> list[dict]:
    """Recent sleep sessions for the device paired with this watch, each
    augmented with a restlessness analysis from accelerometer batches inside
    the session window."""
    from .signal_analysis import analyze_sleep_restlessness

    with get_db() as conn:
        dev_row = _fetchone(conn,
            "SELECT device_id FROM watch_sensor_data "
            "WHERE watch_id = ? ORDER BY id DESC LIMIT 1",
            (watch_id,))
        if not dev_row:
            return []

        sessions = _fetchall(conn,
            "SELECT id, start_time, end_time FROM sleep_sessions "
            "WHERE device_id = ? ORDER BY start_time DESC LIMIT ?",
            (dev_row["device_id"], limit))

        results: list[dict] = []
        for s in sessions:
            try:
                start = datetime.fromisoformat(s["start_time"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(s["end_time"].replace("Z", "+00:00"))
                duration_h = round((end - start).total_seconds() / 3600, 1)

                start_sql = (start.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                             if start.tzinfo else start.strftime("%Y-%m-%d %H:%M:%S"))
                end_sql = (end.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                           if end.tzinfo else end.strftime("%Y-%m-%d %H:%M:%S"))
                accel = _fetchall(conn,
                    "SELECT data_json FROM watch_sensor_data "
                    "WHERE watch_id = ? AND sensor_type = 'accelerometer' "
                    "AND created_at >= ? AND created_at <= ?",
                    (watch_id, start_sql, end_sql))

                results.append({
                    "id": s["id"],
                    "start_time": s["start_time"],
                    "end_time": s["end_time"],
                    "duration_hours": duration_h,
                    "restlessness": analyze_sleep_restlessness(accel) if accel else None,
                })
            except (ValueError, AttributeError, KeyError):
                continue

        return results


def get_cached_insight(watch_id: str, date: str) -> dict | None:
    """Look up a previously-generated AI insight for (watch_id, date)."""
    with get_db() as conn:
        row = _fetchone(conn,
            "SELECT ai_text, model, created_at FROM ai_insights "
            "WHERE watch_id = ? AND date = ?",
            (watch_id, date))
    if not row:
        return None
    return {
        "ai_text": row["ai_text"],
        "model": row["model"],
        "generated_at": str(row["created_at"]),
        "cached": True,
    }


def save_insight(watch_id: str, date: str, summary_json: str, ai_text: str, model: str) -> None:
    """Persist (or refresh) the AI insight for (watch_id, date)."""
    with get_db() as conn:
        if config.DB_TYPE == "postgresql":
            _execute(conn,
                "INSERT INTO ai_insights (watch_id, date, summary_json, ai_text, model) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (watch_id, date) DO UPDATE SET "
                "summary_json = EXCLUDED.summary_json, "
                "ai_text = EXCLUDED.ai_text, "
                "model = EXCLUDED.model, "
                "created_at = NOW()",
                (watch_id, date, summary_json, ai_text, model))
        else:
            _execute(conn,
                "INSERT OR REPLACE INTO ai_insights "
                "(watch_id, date, summary_json, ai_text, model) "
                "VALUES (?, ?, ?, ?, ?)",
                (watch_id, date, summary_json, ai_text, model))
