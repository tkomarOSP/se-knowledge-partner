# Deploying KP Project Artifact Repository to Digital Ocean

The project-artifact-repo MCP server runs on port 8006 behind nginx at
`project-artifacts.innovatingwithcapella.com`. It shares the droplet, venv, and
`/opt/knowledge_partner` clone already set up for `kp-knowledge-repo` and
`kp-viewer` (see `kp/knowledge_repo/deploy/DEPLOY.md` for the original setup).

This is the first **destination-layer** MCP — the landing point for promoted
workspace outputs (Layer 3: FMEA tables, Pugh matrices, trade studies,
requirements impact analyses). It's deliberately minimal: it reuses
`workspace_manager`'s typed-artifact store/types directly rather than
re-implementing them, and only adds session lifecycle + a `write_artifact`
tool. See `kp/workspace_manager/deploy/DEPLOY.md` — this server must be
deployed alongside (or after) `kp-workspace-manager`, since it depends on
the `kp-workspace-manager` Python package.

**HARD REQUIREMENT:** the git repo this server is pointed at via
`create_session` must be its own plain repo — **never the Capella model
repo.** Mixing artifact writes into a remote that `capella-fabric` also
commits to causes fast-forward conflicts. This was a deliberate design
decision after running into exactly that problem.

---

## Prerequisites

- The existing `kp-knowledge-repo`, `kp-viewer`, and `kp-workspace-manager`
  services already deployed (shared venv, shared `/opt/knowledge_partner` clone)
- DNS A record for `project-artifacts.innovatingwithcapella.com` pointing to
  the droplet IP
- `certbot` already installed
- A dedicated git repo for promoted Layer-3 artifacts, separate from any
  Capella model repo

---

## Step 1 — Pull latest code

```bash
cd /opt/knowledge_partner
git pull
```

---

## Step 2 — Install the project_artifact_repo package

This depends on `kp-workspace-manager` (it reuses its store/types modules) —
install both if `kp-workspace-manager` isn't already present:

```bash
sudo /opt/knowledge_partner/.venv/bin/pip install -e kp/workspace_manager -e kp/project_artifact_repo
```

Verify:

```bash
/opt/knowledge_partner/.venv/bin/python -c "import project_artifact_repo; print('OK')"
```

---

## Step 3 — Create the log directory

```bash
sudo mkdir -p /var/log/kp-project-artifact-repo
sudo chown www-data:www-data /var/log/kp-project-artifact-repo
```

---

## Step 4 — Install the systemd service

```bash
sudo cp /opt/knowledge_partner/kp/project_artifact_repo/deploy/kp-project-artifact-repo.service \
    /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable kp-project-artifact-repo
sudo systemctl start kp-project-artifact-repo
```

Check it started cleanly:

```bash
sudo systemctl status kp-project-artifact-repo
sudo tail -f /var/log/kp-project-artifact-repo/mcp-error.log
```

---

## Step 5 — Get the SSL certificate

```bash
sudo certbot certonly --nginx -d project-artifacts.innovatingwithcapella.com
```

---

## Step 6 — Install the nginx config

```bash
sudo cp /opt/knowledge_partner/kp/project_artifact_repo/deploy/nginx_project_artifact_repo.conf \
    /etc/nginx/sites-available/kp-project-artifact-repo.conf

sudo ln -s /etc/nginx/sites-available/kp-project-artifact-repo.conf \
    /etc/nginx/sites-enabled/kp-project-artifact-repo.conf

sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 7 — Verify

```bash
curl -s -o /dev/null -w "%{http_code}" https://project-artifacts.innovatingwithcapella.com/mcp
```

A `405` (Method Not Allowed) means nginx is proxying correctly — the MCP
endpoint only accepts POST.

---

## Register with kp_agent

Set `KP_PROJECT_ARTIFACT_REPO_URL=https://project-artifacts.innovatingwithcapella.com/mcp`
in the kp_agent environment (already defaulted to this in
`kp/kp_agent/config.py` — only needs overriding for local/alternate setups).

---

## Updating the app

```bash
cd /opt/knowledge_partner
git pull
sudo systemctl restart kp-project-artifact-repo
```

No re-install needed unless dependencies changed (re-run Step 2). If
`kp-workspace-manager`'s store/types code changes, restart this service too —
it imports that package directly rather than vendoring a copy.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| 502 Bad Gateway | `systemctl status kp-project-artifact-repo` — service may have crashed |
| 404 on `/mcp` | nginx config not linked — check `sites-enabled/` |
| SSL error | `certbot renew --dry-run` to verify cert renewal |
| MCP tool errors in Claude | `tail /var/log/kp-project-artifact-repo/mcp-error.log` |
| Port 8006 not listening | `ss -tlnp \| grep 8006` — service not running |
| `ImportError: No module named 'workspace_manager'` | install `kp/workspace_manager` first (Step 2) — this server depends on it |
| Push/checkout failures | confirm `create_session` was called with a plain git repo URL, never the Capella model repo |
