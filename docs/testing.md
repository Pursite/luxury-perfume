# Testing and Verification

This guide owns automated verification commands and their limits. Run backend
commands from the repository root with the intended Python environment active.
For environment setup, see [Development](development.md); for failure diagnosis,
see [Troubleshooting](troubleshooting.md).

## Verification layers

| Layer | What it verifies | Important boundary |
| --- | --- | --- |
| Default backend suite | Models, serializers, services, API contracts, tasks, cache behavior, and project configuration | SQLite and LocMem do not establish PostgreSQL locking or Redis atomicity |
| PostgreSQL/Redis integration suite | Real constraints, transaction races, row locks, OTP consumption, and security-cache behavior | Requires dedicated disposable services; does not exercise a real external provider |
| Static and Django checks | Lint rules, common security patterns, system configuration, and missing migrations | Passing checks does not prove the absence of vulnerabilities or safe production migrations |
| Frontend checks | React behavior in jsdom, ESLint rules, and production compilation | Mocked API responses and jsdom do not establish real-browser or live-provider behavior |
| Release checks | Production Compose structure, application image, translation smoke check, and validated frontend artifact | A buildable artifact is not proof of production readiness or data recovery |

Tests complement architectural, authorization, concurrency, and API review.
Coverage is a guardrail, not a substitute for behavioral assertions.

## Prerequisites

Use Python 3.12 to match CI and the application Dockerfile. In your active
virtual environment, install the pinned test dependency set:

```bash
python -m pip install --requirement requirements/requirements-test.txt
```

That file includes [runtime requirements](../requirements/requirements.txt)
and adds pytest, pytest-django, pytest-cov, coverage, factory_boy, Faker,
pytest-mock, Ruff, and Bandit. The normal application image installs only the
runtime set; do not assume it includes test tools.

Default backend tests need no PostgreSQL, Redis, worker, or SMS/payment service.
The default suite also contains an optional Docker scratch-carrier test in
`config/tests/test_frontend_release.py`; it skips when Docker or its daemon is
unavailable. Review skips rather than assuming every check executed.

Integration tests additionally require PostgreSQL 16 and Redis 7; Docker Engine
or Docker Desktop with Compose v2 can provide them. Host Python's psycopg also
requires the PostgreSQL client library (`libpq`). Frontend checks require the
Node version in [`frontend/.nvmrc`](../frontend/.nvmrc) and npm.

## Default backend suite

```bash
python -m pytest
```

[`pytest.ini`](../pytest.ini) discovers `tests.py`, `test_*.py`, and `*_tests.py`
under `apps`, `config`, and `tests`. Its default settings module is
`config.settings.test`. Default `addopts`:

- show extra test outcomes with `-ra`;
- enforce `--strict-config` and `--strict-markers`;
- select `-m "not integration"`;
- measure branch coverage for `apps` and `config` using `.coveragerc`;
- show missing lines and require at least 85% coverage.

The repository registers the `integration` marker; pytest-django supplies
markers such as `django_db`. Unknown markers/configuration should be corrected,
not silently accepted.

For the full default run with CI warning handling:

```bash
python -W error -m pytest
```

This retains all configured pytest options and additionally turns Python
warnings into errors. Plain `python -m pytest` does not request that warning
policy. Investigate deprecations, isolation failures, and dependency warnings
at their source rather than broadly suppressing them.

### Test settings and isolation

[`config/settings/test.py`](../config/settings/test.py) substitutes:

| Dependency | Test configuration |
| --- | --- |
| Database | SQLite `:memory:` |
| Ordinary/security caches | Separate LocMem cache locations |
| Password hashing | MD5 test hasher for speed; not the deployment password hasher |
| Celery broker/results | `memory://` / `cache+memory://` |
| Celery execution | Eager, with task exceptions propagated |
| Email | In-memory backend |

Test-only signing defaults make the suite self-contained. Shared settings still
read the root `.env`, and existing environment variables can affect settings not
explicitly overridden. Check the selected settings when results differ between
machines; never run tests with production settings or credentials.

