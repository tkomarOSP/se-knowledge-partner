# Deploying KP Artifact Viewer to Digital Ocean

Follows the same pattern as `kp/artifact_repo/deploy/`. The viewer runs on port 8080 behind nginx at `artifacts.innovatingwithcapella.com`.

The viewer is multi-tenant: each visitor's browser gets its own signed-cookie session, and within a session you can add multiple repos (your own GitHub PAT for each is your access control — no separate accounts). Nothing is written to disk per visitor except their own git clones under `/var/lib/kp-viewer/sessions/`.

---

## Prerequisites

- SSH access to the droplet
- DNS A record for `artifacts.innovatingwithcapella.com` pointing to the droplet IP
- `certbot` already installed (used for `repo.innovatingwithcapella.com`)
- The existing `kp-artifact-repo` service running (viewer shares the venv)

---

## Step 1 — Pull latest code

```bash
cd /opt/knowledge_partner
git pull
```

---

## Step 2 — Install the viewer package

```bash
sudo /opt/knowledge_partner/.venv/bin/pip install -e kp/viewer
```

Verify it can be imported:

```bash
/opt/knowledge_partner/.venv/bin/python -c "import viewer; print('OK')"
```

---

## Step 3 — Create log and data directories

```bash
sudo mkdir -p /var/log/kp-viewer
sudo chown www-data:www-data /var/log/kp-viewer

sudo mkdir -p /var/lib/kp-viewer
sudo chown www-data:www-data /var/lib/kp-viewer
```

Each visitor's repos clone into `/var/lib/kp-viewer/sessions/{session_id}/{repo_alias}/repo`.

---

## Step 4 — Generate a session secret

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Edit `kp/viewer/deploy/kp-viewer.service` and replace `CHANGE_ME_GENERATE_A_RANDOM_SECRET` with this value before copying it in the next step. If left as the placeholder, the app falls back to a random secret generated fresh on every process start — which logs out every visitor on every restart/deploy. Setting a fixed secret keeps sessions alive across restarts.

---

## Step 5 — Install the systemd service

```bash
sudo cp /opt/knowledge_partner/kp/viewer/deploy/kp-viewer.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable kp-viewer
sudo systemctl start kp-viewer
```

Check it started cleanly:

```bash
sudo systemctl status kp-viewer
sudo tail -f /var/log/kp-viewer/error.log
```

---

## Step 6 — Get the SSL certificate

```bash
sudo certbot certonly --nginx -d artifacts.innovatingwithcapella.com
```

---

## Step 7 — Install the nginx config

```bash
sudo cp /opt/knowledge_partner/kp/viewer/deploy/nginx_viewer.conf \
    /etc/nginx/sites-available/kp-viewer.conf

sudo ln -s /etc/nginx/sites-available/kp-viewer.conf \
    /etc/nginx/sites-enabled/kp-viewer.conf

sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 8 — Add a repo

Open `https://artifacts.innovatingwithcapella.com` in a browser. With no session yet, it redirects to "Add a Repository." Enter:

- **Repo URL** — HTTPS URL of a GitHub repo
- **PAT** — GitHub Personal Access Token (`contents: read` scope is sufficient); leave blank for public repos
- **Branch** — `main` (or whichever branch)

Submit. The viewer clones it into your session and redirects to the package list. Use "+ Add repo" in the nav bar to add more repos to the same session, and the dropdown to switch between them. Each visitor who does this gets their own isolated session — nothing is shared between browsers.

---

## Updating the app

After pushing new code:

```bash
cd /opt/knowledge_partner
git pull
sudo systemctl restart kp-viewer
```

No re-install needed unless dependencies changed (in which case re-run Step 2). Restarting does **not** clear sessions as long as `KP_VIEWER_SESSION_SECRET` is fixed (Step 4) — only the idle-cleanup sweep (`KP_VIEWER_SESSION_TTL`, default 24h) or an explicit Logout removes a session's clones.

---

## Refreshing a repo's content

Each repo has its own clone. Use the **↻ Refresh** button (refreshes whichever repo is active in the selector) to pull latest content, or from the server:

```bash
sudo -u www-data git -C /var/lib/kp-viewer/sessions/{session_id}/{alias}/repo pull --rebase
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| 502 Bad Gateway | `systemctl status kp-viewer` — service crashed on startup |
| Logged out after every deploy | `KP_VIEWER_SESSION_SECRET` still set to the placeholder — generate and set a fixed value (Step 4) |
| Blank package list after adding a repo | `tail /var/log/kp-viewer/error.log` — clone likely failed (bad PAT or URL); the error shown in the form should not contain the PAT itself |
| SSL error | `certbot renew --dry-run` to verify cert renewal works |
| Port conflict | `ss -tlnp \| grep 8080` — change `KP_VIEWER_PORT` in the service file if needed |
| Disk filling up under `/var/lib/kp-viewer/sessions` | Expected for many idle sessions before the TTL sweep runs; lower `KP_VIEWER_SESSION_TTL` if needed |
