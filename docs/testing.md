# Testing and Verification

Luxury Perfume uses multiple layers of automated verification.

The goal of the test strategy is not only to confirm expected API behavior, but also to protect:

* domain invariants;
* authentication and authorization boundaries;
* database consistency;
* concurrency-sensitive workflows;
* cache behavior;
* asynchronous task behavior;
* frontend behavior;
* security-sensitive code;
* migration consistency;
* production build integrity.

The repository separates fast, isolated tests from tests that specifically require PostgreSQL or Redis behavior.

---

## Test Strategy

The main verification layers are:

```text
Frontend
├── ESLint
├── Vitest
└── Production Vite build

Backend
├── SQLite / LocMem test suite
│   ├── pytest
│   ├── branch coverage
│   └── warnings-as-errors
│
├── PostgreSQL / Redis integration suite
│   ├── database constraints
│   ├── transaction behavior
│   ├── concurrency
│   └── Redis atomicity / security state
│
├── Static verification
│   ├── Ruff
│   ├── Bandit
│   ├── Django system checks
│   └── migration drift checks
│
└── Release verification
    ├── production Compose validation
    ├── backend image build
    ├── frontend production build
    └── image smoke checks
```

Each layer has a different responsibility.

A passing unit suite does not replace PostgreSQL/Redis integration coverage, and a green test suite does not replace architecture, security, concurrency, or API-contract review.

---

# Backend Test Environment

Install the test dependency set:

```bash
python -m pip install --requirement requirements/requirements-test.txt
```

This includes the production backend dependencies plus testing and verification tools such as:

* pytest;
* pytest-django;
* pytest-cov;
* coverage;
* factory_boy;
* Faker;
* pytest-mock;
* Ruff;
* Bandit.

Use Python 3.12 to match the supported backend and CI environment.

---

# Default Backend Test Suite

Run the default suite from the repository root:

```bash
python -m pytest
```

For CI-equivalent warning handling:

```bash
python -W error -m pytest
```

The second command is preferred before submitting significant changes because CI treats Python warnings as errors.

---

## Default Test Settings

The standard test suite uses:

```text
Django settings     config.settings.test
Database            SQLite :memory:
Application cache   LocMem
Security cache      LocMem
Celery broker       in-memory
Celery results      in-memory
Celery execution    eager
Email backend       LocMem
```

This environment is intentionally self-contained and fast.

It does not require local PostgreSQL, Redis, Celery workers, or external infrastructure.

---

## Pytest Discovery

Pytest searches:

```text
apps/
config/
tests/
```

and recognizes:

```text
tests.py
test_*.py
*_tests.py
```

The repository uses strict configuration and strict marker validation.

Unknown markers or invalid pytest configuration should fail rather than being silently ignored.

---

# Integration Tests

Tests marked:

```python
@pytest.mark.integration
```

are excluded from the normal test run.

These tests require real PostgreSQL and/or Redis behavior that SQLite or LocMem cannot model accurately.

Examples include behavior involving:

* database row locking;
* concurrent writes;
* uniqueness under contention;
* transaction isolation;
* PostgreSQL constraints;
* Redis atomic operations;
* security-cache races;
* order reservation concurrency;
* payment/reconciliation races;
* notification-delivery concurrency.

Do not move these tests into the ordinary suite merely to simplify local execution.

---

# Running Integration Services Locally

The repository provides a dedicated integration Compose environment:

```bash
docker compose \
  -f docker/docker-compose.integration.yml \
  up -d --wait
```

It starts disposable:

```text
PostgreSQL 16
Redis 7
```

on loopback-only host ports.

The default local integration configuration uses:

```text
PostgreSQL
127.0.0.1:55432

Redis
127.0.0.1:56379
```

PostgreSQL and Redis storage use temporary filesystems in this environment.

The integration stack is test infrastructure, not a development database.

---

## Run the Integration Suite

With the integration services healthy:

```bash
python -m pytest \
  -o addopts="--strict-config --strict-markers" \
  -m integration \
  --ds=config.settings.integration \
  -q
```

The explicit `addopts` replacement is intentional.

The repository's normal pytest configuration excludes integration tests and enables the default coverage configuration. The command above replaces those default options so only explicitly marked integration tests run against the integration settings.

---

## Stop Integration Services

After the integration suite finishes:

```bash
docker compose \
  -f docker/docker-compose.integration.yml \
  down
```

The integration environment should remain isolated from development and production resources.

---

# Integration Environment Overrides

