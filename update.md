# Update Runbook (for Claude Code running on the VPS)

This file is a runbook for **Claude Code running on the production VPS** to
apply updates from `origin/main` to the live HealthConnect deployment at
`api.javohirhm.uz`.

If you are Claude Code on the VPS and the user says *"deploy the latest"*,
*"update the server"*, *"pull the latest changes"*, or anything similar —
follow the steps below in order. Stop and ask the user only on the
explicit checkpoints noted.

---

## Assumptions about the VPS

These match `deploy.md`. If anything differs, ask the user before proceeding.

| Item | Value |
|---|---|
| Install path | `/opt/healthconnect` |
| Owner | `healthconnect:healthconnect` |
| Service name | `healthconnect.service` (systemd) |
| Database | PostgreSQL, db `healthconnect`, user `healthconnect` |
| Domain | `api.javohirhm.uz` |
| Python venv | `/opt/healthconnect/.venv` |

---

## Step 0 — Sanity check

Before touching anything, confirm the service is up so we know what
"working" looks like for the rollback comparison.

```bash
sudo systemctl is-active healthconnect
curl -s -o /dev/null -w "%{http_code}\n" https://api.javohirhm.uz/api/v1/health
```

Both should print `active` and `200`. If either is wrong, **stop and tell
the user the service is already broken before this update** — don't pull on
top of a broken state.

---

## Step 1 — Pull from origin/main

```bash
sudo -u healthconnect git -C /opt/healthconnect fetch --all
sudo -u healthconnect git -C /opt/healthconnect log --oneline HEAD..origin/main
```

That second command lists the new commits. Read them. If any commit
message mentions any of the keywords below, jump to the matching section
**before pulling**:

| Keyword in commit message | Section to read first |
|---|---|
| `requirements.txt` / `pip` / new dependency | §3 — Dependencies |
| `init_db` / `schema` / `CREATE TABLE` / `ALTER TABLE` | §4 — Schema |
| `.env` / `config.py` / new env var | §5 — Env vars |
| `gemini` / `OPENAI` / API key | §5 — Env vars |
| `models/*.pkl` / `models/*.tflite` | §6 — Model files |

For everything else (route handlers, helpers, mobile-only changes), just
proceed.

```bash
sudo -u healthconnect git -C /opt/healthconnect pull --ff-only
```

If the pull errors out with anything other than fast-forward, **stop and
ask the user** — never `git reset --hard` without explicit permission.

---

## Step 2 — Restart the service

```bash
sudo systemctl restart healthconnect
sleep 3
sudo systemctl status healthconnect --no-pager | head -15
```

If `Active: failed`, jump to §8 — Rollback.

---

## Step 3 — Dependencies (only if requirements changed)

If `requirements.txt` was in the diff:

```bash
sudo -u healthconnect /opt/healthconnect/.venv/bin/pip install -r /opt/healthconnect/requirements.txt
sudo systemctl restart healthconnect
```

If the diff *removed* a heavy dep (e.g. `tensorflow`), explicitly uninstall
it to actually free RAM/disk:

```bash
sudo -u healthconnect /opt/healthconnect/.venv/bin/pip uninstall -y <pkg>
```

`requirements-train.txt` (in `training/`) is **never** installed on the
VPS — that's training-only.

---

## Step 4 — Schema (only if database tables changed)

`init_db()` runs on every backend startup and creates new tables via
`CREATE TABLE IF NOT EXISTS`, so additive changes are handled automatically
by Step 2. If the diff includes `ALTER TABLE` or column drops/renames,
ask the user before applying — these need manual review.

---

## Step 5 — Env vars (only if config.py / .env.example changed)

Compare the deployed `.env` against the new `.env.example`:

```bash
diff <(sudo -u healthconnect grep -v '^#' /opt/healthconnect/.env | grep '=' | cut -d= -f1 | sort) \
     <(grep -v '^#' /opt/healthconnect/.env.example | grep '=' | cut -d= -f1 | sort)
```

If `.env.example` introduced a new variable that the live `.env` is
missing, ask the user for the value before adding it. Never make up
secrets.

---

## Step 6 — Model files (only if `models/*.pkl|*.tflite` changed)

