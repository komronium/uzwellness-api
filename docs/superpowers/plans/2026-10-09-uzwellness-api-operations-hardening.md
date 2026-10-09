# UzWellness API Operations Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the live API process, secrets, Unix socket, and Nginx edge while keeping the existing systemd deployment model.

**Architecture:** Keep the live unit name `uzwellness.service` and run its Uvicorn process as a dedicated account with only upload/runtime write access. Load secrets through systemd from a root-only `.env`; allow Nginx to access only the restricted Unix socket. Apply equivalent, loopback-only defaults to local Compose ports and verify with repository checks plus live health/header smoke checks.

**Tech Stack:** FastAPI/Uvicorn, systemd, Nginx, PostgreSQL/Redis, Docker Compose, pytest, Ruff, Python 3.13, uv.

**Spec:** `docs/superpowers/specs/2026-10-09-uzwellness-production-readiness-design.md`

## Global Constraints

- Preserve the running VPS/systemd architecture and the actual `uzwellness.service` unit name.
- Never print, commit, or put secret values in process arguments or logs.
- Keep production CORS limited to exact HTTPS origins.
- Keep Uvicorn reachable only through the Unix socket; Nginx remains the public HTTP/TLS edge.
- Run all application tests outside production with Python 3.13 and the committed `uv.lock`.
- Never point the test suite at the live `sanotour` database; use isolated local PostgreSQL/Redis or a working CI runner.
- Keep the API health check passing before and after every live service switch.

## Review Focus

- The service cannot read its environment file after dropping root; systemd must load it before starting the dedicated user process.
- Nginx must retain socket access after the process user/group change; verify the live proxied health request.
- The app must retain write permission for uploads while the code and virtualenv stay read-only to the service.
- Nginx `add_header` inheritance may drop headers at nested locations; verify the actual API response, not just config text.
- Docker Compose must not publish DB/Redis/API listeners on all interfaces; verify resolved port bindings.

---

### Task 0: Restrict production environment-file access immediately

**Files:**
- Host file: `/var/www/uzwellness-api/.env`

**Interfaces:**
- Consumes: Existing root-owned production environment file; systemd has already loaded it into the running process.
- Produces: Same file and owner with mode `0600`, without restarting the API or printing its contents.

- [ ] **Step 1: Confirm metadata only**

Run `stat -c '%U:%G %a %n' /var/www/uzwellness-api/.env`; expect `root:root 644` and do not read the file.

- [ ] **Step 2: Restrict file permissions**

Run `chmod 0600 /var/www/uzwellness-api/.env` as root. This does not change the loaded environment or require an API restart.

- [ ] **Step 3: Verify permissions and service health**

Confirm metadata reports `root:root 600`, `systemctl is-active uzwellness` remains active, and `/api/health` plus `/api/health/db` still return success.

- [ ] **Step 4: Record secret-rotation follow-ups**

List only names of configured credential types in the private operations checklist. Do not display their values; coordinate replacements with providers before changing payment/email integrations.

### Task 1: Align tracked deployment records with the active host

**Files:**
- Rename: `deploy/systemd/uzwellness-api.service` -> `deploy/systemd/uzwellness.service`
- Modify: `deploy/nginx/api.uzwellness.com`
- Modify: `README.md` and relevant deployment notes found by `rg -n 'uzwellness-api|systemctl' .`

**Interfaces:**
- Consumes: Current live unit name `uzwellness.service` and Nginx Unix-socket upstream `/run/uzwellness/uvicorn.sock`.
- Produces: Tracked deployment files and commands use the same active unit/socket names.

- [ ] **Step 1: Write the failing deployment-consistency test/check**

Add a small test under `tests/test_deployment_config.py` that globs `deploy/systemd/uzwellness*.service`, asserts exactly one canonical file named `uzwellness.service`, then checks its working directory/environment file against the live paths and its socket against the Nginx upstream. With the current `uzwellness-api.service` name, the test must fail on the canonical-name assertion.

- [ ] **Step 2: Run the focused check and verify it fails**

Run: `uv run pytest tests/test_deployment_config.py -q`

Expected: FAIL because the tracked unit currently has the mismatched `uzwellness-api.service` name and/or deployment path identity.

- [ ] **Step 3: Align deployment references**

Rename the systemd template to `deploy/systemd/uzwellness.service`; update its header comment and `README.md`/runbook restart instructions to use `systemctl restart uzwellness`. Preserve the existing socket path and reverse proxy.

- [ ] **Step 4: Verify the focused check**

Run: `uv run pytest tests/test_deployment_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/systemd README.md tests/test_deployment_config.py
git commit -m "docs(deploy): align API service unit name"
```

### Task 2: Restrict the service account, filesystem writes, and socket

**Files:**
- Modify: `deploy/systemd/uzwellness.service`
- Modify: `tests/test_deployment_config.py`

**Interfaces:**
- Consumes: Unit identity from Task 1.
- Produces: A root-managed systemd unit that runs Uvicorn as `uzwellness`, grants only `www-data` socket access, and limits writable paths to uploads/runtime.

- [ ] **Step 1: Add failing assertions for least-privilege unit settings**

Extend `tests/test_deployment_config.py` to assert `User=uzwellness`, `Group=www-data`, `UMask=0007`, `RuntimeDirectoryMode=0750`, `ExecStartPost=/usr/bin/chmod 0660 /run/uzwellness/uvicorn.sock`, restart behavior, and explicit write protection for the upload directory. Uvicorn 0.46.0 explicitly chmods its Unix socket to `0666` after binding, so the umask alone does not secure it.

