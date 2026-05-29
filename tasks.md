# Backend Cleanup Tasks

Goal: make the backend code simple, readable, maintainable, and SOLID enough that a new backend engineer can understand each file without reverse-engineering hidden behavior.

## Rules For Every Cleanup PR

- Keep public API behavior unchanged unless the task explicitly says otherwise.
- Prefer smaller cohesive files over mixed business concerns.
- Keep comments rare. Use comments only for business invariants, security, money movement, or non-obvious operational behavior.
- Keep routers thin: parse request, authorize, call service, return schema.
- Keep services focused on one business capability.
- Do not put query-heavy logic, formatting logic, and mutation logic in the same method.
- Avoid duplicate parsing, permission checks, pricing calculations, and response mapping.
- Add or update tests for every behavior-preserving refactor that touches queries, money, availability, bookings, uploads, or permissions.
- Before commit: run Ruff, compile, focused tests, and full tests when shared code changes.

## Acceptance Checklist

- No backend file should exceed 350 lines without a clear reason.
- No service method should exceed 60 lines without extraction.
- No router endpoint should contain business rules beyond validation and authorization.
- OpenAPI tags should remain business-friendly and not too broad.
- `FRONTEND_HANDOFF.md` should contain only the latest frontend-facing API changes.
- All image upload endpoints must store WebP using config-driven limits.
- Finance, booking, availability, and commission behavior must remain covered by tests.

## Phase 1: File Boundaries

1. Split `app/core/meta.py` - Done
   - Current issue: one large static catalog file.
   - Target:
     - `app/core/meta/amenities.py`
     - `app/core/meta/rooms.py`
     - `app/core/meta/sanatoriums.py`
     - `app/core/meta/travel.py`
     - `app/core/meta/__init__.py`
     - extra split: `app/core/meta/medical.py`, `app/core/meta/stay.py`
   - Keep the API response unchanged.
   - Tests: `tests/test_meta.py`.

2. Split `app/api/routers/sanatoriums.py` - Done
   - Current issue: CRUD, search, featured cards, images, and nested data live together.
   - Target:
     - `sanatoriums.py`: core CRUD/list/detail
     - `sanatorium_images.py`: `/sanatoriums/{id}/images`
     - `sanatorium_featured.py`: `/sanatoriums/featured`
     - `sanatorium_search.py`: `/sanatoriums/search`
   - Keep paths unchanged.
   - Tests: sanatorium, search, image tests.

3. Split `app/api/routers/rooms.py` further if needed - Done
   - Already split image routes.
   - Next target:
     - keep CRUD/list/detail in `rooms.py`
     - move `/rooms/search` to `room_search.py` router if it grows
     - move `/rooms/{id}/availability...` to `room_availability.py`
   - Keep paths unchanged.

4. Review large schema modules - Done
   - `app/schemas/sanatorium.py` is split and under the target size.
   - `app/schemas/room.py` is split and under the target size:
     - room base/create/update
     - room read/list/search
     - room image - Done
     - availability - Done
   - Keep imports stable where possible.

## Phase 2: Service Responsibilities

1. Refactor `SanatoriumService` - Done
   - Current issue: mixed CRUD, listing, featured card query, admin ownership, and JSON preparation.
   - Target:
     - `SanatoriumService`: CRUD and access-safe mutation
     - `SanatoriumQueryService`: list/detail/search queries, featured card query, and pricing row selection
   - Keep transaction boundaries explicit.
   - Tests: `tests/test_sanatoriums.py`, `tests/test_sanatorium_search.py`.

2. Refactor `RoomService` - Done
   - Current issue: still owns CRUD, inventory safety, availability mutation, and enrichment.
   - Target:
     - `RoomService`: CRUD and room mutation
     - `RoomAvailabilityService`: block/upsert/read availability
     - `RoomSearchService`: already started in `room_search.py`
   - Tests: availability, room extras, booking flow.

3. Refactor `FinanceService` - Done
   - Current issue: likely mixes reporting, aggregation, commission math, and role filtering.
   - Target:
     - pure commission calculation helpers
     - report/query service
     - role visibility rules in one place
   - Must preserve exact totals.
   - Tests: `tests/test_finance.py`, commission tests, booking pricing tests.

