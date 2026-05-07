# Training trained ML detectors

Reproducible training scripts that replace the heuristic detectors (AFib,
activity classification, sleep restlessness) with proper ML models.

## What gets produced

| Script | Dataset | Output |
|---|---|---|
| `train_afib.py` | [PhysioNet/CinC 2017 Challenge](https://physionet.org/content/challenge-2017/1.0.0/) | `models/afib_classifier.pkl` |
| `train_activity.py` | [UCI HAR](https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones) | `models/activity_classifier.pkl` |

The **sleep restlessness** detector reuses the activity classifier's output —
no separate model file needed.

## Step-by-step

### 0. Install training deps (one time, NOT installed on the production VPS)

```bash
cd training
pip install -r requirements-train.txt
```

These are kept separate from `backend/requirements.txt` so the production
server stays small.

### 1. Train the AFib model

Download the PhysioNet 2017 dataset:

```bash
mkdir -p datasets/physionet2017
cd datasets/physionet2017
wget https://physionet.org/files/challenge-2017/1.0.0/training2017.zip
unzip training2017.zip
# REFERENCE-original.csv has the labels (Normal, AF, Other, Noisy).
# *.mat files are the ECG recordings at 300 Hz.
cd ../..
```

Run training:

```bash
python train_afib.py --data-dir datasets/physionet2017/training2017
```

Outputs: `../models/afib_classifier.pkl` plus a brief evaluation report on
stdout (accuracy, F1 per class, confusion matrix). Takes ~2 minutes on CPU.

### 2. Train the activity classifier

Download UCI HAR:

```bash
mkdir -p datasets/uci_har
cd datasets/uci_har
wget https://archive.ics.uci.edu/static/public/240/human+activity+recognition+using+smartphones.zip
unzip "human+activity+recognition+using+smartphones.zip"
unzip "UCI HAR Dataset.zip"
cd ../..
```

Run training:

```bash
python train_activity.py --data-dir "datasets/uci_har/UCI HAR Dataset"
```

Outputs: `../models/activity_classifier.pkl`. Takes ~30 seconds on CPU.

### 3. Deploy the models

```bash
# Copy the produced pkl files to the VPS
scp ../models/afib_classifier.pkl healthconnect@<vps>:/opt/healthconnect/models/
scp ../models/activity_classifier.pkl healthconnect@<vps>:/opt/healthconnect/models/

# Restart the backend
ssh <vps> 'sudo systemctl restart healthconnect'
```

The backend auto-detects the new model files at startup. If a file is
present, the trained model is used. If absent, it falls back to the
heuristic (no errors, no breakage).

## Verification

After the backend restart:

```bash
WATCH=$(curl -s "https://api.javohirhm.uz/api/v2/watches" | jq -r '.[0].watch_id')

# Method tag should now show "trained_model" instead of the heuristic tag
curl -s "https://api.javohirhm.uz/api/v2/watch/$WATCH/summary/today" \
  | jq '{rhythm: .rhythm_screen.method, activity: .activity.method}'
```

Expected:

```json
{
  "rhythm": "trained_xgboost",
  "activity": "trained_random_forest"
}
```

If they still say `rr_variability_heuristic` / `welch_fft_cadence`, the
model files didn't load — check `journalctl -u healthconnect | grep -i 'trained model'`.
