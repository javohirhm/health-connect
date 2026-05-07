"""Train an AFib classifier on PhysioNet/CinC 2017 Challenge data.

Strategy:
1. Read each ECG recording at 300 Hz, detect R-peaks, compute RR intervals.
2. Extract a feature vector per recording (CV, pNN50, Shannon entropy,
   RMSSD, mean RR, ratio of long/short, sample entropy).
3. Map labels: Normal=0, AF=1, Other=0, ~=0 (binary AFib vs not-AFib).
4. Train XGBoost with class weighting, evaluate on a held-out 20% split.
5. Save to ../models/afib_classifier.pkl.

Usage:
    python train_afib.py --data-dir datasets/physionet2017/training2017
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import signal as scipy_signal
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from tqdm import tqdm
import wfdb
from xgboost import XGBClassifier


SAMPLE_RATE_HZ = 300  # PhysioNet 2017 sample rate


# ─────────────────────────────────────────────────────────────────────
# Signal processing
# ─────────────────────────────────────────────────────────────────────

def detect_r_peaks(ecg: np.ndarray, fs: int) -> np.ndarray:
    """Pan-Tompkins-style R-peak detector matching the runtime pipeline."""
    diff = np.diff(ecg)
    sq = diff ** 2
    win = max(1, int(0.12 * fs))
    ma = np.convolve(sq, np.ones(win) / win, mode="same")
    threshold = 0.4 * np.max(ma) if ma.size else 0
    refractory = int(0.2 * fs)
    peaks = []
    i = 0
    while i < len(ma):
        if ma[i] > threshold:
            end = min(i + int(0.1 * fs), len(ma))
            peaks.append(i + int(np.argmax(ma[i:end])))
            i = peaks[-1] + refractory
        else:
            i += 1
    return np.asarray(peaks, dtype=int)


def rr_features(rr_ms: np.ndarray) -> np.ndarray | None:
    """Compute the AFib-discriminative features from a sequence of RR intervals.

    Returns None if too few intervals to be reliable.
    """
    rr = rr_ms[(rr_ms > 300) & (rr_ms < 2000)]
    if rr.size < 10:
        return None

    mean_rr = float(np.mean(rr))
    sd_rr = float(np.std(rr))
    cv = sd_rr / mean_rr if mean_rr > 0 else 0.0

    diffs = np.abs(np.diff(rr))
    pnn50 = float(np.mean(diffs > 50)) * 100.0 if diffs.size else 0.0
    rmssd = float(np.sqrt(np.mean(diffs ** 2))) if diffs.size else 0.0

    # Shannon entropy of RR distribution binned at 50 ms
    bins = np.bincount((rr // 50).astype(int))
    p = bins[bins > 0] / rr.size
    entropy = float(-(p * np.log2(p)).sum())

    # Long-vs-short ratio (irregular rhythms have many short intervals)
    median_rr = float(np.median(rr))
    short_ratio = float(np.mean(rr < 0.85 * median_rr))
    long_ratio = float(np.mean(rr > 1.15 * median_rr))

    # Sample entropy (cheap approximation: standard deviation of normalized diffs)
    norm_sd = float(np.std(diffs / mean_rr)) if mean_rr > 0 else 0.0

    # Skew & kurtosis (not strictly needed but cheap and useful)
    centered = rr - mean_rr
    skew = float(np.mean(centered ** 3) / (sd_rr ** 3 + 1e-9))
    kurt = float(np.mean(centered ** 4) / (sd_rr ** 4 + 1e-9))

    return np.array([
        mean_rr, sd_rr, cv, pnn50, rmssd, entropy,
        short_ratio, long_ratio, norm_sd, skew, kurt,
        float(rr.size),  # also useful as a length feature
    ], dtype=np.float32)


FEATURE_NAMES = [
    "mean_rr", "sd_rr", "cv", "pnn50", "rmssd", "entropy",
    "short_ratio", "long_ratio", "norm_sd", "skew", "kurt", "n_beats",
]


# ─────────────────────────────────────────────────────────────────────
# Dataset loading
# ─────────────────────────────────────────────────────────────────────

def load_label_map(data_dir: Path) -> dict[str, str]:
    ref = data_dir / "REFERENCE.csv"
    if not ref.exists():
        ref = data_dir / "REFERENCE-original.csv"
    if not ref.exists():
        raise FileNotFoundError(f"REFERENCE.csv not found in {data_dir}")
    df = pd.read_csv(ref, header=None, names=["record", "label"])
    return dict(zip(df["record"], df["label"]))


def label_to_class(label: str) -> int | None:
    """Binary: AFib (1) vs not-AFib (0). Drop noisy records."""
    if label == "A":
        return 1
    if label in ("N", "O"):  # Normal, Other (still not AFib)
        return 0
    if label == "~":  # noisy — exclude
        return None
    return None


def load_recording(record_id: str, data_dir: Path) -> np.ndarray | None:
    """Read a PhysioNet 2017 .hea/.mat record and return the channel-0 signal."""
    try:
        rec = wfdb.rdrecord(str(data_dir / record_id))
        sig = rec.p_signal[:, 0].astype(np.float32)
        return sig
    except Exception as e:
        print(f"  ! Could not read {record_id}: {e}")
        return None


def build_dataset(data_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Walk the dataset, extract features per recording, return X, y."""
    labels = load_label_map(data_dir)
    X, y = [], []
    skipped = 0

    for record_id, label in tqdm(labels.items(), desc="Extracting features"):
        cls = label_to_class(label)
        if cls is None:
            skipped += 1
            continue
        sig = load_recording(record_id, data_dir)
        if sig is None or sig.size < SAMPLE_RATE_HZ * 5:
            skipped += 1
            continue
        peaks = detect_r_peaks(sig, SAMPLE_RATE_HZ)
        if peaks.size < 11:
            skipped += 1
            continue
        rr_ms = np.diff(peaks) * (1000.0 / SAMPLE_RATE_HZ)
        feats = rr_features(rr_ms)
        if feats is None:
            skipped += 1
            continue
        X.append(feats)
        y.append(cls)

    if not X:
        raise RuntimeError("No usable recordings — check the dataset path.")
    print(f"  Used {len(X)} recordings, skipped {skipped}.")
    return np.asarray(X), np.asarray(y)