4. Review booking services - Done
   - Keep booking creation flow readable step-by-step.
   - Extract only when a block has a stable name:
     - price quote
     - inventory lock
     - commission snapshot
     - payment initialization
   - Avoid clever abstractions around money.

## Phase 3: Shared Helpers

1. Centralize response mapping - Done
   - Avoid repeated `model_validate(...).model_copy(update=...)`.
   - Add small mapper helpers only where the same mapping appears 3+ times.
   - Do not create a generic mapper framework.

2. Centralize upload behavior - Done
   - Keep all image conversion limits in `app/core/config.py`.
   - Keep document uploads separate from image uploads.
   - Add tests for:
     - JPEG to WebP
     - PNG to WebP
     - WebP to normalized WebP
     - too-large byte size
     - too-large dimensions

3. Centralize permissions only where repeated - Done
   - Use small functions like `assert_sanatorium_access`.
   - Do not hide role rules in decorators if the endpoint needs readable ownership context.
   - Kept ownership rules in `require_roles`, `assert_sanatorium_access`,
     `SanatoriumPolicy`, and booking visibility helpers.

## Phase 4: Comments And Readability

1. Remove comments that only narrate the code - Done
2. Keep comments that explain - Done:
   - money invariants
   - currency consistency
   - inventory consistency
   - auth/session security
   - irreversible external side effects
3. Replace long comments with clear helper names where possible - Done
4. Prefer descriptive variable names over explanatory comments - Done

## Phase 5: Tests And Safety - Done

1. Add regression tests before risky refactors - Done
2. Use focused tests during development - Done
3. Run full suite before commit when touching - Done:
   - models
   - schemas used by many routers
   - services used by bookings or finance
   - upload processing
   - permissions
4. Required commands before commit:

```bash
.venv/bin/ruff check app tests scripts alembic
python -m compileall -q app
env UV_CACHE_DIR=/tmp/uv-cache TEST_DATABASE_URL=postgresql+asyncpg://sanotour:sanotour@localhost:5432/sanotour_test uv run pytest
```

Verification run:

- Ruff: passed
- Compile: passed
- Focused regression tests: 156 passed
- Full test suite: 428 passed

## Completed Order

1. Split `app/core/meta.py`.
2. Split sanatorium image/search/featured routers.
3. Split room availability router and service.
4. Split `RoomService` availability mutation into `RoomAvailabilityService`.
5. Split `SanatoriumService` featured/list query logic.
6. Audit `FinanceService` with tests around exact commission visibility.
7. Split large schema modules, including sanatorium service-matrix schemas.
8. Centralize repeated response mapping.
9. Do final comment/readability pass.

## Definition Of Done

- Large files are reduced or have a documented reason to stay large.
- Each module has one clear responsibility.
- A new engineer can identify where to edit CRUD, search, images, availability, bookings, and finance without scanning unrelated code.
- Tests pass.
- OpenAPI remains clean and understandable.
- No unrelated local changes are committed.

## Full Code Audit Round 2

Goal: inspect every backend module, not just previously touched files, and keep reducing methods that mix query construction, business rules, and response formatting.

### Phase 1: Long Methods

1. Split `FinanceService.summary` and `FinanceService.orders` - Done.
   - Issue: both methods build filters, SQL, money rollups, and response dicts inline.
   - Target:
     - service methods read as orchestration only
     - query construction helpers are named by report type
     - row serialization helpers own API dict shape
   - Tests: `tests/test_finance.py`, `tests/test_sanatorium_commission.py`, booking pricing tests.

2. Split `RoomBookingFlow.create` - Done.
   - Issue: validation, reservation, rate-plan adjustment, extra-bed pricing, booking creation, notification, and email are in one method.
   - Target:
     - clear pricing quote helper
     - booking object builder
     - side effects remain explicit
   - Tests: room booking flow, constraints, pricing, availability.

3. Split `RoomBookingFlow._build_extra_beds` - Done.
   - Issue: config loading, ownership validation, currency conversion, and model building are together.
   - Target:
     - load configs once
     - validate config per item
     - convert extra-bed price in one helper
   - Tests: booking flow and pricing.

4. Split stay search internals - Done.
   - Issue: `SearchService.search_stays`, `_find_candidates`, and `room_search.search_rooms` contain query logic and availability/pricing logic together.
   - Target:
     - search query builder helpers
     - availability calculation helpers
     - result ranking helpers
   - Tests: sanatorium search, wellness listing, availability.

