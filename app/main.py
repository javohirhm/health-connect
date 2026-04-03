"""FastAPI backend for Health Connect ecosystem.

Features:
- V1 endpoints: Android Health Connect data (HR, steps, sleep, exercise)
- V2 endpoints: Galaxy Watch raw sensor data (ECG, SpO2, BIA, PPG, etc.)
- ECG arrhythmia classification using trained ML models
- Web dashboard for real-time visualization
- CSV/PDF export of health data
"""

import csv
import io
import json
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

from .config import config
from .models import (
    HealthDataPayload, SyncResponse, DeviceSummary, HealthSummary,
    WatchSensorPayload, WatchSyncResponse,
)
from . import database as db

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL), format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("health-api")

app = FastAPI(
    title="Health Connect Backend",
    description="Health data pipeline: Galaxy Watch 5 → Android Phone → FastAPI Backend",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()
    logger.info("Database initialized (%s)", config.DB_TYPE)


# ═══════════════════════════════════════════════════════════════════════
# V1: Android Health Connect Sync
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/v1/sync", response_model=SyncResponse)
def sync_health_data(payload: HealthDataPayload):
    logger.info("Sync from device=%s hr=%d steps=%d sleep=%d exercise=%d",
        payload.device_id, len(payload.heart_rate), len(payload.steps),
        len(payload.sleep_sessions), len(payload.exercise_sessions))
    db.save_sync(payload.device_id, payload.model_dump_json())
    total = len(payload.heart_rate) + len(payload.steps) + len(payload.sleep_sessions) + len(payload.exercise_sessions)
    saved = 0
    if payload.heart_rate:
        saved += db.save_heart_rate(payload.device_id, [r.model_dump() for r in payload.heart_rate])
    if payload.steps:
        saved += db.save_steps(payload.device_id, [r.model_dump() for r in payload.steps])
    if payload.sleep_sessions:
        saved += db.save_sleep_sessions(payload.device_id, [r.model_dump() for r in payload.sleep_sessions])
    if payload.exercise_sessions:
        saved += db.save_exercise_sessions(payload.device_id, [r.model_dump() for r in payload.exercise_sessions])
    skipped = total - saved
    return SyncResponse(records_saved=saved,
        message=f"{saved} new records saved" + (f", {skipped} already existed" if skipped > 0 else ""))


@app.get("/api/v1/devices/{device_id}", response_model=DeviceSummary)
def get_device(device_id: str):
    summary = db.get_device_summary(device_id)
    if summary["last_sync"] is None and summary["total_heart_rate_records"] == 0:
        raise HTTPException(404, "Device not found")
    return summary


@app.get("/api/v1/devices/{device_id}/heart-rate")
def get_heart_rate(device_id: str, limit: int = 50):
    return db.get_latest_records(device_id, "heart_rate", limit)


@app.get("/api/v1/devices/{device_id}/steps")
def get_steps(device_id: str, limit: int = 50):
    return db.get_latest_records(device_id, "steps", limit)


@app.get("/api/v1/devices/{device_id}/sleep")
def get_sleep(device_id: str, limit: int = 50):
    return db.get_latest_records(device_id, "sleep_sessions", limit)


@app.get("/api/v1/devices/{device_id}/exercise")
def get_exercise(device_id: str, limit: int = 50):
    return db.get_latest_records(device_id, "exercise_sessions", limit)


@app.get("/api/v1/health")
def health_check():
    return {"status": "ok", "db_type": config.DB_TYPE}


# ═══════════════════════════════════════════════════════════════════════
# V2: Galaxy Watch Sensor Data
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/v2/watch/sync", response_model=WatchSyncResponse)
def sync_watch_data(payload: WatchSensorPayload):
    logger.info("Watch sync: device=%s watch=%s sensor=%s",
        payload.device_id, payload.watch_id, payload.sensor_type)
    saved = db.save_watch_sensor_data(
        device_id=payload.device_id, watch_id=payload.watch_id,
        sensor_type=payload.sensor_type, data_json=payload.data_json)
    return WatchSyncResponse(records_saved=saved)


@app.get("/api/v2/watches")
def list_watches():
    return db.get_all_watches()


@app.get("/api/v2/watch/{watch_id}/summary")
def get_watch_summary(watch_id: str):
    return db.get_watch_summary(watch_id)


@app.get("/api/v2/watch/{watch_id}/data")
def get_watch_data(watch_id: str, sensor_type: str = None, limit: int = 50):
    return db.get_watch_sensor_data(watch_id, sensor_type, limit)


@app.get("/api/v2/watch/{watch_id}/heart-rate/latest")
def get_watch_latest_hr(watch_id: str):
    rows = db.get_watch_sensor_data(watch_id, "heart_rate", 1)
    if not rows:
        raise HTTPException(404, "No heart rate data")
    try:
        data = json.loads(rows[0]["data_json"])
        samples = data.get("samples", [])
        if samples:
            latest = samples[-1]
            return {"bpm": latest.get("bpm", 0), "ibi_ms": latest.get("ibiMs", []),
                    "timestamp": latest.get("timestamp", 0), "watch_id": watch_id}
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    raise HTTPException(404, "Could not parse heart rate data")


@app.get("/api/v2/watch/{watch_id}/ecg/latest")
def get_watch_latest_ecg(watch_id: str):
    rows = db.get_watch_sensor_data(watch_id, "ecg", 1)
    if not rows:
        raise HTTPException(404, "No ECG data")
    try:
        data = json.loads(rows[0]["data_json"])
        return {
            "id": rows[0]["id"],
            "samples_millivolts": data.get("samplesMillivolts", []),
            "sample_rate_hz": data.get("sampleRateHz", 500),
            "start_timestamp": data.get("startTimestamp", 0),
            "duration_ms": data.get("durationMs", 0),
            "watch_id": watch_id,
            "recorded_at": rows[0]["created_at"],
        }
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(500, "Could not parse ECG data")


@app.get("/api/v2/watch/{watch_id}/ecg/history")
def get_watch_ecg_history(watch_id: str, limit: int = 20):
    return db.get_ecg_history(watch_id, limit)


@app.get("/api/v2/watch/{watch_id}/ecg/{record_id}")
def get_watch_ecg_by_id(watch_id: str, record_id: int):
    with db.get_db() as conn:
        row = db._fetchone(conn,
            "SELECT * FROM watch_sensor_data WHERE id = ? AND watch_id = ? AND sensor_type = 'ecg'",
            (record_id, watch_id))
    if not row:
        raise HTTPException(404, "ECG recording not found")
    try:
        data = json.loads(row["data_json"])
        return {
            "id": row["id"], "samples_millivolts": data.get("samplesMillivolts", []),
            "sample_rate_hz": data.get("sampleRateHz", 500),
            "start_timestamp": data.get("startTimestamp", 0),
            "duration_ms": data.get("durationMs", 0),
            "lead_off": data.get("leadOff", False),
            "watch_id": watch_id, "recorded_at": row["created_at"],
        }
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(500, "Could not parse ECG data")


@app.get("/api/v2/watch/{watch_id}/spo2/latest")
def get_watch_latest_spo2(watch_id: str):
    rows = db.get_watch_sensor_data(watch_id, "spo2", 1)
    if not rows:
        raise HTTPException(404, "No SpO2 data")
    data = json.loads(rows[0]["data_json"])
    return {"spo2_percent": data.get("spO2Percent", 0), "status": data.get("status", 0),
            "watch_id": watch_id, "recorded_at": rows[0]["created_at"]}


@app.get("/api/v2/watch/{watch_id}/bia/latest")
def get_watch_latest_bia(watch_id: str):
    rows = db.get_watch_sensor_data(watch_id, "bia", 1)
    if not rows:
        raise HTTPException(404, "No BIA data")
    data = json.loads(rows[0]["data_json"])
    return {"body_fat_percent": data.get("bodyFatPercent", 0),
            "skeletal_muscle_percent": data.get("skeletalMusclePercent", 0),
            "basal_metabolic_rate": data.get("basalMetabolicRate", 0),
            "watch_id": watch_id, "recorded_at": rows[0]["created_at"]}


@app.get("/api/v2/watch/{watch_id}/skin-temp/latest")
def get_watch_latest_skin_temp(watch_id: str):
    rows = db.get_watch_sensor_data(watch_id, "skin_temp", 1)
    if not rows:
        raise HTTPException(404, "No skin temperature data")
    data = json.loads(rows[0]["data_json"])
    return {"temperature_celsius": data.get("temperatureCelsius", 0),
            "ambient_celsius": data.get("ambientTemperatureCelsius", 0),
            "watch_id": watch_id, "recorded_at": rows[0]["created_at"]}


# ═══════════════════════════════════════════════════════════════════════
# ECG Arrhythmia Classification
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/v2/watch/{watch_id}/ecg/{record_id}/classify")
def classify_ecg_recording(watch_id: str, record_id: int, model: str = Query("1D-CNN")):
    """Run arrhythmia classification on a stored ECG recording."""
    from .ml_classifier import classify_ecg

    with db.get_db() as conn:
        row = db._fetchone(conn,
            "SELECT * FROM watch_sensor_data WHERE id = ? AND watch_id = ? AND sensor_type = 'ecg'",
            (record_id, watch_id))
    if not row:
        raise HTTPException(404, "ECG recording not found")

    data = json.loads(row["data_json"])
    samples = data.get("samplesMillivolts", [])
    sample_rate = data.get("sampleRateHz", 500)

    result = classify_ecg(samples, sample_rate, model)
    if "error" in result:
        raise HTTPException(400, result["error"])

    # Store classifications in DB
    for c in result["classifications"]:
        db.save_ecg_classification(
            ecg_record_id=record_id, watch_id=watch_id, model_name=model,
            beat_index=c["beat_index"], predicted_class=c["class"],
            confidence=c["confidence"], all_probabilities=c["probabilities"])

    return result


@app.get("/api/v2/watch/{watch_id}/ecg/{record_id}/classifications")
def get_ecg_classifications(watch_id: str, record_id: int):
    """Get stored classification results for an ECG recording."""
    results = db.get_ecg_classifications(record_id)
    if not results:
        raise HTTPException(404, "No classifications found. Run POST .../classify first.")
    return results


@app.get("/api/v2/models")
def list_available_models():
    """List available ML models for ECG classification."""
    from .ml_classifier import _load_models, _models, CLASS_NAMES, CLASS_DESCRIPTIONS
    _load_models()
    return {
        "available_models": list(_models.keys()),
        "classes": CLASS_DESCRIPTIONS,
        "class_order": CLASS_NAMES,
    }


# ═══════════════════════════════════════════════════════════════════════
# Data Export (CSV)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/v1/devices/{device_id}/export/csv")
def export_device_csv(device_id: str):
    """Export all health data for a device as CSV."""
    data = db.get_all_data_for_device(device_id)
    output = io.StringIO()
    writer = csv.writer(output)

    # Heart Rate
    writer.writerow(["--- Heart Rate ---"])
    writer.writerow(["id", "start_time", "end_time", "avg_bpm", "samples_count"])
    for r in data["heart_rate"]:
        samples = json.loads(r.get("samples", "[]")) if isinstance(r.get("samples"), str) else r.get("samples", [])
        avg_bpm = sum(s.get("bpm", s) if isinstance(s, dict) else s for s in samples) / max(len(samples), 1) if samples else 0
        writer.writerow([r["id"], r["start_time"], r["end_time"], round(avg_bpm, 1), len(samples)])

    writer.writerow([])
    writer.writerow(["--- Steps ---"])
    writer.writerow(["id", "start_time", "end_time", "count"])
    for r in data["steps"]:
        writer.writerow([r["id"], r["start_time"], r["end_time"], r["count"]])

    writer.writerow([])
    writer.writerow(["--- Sleep Sessions ---"])
    writer.writerow(["id", "start_time", "end_time", "stages_count"])
    for r in data["sleep"]:
        stages = json.loads(r.get("stages", "[]")) if isinstance(r.get("stages"), str) else r.get("stages", [])
        writer.writerow([r["id"], r["start_time"], r["end_time"], len(stages)])

    writer.writerow([])
    writer.writerow(["--- Exercise Sessions ---"])
    writer.writerow(["id", "start_time", "end_time", "exercise_type"])
    for r in data["exercise"]:
        writer.writerow([r["id"], r["start_time"], r["end_time"], r["exercise_type"]])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=health_data_{device_id}.csv"})


@app.get("/api/v2/watch/{watch_id}/export/csv")
def export_watch_csv(watch_id: str, sensor_type: str = None):
    """Export watch sensor data as CSV."""
    if sensor_type:
        rows = db.get_watch_sensor_data(watch_id, sensor_type, limit=10000)
    else:
        rows = db.get_watch_sensor_data(watch_id, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "sensor_type", "created_at", "data_json"])
    for r in rows:
        writer.writerow([r["id"], r["sensor_type"], r["created_at"], r["data_json"]])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=watch_{watch_id}_{sensor_type or 'all'}.csv"})