The integration settings support these environment variables:

```text
INTEGRATION_DB_NAME
INTEGRATION_DB_USER
INTEGRATION_DB_PASSWORD
INTEGRATION_DB_HOST
INTEGRATION_DB_PORT

INTEGRATION_CACHE_REDIS_URL
INTEGRATION_SECURITY_REDIS_URL
```

The repository defaults match `docker/docker-compose.integration.yml`.

Override them only when intentionally running against dedicated test services.

Never point integration tests at:

* a production PostgreSQL database;
* a shared production Redis instance;
* customer data;
* persistent infrastructure that cannot safely be modified or flushed.

Integration tests may intentionally create, update, lock, or delete data.

---

# Coverage

The default pytest suite measures branch coverage for:

```text
apps/
config/
```

The minimum accepted coverage is:

```text
85%
```

The test run fails when coverage drops below that threshold.

Run:

```bash
python -m pytest
```

to get the configured terminal coverage report, including missing lines.

---

## Coverage Scope

Coverage intentionally excludes infrastructure or generated areas that do not represent ordinary application logic, including:

```text
tests
migrations
__pycache__
config/asgi.py
config/wsgi.py
config/settings/*
```

Branch coverage is enabled.

Coverage percentage is a quality guard, not the definition of adequate testing.

A change can maintain 85% coverage while still missing:

* authorization failures;
* concurrent requests;
* rollback behavior;
* race conditions;
* invalid state transitions;
* boundary values;
* idempotency;
* retry behavior;
* database constraint violations.

Tests should target meaningful behavior rather than lines solely to increase the percentage.

---

# Focused Backend Tests

During development, prefer running the smallest relevant test scope first.

For example:

```bash
python -m pytest apps/users/tests/
```

or:

```bash
python -m pytest apps/products/tests/
```

or an individual test module:

```bash
python -m pytest path/to/test_file.py
```

or a specific test:

```bash
python -m pytest path/to/test_file.py::TestClass::test_name
```

After focused tests pass, run the broader applicable verification before completion.

Bug fixes should include regression coverage demonstrating the previously incorrect behavior.

---

# Warnings as Errors

CI runs the default backend suite using:

```bash
python -W error -m pytest
```

Warnings therefore fail CI.

Do not suppress a warning without understanding its cause.

Warnings can indicate:

* deprecated framework behavior;
* unsafe assumptions;
* test isolation problems;
* configuration mistakes;
* dependency incompatibilities.

Fix the underlying problem where practical.

---

# Python Linting

Run Ruff from the repository root:

```bash
python -m ruff check apps config tests
```

Ruff failures should be fixed rather than bypassed.

Avoid unrelated formatting or refactoring while addressing lint failures unless the change genuinely requires it.

---

# Static Security Analysis

Run Bandit against production Python source:

```bash
python -m bandit \
  -q \
  -r apps config \
  -x 'apps/**/tests/**,config/tests/**'
```

Bandit is a static-analysis signal, not a complete security review.

A clean Bandit run does not prove that:

* authorization is correct;
* object ownership is enforced;
* race conditions are safe;
* secrets cannot leak;
* OTP/JWT flows are secure;
* payment logic is correct;
* cache isolation is correct.

Security-sensitive changes still require explicit review.

See [Security](security.md).

---

# Django System Checks

Run Django's built-in system checks against the standard test configuration:

```bash
python manage.py check \
  --settings=config.settings.test
```

For changes involving PostgreSQL-specific behavior, also run the integration-environment check while its services are available:

```bash
python manage.py check \
  --settings=config.settings.integration
```

---

# Migration Drift

Every model change should be checked for missing migrations.

Run:

```bash
python manage.py makemigrations \
  --check \
  --dry-run \
  --settings=config.settings.test
```

The command should succeed without generating new migrations when the repository is synchronized.

For PostgreSQL-sensitive work, CI performs the equivalent verification using:

```text
config.settings.integration
```

as well.

---

## Migration Testing Rules

Treat migrations as production operations.

When changing persistent models:

1. inspect the existing migration history;
2. generate only migrations required by the schema change;
3. review generated operations;
4. consider existing production data;
5. consider indexes and constraints;
6. consider lock duration and deployment impact;
7. verify migration drift;
8. test behavior that depends on the new constraint or schema.

Do not create empty or unrelated migrations simply to make a check pass.

---

# Frontend Verification

Frontend verification runs from:

```bash
cd frontend
```

Use the Node version declared by `.nvmrc`:

```bash
nvm install
nvm use
```

Install dependencies from the committed lockfile:

```bash
npm ci
```

---

## Frontend Linting

Run:

```bash
npm run lint
```

The lint script allows no warnings.

---

## Frontend Tests

Run:

```bash
npm test
```

The storefront uses Vitest together with Testing Library.

Tests should verify user-visible behavior and application contracts rather than internal implementation details where possible.

Particular attention should be given to:

* authentication state;
* protected routes;
* Cart synchronization;
* API error handling;
* loading and retry states;
* safe navigation;
* forms;
* inaccessible or disabled future features;
* backend-shaped fixtures.

---

# Frontend Production Build

A production build requires an explicit HTTPS API origin.

Run:

```bash
VITE_API_BASE_URL=https://shop.exonplus.ir npm run build
```

The build output is written to:

```text
frontend/dist/
```

Do not commit generated `dist/` output.

The production API URL is deliberately supplied at build time rather than used as an implicit runtime fallback.

Remember that every `VITE_*` value becomes browser-visible configuration and must never contain secrets.

---

# Recommended Frontend Check Sequence

Before completing frontend work:

```bash
cd frontend

npm ci
npm run lint
npm test
VITE_API_BASE_URL=https://shop.exonplus.ir npm run build
```

For dependency-neutral source changes, reinstalling with `npm ci` on every small local iteration is unnecessary, but a clean lockfile-based install is what CI verifies.

---

# Backend Verification Sequence

For meaningful backend changes, a strong local verification sequence is:

```bash
python -W error -m pytest

python -m ruff check apps config tests

python -m bandit \
  -q \
  -r apps config \
  -x 'apps/**/tests/**,config/tests/**'

python manage.py check \
  --settings=config.settings.test

python manage.py makemigrations \
  --check \
  --dry-run \
  --settings=config.settings.test
```

Run PostgreSQL/Redis integration tests when the changed behavior depends on real database or Redis semantics.

---

# When Integration Tests Are Required

Integration coverage should be strongly considered when modifying:

```text
authentication identity constraints
signup races
security-cache behavior
OTP consumption
Cart concurrency
stock mutation
Order reservations
Payment state transitions
Refund processing
Notification delivery claims
database uniqueness
select_for_update() workflows
Redis atomicity
transaction boundaries
```

SQLite or LocMem should not be used as evidence for behavior they cannot accurately model.

---

# Concurrency-Sensitive Testing

For state-changing workflows, test more than the successful sequential path.

Where relevant, verify:

* simultaneous requests;
* duplicate requests;
* stale state;
* lost-update prevention;
* database locking;
* unique constraint races;
* idempotent retries;
* worker redelivery;
* transaction rollback;
* failure after an external operation;
* failure before commit.

The database and durable application state must remain correct even when requests or tasks overlap.

---

# Celery Testing

The standard test configuration runs Celery tasks eagerly:

```text
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
```

This keeps the default test suite self-contained.

When testing asynchronous workflows, distinguish between:

1. domain logic;
2. task enqueue behavior;
3. task execution behavior;
4. retry/redelivery safety;
5. transaction commit ordering.

A task that depends on newly committed database state should normally be scheduled through `transaction.on_commit()`.

Tests should not rely on sending ORM instances through Celery; durable identifiers should be passed instead.

---

# API Regression Tests

When changing an endpoint, verify affected contracts such as:

```text
URL
HTTP method
authentication
permissions
ownership
input schema
response schema
status code
pagination
filters
ordering
visibility
error semantics
localization behavior
```

Do not silently modify an existing API contract as a side effect of refactoring.

See [API Reference](api.md).

---

# Authentication and Security Tests

Changes involving authentication should test both successful and rejected behavior.

Relevant areas include:

* username/password login;
* phone/OTP flows;
* JWT issuance;
* refresh rotation;
* refresh blacklisting;
* logout;
* password reset;
* password-change session invalidation;
* throttling;
* profile-phone verification;
* ownership;
* replay behavior;
* OTP expiry and attempts.

Security tests should prove that unauthorized actions remain impossible, not only that valid requests succeed.

See [Authentication](authentication.md) and [Security](security.md).

---

# Test Data

Prefer factories and explicit fixtures over hidden dependency on existing local data.

Tests should be:

* deterministic;
* isolated;
* independently runnable;
* order-independent;
* safe to retry;
* clear about important state.

Avoid tests that depend on:

* production data;
* developer-specific database contents;
* execution order;
* wall-clock timing without controlled boundaries;
* external providers;
* internet access.

Provider integrations should be tested through controlled adapters, mocks, or purpose-built test doubles unless a dedicated integration environment explicitly exists.

---

# Continuous Integration

GitHub Actions runs the test suite for:

```text
push
pull_request
```

The primary CI workflow contains these major jobs:

```text
React storefront
SQLite and LocMem
PostgreSQL and Redis
Application image
Release gate
```

The release gate succeeds only after the required frontend, backend, integration, and application-image checks pass.

---

## CI Backend Checks

The default backend CI job performs:

```text
pytest with warnings as errors
branch coverage
Ruff
Bandit
Django system checks
migration drift checks
```

The integration job separately performs:

```text
PostgreSQL/Redis integration tests
Django checks against PostgreSQL
migration drift checks against PostgreSQL
```

This separation is intentional.

---

## CI Frontend Checks

The frontend CI job performs:

```text
npm ci
npm run lint
npm test
production build
release stamping / validation
frontend image export
```

CI uses the repository's declared Node version.

---

# Release Verification

After application tests pass, CI also validates release artifacts.

Backend release verification includes:

* validating the production Compose configuration;
* building the final application image;
* attaching source/revision metadata;
* smoke-testing required runtime content from the built image.

Frontend verification includes:

* creating the production Vite build;
* validating/stamping the release;
* building the immutable frontend carrier artifact.

These checks protect the release path itself.

Passing local pytest alone does not prove that the production artifact can be built successfully.

---

# Pre-Pull-Request Checklist

For a backend-focused change, verify the applicable subset of:

```text
[ ] Focused regression tests pass
[ ] Full default pytest suite passes
[ ] Warnings-as-errors suite passes
[ ] Required integration tests pass
[ ] Ruff passes
[ ] Bandit passes
[ ] Django system checks pass
[ ] Migration drift check passes
[ ] Relevant documentation is updated
```

For a frontend-focused change:

```text
[ ] Frontend lint passes
[ ] Frontend tests pass
[ ] Production frontend build succeeds
[ ] Relevant backend contracts remain compatible
[ ] Relevant documentation is updated
```

For cross-stack changes, run both applicable sets.

---

# Test Quality Principles

Good tests should answer a behavioral question.

Prefer tests such as:

```text
an unauthenticated user cannot access an owner-only resource
```

over tests that merely mirror implementation details.

Prefer:

```text
two concurrent cart increments preserve both updates
```

over tests that only check which internal function was called.

Tests should give confidence that observable behavior and durable state remain correct after refactoring.

---

## Do Not Weaken Production Behavior for Tests

Never weaken:

* authentication;
* authorization;
* validation;
* throttling;
* database constraints;
* transaction handling;
* secure cookie behavior;
* concurrency protection;
* cache isolation;

solely to make a test easier to write or pass.

Instead, configure the test environment appropriately or improve the test design.

---

# Debugging Test Failures

When a test fails:

1. reproduce the smallest failing test;
2. determine whether the failure is deterministic;
3. inspect the real implementation and contract;
4. identify the root cause;
5. distinguish an implementation defect from a stale test;
6. fix the correct layer;
7. run the focused regression test;
8. run broader affected verification.

Do not immediately update an assertion simply because production code changed.

The existing test may be protecting an intentional contract.

For common environment and runtime problems, see [Troubleshooting](troubleshooting.md).

---

# Documentation Expectations

Tests and documentation should describe the same implemented system.

When behavior changes, update the appropriate canonical document:

| Change                      | Documentation                       |
| --------------------------- | ----------------------------------- |
| API behavior                | [API Reference](api.md)             |
| Authentication              | [Authentication](authentication.md) |
| Architecture                | [Architecture](architecture.md)     |
| Development workflow        | [Development](development.md)       |
| Test infrastructure         | `testing.md`                        |
| Security behavior           | [Security](security.md)             |
| Deployment/release behavior | [Deployment](deployment.md)         |

Do not document tests that do not exist as though they are already enforced.

Do not claim a check passed unless it was actually executed successfully.

---

## Source of Truth

The authoritative testing configuration is distributed across:

```text
pytest.ini
.coveragerc
requirements/requirements-test.txt
config/settings/test.py
config/settings/integration.py
docker/docker-compose.integration.yml
frontend/package.json
.github/workflows/ci.yml
```

When this document and those files disagree, verify the current implementation and update the documentation accordingly.
