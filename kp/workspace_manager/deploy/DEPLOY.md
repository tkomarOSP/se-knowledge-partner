# Deploying KP Workspace Manager to Digital Ocean

The workspace-manager MCP server runs on port 8005 behind nginx at
`workspace.innovatingwithcapella.com`. It shares the droplet, venv, and
`/opt/knowledge_partner` clone already set up for `kp-artifact-repo` and
`kp-viewer` (see `kp/artifact_repo/deploy/DEPLOY.md` for the original setup).

**HARD REQUIREMENT:** the git repo(s) this server is pointed at via
`create_workspace_session` must never be the Capella model repo. Mixing
workspace artifact commits into a remote that `capella-fabric` also commits to
causes fast-forward conflicts. Always use a plain, dedicated git repo.

---

## Prerequisites

- The existing `kp-artifact-repo` and `kp-viewer` services already deployed
  (shared venv, shared `/opt/knowledge_partner` clone)
- DNS A record for `workspace.innovatingwithcapella.com` pointing to the droplet IP
- `certbot` already installed

---

## Step 1 — Pull latest code

```bash
cd /opt/knowledge_partner
git pull
```

---

## Step 2 — Install the workspace_manager package

```bash
sudo /opt/knowledge_partner/.venv/bin/pip install -e kp/workspace_manager
```

Verify:

```bash
/opt/knowledge_partner/.venv/bin/python -c "import workspace_manager; print('OK')"
```

---

## Step 3 — Create the log directory

```bash
sudo mkdir -p /var/log/kp-workspace-manager
sudo chown www-data:www-data /var/log/kp-workspace-manager
```

---

## Step 4 — Install the systemd service

```bash
sudo cp /opt/knowledge_partner/kp/workspace_manager/deploy/kp-workspace-manager.service \
    /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable kp-workspace-manager
sudo systemctl start kp-workspace-manager
```

Check it started cleanly:

```bash
sudo systemctl status kp-workspace-manager
sudo tail -f /var/log/kp-workspace-manager/mcp-error.log
```

---

## Step 5 — Get the SSL certificate

```bash
sudo certbot certonly --nginx -d workspace.innovatingwithcapella.com
```

---

## Step 6 — Install the nginx config

```bash
sudo cp /opt/knowledge_partner/kp/workspace_manager/deploy/nginx_workspace_manager.conf \
    /etc/nginx/sites-available/kp-workspace-manager.conf

sudo ln -s /etc/nginx/sites-available/kp-workspace-manager.conf \
    /etc/nginx/sites-enabled/kp-workspace-manager.conf

sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 7 — Verify

```bash
curl -s -o /dev/null -w "%{http_code}" https://workspace.innovatingwithcapella.com/mcp
```

A `405` (Method Not Allowed) means nginx is proxying correctly — the MCP
endpoint only accepts POST.

---

## Register with kp_agent

Set `KP_WORKSPACE_MANAGER_URL=https://workspace.innovatingwithcapella.com/mcp`
in the kp_agent environment (already defaulted to this in
`kp/kp_agent/config.py` — only needs overriding for local/alternate setups).

---

## Updating the app

```bash
cd /opt/knowledge_partner
git pull
sudo systemctl restart kp-workspace-manager
```

No re-install needed unless dependencies changed (re-run Step 2).

---

## Troubleshooting

| Symptom | Check |
|---|---|
| 502 Bad Gateway | `systemctl status kp-workspace-manager` — service may have crashed |
| 404 on `/mcp` | nginx config not linked — check `sites-enabled/` |
| SSL error | `certbot renew --dry-run` to verify cert renewal |
| MCP tool errors in Claude | `tail /var/log/kp-workspace-manager/mcp-error.log` |
| Port 8005 not listening | `ss -tlnp \| grep 8005` — service not running |
| Branch checkout failures during write_workspace_artifact | confirm the target session was created against a plain git repo, not the Capella model repo |
