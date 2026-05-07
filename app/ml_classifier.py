"""ECG arrhythmia classification using trained models from graduation project.

Models expect 360-sample beats (360Hz). Watch records at 500Hz, so we resample.
Pipeline: raw ECG -> bandpass filter -> R-peak detection -> beat segmentation -> classify
"""

import json
import logging
import numpy as np
from pathlib import Path
from scipy import signal as scipy_signal
from scipy.interpolate import interp1d
from .config import config

logger = logging.getLogger("health-api.ml")

import math

CLASS_NAMES = ["N", "S", "V", "F", "Q"]
CLASS_DESCRIPTIONS = {
    "N": "Normal",
    "S": "Supraventricular",
    "V": "Ventricular",
    "F": "Fusion",
    "Q": "Unknown/Paced",
}

# Lazy-loaded models
_models = {}
_scaler = None

WATCH_SAMPLE_RATE = 500  # Galaxy Watch ECG is 500Hz
MODEL_SAMPLE_RATE = 360  # MIT-BIH dataset was 360Hz
BEAT_WINDOW = 360        # Samples per beat for the model


def _load_models():
    """Lazy-load ML models on first use."""
    global _models, _scaler
    if _models:
        return

    models_dir = Path(config.MODELS_DIR)
    if not models_dir.exists():
        logger.warning("Models directory not found: %s", models_dir)
        return

    # 1D-CNN and CNN-LSTM keras models are intentionally NOT loaded:
    # SVM (98.24%) and XGBoost (98.18%) match their accuracy without
    # carrying TensorFlow's ~600 MB-per-worker memory footprint.

    # Load XGBoost
    xgb_path = models_dir / "XGBoost.pkl"
    if xgb_path.exists():
        try:
            import joblib
            _models["XGBoost"] = joblib.load(str(xgb_path))
            logger.info("Loaded XGBoost model")
        except Exception as e:
            logger.warning("Failed to load XGBoost: %s", e)

    # Load SVM
    svm_path = models_dir / "SVM_RBF.pkl"
    scaler_path = models_dir / "scaler.pkl"
    if svm_path.exists() and scaler_path.exists():
        try:
            import joblib
            _models["SVM"] = joblib.load(str(svm_path))
            _scaler = joblib.load(str(scaler_path))
            logger.info("Loaded SVM model + scaler")
        except Exception as e:
            logger.warning("Failed to load SVM: %s", e)

    logger.info("Loaded %d models: %s", len(_models), list(_models.keys()))


def _bandpass_filter(ecg_signal: np.ndarray, fs: int, lowcut: float = 0.5, highcut: float = 45.0) -> np.ndarray:
    """Apply bandpass filter to remove noise and baseline wander."""
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = min(highcut / nyq, 0.99)
    b, a = scipy_signal.butter(4, [low, high], btype="band")
    return scipy_signal.filtfilt(b, a, ecg_signal)


def _resample_signal(ecg_signal: np.ndarray, orig_fs: int, target_fs: int) -> np.ndarray:
    """Resample ECG from watch sample rate to model sample rate."""
    if orig_fs == target_fs:
        return ecg_signal
    duration = len(ecg_signal) / orig_fs
    num_samples_new = int(duration * target_fs)
    x_old = np.linspace(0, duration, len(ecg_signal))
    x_new = np.linspace(0, duration, num_samples_new)
    interpolator = interp1d(x_old, ecg_signal, kind="linear")
    return interpolator(x_new)


def _detect_r_peaks(ecg_signal: np.ndarray, fs: int) -> np.ndarray:
    """Simple R-peak detection using derivative + threshold."""
    # Differentiate
    diff = np.diff(ecg_signal)
    squared = diff ** 2

    # Moving average
    window_size = int(0.12 * fs)  # 120ms window
    if window_size < 1:
        window_size = 1
    ma = np.convolve(squared, np.ones(window_size) / window_size, mode="same")

    # Threshold at 40% of max
    threshold = 0.4 * np.max(ma)
    peaks = []
    refractory = int(0.2 * fs)  # 200ms refractory period

    i = 0
    while i < len(ma):
        if ma[i] > threshold:
            # Find local max within window
            window_end = min(i + int(0.1 * fs), len(ma))
            local_max_idx = i + np.argmax(ma[i:window_end])
            peaks.append(local_max_idx)
            i = local_max_idx + refractory
        else:
            i += 1

    return np.array(peaks, dtype=int)