`git pull` already brings the model files (they're tracked in git).
After Step 2's restart, confirm the backend loaded them:

```bash
sudo journalctl -u healthconnect --since "1 minute ago" --no-pager | grep -iE "loaded|model"
```

Expected lines:

```
INFO health-api.ml:    Loaded trained AFib model from /opt/healthconnect/models/afib_classifier.pkl
INFO health-api.ml:    Loaded XGBoost model
INFO health-api.ml:    Loaded SVM model + scaler
INFO health-api.signal: Loaded trained activity model from /opt/healthconnect/models/activity_classifier.pkl
```

If a "Loaded trained ... model" line is **missing**, the file isn't where
the runtime expects. Check:

```bash
sudo -u healthconnect ls -la /opt/healthconnect/models/
```

The runtime reads from the path in `config.MODELS_DIR` — confirm that
matches.

---

## Step 7 — Verification (always do this)

End-to-end smoke test:

```bash
# 7.1: HTTPS + Postgres confirmed by /api/v1/health
curl -s "https://api.javohirhm.uz/api/v1/health" | jq .
# expect {"status": "ok", "db_type": "postgresql"}

# 7.2: Watch list still served
WATCH=$(curl -s "https://api.javohirhm.uz/api/v2/watches" | jq -r '.[0].watch_id')
echo "Watch: $WATCH"
# if $WATCH is null, no watch has synced yet — that's OK, skip 7.3 and 7.4

# 7.3: Today's summary returns AND uses the trained models when present
if [ -n "$WATCH" ] && [ "$WATCH" != "null" ]; then
  curl -s "https://api.javohirhm.uz/api/v2/watch/$WATCH/summary/today" \
    | jq '{
        rhythm_method: .rhythm_screen.method,
        sleep_method: .sleep.restlessness.method,
        hr_samples: .heart_rate.samples,
        activity_minutes: .activity.activity_minutes
      }'
fi
# expect rhythm_method == "trained_xgboost"  (if AFib model deployed)
# expect sleep_method == "trained_random_forest"  (if activity model deployed)

# 7.4: AI insight still works (only call if Gemini is configured)
if sudo -u healthconnect grep -q "^GEMINI_API_KEY=." /opt/healthconnect/.env && [ -n "$WATCH" ]; then
  curl -s "https://api.javohirhm.uz/api/v2/watch/$WATCH/insights/ai" | jq -r '.ai_text' | head -3
fi
```

Report the actual values you see — don't assume.

---

## Step 8 — Rollback (only if Step 2 or 7 failed)

```bash
# Find the previous commit before the pull
sudo -u healthconnect git -C /opt/healthconnect log -2 --oneline

# Roll back the working tree to the previous commit (PRESERVES the local .env)
sudo -u healthconnect git -C /opt/healthconnect reset --hard HEAD~1

# Reinstall any reverted requirements
sudo -u healthconnect /opt/healthconnect/.venv/bin/pip install -r /opt/healthconnect/requirements.txt

sudo systemctl restart healthconnect
sleep 3
sudo systemctl is-active healthconnect
```

After rollback, **tell the user what failed** with the relevant
`journalctl` snippet, and don't try the update again until they
acknowledge.

---

## Step 9 — Refresh AI cache (optional, only when ML / data fields changed)

The Gemini insights endpoint caches per `(watch_id, date)`. If this update
changed anything that flows into the AI prompt — new fields in the today
summary, new detector outputs, prompt rewrites — wipe today's cache so the
next call regenerates with the new content:

```bash
sudo -u postgres psql healthconnect -c \
  "DELETE FROM ai_insights WHERE date = CURRENT_DATE::text OR date = 'total:' || CURRENT_DATE::text;"
```

Don't do this for unrelated updates — every flush burns a Gemini API
call.

---

## Reporting back to the user

When done, report briefly with these specifics:

- The commits applied (`git log --oneline OLD..NEW`).
- Whether dependencies / schema / env / models were touched.
- The output of Step 7 — actual values, not "looks good."
- Whether the AI cache was flushed and why.

Keep it tight. The user doesn't need narration of each command — they
need the diff between *before* and *after*.

---

## Things you must NEVER do without explicit user permission

- `git reset --hard` to anything other than `HEAD~1` for rollback.
- `git push --force` from the VPS (the VPS is downstream).
- Edit `/opt/healthconnect/.env` directly with new secret values you
  came up with yourself.
- `DROP TABLE`, `TRUNCATE`, or any destructive Postgres operation.
- Skip verification (Step 7).
- `sudo rm -rf` anything outside the install path.

If a step seems to need any of those, **stop and ask the user**.
