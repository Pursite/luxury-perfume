# Test Suite Improvement Design

> Historical design record. This dated document is not a current project
> reference. See [Testing](../../../README.md#testing) and the current
> [architecture](../../architecture.md) for the implemented repository state.

## Objective

Improve the Django/DRF test suite so it verifies security-sensitive behavior,
transactional correctness, cache isolation, file lifecycle behavior, and
database-specific guarantees without changing public application behavior.

## Constraints

- Work directly on the current branch.
- Preserve API compatibility and existing application behavior unless a new or
  corrected test proves a real correctness or security defect.
- Preserve the existing staged `.gitignore` changes and the unrelated local
  `docker/docker-compose.prod.yml` change.
- Never expose or log passwords, OTPs, JWTs, credentials, or sensitive internal
  errors in tests, fixtures, CI output, or application changes.
- Keep the default suite fast with SQLite, LocMem caches, eager Celery, and
  isolated temporary media.
- Keep PostgreSQL/Redis tests explicitly marked `integration` and runnable both
  locally and in CI.
- Mock external boundaries such as SMS delivery, task dispatch, storage failure,
  or an intentionally simulated database failure; do not mock the business
  service whose behavior a test claims to verify.
- Measure production code with branch coverage, excluding tests, migrations,
  generated files, and environment entry points, and require at least 85%.

## Test Organization

A root `conftest.py` will own genuinely shared fixtures. It will provide an
`api_client` fixture and an autouse fixture that discovers every configured
cache alias through Django settings, clears each cache before the test, and
clears each again after the test. Product-specific media isolation and domain
factories remain close to the product tests.

Oversized or mixed files will be split by the layer under test:

- model tests cover model methods and database constraints;
- serializer tests cover validation and serialization contracts;
- service tests cover transactions, state changes, OTP flows, logout, and file
  lifecycle orchestration;
- cache tests cover cache-key generation, invalidation, failure policy, OTP
  consumption, and lockouts;
- task tests cover thumbnail generation and task failures;
- API tests cover HTTP status, response shapes, authorization, throttling, and
  non-enumerating OTP responses.

Existing valuable assertions will be moved, not weakened. Duplicate and
implementation-mocking tests will be replaced only when a real integration
test covers the same contract more accurately.

## Authentication and OTP Coverage

Login OTP and password-reset OTP request tests will create real users where
needed and call the real DRF endpoints and business services. Deterministic OTP
generation and SMS task dispatch may be patched because randomness and SMS are
external boundaries. Existing and unknown well-formed phone numbers must return
the same generic status and response body. Unknown numbers must not gain OTP
state or trigger delivery.

Verification tests will assert the exact DRF exception types and details for
invalid codes, consumed codes, lockout thresholds, concurrent leases, and
security-cache failure. Successful verification must consume the OTP so replay
fails. Logout tests will inspect Simple JWT's blacklist records and prove the
same refresh token cannot be used again.

Transaction tests will force a failure inside a real `transaction.atomic()`
boundary and then query the database to prove partial writes were rolled back.
Mocks may inject the failure at a database or storage/task boundary but may not
replace the service under test.

## Product, Cache, File, and Task Coverage

Product model tests will assert the discount check constraint and the partial
unique primary-image constraint at the database level. PostgreSQL integration
tests will exercise real row locking and concurrent primary-image creation using
independent database connections/threads, then assert exactly one primary image.

Cache tests will assert stable canonical keys, namespace version changes, and
`transaction.on_commit` invalidation semantics: rolled-back writes do not
advance the cache version, while committed writes do. Redis integration tests
will verify security-cache lockout/consumption and cache behavior against the
configured Redis aliases.

File tests will use temporary media. They will verify that file deletion happens
only after successful commit, rollback preserves files, both original and
thumbnail files are cleaned up, and storage deletion failures are contained and
reported without exposing sensitive information. Thumbnail task tests will
cover successful WebP output, missing rows, corrupt images, and save failures,
including cleanup or persistence guarantees appropriate to the existing task
contract.

## Pytest, Coverage, Dependencies, and CI

`pytest.ini` will use strict marker and strict configuration handling, declare
the `integration` marker, show warnings normally, exclude integration tests from
the default invocation, and run branch coverage with an 85% production-code
minimum. Coverage configuration will omit test modules, migrations, generated
files, and runtime entry points that are not meaningful unit-test targets.

Production dependencies will remain in `requirements/requirements.txt`.
Test-only packages will move to `requirements/requirements-test.txt`, which
includes the production requirements first. Docker will continue installing
`requirements/requirements.txt`, so runtime images do not gain test tooling
and existing production installation behavior remains compatible.

GitHub Actions will have:

1. a default SQLite/LocMem job running pytest with coverage, `manage.py check`,
   and `makemigrations --check --dry-run`;
2. a PostgreSQL/Redis service job using integration settings and running tests
   explicitly selected with `-m integration`, followed by Django and migration
   checks against PostgreSQL.

The integration settings module will take database and cache endpoints from CI
or local environment variables and will retain test-only secret defaults. A
documented local command will allow developers with PostgreSQL and Redis to run
the same marked suite.

## Verification and Completion

Completion requires all of the following to succeed from the final working tree:

- complete default pytest suite;
- coverage validation with branch coverage and the 85% threshold;
- explicitly selected PostgreSQL/Redis integration suite;
- `python manage.py check` under default test settings and integration settings;
- `python manage.py makemigrations --check --dry-run` under both settings;
- scan confirming no `pytest.raises(Exception)`, debug `print()` calls, committed
  coverage database, or duplicate shared fixtures remain;
- review of the final diff to ensure the unrelated Compose change is untouched
  and the pre-existing `.gitignore` additions are preserved.

If local PostgreSQL/Redis infrastructure cannot be started or reached, the CI
workflow and settings will still be validated statically, but that limitation
must be reported as an unresolved verification risk rather than represented as
a passing integration run.
