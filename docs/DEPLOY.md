# Deploying SanaTour API to a VPS

End-to-end recipe: Ubuntu VPS → public HTTPS API at `https://api.example.com`.

The stack runs as three containers behind the host's existing nginx (which terminates TLS via certbot):

```
Internet ── 443 ──> host nginx ──> app (uvicorn:8000) ──> postgres
                    (host:8001)                       \─> redis
```

If you're starting from scratch on a fresh VPS without an existing reverse proxy, install nginx first (`sudo apt install nginx`) and use certbot for TLS.

## 0. Prerequisites

- A VPS (1 vCPU / 1 GB RAM is enough for v0.1; bump to 2 GB once you add booking).
- A domain you control. DNS **A-record** for `api.example.com` pointing to the VPS public IP.
- SSH access as a non-root user with `sudo`.
- nginx already installed and running on the host (port 80/443).

## 1. Server bootstrap (one-time, skip if already done)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git ufw nginx certbot python3-certbot-nginx

# Firewall
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable

# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in so the group takes effect
```

## 2. Clone the repo

```bash
git clone https://github.com/<you>/sanotour-api.git
cd sanotour-api
```

## 3. Configure secrets

```bash
cp .env.example .env
nano .env
```

Set the production values:

| Variable | How to set |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` |
| `DATABASE_URL` | host = `postgres` (Docker service name), same password embedded |
| `REDIS_URL` | host = `redis` |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `INITIAL_SUPER_ADMIN_EMAIL` / `_PASSWORD` | your admin credentials |
| `CORS_ORIGINS` | JSON array of frontend origins, e.g. `["https://app.example.com"]` |

> The host-side port is hardcoded to `127.0.0.1:8001` in `docker-compose.prod.yml`. If that port is taken on your VPS, change it there and update the nginx `proxy_pass` line to match.

Verify `.env` is gitignored:

```bash
git check-ignore .env   # should print: .env
```

## 4. First boot

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

What happens:
1. Postgres + Redis start, healthchecks go green.
2. The `app` container runs `alembic upgrade head`, then `python -m scripts.seed`, then starts uvicorn on `:8000` (inside the container) bound to `127.0.0.1:8001` on the host.

Watch logs:

```bash
docker compose -f docker-compose.prod.yml logs -f app
```

Wait for `Uvicorn running on http://0.0.0.0:8000`, then sanity check from the host:

```bash
curl http://127.0.0.1:8001/api/v1/health
# {"status":"ok"}
```

## 5. Wire up nginx

Create `/etc/nginx/sites-available/api.example.com`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name api.example.com;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout    300s;
        proxy_connect_timeout 75s;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/api.example.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 6. TLS via certbot

DNS A-record must point to the VPS first.

```bash
sudo certbot --nginx -d api.example.com
```

Certbot fetches a Let's Encrypt cert, adds the SSL block to the nginx config, sets up the HTTP→HTTPS redirect, and registers auto-renewal.

## 7. Smoke test

```bash
curl https://api.example.com/api/v1/health
# {"status":"ok"}

curl -X POST https://api.example.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"<your INITIAL_SUPER_ADMIN_PASSWORD>"}'
```

OpenAPI docs: `https://api.example.com/docs`.

## 8. Day-to-day operations

### Deploy a new version

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build app
```

`app` re-runs `alembic upgrade head` on every start, so migrations apply automatically. Postgres and Redis are not recreated.

### View logs

```bash
docker compose -f docker-compose.prod.yml logs -f app
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

### Database access

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U sanotour -d sanotour
```

### Backups (manual)

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U sanotour sanotour | gzip > backup-$(date +%F).sql.gz
```

Automated daily backups via cron:

```cron
0 3 * * * cd /home/<user>/sanotour-api && docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U sanotour sanotour | gzip > /home/<user>/backups/sanotour-$(date +\%F).sql.gz
```

### Restore from backup

```bash
gunzip -c backup-2026-05-10.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U sanotour -d sanotour
```

### Stop everything

```bash
docker compose -f docker-compose.prod.yml down
# add -v to also wipe data volumes (DESTRUCTIVE)
```

## 9. Notes and gotchas

- **Postgres and Redis ports are not exposed to the host** — they're only reachable from inside the Docker network.
- **App is bound to `127.0.0.1:8001`**, not `0.0.0.0` — only reachable from the host (and from nginx through `proxy_pass`). The public never hits uvicorn directly.
- **`docker-compose.yml`** (the dev one) publishes Postgres on `:5432`. Don't run it on the VPS — only `docker-compose.prod.yml`.
- **certbot auto-renews** every ~60 days via systemd timer (`systemctl status certbot.timer`).
- **`uvicorn` runs single-process.** For v0.1 that's fine; for heavier load switch to `--workers N` or `gunicorn -k uvicorn.workers.UvicornWorker`.
- **Health check route:** `/api/v1/health` (no auth). Wire it into UptimeRobot or similar.