@app.get("/api/v2/watch/{watch_id}/ecg/{record_id}/export/csv")
def export_ecg_csv(watch_id: str, record_id: int):
    """Export a single ECG recording as CSV with millivolt samples."""
    with db.get_db() as conn:
        row = db._fetchone(conn,
            "SELECT * FROM watch_sensor_data WHERE id = ? AND watch_id = ? AND sensor_type = 'ecg'",
            (record_id, watch_id))
    if not row:
        raise HTTPException(404, "ECG recording not found")

    data = json.loads(row["data_json"])
    samples = data.get("samplesMillivolts", [])
    sample_rate = data.get("sampleRateHz", 500)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["sample_index", "time_seconds", "millivolts"])
    for i, mv in enumerate(samples):
        writer.writerow([i, round(i / sample_rate, 4), mv])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ecg_{record_id}.csv"})


# ═══════════════════════════════════════════════════════════════════════
# Health Report PDF
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/v2/watch/{watch_id}/report")
def generate_health_report(watch_id: str):
    """Generate a comprehensive health report as HTML (printable as PDF)."""
    summary = db.get_watch_summary(watch_id)

    # Gather latest data for each sensor
    hr_data = db.get_watch_sensor_data(watch_id, "heart_rate", 10)
    ecg_data = db.get_ecg_history(watch_id, 5)
    spo2_data = db.get_watch_sensor_data(watch_id, "spo2", 5)
    bia_data = db.get_watch_sensor_data(watch_id, "bia", 1)
    temp_data = db.get_watch_sensor_data(watch_id, "skin_temp", 5)

    # Parse HR values
    hr_values = []
    for r in hr_data:
        try:
            d = json.loads(r["data_json"])
            for s in d.get("samples", []):
                hr_values.append(s.get("bpm", 0))
        except (json.JSONDecodeError, KeyError):
            pass

    avg_hr = round(sum(hr_values) / len(hr_values), 1) if hr_values else "N/A"
    min_hr = min(hr_values) if hr_values else "N/A"
    max_hr = max(hr_values) if hr_values else "N/A"

    # Parse SpO2
    spo2_values = []
    for r in spo2_data:
        try:
            d = json.loads(r["data_json"])
            spo2_values.append(d.get("spO2Percent", 0))
        except (json.JSONDecodeError, KeyError):
            pass
    avg_spo2 = round(sum(spo2_values) / len(spo2_values), 1) if spo2_values else "N/A"

    # Parse BIA
    bia_info = {}
    if bia_data:
        try:
            bia_info = json.loads(bia_data[0]["data_json"])
        except (json.JSONDecodeError, KeyError):
            pass

    # Parse Skin Temp
    temp_values = []
    for r in temp_data:
        try:
            d = json.loads(r["data_json"])
            temp_values.append(d.get("temperatureCelsius", 0))
        except (json.JSONDecodeError, KeyError):
            pass
    avg_temp = round(sum(temp_values) / len(temp_values), 1) if temp_values else "N/A"

    # ECG classifications
    ecg_class_html = ""
    for ecg in ecg_data[:3]:
        classes = db.get_ecg_classifications(ecg["id"])
        if classes:
            normal_count = sum(1 for c in classes if c["predicted_class"] == "N")
            total = len(classes)
            ecg_class_html += f"""
            <div class="card">
                <h3>ECG #{ecg['id']} — {ecg['sample_count']} samples</h3>
                <p>Recorded: {ecg['recorded_at']}</p>
                <p>Beats classified: {total} | Normal: {normal_count} | Abnormal: {total - normal_count}</p>
                <div class="bar"><div class="bar-fill" style="width:{normal_count/max(total,1)*100:.0f}%"></div></div>
            </div>"""
        else:
            ecg_class_html += f"""
            <div class="card">
                <h3>ECG #{ecg['id']} — {ecg['sample_count']} samples</h3>
                <p>Recorded: {ecg['recorded_at']}</p>
                <p style="color:#FF9F0A">Not yet classified — POST /api/v2/watch/{watch_id}/ecg/{ecg['id']}/classify</p>
            </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Health Report — {watch_id}</title>
<style>
    @media print {{ body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #000; color: #fff; padding: 40px; }}
    h1 {{ font-size: 32px; margin-bottom: 4px; }}
    h2 {{ font-size: 22px; color: #86868b; margin: 30px 0 15px; }}
    .subtitle {{ color: #86868b; font-size: 14px; margin-bottom: 30px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }}
    .card {{ background: #1C1C1E; border-radius: 16px; padding: 20px; }}
    .card h3 {{ font-size: 14px; color: #86868b; margin-bottom: 8px; }}
    .big {{ font-size: 42px; font-weight: 700; }}
    .unit {{ font-size: 16px; color: #86868b; }}
    .red {{ color: #FF453A; }} .blue {{ color: #0A84FF; }} .green {{ color: #30D158; }}
    .purple {{ color: #BF5AF2; }} .orange {{ color: #FF9F0A; }} .cyan {{ color: #64D2FF; }}
    .bar {{ background: #2C2C2E; border-radius: 4px; height: 8px; margin-top: 8px; }}
    .bar-fill {{ background: #30D158; border-radius: 4px; height: 100%; }}
    .footer {{ margin-top: 40px; color: #48484a; font-size: 12px; text-align: center; }}
</style></head><body>
    <h1>Health Report</h1>
    <p class="subtitle">Watch: {watch_id} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Total records: {summary['total_records']}</p>

    <h2>Vital Signs</h2>
    <div class="grid">
        <div class="card">
            <h3>Heart Rate</h3>
            <div class="big red">{avg_hr} <span class="unit">bpm</span></div>
            <p style="color:#86868b;margin-top:8px">Range: {min_hr}–{max_hr} bpm</p>
        </div>
        <div class="card">
            <h3>Blood Oxygen (SpO2)</h3>
            <div class="big blue">{avg_spo2}<span class="unit">%</span></div>
        </div>
        <div class="card">
            <h3>Skin Temperature</h3>
            <div class="big orange">{avg_temp}<span class="unit">&deg;C</span></div>
        </div>
    </div>

    <h2>Body Composition (BIA)</h2>
    <div class="grid">
        <div class="card">
            <h3>Body Fat</h3>
            <div class="big purple">{bia_info.get('bodyFatPercent', 'N/A')}<span class="unit">%</span></div>
        </div>
        <div class="card">
            <h3>Skeletal Muscle</h3>
            <div class="big green">{bia_info.get('skeletalMusclePercent', 'N/A')}<span class="unit">%</span></div>
        </div>
        <div class="card">
            <h3>BMR</h3>
            <div class="big cyan">{bia_info.get('basalMetabolicRate', 'N/A')}<span class="unit">kcal</span></div>
        </div>
    </div>

    <h2>ECG Recordings ({len(ecg_data)} total)</h2>
    {ecg_class_html if ecg_class_html else '<div class="card"><p>No ECG recordings yet</p></div>'}

    <h2>Data Summary</h2>
    <div class="grid">
        {''.join(f'<div class="card"><h3>{s["sensor_type"]}</h3><div class="big cyan">{s["count"]}</div><p style="color:#86868b">Last: {s["last_seen"]}</p></div>' for s in summary.get('sensors', []))}
    </div>

    <p class="footer">Health Connect Ecosystem — Galaxy Watch 5 → Android Phone → FastAPI Backend</p>
</body></html>"""

    return HTMLResponse(content=html)