The root [`conftest.py`](../conftest.py) supplies a DRF API client with a test
Origin and clears **every configured cache alias before and after each test**.
Product tests and integration tests redirect media to temporary paths through
their scoped fixtures. Use the relevant fixtures for uploads and generated files
rather than writing into a developer's media directory. Factory modules supply
explicit users, products, carts, and other domain records.

Use `django_db` for ordinary database tests; tests requiring actual commits and
transaction boundaries use `django_db(transaction=True)`. Neither marker makes
SQLite behave like PostgreSQL.

## PostgreSQL and Redis integration suite

### Start isolated services

Run from the repository root:

```bash
docker compose -f docker/docker-compose.integration.yml up -d --wait
```

[`docker/docker-compose.integration.yml`](../docker/docker-compose.integration.yml)
uses project `luxury-perfume-integration`, services `integration-db` and
`integration-redis`, loopback-only ports, and tmpfs storage. It is separate from
the normal development stack and needs no root development `.env` for Compose.

| Setting | Local default |
| --- | --- |
| PostgreSQL | `127.0.0.1:55432`, PostgreSQL 16 |
| Database/user | `luxury_perfume_test` / `luxury_perfume_test` |
| Database authentication | Disposable Compose database uses `trust`; integration password default is empty |
| Ordinary Redis cache | `redis://127.0.0.1:56379/14` |
| Security Redis cache | `redis://127.0.0.1:56379/15` |

Trust authentication is for this isolated test service, not a deployment recipe.
The database user must be able to create Django's test database. Tmpfs data is
ephemeral and can be lost when containers stop or are removed.

### Run the marked suite

```bash
python -m pytest \
  -o addopts="--strict-config --strict-markers" \
  -m integration \
  --ds=config.settings.integration \
  -q
```

This command runs Host Python against the published integration ports.
[`config/settings/integration.py`](../config/settings/integration.py) inherits
test settings but replaces SQLite and LocMem with PostgreSQL and Redis.
Celery remains eager; no worker or Beat is started by this integration stack.

The `-o addopts=...` replacement removes the normal `not integration` selector
and all coverage options, retaining strict configuration and marker validation.
`-m integration` then selects the marked tests and `--ds` explicitly chooses the
integration settings. Merely changing settings does not select integration tests.
The explicit integration command neither enforces the default 85% coverage gate
nor enables `-W error`; CI uses the same separation. Integration results must
not be described as a full default-suite or coverage run.

### Why real services matter

Existing modules under [`tests/integration/`](../tests/integration/) cover:

| Module | Examples of implemented checks |
| --- | --- |
| `test_postgres_transactions.py` | Named constraints, rollback/on-commit behavior, product-image row locking, identity uniqueness, concurrent signup |
| `test_cart_transactions.py` | First-cart creation races, same-item increments, constraints, and unrelated-owner lock isolation |
| `test_order_transactions.py` | Last-item checkout races, duplicate checkout keys, expiry/payment ordering, and stock updates |
| `test_payment_transactions.py` | Initialization, verification/refund claims, callback/reconciliation races, and transaction identity conflicts |
| `test_notification_transactions.py` | Concurrent delivery claims and notification transaction behavior |
| `test_redis_security_cache.py` | Cache-alias isolation, throttle keys, OTP lockouts, leases, and concurrent consumption |

These tests use real transaction boundaries and, where needed, separate thread
connections and synchronization. SQLite cannot validate PostgreSQL row-lock
ordering or contention. LocMem cannot validate Redis server-side atomic
operations, lease ownership, or cross-connection state. OTP tests exercise both
Redis admission state and durable database redemption; Redis alone is not the
source of replay protection.

Run integration checks for changes involving identity constraints, signup races,
Cart mutations, stock/reservations, Payment/Refund transitions, Notification
claims, OTP/security-cache behavior, or transaction/lock ordering.

### Overrides and teardown

The integration settings accept:

```text
INTEGRATION_DB_NAME
INTEGRATION_DB_USER
INTEGRATION_DB_PASSWORD
INTEGRATION_DB_HOST
INTEGRATION_DB_PORT
INTEGRATION_CACHE_REDIS_URL
INTEGRATION_SECURITY_REDIS_URL
```

