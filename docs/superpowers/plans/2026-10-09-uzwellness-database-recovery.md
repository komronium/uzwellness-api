# UzWellness Database Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish and test a PostgreSQL recovery path, then safely bring the live database to migration head `601c80146dfd`.

**Architecture:** Run a root-managed, daily `pg_dump` service using local PostgreSQL peer access, store atomic custom-format archives in a private backup directory with finite retention, and verify restore into a uniquely named isolated database before touching production schema. Apply the one pending migration only after restore succeeds; leave external/off-host backup status explicit when VPS-provider access is unavailable.

**Tech Stack:** PostgreSQL 16, `pg_dump`, `pg_restore`, systemd service/timer, Alembic, bash, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-uzwellness-production-readiness-design.md`

## Global Constraints

- Never overwrite, drop, or restore over the production `sanotour` database during a restore drill.
- Store backups outside the application checkout with directory mode `0700` and archive mode `0600`.
- Publish a backup archive atomically only after `pg_dump` succeeds and `pg_restore --list` can read it.
- Preserve at least 14 days of verified daily backups; prune only matching archives older than retention.
- Apply migration `601c80146dfd` only after a restore drill succeeds and the migration preflight passes.
- Do not automatically downgrade the FK migration; downgrade restores cascade-delete behavior.
- A same-host backup does not count as protection against VPS loss; report provider/off-host state separately.

## Review Focus

- A failed dump must not replace or masquerade as the latest valid backup; test atomic publication and cleanup.
- `pg_dump` must use the local PostgreSQL peer-auth path without exposing DB credentials in command arguments.
- The restore drill must target only a fresh, uniquely named temporary DB and must clean it up on success or failure.
- Retention must delete only the script's own archive naming pattern and must never delete the newest successful dump.
- The FK migration must preserve existing payments and verify `ON DELETE RESTRICT` after application.

---

### Task 1: Add a safe, repeatable local PostgreSQL backup job

**Files:**
- Create: `deploy/backup/uzwellness-postgres-backup.sh`
- Create: `deploy/systemd/uzwellness-postgres-backup.service`
- Create: `deploy/systemd/uzwellness-postgres-backup.timer`
- Create: `tests/test_postgres_backup_script.py`
- Modify: `README.md` or `docs/deploy/production.md`

**Interfaces:**
- Consumes: Local PostgreSQL 16 cluster and database name `sanotour`.
- Produces: `/var/backups/uzwellness/sanotour-UTC_TIMESTAMP.dump` in PostgreSQL custom format; service exits nonzero on dump or validation failure.

- [ ] **Step 1: Write failing script tests**

Test with temporary fake `pg_dump`, `pg_restore`, `date`, and backup directories that the script (a) writes a temporary archive with private permissions, (b) validates it with `pg_restore --list`, (c) atomically renames only after success, (d) removes incomplete temporary output, and (e) prunes only matching files older than 14 days.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run pytest tests/test_postgres_backup_script.py -q`

Expected: FAIL because the backup script/service do not exist.

- [ ] **Step 3: Implement the backup script and systemd schedule**

Create `/var/backups/uzwellness` mode `0700`; use `umask 077`; dump as PostgreSQL OS user `postgres` through local peer auth; write to a temporary file in that directory; validate the archive; set mode `0600`; atomically rename; then prune matching archives older than 14 days. Add a oneshot service and daily timer with `Persistent=true`; do not store credentials in the unit.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_postgres_backup_script.py -q`

Expected: PASS, including simulated dump and validation failures.

- [ ] **Step 5: Commit**

```bash
git add deploy/backup/uzwellness-postgres-backup.sh deploy/systemd/uzwellness-postgres-backup.service deploy/systemd/uzwellness-postgres-backup.timer tests/test_postgres_backup_script.py README.md
git commit -m "ops(db): add verified local Postgres backups"
```

### Task 2: Install backup schedule and verify a real restore in isolation

**Files:**
- Host paths: `/var/backups/uzwellness`, `/etc/systemd/system/uzwellness-postgres-backup.service`, `/etc/systemd/system/uzwellness-postgres-backup.timer`
- Modify: `docs/deploy/production.md`

**Interfaces:**
- Consumes: Tested backup job from Task 1.
- Produces: One verified live archive and a documented isolated restore procedure.

- [ ] **Step 1: Preflight storage and Postgres tools**

Record `df` free space, `pg_database_size('sanotour')`, PostgreSQL major version, current Alembic revision, backup directory ownership/mode, and whether provider/off-host snapshots are configured. Stop if free space is insufficient for at least one compressed dump plus a restore copy.

- [ ] **Step 2: Install and run the oneshot backup once**

Create the backup directory as root mode `0700`; install tested service/timer files; run `systemctl daemon-reload` and `systemctl start uzwellness-postgres-backup.service`. Confirm the service succeeded and the resulting archive is root-readable only and passes `pg_restore --list`.

- [ ] **Step 3: Restore into an isolated temporary database**

Create a unique database such as `uzwellness_restorecheck_<UTC timestamp>` as OS user `postgres`; restore using `runuser -u postgres -- pg_restore --no-owner --no-privileges --dbname=<temporary database>`; verify expected tables and the Alembic version in that database. Never target `sanotour`. Drop only the uniquely named temporary database after recording successful verification.

- [ ] **Step 4: Enable the daily timer and verify scheduling**

Run: `systemctl enable --now uzwellness-postgres-backup.timer` and `systemctl list-timers uzwellness-postgres-backup.timer`

Expected: timer enabled with a future run; latest oneshot success remains visible in the journal.

- [ ] **Step 5: Document the recovery commands and limitations**

Document archive location, 14-day retention, restore-to-new-database commands, success checks, cleanup, and that off-host snapshots remain unverified unless provider access confirms them.

### Task 3: Preflight and apply the pending FK migration

**Files:**
- Verify: `alembic/versions/601c80146dfd_payments_booking_id_restrict_delete.py`
- Host DB: `sanotour`

**Interfaces:**
- Consumes: A successful isolated restore drill from Task 2.
- Produces: Production DB at `601c80146dfd` with `payments_booking_id_fkey` set to `ON DELETE RESTRICT`.

- [ ] **Step 1: Reconfirm the expected migration chain and production state**

Run `uv run alembic heads` locally, then on the host run `.venv/bin/alembic current` from `/var/www/uzwellness-api` and inspect `payments_booking_id_fkey` through read-only PostgreSQL catalog queries. Confirm current is `9136b80e268a` and target head is `601c80146dfd`; stop if the graph differs.

- [ ] **Step 2: Confirm a fresh validated backup exists**

Run `pg_restore --list` on the latest archive and verify timestamp/permissions. Stop if validation fails or the restore drill has not completed.

- [ ] **Step 3: Apply only the known pending migration**

Run from the deployed application checkout: `.venv/bin/alembic upgrade 601c80146dfd`. Do not run downgrade automatically.

- [ ] **Step 4: Verify migration and constraint behavior**

Run `.venv/bin/alembic current` and query PostgreSQL catalogs to confirm revision `601c80146dfd` and `confdeltype = 'r'` (RESTRICT) for `payments_booking_id_fkey`. Re-run `/api/health/db`.

- [ ] **Step 5: Commit the runbook update**

```bash
git add docs/deploy/production.md
git commit -m "docs(ops): document database recovery and migration"
```

## Final verification

- The backup timer is enabled; a real archive is private, readable by `pg_restore`, and restored successfully into a temporary DB.
- Production Alembic revision is `601c80146dfd`; the live API and DB health checks pass.
- Report whether off-host/provider backup is actually configured. Do not imply that same-host retention is disaster recovery.
