# HealthConnect Backend — Production Deployment Runbook

This file is a deployment runbook for the HealthConnect FastAPI backend
(`https://github.com/javohirhm/health-connect.git`). It assumes you (Claude
Code) are running on the target VPS with sudo access and will execute the
steps below interactively.

## What you're deploying

A FastAPI server that ingests data from a Galaxy Watch 5 + Android phone and
runs ML arrhythmia detection on ECG recordings. PostgreSQL replaces SQLite in
production. ML inference (TensorFlow + XGBoost + scikit-learn) runs in-process,
so RAM matters.

Architecture: `Nginx (80/443) → uvicorn workers (127.0.0.1:8000) → PostgreSQL`.
TLS via Let's Encrypt. Process supervised by systemd.

## Step 0 — Ask the user for these BEFORE running anything destructive

Stop and prompt the user for each of these. Save them somewhere safe.

| Variable          | Example                       | Notes |
|-------------------|-------------------------------|-------|
| `DOMAIN`          | `health.example.com`          | DNS A-record must already point at this VPS's public IP. Verify with `dig +short $DOMAIN`. |
| `APP_USER`        | `healthconnect`               | Non-root system user that will own the code and run the service. |
| `APP_DIR`         | `/opt/healthconnect`          | Install path. |
| `PG_PASSWORD`     | (generate)                    | Generate with `openssl rand -base64 24`. Show it to the user once and tell them to record it. |
| `LETSENCRYPT_EMAIL` | `you@example.com`           | For cert renewal notices. |

Do **not** proceed past step 4 (HTTPS) until `dig +short $DOMAIN` returns the
VPS's public IP. Confirm with the user if it doesn't match.

## Step 1 — System packages

Tested against Ubuntu 22.04 / 24.04. For other distros, adapt package names.
Run `lsb_release -a` first to confirm.

```bash
sudo apt update
sudo apt install -y \
    python3 python3-venv python3-pip \
    postgresql postgresql-contrib \
    nginx \
    certbot python3-certbot-nginx \
    git curl ufw \
    build-essential
```

Verify:
```bash
python3 --version          # 3.10+ required, 3.11 or 3.12 ideal
psql --version
nginx -v
```

## Step 2 — Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'   # opens 80 and 443
sudo ufw --force enable
sudo ufw status
```

If you're on a cloud provider with its own firewall (DigitalOcean, Hetzner,
AWS), also confirm the cloud-side rules allow 22, 80, 443.

## Step 3 — PostgreSQL

```bash
# Create role and database. Use the PG_PASSWORD from Step 0.
sudo -u postgres psql <<EOF
CREATE USER healthconnect WITH PASSWORD '<PG_PASSWORD>';
CREATE DATABASE healthconnect OWNER healthconnect;
GRANT ALL PRIVILEGES ON DATABASE healthconnect TO healthconnect;
EOF
```

Verify the connection works from the app's perspective:
```bash
PGPASSWORD='<PG_PASSWORD>' psql -h localhost -U healthconnect -d healthconnect -c '\conninfo'
```

The schema is auto-created by the app on first startup (see [app/main.py:44](app/main.py:44),
which calls `db.init_db()` on FastAPI startup), so you don't need to run any
DDL manually.

## Step 4 — Application user, code, virtualenv

```bash
# Create the system user
sudo useradd --system --create-home --home-dir /home/healthconnect --shell /bin/bash healthconnect

# Clone code into APP_DIR
sudo mkdir -p /opt/healthconnect
sudo chown healthconnect:healthconnect /opt/healthconnect
sudo -u healthconnect git clone https://github.com/javohirhm/health-connect.git /opt/healthconnect

# Virtualenv + dependencies
sudo -u healthconnect bash -c '
  cd /opt/healthconnect
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
  .venv/bin/pip install gunicorn  # not in requirements.txt; we use it for graceful workers
'
```

> **TensorFlow note.** `requirements.txt` pulls TensorFlow (~600 MB on disk per
> install, plus ~600 MB resident per worker). On a 2 GB VPS use `WORKERS=1`. On
> 4 GB use `WORKERS=2`. Anything more wants 8 GB+.

## Step 5 — `.env` file

Create `/opt/healthconnect/.env` (ownership `healthconnect:healthconnect`,
mode 600). Substitute the values from Step 0.

```env
# Database
DB_TYPE=postgresql
PG_HOST=localhost
PG_PORT=5432
PG_USER=healthconnect
PG_PASSWORD=<PG_PASSWORD>
PG_DATABASE=healthconnect

# Server
HOST=127.0.0.1
PORT=8000
RELOAD=false
WORKERS=2

# CORS — only used by the web dashboard. Add your domain here. Mobile/watch
# don't need CORS, but the dashboard runs in a browser.
CORS_ORIGINS=https://<DOMAIN>

# ML models
MODELS_DIR=/opt/healthconnect/models

# Logging
LOG_LEVEL=INFO
```

Lock it down:
```bash
sudo chown healthconnect:healthconnect /opt/healthconnect/.env
sudo chmod 600 /opt/healthconnect/.env
```

## Step 6 — Smoke test the app before fronting it with nginx

Run uvicorn manually as the app user. This proves DB connection + schema
creation + ML model loading all work before involving systemd.

```bash
sudo -u healthconnect bash -c '
  cd /opt/healthconnect
  .venv/bin/python -c "from app.config import config; print(\"DB:\", config.DB_TYPE, config.pg_url)"
  .venv/bin/python run.py &
  PID=$!
  sleep 8
  curl -s http://127.0.0.1:8000/ || true
  kill $PID
