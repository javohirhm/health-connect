"""Activity classification + sleep restlessness.

When a trained Random Forest model file is present (training/train_activity.py
produces it from UCI HAR), we use it for the primary still/walking decision
and overlay cadence rules to subdivide walking into running/active. When the
model file is absent, we fall back to FFT-cadence-only heuristics so the
runtime keeps working with no model files at all.

Sleep restlessness reuses classify_activity_batch — anything classified
"still" is quiet, anything else is restless within the sleep window.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.signal import welch

from .config import config

logger = logging.getLogger("health-api.signal")

# Each accel batch from the watch is ~125 samples at ~25 Hz → ~5 seconds.
ACCEL_BATCH_SECONDS = 5
ASSUMED_FS_HZ = 25


# ─────────────────────────────────────────────────────────────────────
# Trained model loader (Random Forest from UCI HAR)
# ─────────────────────────────────────────────────────────────────────

_activity_bundle: dict | None = None
_activity_load_attempted = False


def _load_activity_model() -> dict | None:
    """Load training/train_activity.py output. Cached after first call."""
    global _activity_bundle, _activity_load_attempted
    if _activity_load_attempted:
        return _activity_bundle
    _activity_load_attempted = True
    try:
        import joblib
        path = Path(config.MODELS_DIR) / "activity_classifier.pkl"
        if path.exists():
            _activity_bundle = joblib.load(str(path))
            logger.info("Loaded trained activity model from %s", path)
        else:
            logger.info("No trained activity model at %s — using heuristic", path)
    except Exception as e:
        logger.warning("Failed to load trained activity model: %s", e)
    return _activity_bundle


def _activity_features(samples: list) -> np.ndarray | None:
    """Compute the 22-feature vector that train_activity.py produces.

    Order MUST match training/train_activity.py's RUNTIME_FEATURE_INDICES_NAMES.
    """
    xs, ys, zs = [], [], []
    for s in samples:
        try:
            xs.append(float(s.get("x", 0) or 0))
            ys.append(float(s.get("y", 0) or 0))
            zs.append(float(s.get("z", 0) or 0))
        except (TypeError, ValueError):
            continue
    if len(xs) < 10:
        return None
    x = np.asarray(xs, dtype=np.float32)
    y = np.asarray(ys, dtype=np.float32)
    z = np.asarray(zs, dtype=np.float32)
    mag = np.sqrt(x * x + y * y + z * z)

    def mad(v: np.ndarray) -> float:
        return float(np.median(np.abs(v - np.median(v))))

    feats = [
        float(np.mean(x)), float(np.mean(y)), float(np.mean(z)),
        float(np.std(x)), float(np.std(y)), float(np.std(z)),
        mad(x), mad(y), mad(z),
        float(np.max(x)), float(np.max(y)), float(np.max(z)),
        float(np.min(x)), float(np.min(y)), float(np.min(z)),
        float(np.mean(mag)), float(np.std(mag)), mad(mag),
        float(np.max(mag)), float(np.min(mag)),
        float(np.mean(mag * mag)),                         # energy
        float(np.percentile(mag, 75) - np.percentile(mag, 25)),  # iqr
    ]
    return np.asarray(feats, dtype=np.float32).reshape(1, -1)


# ─────────────────────────────────────────────────────────────────────
# Activity classification
# ─────────────────────────────────────────────────────────────────────

def _peak_cadence_freq(samples: list) -> tuple[float, float]:
    """Helper: returns (peak_freq_hz, magnitude_std_dev)."""
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
        return 0.0, 0.0
    mean = sum(mags) / len(mags)
    detrended = [m - mean for m in mags]
    var = sum(d * d for d in detrended) / len(detrended)
    sd = math.sqrt(var)
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
        logger.debug("Welch failed: %s", e)
    return peak_freq, sd


def classify_activity_batch(samples: list) -> str:
    """Classify a single accel batch into ``still``, ``walking``, ``running``, ``active``.

    Strategy:
      1. If a trained Random Forest model is on disk, run it first — it gives
         the still vs walking decision with much better precision than std-dev
         thresholds. Then we overlay cadence rules: if the model says
         "walking" but the cadence is in the running band (2.4-4.5 Hz) and
         the magnitude variance is high, we promote to "running".
         Cadence-less high-variance motion gets promoted to "active".
      2. If no trained model is loaded, fall back to FFT-cadence-only rules.
    """
    if not samples or len(samples) < 10:
        return "still"

    bundle = _load_activity_model()
    peak_freq, sd = _peak_cadence_freq(samples)

    if bundle is not None:
        feats = _activity_features(samples)
        if feats is not None:
            try:
                scaler = bundle.get("scaler")
                X = scaler.transform(feats) if scaler is not None else feats
                pred = str(bundle["model"].predict(X)[0])
                # `pred` is "still" or "walking" (UCI HAR has no running)
                if pred == "still":
                    return "still"
                # Model says walking — check cadence for running/active overlay
                if 2.4 <= peak_freq <= 4.5 and sd >= 2.0:
                    return "running"
                if 1.4 <= peak_freq <= 2.6:
                    return "walking"
                if sd >= 2.0:
                    return "active"
                return "walking"
            except Exception as e:
                logger.warning("Trained activity inference failed, falling back: %s", e)

    # ── Heuristic fallback (cadence + std-dev only) ─────────────────────
    if sd < 0.5:
        return "still"
    if 2.4 <= peak_freq <= 4.5 and sd >= 2.0:
        return "running"
    if 1.4 <= peak_freq <= 2.6:
        return "walking"
    if sd >= 2.0:
        return "active"
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
    """Estimate sleep restlessness by running classify_activity_batch on every
    accelerometer batch in the sleep window. Anything classified ``still``
    counts as quiet sleep; any other label (walking / running / active —
    these are unusual *during* sleep, so they map to brief wake / movement)
    counts as restless.

    Because classify_activity_batch transparently uses the trained Random
    Forest when available, this function inherits the ML-vs-heuristic choice
    automatically — when a trained activity model is loaded, sleep
    restlessness is also ML-driven.

    Caller is responsible for passing rows that fall within an actual sleep
    window — this function makes no wake/sleep judgement of its own.
    """
    if not accel_rows:
        return None

    using_trained = _load_activity_model() is not None
    restless = 0
    quiet = 0

    for r in accel_rows:
        try:
            payload = json.loads(r["data_json"])
            samples = payload.get("samples", [])
            if len(samples) < 10:
                continue
            label = classify_activity_batch(samples)
            if label == "still":
                quiet += 1
            else:
                restless += 1
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
        "method": "trained_random_forest" if using_trained else "accel_cadence_heuristic",
    }
