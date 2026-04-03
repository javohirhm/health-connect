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

    # Load 1D-CNN (best performer at 98.28%)
    cnn_path = models_dir / "1D_CNN.keras"
    if cnn_path.exists():
        try:
            import tensorflow as tf
            tf.get_logger().setLevel("ERROR")
            _models["1D-CNN"] = tf.keras.models.load_model(str(cnn_path))
            logger.info("Loaded 1D-CNN model")
        except Exception as e:
            logger.warning("Failed to load 1D-CNN: %s", e)

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


def classify_ecg(samples_millivolts: list[float], sample_rate_hz: int = 500,
                 model_name: str = "1D-CNN") -> dict:
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

    if model_name == "1D-CNN":
        # Deep learning: input shape (N, 360, 1)
        X = np.array(beats).reshape(-1, BEAT_WINDOW, 1)
        probabilities = model.predict(X, verbose=0)
        for i, probs in enumerate(probabilities):
            pred_idx = int(np.argmax(probs))
            pred_class = CLASS_NAMES[pred_idx]
            summary[pred_class] += 1
            classifications.append({
                "beat_index": i,
                "class": pred_class,
                "class_name": CLASS_DESCRIPTIONS[pred_class],
                "confidence": round(float(probs[pred_idx]) * 100, 1),
                "probabilities": {CLASS_NAMES[j]: round(float(p) * 100, 1) for j, p in enumerate(probs)},
            })
    elif model_name in ("XGBoost", "SVM"):
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