Defaults match the local integration Compose file. If its ports conflict, use
independently managed, dedicated test services and set the matching variables;
changing an environment variable does not change the Compose port mapping.
CI instead supplies service ports `5432` and `6379` through these overrides.

**Never target production, shared development data, or valuable Redis databases.**
Django creates a test database; transaction tests mutate/flush data, and the root
fixture clears the configured Redis databases around each test. Redis databases
14/15 are numbers, not an access-control boundary. Do not run competing suites
against the same services.

When finished:

```bash
docker compose -f docker/docker-compose.integration.yml down
```

This removes the disposable integration containers. It is not a command for the
persistent development stack.

## Coverage

Both [`pytest.ini`](../pytest.ini) and [`.coveragerc`](../.coveragerc) specify
85%; pytest also explicitly enables branch coverage. The terminal report shows
missing lines and skips fully covered files. The measured production sources
are `apps` and `config`.

The configured omit patterns exclude test directories, migrations, bytecode,
`config/asgi.py`, `config/wsgi.py`, and `config/settings/*`. Report exclusions
also cover `if TYPE_CHECKING:` and `if __name__ == "__main__":` branches.
These are intentional measurement boundaries, not evidence that those areas
need no review. Migration drift and image checks verify different concerns.

Do not lower the threshold or exclude changed business logic to pass a build.
Use missing lines/branches to find untested behavior, then add assertions for
meaningful outcomes, including rejection and rollback paths.

## Focused tests and regression design

Start with an actual module or node ID:

```bash
python -m pytest apps/users/tests/test_password_management.py -q
python -m pytest apps/cart/tests/test_api.py::test_get_empty_cart_does_not_create_cart -q
```

Focused runs retain the full coverage gate and may fail it despite passing
assertions. For a diagnostic iteration only, disable coverage collection:

```bash
python -m pytest apps/users/tests/test_password_management.py --no-cov -q
```

Then return to the full default suite. For a focused integration run, retain
all options from the integration command and append the specific module/node ID.

Bug fixes require regression tests for the verified failure. Review the affected
contract: URL/method, authentication, permissions, ownership, input/output
schemas, status/error semantics, visibility, pagination/filtering, and localized
human messages. Include rejected requests and another owner's records.

Authentication tests include username/password signup/login, OTP flows, refresh
rotation/blacklisting, logout, password change/setup/reset, phone verification,
throttling, and rollback/retry of OTP-authorized writes. Domain suites cover
Cart ownership, Order snapshots/reservations, Payment/Refund state, image
lifecycle, and Notification retry/manual-review outcomes. Inspect the relevant
tests before extending a claim of coverage.

For contended writes, assert durable outcomes under concurrency: no lost updates,
duplicate success, partial rollback, or invalid transition. Test idempotency,
retry/redelivery, and commit ordering where applicable. Passing sequential tests
or mocking a lock call is insufficient evidence of real lock safety.

### Celery and provider boundaries

Eager execution uses `CELERY_TASK_ALWAYS_EAGER=True` and
`CELERY_TASK_EAGER_PROPAGATES=True`, including in integration settings. Tests
exercise task functions and enqueue behavior without proving broker delivery,
worker isolation, or Beat scheduling in a running cluster.

Tests such as the product-thumbnail suite explicitly execute captured
`transaction.on_commit()` callbacks where needed. Ordinary test transaction
rollback does not execute those callbacks automatically. Distinguish domain
logic, enqueueing after commit, task execution, and retry safety. Tasks should
receive simple identifiers rather than ORM instances.

The Users `operational_sms` fixture registers a controlled test adapter; Payment
and Notification tests also use doubles. Success in those tests is not evidence
of live SMS delivery or a real payment gateway. Avoid external providers,
network dependencies, developer data, and uncontrolled clock assumptions in
regression tests. See [Authentication](authentication.md), [API](api.md), and
[Security](security.md) for the contracts under test.

## Static checks and migrations

After focused testing, this block completes the default backend verification
sequence; pair it with the warnings-as-errors full suite above:

```bash
python -m ruff check apps config tests
python -m bandit -q -r apps config -x 'apps/**/tests/**,config/tests/**'
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

Ruff checks configured lint rules; Bandit identifies common static security
patterns in production Python. Neither proves vulnerability freedom. Review
authentication, authorization, secrets, uploads, cache isolation, concurrency,
and API compatibility separately. Never weaken production protections to make
a test or static check pass.

With integration services running, also use:

```bash
python manage.py check --settings=config.settings.integration
python manage.py makemigrations --check --dry-run --settings=config.settings.integration
```

Drift checks do not write migrations. They detect model changes lacking matching
migration state, not compatibility with every existing production database.
For schema changes, inspect history, existing data, constraints, indexes,
locking, and rollback implications; generate only the required migration and
test its behavior. See [Deployment](deployment.md) for operational procedures.

## Frontend verification

From the repository root:

```bash
cd frontend
nvm install
nvm use
npm ci
npm run lint
npm test
VITE_API_BASE_URL=https://shop.exonplus.ir npm run build
```

[`.nvmrc`](../frontend/.nvmrc) selects Node 24.19.0;
[`package.json`](../frontend/package.json) requires `>=24.15.0 <25`.
`npm ci` uses the committed lockfile. It is what CI verifies; reinstalling after
every dependency-neutral edit is unnecessary.

ESLint allows zero warnings. `npm test` runs Vitest once in jsdom with Testing
Library; tests live alongside source. Shared setup installs DOM matchers,
cleans rendered components, and clears session storage. API-shaped fixtures and
mocked fetch responses support tests for authentication/restoration, password
management and SMS gating, protected routes, catalogue/product rendering,
Account forms, Cart synchronization, loading/error states, and safe navigation.
This is not a browser end-to-end suite against a live backend.

Vite requires a build-time HTTPS `VITE_API_BASE_URL` with a root pathname.
Use an origin without an API path; CI uses the public origin above. Output goes
to ignored `frontend/dist/`. `VITE_*` values are public browser configuration
and must contain no secrets. Release validation additionally expects the
repository's production origin; an arbitrary valid HTTPS origin can compile
but fail the release check. See the [frontend guide](../frontend/README.md)
for client behavior and design ownership.

## CI verification boundaries

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on pushes and
pull requests:

| Job | Enforced checks |
| --- | --- |
| React storefront | Clean npm install, ESLint, Vitest, production build, release stamp/validation, frontend carrier image build/export |
| SQLite and LocMem | Python 3.12, test dependencies, full pytest with `-W error` and branch coverage, Ruff, Bandit, Django checks, migration drift |
| PostgreSQL and Redis | Real PostgreSQL 16/Redis 7 services, explicit integration pytest command, integration Django checks and migration drift |
| Application image | After backend jobs: production Compose validation, final Docker image build/export, Persian translation catalogue smoke check |
| Release gate | Requires all four jobs above |

The image smoke check verifies a committed translation in the final image; it
is not a complete application startup test. A successful local pytest run does
not establish that the production image or frontend release can be built.

On pushes to `main`, separate publication jobs promote archived images after
the gate. Production deployment is a separate manual workflow, not part of a
pull-request test run. Keep pipeline details in [CI/CD](ci-cd.md) (currently a
placeholder for the next documentation phase) and operational details in
[Deployment](deployment.md).

## Before a pull request

1. Run focused regressions and inspect the affected implementation/API contract.
2. Run the full default backend suite with warnings as errors for backend changes.
3. Run the real-service integration suite when database/Redis semantics matter.
4. Run the applicable static, system, and migration checks above.
5. Run frontend lint, tests, and the production build for frontend changes.
6. Review security, ownership, transactions, queries, and compatibility beyond
   the automated results; update the owning documentation.
7. Run `git diff --check` and inspect the intended diff for unrelated files or secrets.
8. Report exactly which checks ran and their results; distinguish skipped checks
   and environment failures from passing assertions.

For failures, isolate the smallest reproducible test before changing code or
assertions. [Troubleshooting](troubleshooting.md) provides environment diagnostics.
