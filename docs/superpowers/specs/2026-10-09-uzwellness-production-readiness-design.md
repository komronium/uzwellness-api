# UzWellness API Production Readiness Design

**Date:** 2026-10-09
**Scope:** Backend API repository and its current systemd/VPS deployment. Frontend, DNS, and provider consoles are outside the available source scope.

## Goal

Harden the existing VPS deployment without replacing systemd, protect customer and payment data, reconcile the production database with the deployed code, and restore reproducible release checks. Readiness requires least-privilege service and secret access, a tested database recovery path, the database at the repository migration head, and passing local or hosted checks.

## Evidence and constraints

- Live API and DB health succeed; Redis responds to `PING`.
- Live checkout revision matches repository commit `2d5290e`.
- Live `.env` is `root:root` mode `0644`; Uvicorn runs as root and its Unix socket is mode `0666`. The deployed Uvicorn 0.46.0 code explicitly resets Unix socket permissions to `0666`, so `UMask` alone cannot secure it.
- The active unit is `uzwellness.service`; the tracked copy is named `uzwellness-api.service`.
- Production Alembic revision is `9136b80e268a`; repository head is `601c80146dfd`, which changes `payments.booking_id` to `ON DELETE RESTRICT`.
- No UzWellness database backup/restore process was found on the host. External provider snapshots were not inspected.
- Latest GitHub Actions did not start because of an account billing lock. Local test tooling is unavailable in the audit workspace.
- Production has `DEBUG=false`, HTTPS-only exact CORS origins, Resend, and configured Uzum providers.

## Selected approach

Keep the current VPS, Nginx, PostgreSQL, Redis, and systemd model. Use the actual unit name `uzwellness.service` as the canonical tracked name. A Docker migration would add risk without solving a current requirement.

## Design

### Service and secrets

- Set the live `.env` to root-only access and never print/copy its values to source control, process arguments, or logs.
- Run Uvicorn as a dedicated `uzwellness` user with write access only to required runtime/upload paths.
- Give Nginx access to the Unix socket through a dedicated group and mode `0660`; restrict the runtime directory to the service and group.
- Update tracked systemd and runbook names to match the active `uzwellness.service`, retaining boot enablement and restart behavior.
- Inventory secret names only. Prepare provider rotation steps for secrets that may have been readable locally. Rotate only with replacement credentials ready; never expose secret values.

### Database recovery and migration

- Check free disk space, DB size, and provider snapshot status.
- Create a root-only PostgreSQL backup outside the app checkout, with documented retention. Do not treat it as verified until restoring it into an isolated temporary database and checking schema/data succeeds.
- Confirm the existing FK and payment data, then apply `601c80146dfd` during a controlled service window. Verify the revision and FK afterward.
- Stop before migration if space is inadequate or backup restore verification fails.
- Track off-host backups as an open requirement if provider snapshot or remote storage access is unavailable; same-host copies do not cover VPS loss.

### API edge and deployment record

- Add standard HTTPS/security response headers to the API Nginx server and verify them after reload.
- Keep current HTTPS certificate renewal and exact CORS origins.
- Make tracked Nginx/systemd files and runbook match live configuration. Treat Compose as development configuration and bind any published ports to loopback if Compose remains available.
- Preserve provider-status verification for payment callbacks; callback payloads must not authorize payment state changes.

### Release verification

- Recreate the environment with Python 3.13 and `uv.lock`; run Ruff, compile, Alembic-head validation, and the full test suite outside production.
- Fix failures before production deployment. A GitHub billing failure is not a passing CI result.
- Recheck GitHub billing as an external dependency; if blocked, distinguish local verification from hosted CI status.
- After rollout, verify API/DB health, Redis, unit restart, TLS, security headers, migration state, checkout availability, and Nginx-to-socket access.

## Rollout and recovery

1. Record current service state, commit, DB revision, and API behavior.
2. Run repository checks before touching production.
3. Create and restore-verify a DB backup.
4. Prepare the service user, writable paths, and matching systemd/Nginx files.
5. Apply the migration, switch/restart the service, and immediately run health/proxy smoke checks.
6. On failure, restore the prior unit/configuration and restart the previous app revision. Do not automatically downgrade the migration; downgrade restores cascade-delete behavior and needs separate review.
7. Report provider credential rotations and off-host backup status as open dependencies when provider access is unavailable.

## Risks

- Running as a dedicated user may reveal undocumented write paths; inventory and validate ownership first.
- The migration changes payment deletion behavior; backup and data checks precede it.
- JWT key rotation invalidates active sessions; provider key rotation can interrupt payments without coordination.
- Same-host backups do not protect from VPS loss.
- One systemd worker restart may cause a brief API interruption.

## Out of scope

Frontend/Vercel, DNS, payment-provider account changes, formal third-party penetration testing, container migration, and product booking/payment behavior changes.