'
```

Expected:
- the print line shows `DB: postgresql postgresql://healthconnect:...@localhost:5432/healthconnect`
- the `curl /` returns a JSON or HTML response
- no Python tracebacks
- `psql -U healthconnect -d healthconnect -c '\dt'` now lists tables (`heart_rate`,
  `steps`, `watch_sensor_data`, `ecg_classifications`, etc.)

If TensorFlow throws on model load, check `MODELS_DIR` and that `models/` was
cloned (it's ~18 MB, all `.keras` and `.pkl` files).

## Step 7 — systemd service

Write `/etc/systemd/system/healthconnect.service`:

```ini
[Unit]
Description=HealthConnect FastAPI backend
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=healthconnect
Group=healthconnect
WorkingDirectory=/opt/healthconnect
EnvironmentFile=/opt/healthconnect/.env
ExecStart=/opt/healthconnect/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=20

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/healthconnect

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now healthconnect
sudo systemctl status healthconnect --no-pager
```

If status is not `active (running)`, check `journalctl -u healthconnect -n 100 --no-pager`.

Verify via the loopback:
```bash
curl -s http://127.0.0.1:8000/
```

## Step 8 — Nginx reverse proxy

Write `/etc/nginx/sites-available/healthconnect`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name <DOMAIN>;

    # ECG payloads can be a few MB. Default 1MB is too tight.
    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Long-lived requests for ECG classification + report generation
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;

        # WebSocket-friendly (future-proofing for the planned WS streaming feature)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Enable it:
```bash
sudo ln -sf /etc/nginx/sites-available/healthconnect /etc/nginx/sites-enabled/healthconnect
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Verify on port 80:
```bash
curl -sI http://<DOMAIN>/
```

Should be a `200` (or whatever the root returns), proxied through nginx. **Do
not proceed to TLS until this works.**

## Step 9 — HTTPS via Let's Encrypt

```bash
sudo certbot --nginx -d <DOMAIN> --non-interactive --agree-tos -m <LETSENCRYPT_EMAIL> --redirect
```

`--redirect` rewrites the nginx config to force HTTPS. Verify:
```bash
curl -sI https://<DOMAIN>/
curl -sI http://<DOMAIN>/        # should 301 to https
```

Auto-renewal is handled by the `certbot.timer` systemd unit (installed by the
package). Confirm with `systemctl list-timers | grep certbot`.

## Step 10 — End-to-end check

```bash
# Should serve the dashboard HTML
curl -s https://<DOMAIN>/dashboard | head -20

# Should return JSON with empty lists / zero counts (fresh database)
curl -s https://<DOMAIN>/api/v2/watches
```

Tail logs while you trigger a request to confirm the proxy chain is intact:
```bash
sudo journalctl -u healthconnect -f
# or:
sudo tail -f /var/log/nginx/access.log
```

## Step 11 — Tell the user to update the mobile app

The mobile app currently defaults to `http://192.168.1.16:8000`. Two options:

1. **Recommended (no rebuild):** open the Android app → Profile → Health Settings,
   change the server URL to `https://<DOMAIN>`. This is stored via
   `SyncPreferences.saveServerUrl()` and persists.
2. Change the compiled-in default in
   `health-connect-app/mobile/src/main/.../SyncPreferences.kt` and rebuild — only
   needed if shipping a new APK.

## Operational cheat sheet

```bash
# Logs
sudo journalctl -u healthconnect -f               # app
sudo tail -f /var/log/nginx/{access,error}.log    # nginx

# Restart after .env or code changes
sudo systemctl restart healthconnect

# Pull latest code
sudo -u healthconnect git -C /opt/healthconnect pull
sudo -u healthconnect /opt/healthconnect/.venv/bin/pip install -r /opt/healthconnect/requirements.txt
sudo systemctl restart healthconnect

# Postgres backup (run from a cron or on demand)
sudo -u postgres pg_dump healthconnect | gzip > "/var/backups/healthconnect-$(date +%F).sql.gz"

# Postgres shell
sudo -u postgres psql healthconnect
```

## Operational notes

- **WORKERS sizing**: each uvicorn worker loads its own copy of TensorFlow
  (~600 MB resident). Start with `WORKERS=2`. If `journalctl` shows OOM kills,
  drop to `WORKERS=1` or upgrade RAM.
- **First-startup race on fresh DB**: with `WORKERS>1`, multiple workers can
  run `init_db()` concurrently and one may lose a `CREATE INDEX` race. It
  recovers (the index ends up created) and won't recur once tables exist. To
  avoid the warning entirely on fresh installs, run
  `python -c "from app.database import init_db; init_db()"` once before the
  first `systemctl start`.

## Done criteria

- [ ] `systemctl is-active healthconnect` → `active`
- [ ] `curl -sI https://<DOMAIN>/` → `HTTP/2 200`
- [ ] `curl -sI http://<DOMAIN>/` → `HTTP/1.1 301` (redirect to HTTPS)
- [ ] `psql ... -c '\dt'` shows the 7 application tables
- [ ] Mobile app, with server URL pointed at `https://<DOMAIN>`, successfully
      syncs at least one heart-rate sample (verify with
      `select count(*) from heart_rate;` in psql)