def _segment_beats(ecg_signal: np.ndarray, r_peaks: np.ndarray, beat_size: int = 360) -> list[np.ndarray]:
    """Extract fixed-size beats centered on R-peaks."""
    half = beat_size // 2
    beats = []
    for peak in r_peaks:
        start = peak - half
        end = peak + half
        if start >= 0 and end <= len(ecg_signal):
            beat = ecg_signal[start:end]
            # Z-score normalize
            std = np.std(beat)
            if std > 0:
                beat = (beat - np.mean(beat)) / std
            beats.append(beat)
    return beats


def _extract_features(beat: np.ndarray) -> np.ndarray:
    """Extract 24 handcrafted features for classical ML models."""
    features = []
    # Statistical
    features.append(np.mean(beat))
    features.append(np.std(beat))
    features.append(np.max(beat))
    features.append(np.min(beat))
    features.append(np.ptp(beat))  # peak-to-peak
    features.append(float(np.mean(beat ** 2)))  # energy/RMS squared
    features.append(float(np.median(beat)))
    features.append(float(np.sqrt(np.mean(beat ** 2))))  # RMS

    # Zero-crossing rate
    zcr = np.sum(np.abs(np.diff(np.sign(beat)))) / (2 * len(beat))
    features.append(zcr)

    # Skewness and kurtosis
    from scipy.stats import skew, kurtosis
    features.append(float(skew(beat)))
    features.append(float(kurtosis(beat)))

    # Percentiles
    features.append(float(np.percentile(beat, 25)))
    features.append(float(np.percentile(beat, 75)))

    # Derivative features
    d1 = np.diff(beat)
    features.append(float(np.mean(d1)))
    features.append(float(np.std(d1)))
    features.append(float(np.max(np.abs(d1))))

    d2 = np.diff(d1)
    features.append(float(np.mean(d2)))
    features.append(float(np.std(d2)))
    features.append(float(np.max(np.abs(d2))))

    # FFT features (top 5 magnitudes)
    fft_vals = np.abs(np.fft.rfft(beat))
    fft_vals = fft_vals / (np.sum(fft_vals) + 1e-10)
    top5 = np.sort(fft_vals)[-5:][::-1]
    features.extend(top5.tolist())

    return np.array(features, dtype=np.float32)


# ─────────────────────────────────────────────────────────────────────
# AFib detection — heuristic screener over the day's IBI series.
# Method: RR-interval variability statistics, no learned model required.
# Documented thresholds (Tateno & Glass 2001, Lake & Moorman 2011).
# Treat as a SCREENER, not a diagnostic: flags irregular rhythm patterns
# consistent with AFib so the user knows to follow up with a clinician.
# ─────────────────────────────────────────────────────────────────────

# Lazy-loaded trained AFib model (set on first call)
_afib_bundle: dict | None = None
_afib_load_attempted = False


def _load_afib_model() -> dict | None:
    """Load the trained AFib classifier if present. Cached after first call."""
    global _afib_bundle, _afib_load_attempted
    if _afib_load_attempted:
        return _afib_bundle
    _afib_load_attempted = True
    try:
        import joblib
        path = Path(config.MODELS_DIR) / "afib_classifier.pkl"
        if path.exists():
            _afib_bundle = joblib.load(str(path))
            logger.info("Loaded trained AFib model from %s", path)
        else:
            logger.info("No trained AFib model at %s — using heuristic", path)
    except Exception as e:
        logger.warning("Failed to load trained AFib model: %s", e)
    return _afib_bundle