- [ ] **Step 2: Run the focused check and verify it fails**

Run: `uv run pytest tests/test_deployment_config.py -q`

Expected: FAIL on the current `User=root`, `Group=root`, and permissive runtime/socket defaults.

- [ ] **Step 3: Harden the unit template**

Set `User=uzwellness`, `Group=www-data`, `UMask=0007`, and a `0750` runtime directory. Add `ExecStartPost=/usr/bin/chmod 0660 /run/uzwellness/uvicorn.sock` because the deployed Uvicorn version resets the socket to `0666`; verify this exact behavior after restart. Add `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, `NoNewPrivileges=true`, and `ReadWritePaths=/var/www/uzwellness-api/uploads`. Keep the working directory and virtualenv readable/executable; do not add `.env` to `ReadWritePaths`.

- [ ] **Step 4: Verify the focused check**

Run: `uv run pytest tests/test_deployment_config.py -q`

Expected: PASS; the service explicitly changes the Uvicorn-created socket to `0660`, and the upload directory remains writable.

- [ ] **Step 5: Commit**

```bash
git add deploy/systemd/uzwellness.service tests/test_deployment_config.py
git commit -m "security(deploy): run API with least privilege"
```

### Task 3: Harden API response headers and local Compose bindings

**Files:**
- Modify: `deploy/nginx/api.uzwellness.com`
- Modify: `docker-compose.yml`
- Modify: `tests/test_deployment_config.py`

**Interfaces:**
- Consumes: Existing Nginx API server and Compose services.
- Produces: API responses with standard HTTPS/security headers and Compose ports bound only to loopback.

- [ ] **Step 1: Add failing config checks**

Assert the API Nginx server config includes `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy` with `always`; assert Compose publishes `127.0.0.1` bindings for PostgreSQL, Redis, and the API.

- [ ] **Step 2: Run the focused check and verify it fails**

Run: `uv run pytest tests/test_deployment_config.py -q`

Expected: FAIL because API responses lack these headers and Compose currently binds all published ports to all interfaces.

- [ ] **Step 3: Apply the config changes**

Add headers at the API server block and confirm any nested location that adds its own header repeats inherited security headers as needed. Bind Compose host ports to `127.0.0.1` and preserve their current container ports.

- [ ] **Step 4: Verify the focused check and parsed Compose model**

Run: `uv run pytest tests/test_deployment_config.py -q` and `docker compose config`

Expected: PASS; host bindings resolve to loopback only.

- [ ] **Step 5: Commit**

```bash
git add deploy/nginx/api.uzwellness.com docker-compose.yml tests/test_deployment_config.py
git commit -m "security(deploy): restrict API edge and local ports"
```

### Task 4: Run full repository checks before production changes

**Files:**
- Verify: repository, especially `tests/`, `deploy/`, and Alembic migration graph.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: A tested release candidate; no production server mutation in this task.

- [ ] **Step 1: Run the full check set**

Run: `uv run ruff check .`, `python -m compileall app`, `test "$(uv run alembic heads | wc -l)" = "1"`, `uv run pytest` with isolated PostgreSQL 16/Redis. If local test services are unavailable, wait for hosted CI billing to be resolved; never substitute the production DB.

Expected: all commands pass on Python 3.13 using `uv.lock`.

- [ ] **Step 2: Commit any check-only fixes separately**

Do not bundle unrelated application behavior changes into deployment hardening.

### Task 5: Stage and switch the live API service

**Files:**
- Host paths: `/etc/systemd/system/uzwellness.service`, `/var/www/uzwellness-api/.env`, `/var/www/uzwellness-api/uploads`, `/run/uzwellness/uvicorn.sock`

**Interfaces:**
- Consumes: Tested unit/Nginx files from Tasks 1–4; backup/migration readiness from the database plan.
- Produces: Active non-root API service with root-only secrets and a restricted socket.

- [ ] **Step 1: Record current state and preflight**

Record active unit, current commit, DB revision, upload owner/mode, disk space, and health response. Confirm the database recovery plan has completed before continuing.

- [ ] **Step 2: Prepare the dedicated account and filesystem permissions**

First change the live `.env` to `root:root` mode `0600` (systemd has already loaded its current environment; this permission change itself needs no restart). Then create system account `uzwellness` if absent; make uploads writable by it; ensure the application code and virtualenv are readable/executable but not writable by the service user. Inventory potentially exposed secret names without printing values and record required provider-side rotations as open follow-up until replacement credentials are issued.

- [ ] **Step 3: Install config and restart the existing unit name**

Install the tested unit as `/etc/systemd/system/uzwellness.service`, reload systemd, restart `uzwellness.service`, and reload Nginx only after `nginx -t` succeeds.

- [ ] **Step 4: Verify the live service**

Check `systemctl is-active/is-enabled uzwellness`, process UID/GID, socket mode `0660`, socket directory mode `0750`, `/api/health`, `/api/health/db`, Nginx upstream access, upload directory writability, and API security headers. Confirm ports 5432/6379 remain loopback-only.

- [ ] **Step 5: Roll back on failure**

Restore the recorded unit/Nginx config and prior file ownership, restart `uzwellness.service`, then rerun health checks. Preserve the failure output without printing secrets.

## Final verification

- The GitHub Actions billing lock is external. Check latest run status; do not mark hosted CI as passing unless a run starts and succeeds.
- Provider credential rotation for any secret previously readable from `.env` requires issuing replacement credentials in the relevant provider console. Do not claim rotation is complete without that confirmation.