### Phase 2: Router Boundary Audit

1. Review routers over 120 lines:
   - `packages.py`
   - `treatment_focuses.py`
   - `destinations.py`
   - `room_images.py`
   - `sanatorium_images.py`
   - Status: audited with function-length scan; endpoint bodies are under the
     current threshold and no behavior-neutral split is needed now.
2. Move repeated upload/form parsing into helpers only when it reduces duplication.
   - Status: existing upload helpers stay as-is; no new abstraction added.
3. Keep endpoint functions below 40 lines unless they are purely parameter declarations.
   - Status: no endpoint currently requires immediate extraction for business logic.

### Phase 3: Service Boundary Audit

1. Review services over 180 lines:
   - `package_service.py`
   - `destination_service.py`
   - `user_service.py`
   - `payment_service.py`
   - `b2b_service.py`
   - `review_service.py`
   - Status: high-risk long methods were reduced first; remaining services have
     cohesive methods under the current threshold.
2. Extract helpers only when a method has a stable business name.
   - Status: applied to finance reports, booking flows, room availability,
     sanatorium list filters, and search.
3. Avoid abstract base classes unless there are at least two real implementations.
   - Status: no new abstract layer added.

### Phase 4: Schema And Model Audit

1. Review schemas over 250 lines:
   - `room.py`
   - `sanatorium.py`
   - Status: `SanatoriumRead.from_obj` split into named mapping helpers.
2. Split only if a section can be named by business concept.
   - Status: no extra schema split added beyond named mapping helpers.
3. Keep backward-compatible imports where existing tests or callers depend on them.
   - Status: kept.

### Phase 5: Verification

1. Run function-length audit again and keep every non-schema method near 60 lines or document why it stays larger - Done.
2. Run Ruff and compile - Done.
3. Run focused tests for every touched area - Done.
4. Run full suite before commit - Done.

Round 2 focused verification:

- Finance/commission/pricing: 22 passed
- Booking flows, package bookings, session bookings: 44 passed
- Availability and booking flow: 54 passed
- Search and availability: 45 passed
- Sanatorium/destination: 96 passed
- Sanatorium/locale/policy: 100 passed
- Full suite: 428 passed

Round 2 final audit:

- Longest backend file: 350 lines
- Longest function/method: 58 lines
- Ruff: passed
- Compile: passed

## Full Code Audit Round 3

Goal: verify architecture boundaries and remove low-value comments/type ignores without changing behavior.

### Phase 1: Type Ignore And Dead Marker Cleanup

1. Remove avoidable `type: ignore` comments - Done.
   - Replaced locale casts with explicit locale narrowing.
   - Replaced post-write return ignores with required-load helpers.
   - Replaced UUIDv7 ignore with `getattr`.
   - Replaced extra-bed exchange-rate ignore with runtime sentinel guard.
2. Remove `pass`, TODO, and FIXME markers - Done.
   - `Base` now uses `__abstract__ = True`.
   - No `pass`, TODO, FIXME, or `type: ignore` remains in `app`.

### Phase 2: Layer Boundary Check

1. Ensure `models` do not import API, services, or schemas - Done.
2. Ensure `schemas` do not import API or services - Done.
3. Ensure `core` does not import API or services - Done.
   - Moved FastAPI auth-aware rate-limit wrappers to `app/api/rate_limits.py`.
   - Kept `app/core/rate_limit.py` as pure rate-limit logic.
4. Ensure services do not import API routers - Done.

### Phase 3: Comment Cleanup

1. Remove low-value docstrings/comments from touched utility files - Done.
2. Keep only business/security/money/invariant comments - Done.
   - Remaining comments are around refunds, currency/package invariants,
     auth replay defense, rate-plan snapshots, and route-specific ownership.

### Phase 4: Verification

1. Ruff and compile targeted files - Done.
2. Layer check - Done.
3. Focused tests - Done:
   - Auth, booking flow, booking constraints, booking pricing,
     package bookings, session bookings, locale resolution: 72 passed.
4. Full suite before commit - Done.

Round 3 final verification:

- Ruff: passed
- Compile: passed
- Layer check: passed
- `type: ignore`, `pass`, TODO, FIXME scan: clean
- Focused tests: 72 passed
- Full suite: 428 passed
