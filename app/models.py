"""Pydantic models for Health Connect data coming from the Android app."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Incoming payloads from the Android app ───────────────────────────

class HeartRateSample(BaseModel):
    bpm: int = Field(..., ge=1, le=300, description="Beats per minute")
    time: datetime


class HeartRateRecord(BaseModel):
    start_time: datetime
    end_time: datetime
    samples: list[HeartRateSample]


class StepsRecord(BaseModel):
    start_time: datetime
    end_time: datetime
    count: int = Field(..., ge=0)


class SleepStage(BaseModel):
    start_time: datetime
    end_time: datetime
    stage: int = Field(..., description="Sleep stage type code from Health Connect")


class SleepSessionRecord(BaseModel):
    start_time: datetime
    end_time: datetime
    stages: list[SleepStage] = []


class ExerciseSessionRecord(BaseModel):
    start_time: datetime
    end_time: datetime
    exercise_type: int = Field(..., description="Exercise type code from Health Connect")


class HealthDataPayload(BaseModel):
    """Top-level payload the Android app sends in a single POST."""
    device_id: str = Field(..., min_length=1, description="Unique device identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    heart_rate: list[HeartRateRecord] = []
    steps: list[StepsRecord] = []
    sleep_sessions: list[SleepSessionRecord] = []
    exercise_sessions: list[ExerciseSessionRecord] = []


# ── Response models ──────────────────────────────────────────────────

class SyncResponse(BaseModel):
    status: str = "ok"
    message: str = "Data received successfully"
    records_saved: int = 0


class DeviceSummary(BaseModel):
    device_id: str
    last_sync: Optional[datetime] = None
    total_heart_rate_records: int = 0
    total_steps_records: int = 0
    total_sleep_sessions: int = 0
    total_exercise_sessions: int = 0


class HealthSummary(BaseModel):
    device_id: str
    period: str
    total_steps: int = 0
    avg_heart_rate: Optional[float] = None
    sleep_sessions: int = 0
    exercise_sessions: int = 0


# ── Watch sensor payloads (raw data from Galaxy Watch) ───────────────

class WatchSensorPayload(BaseModel):
    """Payload forwarded by the phone from the watch via Wearable Data Layer."""
    model_config = {"populate_by_name": True}

    device_id: str = Field(..., alias="deviceId", description="Phone's ANDROID_ID")
    watch_id: str = Field(..., alias="watchId", description="Watch identifier")
    sensor_type: str = Field(..., alias="sensorType", description="e.g. heart_rate, ecg, ppg_green, accelerometer")
    data_json: str = Field(..., alias="dataJson", description="Raw JSON from the watch sensor tracker")


class WatchSyncResponse(BaseModel):
    success: bool = True
    message: str = "Watch data received"
    records_saved: int = 0