# ═══════════════════════════════════════════════════════════════════════
# Web Dashboard
# ═══════════════════════════════════════════════════════════════════════

@app.get("/dashboard", response_class=HTMLResponse)
def web_dashboard():
    """Real-time web dashboard for health data visualization."""
    return HTMLResponse(content=_DASHBOARD_HTML)


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Health Connect Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #000; color: #fff; min-height: 100vh; }
    .header { padding: 30px 40px 20px; }
    .header h1 { font-size: 34px; font-weight: 700; }
    .header p { color: #86868b; margin-top: 4px; }
    .status { display: inline-flex; align-items: center; gap: 6px; background: #1C1C1E;
              padding: 6px 14px; border-radius: 20px; font-size: 13px; margin-top: 10px; }
    .status .dot { width: 8px; height: 8px; border-radius: 50%; background: #30D158; }
    .container { padding: 0 40px 40px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card { background: #1C1C1E; border-radius: 16px; padding: 20px; transition: transform 0.2s; }
    .card:hover { transform: translateY(-2px); }
    .card-label { font-size: 13px; color: #86868b; text-transform: uppercase; letter-spacing: 0.5px; }
    .card-value { font-size: 44px; font-weight: 700; margin: 8px 0 4px; }
    .card-sub { font-size: 13px; color: #636366; }
    .chart-card { background: #1C1C1E; border-radius: 16px; padding: 24px; margin-bottom: 16px; }
    .chart-card h3 { font-size: 17px; margin-bottom: 16px; }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .red { color: #FF453A; } .blue { color: #0A84FF; } .green { color: #30D158; }
    .purple { color: #BF5AF2; } .orange { color: #FF9F0A; } .cyan { color: #64D2FF; }
    .btn { display: inline-block; padding: 10px 20px; border-radius: 10px; border: none;
           color: #fff; font-size: 14px; cursor: pointer; text-decoration: none; margin: 4px; }
    .btn-blue { background: #0A84FF; } .btn-green { background: #30D158; color: #000; }
    .btn-purple { background: #BF5AF2; } .btn-red { background: #FF453A; }
    .ecg-list { margin-top: 12px; }
    .ecg-item { background: #2C2C2E; border-radius: 10px; padding: 14px; margin-bottom: 8px;
                display: flex; justify-content: space-between; align-items: center; }
    .ecg-item .info { font-size: 14px; }
    .ecg-item .info span { color: #86868b; font-size: 12px; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    .badge-normal { background: #0b3d1a; color: #30D158; }
    .badge-abnormal { background: #3d0b0b; color: #FF453A; }
    .badge-pending { background: #2C2C2E; color: #86868b; }
    #ecgCanvas { width: 100%; height: 200px; }
    .actions { padding: 20px 40px; }
    @media (max-width: 768px) {
        .header, .container, .actions { padding-left: 20px; padding-right: 20px; }
        .two-col { grid-template-columns: 1fr; }
        .card-value { font-size: 36px; }
    }
</style>
</head><body>
<div class="header">
    <h1>Health Connect</h1>
    <p>Real-time health data dashboard</p>
    <div class="status"><span class="dot"></span> <span id="dbType">Loading...</span></div>
</div>

<div class="container">
    <!-- Vital Signs Cards -->
    <div class="grid" id="vitals">
        <div class="card"><div class="card-label">Heart Rate</div>
            <div class="card-value red" id="hrValue">--</div>
            <div class="card-sub" id="hrSub">Loading...</div></div>
        <div class="card"><div class="card-label">SpO2</div>
            <div class="card-value blue" id="spo2Value">--</div>
            <div class="card-sub" id="spo2Sub">Loading...</div></div>
        <div class="card"><div class="card-label">Skin Temp</div>
            <div class="card-value orange" id="tempValue">--</div>
            <div class="card-sub" id="tempSub">Loading...</div></div>
        <div class="card"><div class="card-label">Total Records</div>
            <div class="card-value green" id="totalRecords">--</div>
            <div class="card-sub" id="sensorCount">Loading...</div></div>
    </div>

    <!-- ECG Waveform -->
    <div class="chart-card">
        <h3><span class="red">ECG Waveform</span> — Latest Recording</h3>
        <canvas id="ecgChart" height="200"></canvas>
        <div id="ecgInfo" class="card-sub" style="margin-top:8px"></div>
    </div>

    <!-- Heart Rate History -->
    <div class="two-col">
        <div class="chart-card">
            <h3><span class="red">Heart Rate</span> History</h3>
            <canvas id="hrChart" height="200"></canvas>
        </div>
        <div class="chart-card">
            <h3><span class="cyan">Sensor Data</span> Distribution</h3>
            <canvas id="sensorChart" height="200"></canvas>
        </div>
    </div>

    <!-- ECG Recordings List -->
    <div class="chart-card">
        <h3><span class="purple">ECG Recordings</span></h3>
        <div class="ecg-list" id="ecgList"><p class="card-sub">Loading...</p></div>
    </div>

    <!-- Export Actions -->
    <div style="margin-top:16px">
        <h3 style="margin-bottom:12px">Export & Analysis</h3>
        <a class="btn btn-blue" id="btnReport" href="#">View Health Report</a>
        <a class="btn btn-green" id="btnExportCSV" href="#">Export CSV</a>
        <button class="btn btn-purple" id="btnClassifyAll" onclick="classifyAllEcg()">Classify All ECG</button>
    </div>
</div>

<script>
const API = window.location.origin;
let currentWatchId = null;

async function fetchJSON(url) {
    try { const r = await fetch(url); return r.ok ? await r.json() : null; }
    catch(e) { return null; }
}

async function loadDashboard() {
    // Get watches
    const watches = await fetchJSON(API + '/api/v2/watches');
    if (!watches || watches.length === 0) {
        document.getElementById('dbType').textContent = 'No watches connected';
        return;
    }
    currentWatchId = watches[0].watch_id;
    document.getElementById('dbType').textContent =
        'Watch: ' + currentWatchId + ' | ' + watches[0].total_records + ' records';

    // Update export links
    document.getElementById('btnReport').href = API + '/api/v2/watch/' + currentWatchId + '/report';
    document.getElementById('btnExportCSV').href = API + '/api/v2/watch/' + currentWatchId + '/export/csv';

    // Load summary
    const summary = await fetchJSON(API + '/api/v2/watch/' + currentWatchId + '/summary');
    if (summary) {
        document.getElementById('totalRecords').textContent = summary.total_records;
        document.getElementById('sensorCount').textContent = summary.sensors.length + ' sensor types';
        loadSensorChart(summary.sensors);
    }

    // Load vitals
    loadHR(); loadSpO2(); loadTemp(); loadECG(); loadECGHistory();
}

async function loadHR() {
    const hr = await fetchJSON(API + '/api/v2/watch/' + currentWatchId + '/heart-rate/latest');
    if (hr) {
        document.getElementById('hrValue').textContent = hr.bpm + ' bpm';
        document.getElementById('hrSub').textContent = 'Latest reading';
    }
    // HR history chart
    const hrData = await fetchJSON(API + '/api/v2/watch/' + currentWatchId + '/data?sensor_type=heart_rate&limit=20');
    if (hrData && hrData.length > 0) {
        const bpms = []; const labels = [];
        hrData.reverse().forEach((r, i) => {
            try {
                const d = JSON.parse(r.data_json);
                (d.samples || []).forEach(s => { bpms.push(s.bpm); labels.push(''); });
            } catch(e) {}
        });
        if (bpms.length > 0) loadHRChart(labels.slice(-50), bpms.slice(-50));
    }
}

async function loadSpO2() {
    const d = await fetchJSON(API + '/api/v2/watch/' + currentWatchId + '/spo2/latest');
    if (d) {
        document.getElementById('spo2Value').textContent = d.spo2_percent + '%';
        document.getElementById('spo2Sub').textContent = d.recorded_at || '';
    } else {
        document.getElementById('spo2Value').textContent = 'N/A';
        document.getElementById('spo2Sub').textContent = 'No data';
    }
}

async function loadTemp() {
    const d = await fetchJSON(API + '/api/v2/watch/' + currentWatchId + '/skin-temp/latest');
    if (d) {
        document.getElementById('tempValue').textContent = d.temperature_celsius + '°C';
        document.getElementById('tempSub').textContent = d.recorded_at || '';
    } else {
        document.getElementById('tempValue').textContent = 'N/A';
        document.getElementById('tempSub').textContent = 'No data';
    }
}

async function loadECG() {
    const d = await fetchJSON(API + '/api/v2/watch/' + currentWatchId + '/ecg/latest');
    if (d && d.samples_millivolts) {
        const samples = d.samples_millivolts;
        const step = Math.max(1, Math.floor(samples.length / 1000));
        const downsampled = samples.filter((_, i) => i % step === 0);
        const labels = downsampled.map((_, i) => (i * step / d.sample_rate_hz).toFixed(2));

        new Chart(document.getElementById('ecgChart'), {
            type: 'line',
            data: { labels, datasets: [{ data: downsampled, borderColor: '#FF453A',
                    borderWidth: 1, pointRadius: 0, tension: 0.1 }] },
            options: { responsive: true, plugins: { legend: { display: false } },
                scales: { x: { display: true, ticks: { color: '#636366', maxTicksLimit: 10 },
                          title: { display: true, text: 'Time (s)', color: '#86868b' } },
                         y: { ticks: { color: '#636366' }, title: { display: true, text: 'mV', color: '#86868b' },
                              grid: { color: '#2C2C2E' } } } }
        });
        document.getElementById('ecgInfo').textContent =
            samples.length + ' samples | ' + d.sample_rate_hz + ' Hz | ' +
            (samples.length / d.sample_rate_hz).toFixed(1) + 's duration';
    }
}

async function loadECGHistory() {
    const ecgs = await fetchJSON(API + '/api/v2/watch/' + currentWatchId + '/ecg/history');
    const el = document.getElementById('ecgList');
    if (!ecgs || ecgs.length === 0) { el.innerHTML = '<p class="card-sub">No ECG recordings</p>'; return; }
    el.innerHTML = ecgs.map(e => {
        const dur = (e.sample_count / e.sample_rate_hz).toFixed(1);
        return '<div class="ecg-item"><div class="info">ECG #' + e.id +
            ' <span>| ' + e.sample_count + ' samples | ' + dur + 's | ' + e.recorded_at + '</span></div>' +
            '<div><button class="btn btn-purple" style="padding:6px 12px;font-size:12px" ' +
            'onclick="classifyEcg(' + e.id + ', this)">Classify</button></div></div>';
    }).join('');
}

function loadHRChart(labels, data) {
    new Chart(document.getElementById('hrChart'), {
        type: 'line',
        data: { labels, datasets: [{ data, borderColor: '#FF453A', backgroundColor: 'rgba(255,69,58,0.1)',
                fill: true, borderWidth: 2, pointRadius: 0, tension: 0.3 }] },
        options: { responsive: true, plugins: { legend: { display: false } },
            scales: { x: { display: false }, y: { ticks: { color: '#636366' },
                      grid: { color: '#2C2C2E' }, title: { display: true, text: 'BPM', color: '#86868b' } } } }
    });
}

function loadSensorChart(sensors) {
    const colors = ['#FF453A','#0A84FF','#30D158','#BF5AF2','#FF9F0A','#64D2FF','#FFD60A','#AC8E68'];
    new Chart(document.getElementById('sensorChart'), {
        type: 'doughnut',
        data: { labels: sensors.map(s => s.sensor_type),
                datasets: [{ data: sensors.map(s => s.count), backgroundColor: colors.slice(0, sensors.length),
                             borderWidth: 0 }] },
        options: { responsive: true, plugins: { legend: { position: 'right',
                   labels: { color: '#fff', padding: 12, font: { size: 12 } } } } }
    });
}

async function classifyEcg(recordId, btn) {
    btn.textContent = 'Classifying...'; btn.disabled = true;
    const r = await fetch(API + '/api/v2/watch/' + currentWatchId + '/ecg/' + recordId + '/classify', { method: 'POST' });
    if (r.ok) {
        const result = await r.json();
        btn.textContent = result.overall_status;
        btn.style.background = result.abnormal_count > 0 ? '#FF453A' : '#30D158';
        btn.style.color = result.abnormal_count > 0 ? '#fff' : '#000';
    } else {
        btn.textContent = 'Error'; btn.style.background = '#FF9F0A';
    }
}

async function classifyAllEcg() {
    const btn = document.getElementById('btnClassifyAll');
    btn.textContent = 'Classifying all...'; btn.disabled = true;
    const ecgs = await fetchJSON(API + '/api/v2/watch/' + currentWatchId + '/ecg/history');
    for (const e of (ecgs || [])) {
        await fetch(API + '/api/v2/watch/' + currentWatchId + '/ecg/' + e.id + '/classify', { method: 'POST' });
    }
    btn.textContent = 'Done!'; btn.disabled = false;
    loadECGHistory();
}

loadDashboard();
setInterval(loadDashboard, 30000); // Refresh every 30s
</script>
</body></html>"""