# ─────────────────────────────────────────────────────────────────────
# Train + save
# ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", required=True,
                   help="Path to PhysioNet 2017 training set (containing REFERENCE.csv + .hea + .mat)")
    p.add_argument("--out", default=None,
                   help="Output .pkl path (default: ../models/afib_classifier.pkl)")
    args = p.parse_args()

    data_dir = Path(args.data_dir).resolve()
    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent / "models" / "afib_classifier.pkl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"== Building dataset from {data_dir}")
    X, y = build_dataset(data_dir)
    print(f"   X shape: {X.shape}, AFib positives: {y.sum()} / {y.size}")

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y,
    )

    pos_ratio = (y_tr == 1).sum() / max(1, (y_tr == 0).sum())
    model = XGBClassifier(
        n_estimators=400, max_depth=4, learning_rate=0.05,
        subsample=0.85, colsample_bytree=0.85,
        scale_pos_weight=1.0 / pos_ratio if pos_ratio > 0 else 1.0,
        eval_metric="logloss",
        random_state=42, n_jobs=-1,
    )
    print("== Training XGBoost")
    model.fit(X_tr, y_tr)

    print("== Evaluating")
    y_pred = model.predict(X_te)
    print(classification_report(y_te, y_pred, target_names=["Not AFib", "AFib"]))
    print("Confusion matrix:")
    print(confusion_matrix(y_te, y_pred))
    print(f"Macro F1: {f1_score(y_te, y_pred, average='macro'):.4f}")

    bundle = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "classes": ["not_afib", "afib"],
        "trained_on": "physionet_cinc_2017",
        "method_tag": "trained_xgboost",
    }
    joblib.dump(bundle, out_path)
    print(f"== Saved {out_path}")


if __name__ == "__main__":
    main()
