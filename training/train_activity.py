"""Train an activity classifier on UCI HAR.

The dataset already provides 561 hand-crafted features per 2.56-second window
covering 6 activities. We map them to our 4 application labels:
  WALKING, WALKING_UPSTAIRS, WALKING_DOWNSTAIRS  →  walking
  STANDING, SITTING, LAYING                       →  still
(LAYING is treated as "still" — for our use case "in-bed quiet" is what we
care about; we don't distinguish lying-down from sitting at rest.)

Running detection: UCI HAR doesn't include running. We add a synthetic
"running" rule at runtime: if the dominant cadence frequency is in the
2.5–4.5 Hz band AND magnitude SD is high, we override the model to "running"
(matching the existing FFT heuristic). The model itself trains on the 4-class
problem.

Usage:
    python train_activity.py --data-dir "datasets/uci_har/UCI HAR Dataset"
"""
from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.preprocessing import StandardScaler


# Map UCI HAR's 6 activity codes to our 4 application labels.
# Codes 1-3 are WALKING / WALKING_UPSTAIRS / WALKING_DOWNSTAIRS → walking
# Codes 4-5 are SITTING / STANDING → still (sedentary)
# Code 6 is LAYING → still (in-bed, quiet)
UCI_TO_APP = {
    1: "walking", 2: "walking", 3: "walking",
    4: "still", 5: "still", 6: "still",
}


# Feature subset we want to use at inference time.
# The full 561-feature vector is overkill; we pick the most informative axes
# (means and std-devs of body acceleration) so the runtime can compute them
# directly from a 125-sample accel batch without needing the UCI feature
# extractor.
RUNTIME_FEATURE_INDICES_NAMES: list[tuple[str, str]] = [
    # All from features.txt (UCI HAR convention). Index is 1-based in features.txt
    # so we'll resolve them by name below.
    ("tBodyAcc-mean()-X", "mean_x"),
    ("tBodyAcc-mean()-Y", "mean_y"),
    ("tBodyAcc-mean()-Z", "mean_z"),
    ("tBodyAcc-std()-X", "sd_x"),
    ("tBodyAcc-std()-Y", "sd_y"),
    ("tBodyAcc-std()-Z", "sd_z"),
    ("tBodyAcc-mad()-X", "mad_x"),
    ("tBodyAcc-mad()-Y", "mad_y"),
    ("tBodyAcc-mad()-Z", "mad_z"),
    ("tBodyAcc-max()-X", "max_x"),
    ("tBodyAcc-max()-Y", "max_y"),
    ("tBodyAcc-max()-Z", "max_z"),
    ("tBodyAcc-min()-X", "min_x"),
    ("tBodyAcc-min()-Y", "min_y"),
    ("tBodyAcc-min()-Z", "min_z"),
    ("tBodyAccMag-mean()", "mag_mean"),
    ("tBodyAccMag-std()", "mag_sd"),
    ("tBodyAccMag-mad()", "mag_mad"),
    ("tBodyAccMag-max()", "mag_max"),
    ("tBodyAccMag-min()", "mag_min"),
    ("tBodyAccMag-energy()", "mag_energy"),
    ("tBodyAccMag-iqr()", "mag_iqr"),
]


def load_features_index(data_dir: Path) -> dict[str, int]:
    """Parse features.txt → {name: 0-based column index}"""
    feats_path = data_dir / "features.txt"
    out: dict[str, int] = {}
    with open(feats_path) as f:
        for line in f:
            parts = line.strip().split(maxsplit=1)
            if len(parts) != 2:
                continue
            idx_1based, name = parts
            # UCI HAR has duplicate column names — keep the first occurrence
            if name not in out:
                out[name] = int(idx_1based) - 1
    return out


def load_split(split_dir: Path, indices: list[int]) -> tuple[np.ndarray, np.ndarray]:
    X = pd.read_csv(
        split_dir / f"X_{split_dir.name}.txt",
        sep=r"\s+", header=None,
    ).values.astype(np.float32)
    y = pd.read_csv(
        split_dir / f"y_{split_dir.name}.txt",
        sep=r"\s+", header=None,
    ).values.ravel().astype(int)
    return X[:, indices], y


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", required=True,
                   help="Path to extracted 'UCI HAR Dataset' folder")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    data_dir = Path(args.data_dir).resolve()
    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent / "models" / "activity_classifier.pkl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"== Loading UCI HAR from {data_dir}")
    feats_idx = load_features_index(data_dir)

    # Resolve feature indices by name
    indices = []
    runtime_names = []
    missing = []
    for uci_name, runtime_name in RUNTIME_FEATURE_INDICES_NAMES:
        if uci_name in feats_idx:
            indices.append(feats_idx[uci_name])
            runtime_names.append(runtime_name)
        else:
            missing.append(uci_name)
    if missing:
        print(f"  ! Missing UCI features (will train without them): {missing}")
    print(f"  Using {len(indices)} features.")

    # Load train + test splits
    X_tr, y_tr_uci = load_split(data_dir / "train", indices)
    X_te, y_te_uci = load_split(data_dir / "test", indices)

    # Map to our 4-class application label
    y_tr = np.array([UCI_TO_APP[c] for c in y_tr_uci])
    y_te = np.array([UCI_TO_APP[c] for c in y_te_uci])

    print(f"  Train: {X_tr.shape}, Test: {X_te.shape}")
    print(f"  Train class counts: {pd.Series(y_tr).value_counts().to_dict()}")

    scaler = StandardScaler().fit(X_tr)
    X_tr_s = scaler.transform(X_tr)
    X_te_s = scaler.transform(X_te)

    print("== Training Random Forest")
    model = RandomForestClassifier(
        n_estimators=300, max_depth=12, min_samples_split=4,
        class_weight="balanced", random_state=42, n_jobs=-1,
    )
    model.fit(X_tr_s, y_tr)

    print("== Evaluating")
    y_pred = model.predict(X_te_s)
    print(classification_report(y_te, y_pred))
    print("Confusion matrix:")
    print(confusion_matrix(y_te, y_pred, labels=sorted(set(y_tr))))
    print(f"Macro F1: {f1_score(y_te, y_pred, average='macro'):.4f}")

    bundle = {
        "model": model,
        "scaler": scaler,
        "feature_names": runtime_names,
        "classes": sorted(set(y_tr)),  # ['still', 'walking']
        "trained_on": "uci_har",
        "method_tag": "trained_random_forest",
        # Runtime is responsible for adding the "running"/"active" labels
        # via cadence rules — UCI HAR doesn't contain running, so the model
        # sees only still/walking.
    }
    joblib.dump(bundle, out_path)
    print(f"== Saved {out_path}")


if __name__ == "__main__":
    main()
