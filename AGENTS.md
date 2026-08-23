# AGENTS.md

## Project Priorities

This is a production-oriented Django/DRF backend.

Priorities, in order:

1. Correctness and data integrity
2. Security
3. Database and server performance
4. Backward compatibility
5. Maintainability
6. Simplicity

Never trade correctness or security for a premature optimization.

Before making meaningful changes, inspect the relevant code path and
understand its callers, database behavior, tests, and external API contract.

Do not guess about repository behavior when it can be verified from the code.


## Architecture

The project uses Django and Django REST Framework with PostgreSQL-oriented
application design, Redis, Celery, JWT authentication, django-filter,
and pytest.

Respect the existing architecture and conventions.

Prefer:

request
→ view/API boundary
→ serializer/input validation
→ service/domain operation where appropriate
→ model/database
→ background task for asynchronous side effects

Do not move business logic into views merely for convenience.

Do not introduce new abstractions, dependencies, service layers, signals,
or infrastructure unless they solve a concrete problem.


## Change Discipline

For every change:

- Inspect the affected code and its callers first.
- Prefer the smallest complete change that fixes the root cause.
- Do not patch symptoms when the root cause can be identified.
- Avoid unrelated refactors.
- Preserve public API behavior unless the task explicitly changes it.
- Preserve database compatibility unless a migration is intentionally required.
- Do not silently change response schemas, status codes, permissions,
  pagination behavior, filtering semantics, URL contracts, or error formats.
- Reuse existing project conventions before introducing a new pattern.

If requirements conflict, call out the conflict instead of silently choosing
a risky interpretation.


## Security

Security-sensitive changes require explicit review of the complete request
and data flow.

Always consider, when relevant:

- authentication
- authorization
- object-level permissions and IDOR
- serializer input/output field exposure
- mass-assignment risks
- validation and normalization
- JWT/token handling and revocation
- secrets and credentials
- password and OTP handling
- rate limiting and abuse prevention
- CSRF and CORS behavior
- unsafe redirects
- file upload validation
- sensitive logging
- information disclosure
- cache isolation
- database integrity
- race conditions and replay/idempotency risks

Never:

- expose or log passwords, OTPs, JWTs, refresh tokens, API keys,
  credentials, secrets, or sensitive internal state
- hard-code secrets
- weaken authentication, authorization, throttling, validation,
  or security settings merely to make a test pass
- return internal exception details to API clients
- trust client-provided ownership or permission-sensitive fields
  without server-side validation

Prefer server-side and database-enforced security invariants over assumptions
in application code.


## Database Integrity and Concurrency

Treat PostgreSQL/database correctness as authoritative.

For multi-step writes:

- determine whether transaction.atomic() is required
- consider rollback behavior
- consider concurrent requests
- avoid check-then-write race conditions
- use database constraints for invariants where practical
- use select_for_update(), F expressions, conditional updates, or other
  concurrency controls when the use case requires them

Do not rely only on model clean() or serializer validation for invariants that
must remain correct under concurrent requests.

Changes involving stock, payments, orders, counters, uniqueness, or other
contended state must explicitly consider race conditions and lost updates.


## Query and Server Performance

For API and database changes, inspect query behavior.

Actively look for:

- N+1 queries
- queries inside loops
- unnecessary duplicate queries
- unnecessary model hydration
- missing select_related()
- missing or excessive prefetch_related()
- unbounded result sets
- inefficient pagination
- expensive annotations or subqueries
- unnecessary database round trips
- filters/orderings that may need an index
- loading fields that are not needed
- synchronous expensive work in request/response paths

Do not add indexes blindly.

Add or modify an index only when supported by the actual query pattern,
constraint requirement, or a clearly justified production access path.

Do not optimize solely from intuition.
Measure or reason from concrete query behavior.

When query count is important, add query-count regression tests where practical.

Avoid introducing caches to hide inefficient database access.
Fix the underlying query first when feasible.


## API Design

For DRF endpoints:

- keep permissions explicit
- validate all untrusted input
- keep serializers intentional about writable and exposed fields
- maintain pagination for potentially large collections
- avoid leaking internal identifiers or fields unnecessarily
- avoid changing endpoint contracts unintentionally
- consider query counts introduced by serializer relations

Public URL identifiers and internal database identifiers are separate concerns.

Do not replace a stable internal primary key merely because a different
public URL identifier such as a slug is required.

When using slugs publicly:

- enforce an appropriate uniqueness policy
- consider indexing and lookup cost
- define slug mutation behavior
- consider URL stability and backward compatibility


## Celery and Background Tasks

Keep expensive or non-request-critical work out of synchronous request paths
when the existing architecture uses Celery for it.

Celery tasks should be:

- safe to retry where practical
- idempotent where retries can duplicate effects
- explicit about failure behavior
- bounded by reasonable timeout/retry policies
- passed simple serializable identifiers rather than ORM model instances

When a task depends on committed database state, enqueue it only after the
transaction commits, using transaction.on_commit() where appropriate.

Do not create background tasks for trivial operations that are cheaper and
safer to execute synchronously.


## Redis and Caching

Caching must never compromise correctness or authorization.

Before adding or changing caching:

- define the cache key scope
- define TTL behavior
- define invalidation behavior
- ensure user-specific or permission-sensitive data cannot leak between users
- consider Redis failure behavior
- avoid caching sensitive authentication material unnecessarily

A cache is an optimization, not the source of truth.


## Migrations

Treat migrations as production operations.

Before creating a migration:

- inspect existing migrations
- determine whether existing data is affected
- preserve data whenever possible
- consider uniqueness and nullability transitions
- consider indexes and constraints
- avoid unnecessary table rewrites or long blocking operations

Never edit an already-applied migration merely to make the current state pass
unless the repository explicitly treats that migration as unreleased.


## Testing

Every behavior change must be validated.

For bug fixes:

- add a regression test that would fail before the fix

For API changes:

- test success behavior
- test validation failures
- test authentication/authorization where relevant
- test response contract where relevant

For database-sensitive behavior:

- test constraints and transaction behavior where relevant
- add concurrency tests for race-condition fixes when practical
- add query-count tests for meaningful query-performance regressions

Use the repository's configured pytest suite.

The default test configuration requires branch coverage and an overall
coverage threshold of at least 85%.

Do not reduce coverage thresholds or weaken tests to make a change pass.

Run the smallest relevant tests while developing, then run the broader
relevant suite before completion.

Run integration tests when the change depends on PostgreSQL, Redis,
Celery, or other integration behavior and the required environment is available.

Never claim a test or check passed unless it was actually executed.


## Documentation

Update documentation when a change affects:

- public API behavior
- URLs
- authentication
- environment variables
- deployment
- migrations
- architecture
- operational behavior
- background tasks

Documentation must describe the final implemented behavior, not the intended
behavior if they differ.


## Completion Checklist

Before declaring meaningful work complete:

1. Review the final diff.
2. Remove accidental or unrelated changes.
3. Check for security regressions.
4. Check database/query performance.
5. Check transaction and concurrency implications.
6. Check API compatibility.
7. Verify migrations if models changed.
8. Run relevant tests and configured checks.
9. Check that no secrets or debug artifacts were introduced.
10. Update relevant documentation.

Then report:

- what changed
- why it changed
- important architectural decisions
- security impact
- performance impact
- API compatibility impact
- migrations created or modified
- tests/checks actually executed and their results
- remaining risks or follow-up work


## Autonomy

For requests to review, analyze, diagnose, explain, or plan:

- inspect the relevant repository code
- report findings
- do not modify code unless implementation was explicitly requested

For requests to implement, fix, refactor, or change:

- make the requested in-scope local changes
- run relevant non-destructive validation
- do not ask for confirmation for ordinary local edits or test execution

Require explicit confirmation before destructive operations, external writes,
credential changes, production actions, or material expansion of scope.