def _afib_features_from_ibis(rr: np.ndarray) -> np.ndarray | None:
    """Match the 12-feature vector emitted by training/train_afib.py."""
    rr = rr[(rr > 300) & (rr < 2000)]
    if rr.size < 10:
        return None
    mean_rr = float(np.mean(rr))
    sd_rr = float(np.std(rr))
    cv = sd_rr / mean_rr if mean_rr > 0 else 0.0
    diffs = np.abs(np.diff(rr))
    pnn50 = float(np.mean(diffs > 50)) * 100.0 if diffs.size else 0.0
    rmssd = float(np.sqrt(np.mean(diffs ** 2))) if diffs.size else 0.0
    bins = np.bincount((rr // 50).astype(int))
    p = bins[bins > 0] / rr.size
    entropy = float(-(p * np.log2(p)).sum())
    median_rr = float(np.median(rr))
    short_ratio = float(np.mean(rr < 0.85 * median_rr))
    long_ratio = float(np.mean(rr > 1.15 * median_rr))
    norm_sd = float(np.std(diffs / mean_rr)) if mean_rr > 0 else 0.0
    centered = rr - mean_rr
    skew = float(np.mean(centered ** 3) / (sd_rr ** 3 + 1e-9))
    kurt = float(np.mean(centered ** 4) / (sd_rr ** 4 + 1e-9))
    return np.array([
        mean_rr, sd_rr, cv, pnn50, rmssd, entropy,
        short_ratio, long_ratio, norm_sd, skew, kurt, float(rr.size),
    ], dtype=np.float32).reshape(1, -1)


def detect_afib(ibi_ms: list, beat_classes: list | None = None) -> dict:
    """AFib screen.

    Uses the trained XGBoost model (training/train_afib.py) when present,
    falls back to the documented Tateno & Glass heuristic otherwise. The
    response always includes a `method` field so the UI can tell which
    path produced the answer.
    """
    bundle = _load_afib_model()
    if bundle is not None:
        valid = [int(x) for x in ibi_ms if isinstance(x, (int, float)) and 300 < x < 2000]
        if len(valid) >= 30:
            feats = _afib_features_from_ibis(np.asarray(valid, dtype=np.float32))
            if feats is not None:
                try:
                    proba = bundle["model"].predict_proba(feats)[0]
                    afib_p = float(proba[1])
                    if afib_p > 0.7:
                        likelihood = "high"
                        notes = (
                            f"Model classifies this rhythm as atrial fibrillation "
                            f"(probability {afib_p:.0%}). Consider showing a clinician."
                        )
                    elif afib_p > 0.4:
                        likelihood = "moderate"
                        notes = (
                            f"Some AFib features detected (probability {afib_p:.0%}). "
                            "Worth monitoring."
                        )
                    else:
                        likelihood = "low"
                        notes = f"Rhythm classified as not-AFib (probability {afib_p:.0%})."
                    return {
                        "likelihood": likelihood,
                        "afib_probability": round(afib_p, 3),
                        "ibi_samples_used": len(valid),
                        "notes": notes,
                        "method": bundle.get("method_tag", "trained_xgboost"),
                    }
                except Exception as e:
                    logger.warning("Trained AFib inference failed, falling back: %s", e)

    # ── Heuristic fallback ─────────────────────────────────────────────
    valid = [int(x) for x in ibi_ms if isinstance(x, (int, float)) and 300 < x < 2000]
    n = len(valid)

    if n < 30:
        return {
            "likelihood": "insufficient_data",
            "ibi_samples_used": n,
            "notes": "Need at least 30 heartbeats with IBI data to screen for AFib.",
        }

    mean_rr = sum(valid) / n
    var = sum((x - mean_rr) ** 2 for x in valid) / n
    sd_rr = math.sqrt(var)
    cv = sd_rr / mean_rr if mean_rr > 0 else 0

    diffs = [abs(valid[i + 1] - valid[i]) for i in range(n - 1)]
    nn50 = sum(1 for d in diffs if d > 50)
    pnn50 = nn50 / len(diffs) * 100 if diffs else 0

    # Shannon entropy of RR distribution binned at 50 ms resolution.
    # AFib tends to have a flatter, more uniform RR distribution.
    bin_width = 50
    buckets: dict[int, int] = {}
    for x in valid:
        b = x // bin_width
        buckets[b] = buckets.get(b, 0) + 1
    entropy = 0.0
    for cnt in buckets.values():
        p = cnt / n
        if p > 0:
            entropy -= p * math.log2(p)

    # Bucket the likelihood. Thresholds chosen to be conservative — moderate
    # is common during exercise / stress / poor signal, high requires both
    # CV and pNN50 to be clearly elevated.
    high_irregularity = cv > 0.10 and pnn50 > 30
    moderate_irregularity = cv > 0.06 or pnn50 > 25 or entropy > 2.4

    if high_irregularity:
        likelihood = "high"
        notes = (
            f"RR intervals are markedly irregular (CV {cv * 100:.1f}%, "
            f"pNN50 {pnn50:.0f}%, entropy {entropy:.2f}). "
            "This pattern is consistent with atrial fibrillation. "
            "Consider showing this to a clinician — not a diagnosis."
        )
    elif moderate_irregularity:
        likelihood = "moderate"
        notes = (
            f"Some irregularity detected (CV {cv * 100:.1f}%, "
            f"pNN50 {pnn50:.0f}%). Could be normal variation, exercise, or "
            "early arrhythmia signs — worth monitoring."
        )
    else:
        likelihood = "low"
        notes = (
            f"RR intervals look regular (CV {cv * 100:.1f}%, "
            f"pNN50 {pnn50:.0f}%). No AFib pattern detected."
        )

    # Boost if ECG beats showed lots of supraventricular/ventricular ectopy.
    if beat_classes:
        bc = [c for c in beat_classes if c]
        if bc:
            s_pct = sum(1 for c in bc if c == "S") / len(bc) * 100
            v_pct = sum(1 for c in bc if c == "V") / len(bc) * 100
            if (s_pct > 5 or v_pct > 5) and likelihood == "low":
                likelihood = "moderate"
                notes += (
                    f" {s_pct:.0f}% of analyzed beats were supraventricular and "
                    f"{v_pct:.0f}% were ventricular — adds some concern."
                )

    return {
        "likelihood": likelihood,
        "rr_cv": round(cv, 3),
        "pnn50_percent": round(pnn50, 1),
        "rr_entropy": round(entropy, 2),
        "ibi_samples_used": n,
        "notes": notes,
        "method": "rr_variability_heuristic",
    }


def classify_ecg(samples_millivolts: list[float], sample_rate_hz: int = 500,
                 model_name: str = "XGBoost") -> dict:
    """
    Classify ECG recording into arrhythmia classes.

    Returns dict with:
    - beats_classified: number of beats found and classified
    - classifications: list of {beat_index, class, class_name, confidence, probabilities}
    - summary: {N: count, S: count, V: count, F: count, Q: count}
    - overall_status: "Normal" or "Abnormal beats detected"
    """
    _load_models()

    if model_name not in _models:
        available = list(_models.keys())
        return {"error": f"Model '{model_name}' not loaded. Available: {available}"}

    ecg = np.array(samples_millivolts, dtype=np.float64)
    if len(ecg) < 500:
        return {"error": "ECG recording too short (need at least 1 second)"}

    # 1. Bandpass filter
    filtered = _bandpass_filter(ecg, sample_rate_hz)

    # 2. Resample from watch rate to model rate
    resampled = _resample_signal(filtered, sample_rate_hz, MODEL_SAMPLE_RATE)

    # 3. Detect R-peaks
    r_peaks = _detect_r_peaks(resampled, MODEL_SAMPLE_RATE)
    if len(r_peaks) == 0:
        return {"error": "No heartbeats detected in ECG signal"}

    # 4. Segment beats
    beats = _segment_beats(resampled, r_peaks, BEAT_WINDOW)
    if len(beats) == 0:
        return {"error": "Could not extract valid beats from ECG"}

    # 5. Classify
    model = _models[model_name]
    classifications = []
    summary = {c: 0 for c in CLASS_NAMES}

    if model_name in ("XGBoost", "SVM"):
        # Classical ML: extract features
        features = np.array([_extract_features(beat) for beat in beats])
        if model_name == "SVM" and _scaler is not None:
            features = _scaler.transform(features)
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(features)
            predictions = np.argmax(probabilities, axis=1)
        else:
            predictions = model.predict(features)
            probabilities = None

        for i, pred_idx in enumerate(predictions):
            pred_idx = int(pred_idx)
            pred_class = CLASS_NAMES[pred_idx]
            summary[pred_class] += 1
            probs_dict = {}
            conf = 100.0
            if probabilities is not None:
                probs = probabilities[i]
                conf = round(float(probs[pred_idx]) * 100, 1)
                probs_dict = {CLASS_NAMES[j]: round(float(p) * 100, 1) for j, p in enumerate(probs)}
            classifications.append({
                "beat_index": i,
                "class": pred_class,
                "class_name": CLASS_DESCRIPTIONS[pred_class],
                "confidence": conf,
                "probabilities": probs_dict,
            })

    abnormal_count = summary["S"] + summary["V"] + summary["F"] + summary["Q"]
    total = len(classifications)

    return {
        "model_name": model_name,
        "beats_classified": total,
        "beats_detected": len(r_peaks),
        "classifications": classifications,
        "summary": summary,
        "abnormal_count": abnormal_count,
        "normal_percentage": round(summary["N"] / total * 100, 1) if total > 0 else 0,
        "overall_status": "Normal" if abnormal_count == 0 else f"Abnormal beats detected ({abnormal_count}/{total})",
        "signal_info": {
            "original_samples": len(samples_millivolts),
            "original_sample_rate": sample_rate_hz,
            "resampled_to": MODEL_SAMPLE_RATE,
            "duration_seconds": round(len(samples_millivolts) / sample_rate_hz, 1),
        },
    }
