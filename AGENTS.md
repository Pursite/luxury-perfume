# AGENTS.md

## Project Context

Luxury Perfume is a production-oriented perfume e-commerce backend built with
Django and Django REST Framework.

Main architecture:

request
→ view
→ serializer
→ service for mutations / selector for reads
→ model / PostgreSQL
→ response

The project uses PostgreSQL, Redis, Celery, Simple JWT, django-filter, Pillow,
Gunicorn, Docker Compose, and Pytest.

`apps.users` owns authentication, OTP, JWT, profiles, and addresses.
`apps.products` owns the fragrance catalogue, products, categories, brands,
fragrance notes, images, filtering, caching, and thumbnail processing.
`apps.cart` owns owner-bound purchase-intent carts and synchronous Cart writes.
`apps.orders` owns checkout snapshots, stock reservations, and fulfillment
transitions. `apps.payments` owns Payment attempts, verification, and Refunds.
`apps.notifications` owns the durable Order-SMS outbox and delivery state.
`apps.lib` owns shared infrastructure.

---

## Priorities

Priorities, in order:

1. Correctness and data integrity
2. Security
3. Reliability
4. Performance
5. API compatibility
6. Maintainability
7. Simplicity

Prefer the smallest complete fix for a verified root cause.

Do not over-engineer theoretical edge cases with low practical impact.

Inspect actual repository code, callers, tests, constraints, and API contracts
before making meaningful changes. Do not guess when behavior can be verified.

---

## Architecture Rules

Keep HTTP concerns in views.

Use serializers for input validation and output representation.

Use services for meaningful state-changing workflows.

Use selectors for reusable read/query logic.

Keep durable invariants in models and PostgreSQL constraints.

Use Celery only for expensive or non-request-critical asynchronous work.

Do not move business logic into views or introduce unnecessary abstractions.

---

## Security

Always consider authentication, authorization, object ownership, validation,
JWT/OTP handling, throttling, secrets, uploads, logging, cache isolation,
CSRF/CORS, HTTPS/cookies, race conditions, and replay/idempotency where relevant.

Never expose or log passwords, OTPs, JWTs, refresh tokens, credentials,
secrets, or sensitive internal errors.

Never weaken authorization, validation, throttling, or security settings merely
to make tests pass.

Prefer server-side and database-enforced guarantees.

---

## Database and Concurrency

PostgreSQL is the source of truth.

For multi-step or contended writes consider:

- `transaction.atomic()`
- rollback behavior
- concurrent requests
- `select_for_update()`
- `F()` expressions
- conditional updates
- database constraints

Do not rely only on serializer validation or `model.clean()` for invariants
that must survive concurrency.

Stock, cart, orders, and payments require explicit race-condition and lost-update
analysis.

New Orders snapshot the exact server-owned
`ORDER_SHIPPING_FLAT_RATE_IRT` value. Clients cannot submit shipping, Payments
derive their amount only from `Order.total`, and historical Order snapshots are
never recalculated.

---

## ORM and Performance

Check for:

- N+1 queries
- queries inside loops
- duplicate queries
- missing `select_related()` / `prefetch_related()`
- unbounded querysets
- expensive filters/search/orderings
- unnecessary database round trips
- serializer-triggered queries

Do not add indexes or caches blindly.

Optimize from real query patterns or measured requirements.

---

## Redis

The ordinary catalogue cache is an optimization and may fail open when safe.

The security cache protects OTPs, attempts, locks, leases, and authentication
throttling and must not silently fail open.

Before changing cache behavior consider key scope, TTL, invalidation,
authorization boundaries, concurrency, and failure behavior.

Never treat Redis as the durable source of truth.

---

## Celery

Celery tasks must use simple serializable identifiers rather than ORM instances.

Tasks should be safe under retry/redelivery and idempotent where duplicate
delivery is possible.

Use `transaction.on_commit()` when a task depends on committed database state.

Do not send uploaded image binaries through Celery.

---

## Product Images

Image handling spans PostgreSQL and non-transactional file storage.

Consider upload validation, safe filenames, rollback cleanup, orphaned files,
thumbnail retry/idempotency, corrupt or partial files, concurrent deletion,
storage cleanup, API writes, and Django Admin writes.

All supported write paths must preserve the important ProductImage lifecycle
invariants.

Prefer preserving valid referenced data over aggressive cleanup.

---

## API Compatibility

Do not silently change:

- URLs
- permissions
- authentication requirements
- request or response schemas
- status codes
- pagination
- filters
- ordering
- visibility rules
- error semantics

Human-readable API messages may be localized for `en` and `fa`; stable machine
contracts must not be translated. This includes JSON keys, status and enum
values, response codes, URLs, identifiers, provider/failure codes, Celery task
names, cache keys, audit/log event names, and system-check IDs.

Products use internal database IDs, stable UUID response identifiers, and
immutable lowercase public slugs.

Do not reintroduce UUID product URLs unless explicitly requested.

---

## Migrations

Treat migrations as production operations.

Inspect current migration history before creating or changing one.

Consider existing data, constraints, indexes, locking, compatibility, and
rollback implications.

Do not create migrations when the database schema does not change.

Documentation must describe the migration history that actually exists.

---

## Testing and Verification

Every bug fix requires regression coverage.

Use PostgreSQL/Redis integration tests for behavior SQLite or LocMem cannot
represent correctly.

Before completion, run applicable checks:

- focused tests
- full pytest suite
- integration tests
- Ruff
- Bandit
- Django checks
- migration drift check
- `git diff --check`

Never claim a check passed unless it actually ran successfully.

A green test suite does not replace architectural, security, concurrency, or
API review.

---

## Documentation

Keep implementation synchronized with:

- `README.md`
- `docs/api.md`
- `docs/architecture.md`
- `docs/authentication.md`
- `docs/security.md`
- `docs/deployment.md`

Update only documentation affected by the change.

Do not preserve obsolete intended or historical behavior as if it were current.

---

## Change Discipline

For each task:

1. Inspect the relevant implementation.
2. Identify the root cause.
3. Make the smallest complete change.
4. Preserve unrelated behavior.
5. Add regression coverage.
6. Review security and concurrency impact.
7. Review database/query impact.
8. Review API compatibility.
9. Run appropriate verification.
10. Update affected documentation.

Avoid unrelated refactors.

Distinguish verified defects from speculative risks.

---

## Autonomy

For review or analysis, inspect the repository and report verified findings
without modifying code unless implementation was requested.

For implementation requests, make the requested local changes and run
non-destructive verification without unnecessary confirmation.

Require explicit approval before production actions, destructive data changes,
credential changes, external writes, force pushes, or major scope expansion.

Do not commit or push unless explicitly requested.
