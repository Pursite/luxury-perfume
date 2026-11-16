# Test Suite Improvement Implementation Plan

> Historical implementation record. This dated plan is not a current project
> reference. See [Testing](../../../README.md#testing) and the current
> [architecture](../../architecture.md) for the implemented repository state.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize and strengthen the Django/DRF test suite, add production-code branch coverage enforcement, and verify PostgreSQL/Redis-specific guarantees in a separate CI integration job.

**Architecture:** Shared test isolation lives in the root `conftest.py`; domain tests are organized by the production layer they exercise. SQLite/LocMem remains the default, while an environment-driven integration settings module and explicit marker select PostgreSQL/Redis tests locally or in CI.

**Tech Stack:** Python 3.12, Django 6, Django REST Framework, pytest, pytest-django, pytest-cov/coverage.py, Simple JWT, PostgreSQL 16, Redis 7, GitHub Actions.

## Global Constraints

- Work directly on the current branch.
- Preserve API compatibility and existing application behavior unless a failing test proves a correctness or security defect.
- Preserve the staged `.gitignore` change and unrelated `docker/docker-compose.prod.yml` edit.
- Exclude tests, migrations, generated files, and environment entry points from coverage.
- Enforce branch coverage and at least 85% production-code coverage.
- Keep integration tests explicitly marked and runnable locally and in CI.
- Mock external boundaries, never the business service being tested.
- Do not expose passwords, OTPs, JWTs, credentials, or sensitive internal errors.

---

### Task 1: Shared Isolation and Strict Test Configuration

**Files:**
- Create: `conftest.py`
- Create: `.coveragerc`
- Create: `config/tests/test_test_setup.py`
- Modify: `pytest.ini`
- Modify: `.gitignore`
- Delete: `.coverage`
- Modify: test modules that define duplicate `api_client` or cache fixtures

**Interfaces:**
- Produces: `api_client() -> rest_framework.test.APIClient`
- Produces: autouse `clear_all_caches()` that clears every alias in `settings.CACHES` before and after every test.

- [ ] **Step 1: Add a test proving all configured cache aliases are isolated**

```python
def test_all_cache_aliases_start_empty():
    assert caches["default"].get("isolation-probe") is None
    assert caches["security"].get("isolation-probe") is None
    caches["default"].set("isolation-probe", "default")
    caches["security"].set("isolation-probe", "security")
```

- [ ] **Step 2: Run both isolation nodes and verify stale values leak before central cleanup**

Seed both aliases in a preceding temporary test and run the seeding and empty-assertion nodes together.

- [ ] **Step 3: Add shared fixtures and remove duplicates**

```python
@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture(autouse=True)
def clear_all_caches(settings):
    configured = [caches[alias] for alias in settings.CACHES]
    for backend in configured:
        backend.clear()
    yield
    for backend in configured:
        backend.clear()
```

- [ ] **Step 4: Configure strict pytest and production-only coverage**

Set `--strict-markers`, `--strict-config`, `-m "not integration"`, `--cov`, `--cov-branch`, and `--cov-fail-under=85`; register `integration`; remove `--disable-warnings`. Configure coverage sources as `apps` and `config` while omitting tests, migrations, generated files, ASGI/WSGI entry points, and environment-specific settings.

- [ ] **Step 5: Remove committed/generated artifacts without disturbing staged work**

Delete tracked `.coverage`, retain the staged ignore entries, and scan with `git ls-files` and `rg`.

- [ ] **Step 6: Run the default suite and inspect warnings**

Run: `COVERAGE_FILE=/tmp/luxury-perfume-task1.coverage venv/bin/python -m pytest -q`

---

### Task 2: Authentication Tests by Layer and Non-enumerating OTP APIs

**Files:**
- Create/Modify: `apps/users/tests/test_models.py`
- Create: `apps/users/tests/test_serializers.py`
- Create: `apps/users/tests/test_services.py`
- Create: `apps/users/tests/test_cache.py`
- Create: `apps/users/tests/test_tasks.py`
- Create: `apps/users/tests/test_auth_api.py`
- Create: `apps/users/tests/test_profile_api.py`
- Create: `apps/users/tests/test_signup_api.py`
- Delete: superseded mixed/flow files under `apps/users/tests/`

**Interfaces:**
- Consumes: root `api_client` and cache isolation fixtures.
- Verifies: existing DRF endpoint contracts and service return values.

- [ ] **Step 1: Replace mocked login/reset OTP request tests with failing real API tests**

```python
@pytest.mark.parametrize("url_name", ["users:login_send_otp", "users:password_reset_send_otp"])
def test_otp_request_does_not_enumerate_accounts(api_client, mocker, url_name):
    delivery = mocker.patch("apps.users.tasks.send_otp_sms_task.delay")
    existing = "09123456789"
    unknown = "09123456788"
    UserFactory(phone_number=existing)
    known_response = api_client.post(reverse(url_name), {"phone_number": existing})
    caches["default"].clear()
    unknown_response = api_client.post(reverse(url_name), {"phone_number": unknown})
    assert known_response.status_code == unknown_response.status_code == 200
    assert known_response.data == unknown_response.data
    assert delivery.call_count == 1
```

- [ ] **Step 2: Run the focused tests and confirm the old mocked expectations are misleading**

Run: `venv/bin/python -m pytest apps/users/tests/test_auth_api.py -k 'does_not_enumerate' -q -o addopts=''`

- [ ] **Step 3: Move valuable tests into focused files and use real services**

Move model/selector assertions, serializer validation, service state changes, security-cache guards, Celery task behavior, and HTTP contracts without weakening assertions. Patch only OTP generation/delivery, time, or injected persistence failures.

- [ ] **Step 4: Replace broad exception assertions with exact types and details**

```python
with pytest.raises(ValidationError) as exc_info:
    guard.verify("000000")
assert "Invalid or expired verification code" in str(exc_info.value.detail)

with pytest.raises(Throttled, match="Too many verification attempts"):
    guard.verify("123456")
```

- [ ] **Step 5: Add OTP consumption, lockout, and logout blacklist tests**

Assert consumed OTP replay raises `ValidationError`, threshold attempts create a lock and then raise `Throttled`, successful verification clears keys, `BlacklistedToken` exists after logout, and a second logout with the same refresh returns 400.

- [ ] **Step 6: Add real transaction rollback tests**

Inject an `IntegrityError` from the second database write inside the real profile service and assert user fields/password and address count remain unchanged. Do not alter password-reset transaction scope unless a failing correctness test demonstrates the need.

- [ ] **Step 7: Run all user tests**

Run: `COVERAGE_FILE=/tmp/luxury-perfume-users.coverage venv/bin/python -m pytest apps/users/tests -q`

---

### Task 3: Product Tests by Layer and Transaction/File Guarantees

**Files:**
- Create: `apps/products/tests/test_models.py`
- Create: `apps/products/tests/test_serializers.py`
- Create: `apps/products/tests/test_services.py`
- Create: `apps/products/tests/test_cache.py`
- Create: `apps/products/tests/test_tasks.py`
- Create: `apps/products/tests/test_api.py`
- Modify: `apps/products/tests/conftest.py`
- Delete: `apps/products/tests/test_views.py`
- Delete or reduce: `apps/products/tests/test_hardening.py`

**Interfaces:**
- Consumes: factories, root `api_client`, product media isolation.
- Verifies: product constraints, service transactions, cache signals, storage cleanup, thumbnails, and API contracts.

- [ ] **Step 1: Move existing product tests by layer without behavior changes**

Keep HTTP assertions in `test_api.py`, validation in `test_serializers.py`, hierarchy/constraint assertions in `test_models.py`, cache behavior in `test_cache.py`, service orchestration in `test_services.py`, and thumbnail behavior in `test_tasks.py`.

- [ ] **Step 2: Add database-constraint tests**

```python
invalid_product = ProductFactory.build(
    price=Decimal("10.00"),
    discount_price=Decimal("10.00"),
)
with pytest.raises(IntegrityError), transaction.atomic():
    invalid_product.save(force_insert=True)

ProductImageFactory(product=product, is_primary=True)
with pytest.raises(IntegrityError), transaction.atomic():
    ProductImageFactory(product=product, is_primary=True)
```

Use `transaction=True` or a nested atomic block so the connection remains usable after the expected error.

- [ ] **Step 3: Add commit-versus-rollback cache invalidation tests**

Capture the namespace version, save inside `transaction.atomic()`, force rollback, and assert the version did not advance. Repeat with a committed write and assert it advances after commit hooks run.

- [ ] **Step 4: Add file cleanup tests**

Create original and thumbnail files under temporary media, call the real delete service inside `captureOnCommitCallbacks`, execute callbacks, and assert both files are absent. Force rollback and assert the database row and files remain. Simulate a storage deletion error and assert the service does not re-raise after commit.

- [ ] **Step 5: Add thumbnail failure tests**

Assert a missing row returns without creating files, corrupt input raises the exact Pillow exception used by the task retry contract, and a thumbnail save failure propagates while leaving the original image intact.

- [ ] **Step 6: Run all product tests**

Run: `COVERAGE_FILE=/tmp/luxury-perfume-products.coverage venv/bin/python -m pytest apps/products/tests -q`

---

### Task 4: PostgreSQL/Redis Integration Settings and Tests

**Files:**
- Create: `config/settings/integration.py`
- Create: `tests/integration/test_postgres_transactions.py`
- Create: `tests/integration/test_redis_security_cache.py`
- Create: `tests/integration/__init__.py`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes dedicated integration environment variables
  `INTEGRATION_DB_NAME`, `INTEGRATION_DB_USER`,
  `INTEGRATION_DB_PASSWORD`, `INTEGRATION_DB_HOST`,
  `INTEGRATION_DB_PORT`, `INTEGRATION_CACHE_REDIS_URL`, and
  `INTEGRATION_SECURITY_REDIS_URL`.
- Produces a Django settings module selected with `--ds=config.settings.integration`.

- [ ] **Step 1: Add integration settings**

Import test-safe defaults from `config.settings.test`, then override `DATABASES`
with the five `DB_*` environment variables and define both aliases by calling
`redis_cache(env("CACHE_REDIS_URL"))` and
`redis_cache(env("SECURITY_REDIS_URL"))`. Use only test credentials in
documentation and CI.

- [ ] **Step 2: Add a real primary-image concurrency test**

Mark with `@pytest.mark.integration` and `@pytest.mark.django_db(transaction=True)`. Create two independent thread/database connections synchronized by a barrier; call the real image service concurrently; close old connections in each worker; assert both operations complete and exactly one row is primary.

- [ ] **Step 3: Add PostgreSQL constraint and transaction tests**

Assert the named partial unique and discount constraints reject invalid writes and prove a forced rollback leaves no partial product/image writes or cache invalidation callback.

- [ ] **Step 4: Add Redis security-cache tests**

Use the real `security` alias to store/verify/consume OTP state, verify replay failure, verify lockout survives a distinct guard instance, and verify aliases are independent.

- [ ] **Step 5: Document the local integration command**

```bash
DJANGO_SETTINGS_MODULE=config.settings.integration \
INTEGRATION_DB_NAME=luxury_perfume_test INTEGRATION_DB_USER=luxury_perfume \
INTEGRATION_DB_HOST=127.0.0.1 INTEGRATION_DB_PORT=5432 \
INTEGRATION_CACHE_REDIS_URL=redis://127.0.0.1:6379/14 \
INTEGRATION_SECURITY_REDIS_URL=redis://127.0.0.1:6379/15 \
venv/bin/python -m pytest -m integration --ds=config.settings.integration -q
```

- [ ] **Step 6: Run the marked suite against local services**

Run the documented command. If services are unavailable, start isolated Docker Compose services with explicit test credentials and non-production volumes, then rerun.

---

### Task 5: Dependency Separation and CI

**Files:**
- Modify: `requirements/requirements.txt`
- Create: `requirements/requirements-test.txt`
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- `requirements/requirements-test.txt` includes `-r requirements.txt` and pins pytest, pytest-django, pytest-cov, pytest-mock, factory_boy, Faker, and coverage tooling.
- Docker continues consuming `requirements/requirements.txt` in its updated path and unchanged invocation behavior.

- [ ] **Step 1: Move test-only direct dependencies**

Remove test runners, plugins, coverage tools, factory_boy, Faker, and test-only direct helpers from production requirements. Add exact pins to `requirements/requirements-test.txt` after `-r requirements.txt`.

- [ ] **Step 2: Verify production imports and Docker dependency path**

Run `venv/bin/python manage.py check` and inspect `docker/Dockerfile` to confirm it still installs `requirements/requirements.txt` only.

- [ ] **Step 3: Add the default CI job**

Install `requirements/requirements-test.txt`; run `pytest`, `manage.py check`, and `manage.py makemigrations --check --dry-run` using test settings.

- [ ] **Step 4: Add the PostgreSQL/Redis integration CI job**

Declare PostgreSQL 16 and Redis 7 services with health checks and test-only environment values. Run `pytest -m integration --ds=config.settings.integration`, then Django and migration checks using integration settings.

- [ ] **Step 5: Validate workflow syntax and dependency consistency**

Inspect YAML, run available local YAML validation if installed, and compare imported test packages with test requirements.

---

### Task 6: Final Verification and Review

**Files:**
- Modify only files required by failures proven during verification.

**Interfaces:**
- Produces exact test counts, coverage totals, commands, file list, and unresolved risks.

- [ ] **Step 1: Run the complete default suite with enforced coverage**

Run: `COVERAGE_FILE=/tmp/luxury-perfume-final.coverage venv/bin/python -m pytest`

- [ ] **Step 2: Run the complete marked integration suite**

Run the documented PostgreSQL/Redis command with `-m integration` and integration settings.

- [ ] **Step 3: Run Django checks**

```bash
venv/bin/python manage.py check --settings=config.settings.test
venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
venv/bin/python manage.py check --settings=config.settings.integration
venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.integration
```

- [ ] **Step 4: Scan for forbidden and stale patterns**

Search for `pytest.raises(Exception)`, debug `print(`, duplicate `api_client` fixtures, duplicate cache fixtures, tracked `.coverage`, and ignored artifacts.

- [ ] **Step 5: Review the final diff and working tree**

Confirm `.gitignore` retains the pre-existing staged lines, `docker/docker-compose.prod.yml` differs only by the user's unrelated edit, no secrets appear, and no assertions were weakened merely to pass.

- [ ] **Step 6: Report exact evidence**

Include commands executed, test counts, branch coverage result, changed files, compatibility impact, security/maintainability benefits, and any remaining risk.
