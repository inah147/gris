# Gris - Docker Deployment Guide (frappe_docker)

Deploy the Gris Frappe app using the official **frappe_docker** pattern with
immutable Docker images.

> **Key concept:** Apps are baked into the Docker image at build time.
> You do **not** run `bench get-app` inside a running container.
> To update the app, rebuild the image and redeploy.

---

## Prerequisites

| Requirement | Minimum |
|---|---|
| Docker Engine | 20.10+ |
| Docker Compose | v2 |
| RAM | 4 GB |
| Disk | 20 GB |
| Git | any |

---

## Repository Structure (Docker files)

```
gris/
├── apps.json              # Apps to install in the image
├── Containerfile           # Multi-stage build (custom image)
├── compose.yaml            # Production docker compose
├── .env.example            # Environment variables template
└── resources/
    ├── nginx-template.conf # Nginx config template
    └── nginx-entrypoint.sh # Nginx startup script
```

---

## Step 1 — Edit `apps.json`

Update `apps.json` with the URL and branch of your gris repo:

```json
[
  {
    "url": "https://github.com/AtelieDigital/gris",
    "branch": "main"
  }
]
```

> If you need ERPNext or other apps, add them to this array.

---

## Step 2 — Build the Docker Image

```bash
# Generate APPS_JSON_BASE64 from apps.json
export APPS_JSON_BASE64=$(base64 -w 0 apps.json)

# Build the image
docker build \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg=FRAPPE_BRANCH=version-15 \
  --build-arg=PYTHON_VERSION=3.11.10 \
  --build-arg=NODE_VERSION=18.20.4 \
  --build-arg=APPS_JSON_BASE64=$APPS_JSON_BASE64 \
  --tag=gris:latest \
  --file=Containerfile .
```

This builds a production image with Frappe v15 + your gris app baked in.

> **macOS / base64 without `-w`?** Use `export APPS_JSON_BASE64=$(base64 apps.json | tr -d '\n')`

---

## Step 3 — Configure Environment

```bash
cp .env.example .env
```

Edit `.env` — at minimum set:

```dotenv
DB_PASSWORD=a-strong-password
FRAPPE_SITE_NAME_HEADER=gris.local
```

---

## Step 4 — Start All Services

```bash
docker compose up -d
```

This starts: **db**, **redis-cache**, **redis-queue**, **configurator**,
**backend**, **frontend** (nginx), **websocket**, **queue-short**,
**queue-long**, **scheduler**.

Wait for `configurator` to finish:

```bash
docker compose logs configurator -f
```

---

## Step 5 — Create the Site

```bash
docker compose exec backend bench new-site gris.local \
  --mariadb-user-host-login-scope='%' \
  --db-root-password=a-strong-password \
  --admin-password=admin \
  --install-app gris
```

> Replace passwords with what you set in `.env`.

---

## Step 6 — Access the Application

Open **http://your-server:8080** in a browser.

Login: `Administrator` / `admin` (or whatever `--admin-password` you used).

---

## Common Operations

### Run database migrations (after code update)

```bash
docker compose exec backend bench --site gris.local migrate
```

### Backup

```bash
docker compose exec backend bench --site gris.local backup --with-files
```

### View logs

```bash
docker compose logs backend -f
docker compose logs scheduler -f
```

### Enter the container shell

```bash
docker compose exec backend bash
```

### Restart all services

```bash
docker compose restart
```

---

## Updating the App

Since apps are **immutable** inside the Docker image:

```bash
# 1. Pull latest code
git pull

# 2. Rebuild the image
export APPS_JSON_BASE64=$(base64 -w 0 apps.json)
docker build \
  --build-arg=FRAPPE_BRANCH=version-15 \
  --build-arg=APPS_JSON_BASE64=$APPS_JSON_BASE64 \
  --tag=gris:latest \
  --file=Containerfile .

# 3. Recreate containers with new image
docker compose up -d

# 4. Run migrations
docker compose exec backend bench --site gris.local migrate
```

---

## Architecture

```
                    ┌──────────────┐
     :8080    ───►  │   frontend   │  (nginx)
                    │   (proxy)    │
                    └──┬───────┬───┘
                       │       │
              ┌────────▼──┐  ┌─▼──────────┐
              │  backend   │  │ websocket  │
              │ (gunicorn) │  │ (node.js)  │
              └─────┬──────┘  └────┬───────┘
                    │              │
        ┌───────────┼──────────────┤
        │           │              │
   ┌────▼───┐  ┌───▼────┐  ┌──────▼──────┐
   │  db    │  │ redis  │  │   redis     │
   │(maria) │  │ cache  │  │   queue     │
   └────────┘  └────────┘  └─────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │              │
              ┌─────▼────┐ ┌─────▼────┐  ┌──────▼─────┐
              │ q-short  │ │ q-long   │  │ scheduler  │
              │ (worker) │ │ (worker) │  │  (cron)    │
              └──────────┘ └──────────┘  └────────────┘
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `configurator` keeps restarting | Check DB is healthy: `docker compose logs db` |
| Site not accessible | Verify `FRAPPE_SITE_NAME_HEADER` matches your site name |
| Static assets 404 | Run `docker compose exec backend bench build` then restart frontend |
| Permission denied on volumes | Ensure volumes are owned by uid 1000 (frappe user) |
| Build fails on `bench init` | Check git repo URL in `apps.json` is accessible |

---

## References

- [frappe_docker](https://github.com/frappe/frappe_docker) — official Docker images & compose
- [Docker Immutability](https://github.com/frappe/frappe_docker/blob/main/docs/01-getting-started/02-docker-immutability.md)
- [Build Setup](https://github.com/frappe/frappe_docker/blob/main/docs/02-setup/02-build-setup.md)
- [Frappe Framework Docs](https://frappeframework.com/docs)
