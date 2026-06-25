# Deploying KP Knowledge Repository MCP Server to Digital Ocean

The knowledge-repo MCP server runs on port 8002 behind nginx at `repo.innovatingwithcapella.com`.

---

## Prerequisites

- SSH access to the droplet
- DNS A record for `repo.innovatingwithcapella.com` pointing to the droplet IP
- Python 3.11+ and `git` installed on the droplet
- `certbot` and `nginx` installed

---

## Step 1 — Clone the repository

```bash
sudo mkdir -p /opt/knowledge_partner
sudo chown $USER:$USER /opt/knowledge_partner
git clone https://github.com/YOUR_ORG/YOUR_REPO.git /opt/knowledge_partner
```

---

## Step 2 — Create the virtual environment and install packages

```bash
cd /opt/knowledge_partner
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e kp/knowledge_repo
```

Verify:

```bash
.venv/bin/python -c "import knowledge_repo; print('OK')"
```

---

## Step 3 — Create log directory

```bash
sudo mkdir -p /var/log/kp-knowledge-repo
sudo chown www-data:www-data /var/log/kp-knowledge-repo
```

---

## Step 4 — Install the systemd service

```bash
sudo cp /opt/knowledge_partner/kp/knowledge_repo/deploy/kp-knowledge-repo.service \
    /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable kp-knowledge-repo
sudo systemctl start kp-knowledge-repo
```

Check it started cleanly:

```bash
sudo systemctl status kp-knowledge-repo
sudo tail -f /var/log/kp-knowledge-repo/mcp-error.log
```

---

## Step 5 — Get the SSL certificate

```bash
sudo certbot certonly --nginx -d repo.innovatingwithcapella.com
```

---

## Step 6 — Install the nginx config

```bash
sudo cp /opt/knowledge_partner/kp/knowledge_repo/deploy/nginx_knowledge_repo.conf \
    /etc/nginx/sites-available/kp-knowledge-repo.conf

sudo ln -s /etc/nginx/sites-available/kp-knowledge-repo.conf \
    /etc/nginx/sites-enabled/kp-knowledge-repo.conf

sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 7 — Verify

Test the MCP endpoint responds:

```bash
curl -s -o /dev/null -w "%{http_code}" https://repo.innovatingwithcapella.com/mcp
```

A `405` (Method Not Allowed) means nginx is proxying correctly — the MCP endpoint only accepts POST.

---

## Updating the app

After pushing new code:

```bash
cd /opt/knowledge_partner
git pull
sudo systemctl restart kp-knowledge-repo
```

No re-install needed unless dependencies changed (in which case re-run Step 2).

---

## Troubleshooting

| Symptom | Check |
|---|---|
| 502 Bad Gateway | `systemctl status kp-knowledge-repo` — service may have crashed |
| 404 on `/mcp` | nginx config not linked — check `sites-enabled/` |
| SSL error | `certbot renew --dry-run` to verify cert renewal |
| MCP tool errors in Claude | `tail /var/log/kp-knowledge-repo/mcp-error.log` |
| Port 8002 not listening | `ss -tlnp \| grep 8002` — service not running |
