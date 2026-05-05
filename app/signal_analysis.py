"""Heuristic signal-processing helpers for activity classification and sleep
restlessness.

These are NOT trained ML models — they're well-known signal-processing rules
(FFT cadence detection, movement-threshold restlessness) that classical step
counters and sleep trackers used before deep learning. They run in
microseconds, ship zero model files, and produce useful labels today. Upgrade
path: swap each function for a trained model once we have labeled data.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Optional

import numpy as np
from scipy.signal import welch

logger = logging.getLogger("health-api.signal")

# Each accel batch from the watch is ~125 samples at ~25 Hz → ~5 seconds.
ACCEL_BATCH_SECONDS = 5
ASSUMED_FS_HZ = 25


# ─────────────────────────────────────────────────────────────────────
# Activity classification
# ─────────────────────────────────────────────────────────────────────

def classify_activity_batch(samples: list) -> str:
    """Classify a single accel batch into a coarse activity label.

    Returns one of: ``still``, ``walking``, ``running``, ``active``.
    Logic:
      1. If the magnitude std-dev is below a quiet threshold → still.
      2. Otherwise look at the 1–5 Hz dominant frequency (human cadence range):
         1.4–2.5 Hz → walking (90–150 steps/min)
         2.4–4.5 Hz → running (150–270 steps/min)
      3. High variance with no clear cadence → "active" (cycling, gym, etc.).
    """
    if not samples or len(samples) < 10:
        return "still"

    mags = []
    for s in samples:
        try:
            x = float(s.get("x", 0) or 0)
            y = float(s.get("y", 0) or 0)
            z = float(s.get("z", 0) or 0)
        except (TypeError, ValueError):
            continue
        mags.append(math.sqrt(x * x + y * y + z * z))

    if len(mags) < 10:
        return "still"

    mean = sum(mags) / len(mags)
    detrended = [m - mean for m in mags]
    var = sum(d * d for d in detrended) / len(detrended)
    sd = math.sqrt(var)

    if sd < 0.5:
        return "still"

    # Dominant frequency in the human-cadence band via Welch's method.
    peak_freq = 0.0
    try:
        arr = np.asarray(detrended, dtype=np.float64)
        nperseg = min(64, len(arr))
        if nperseg >= 16:
            f, pxx = welch(arr, fs=ASSUMED_FS_HZ, nperseg=nperseg)
            mask = (f >= 1.0) & (f <= 5.0)
            if mask.any():
                peak_freq = float(f[mask][int(np.argmax(pxx[mask]))])
    except Exception as e:
        logger.debug("Welch failed, falling back: %s", e)

    if 2.4 <= peak_freq <= 4.5 and sd >= 2.0:
        return "running"
    if 1.4 <= peak_freq <= 2.6:
        return "walking"
    if sd >= 2.0:
        return "active"
    # Slow / mild movement that didn't match any cadence band.
    return "walking"


def aggregate_activity(accel_rows: list) -> Optional[dict]:
    """Sum per-batch labels across a day's accelerometer rows.

    Returns minutes in each label bucket, or None if no rows.
    """
    if not accel_rows:
        return None

    counts = {"still": 0, "walking": 0, "running": 0, "active": 0}
    for r in accel_rows:
        try:
            payload = json.loads(r["data_json"])
            samples = payload.get("samples", [])
            label = classify_activity_batch(samples)
            counts[label] += 1
        except (json.JSONDecodeError, TypeError, KeyError):
            continue

    return {k: round(v * ACCEL_BATCH_SECONDS / 60) for k, v in counts.items()}


# ─────────────────────────────────────────────────────────────────────
# Sleep restlessness
# ─────────────────────────────────────────────────────────────────────

def analyze_sleep_restlessness(accel_rows: list) -> Optional[dict]:
    """Estimate sleep restlessness from accelerometer batches in a sleep window.

    For each batch we look at magnitude std-dev:
      - sd > 1.0 (m/s² or g, unit-relative)  → restless
      - sd ≤ 1.0                              → quiet

    Returns minutes per bucket plus a 0–100 quality score (% time quiet).
    Caller is responsible for passing rows that fall within an actual sleep
    window — this function makes no judgement about wakefulness vs sleep.
    """
    if not accel_rows:
        return None

    restless = 0
    quiet = 0

    for r in accel_rows:
        try:
            payload = json.loads(r["data_json"])
            samples = payload.get("samples", [])
            if len(samples) < 10:
                continue
            mags = []
            for s in samples:
                try:
                    x = float(s.get("x", 0) or 0)
                    y = float(s.get("y", 0) or 0)
                    z = float(s.get("z", 0) or 0)
                except (TypeError, ValueError):
                    continue
                mags.append(math.sqrt(x * x + y * y + z * z))
            if len(mags) < 10:
                continue
            mean = sum(mags) / len(mags)
            sd = math.sqrt(sum((m - mean) ** 2 for m in mags) / len(mags))
            if sd > 1.0:
                restless += 1
            else:
                quiet += 1
        except (json.JSONDecodeError, TypeError, KeyError):
            continue

    total = restless + quiet
    if total == 0:
        return None

    restless_min = round(restless * ACCEL_BATCH_SECONDS / 60)
    quiet_min = round(quiet * ACCEL_BATCH_SECONDS / 60)
    quality = round(quiet / total * 100)

    return {
        "total_minutes": restless_min + quiet_min,
        "restless_minutes": restless_min,
        "quiet_minutes": quiet_min,
        "quality_score": quality,
        "method": "accel_movement_threshold",
    }
