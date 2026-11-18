# Luxury Perfume

A fragrance e-commerce project with a Django REST Framework backend and an
independent React/Vite storefront. PostgreSQL owns durable state; Redis provides
catalogue caching, temporary security state, and Celery transport/results.
Docker Compose defines local development and a single-VPS production layout.

The backend implements identity, catalogue, owner-bound Cart, Order/stock, and
provider-neutral financial/delivery workflows. The storefront exposes a subset
of those capabilities. Real Payment and SMS adapters are not registered, and
provider-dependent flows are disabled by default; this is not a claim of a live
commercial deployment.

## Engineering highlights

- **Domain boundaries:** views coordinate HTTP, serializers validate/represent,
  services own mutations, and selectors own reusable reads. PostgreSQL
  constraints complement supported validation paths.
- **Transactions and ownership:** sensitive user mutations, Cart writes,
  checkout/stock reservations, and financial transitions use workflow-specific
  locks and constraints. Owner-scoped queries protect private resources;
  identifiers alone never authorize access.
- **Identity and sessions:** bearer access tokens, rotating HttpOnly refresh
  cookies, refresh blacklisting, and password-state revocation. OTP workflows
  combine durable PostgreSQL `OTPChallenge` redemption with Redis generations,
  attempts, and leases; the two stores do not share a distributed transaction.
- **Commerce integrity:** Cart uses current prices/availability without reserving
  stock. Checkout snapshots customer/address/Product/prices, reserves stock,
  and clears captured lines transactionally. Orders own inventory transitions;
  Payments owns verification and Refund obligations.
- **Recovery boundaries:** provider-neutral Payment reconciliation and a durable
  Order-SMS outbox handle retries/manual-review states. External effects remain
  uncertain until supported evidence is recorded; provider acceptance is not
  handset delivery, and browser callbacks are not financial proof.
- **Verification and delivery:** real PostgreSQL/Redis concurrency tests complement
  SQLite/LocMem tests. CI validates backend/frontend artifacts; manual CD checks
  matching revision labels/digests and prepares a stamped static frontend before
  atomic symlink activation. This is not an atomic database/container rollback.

See [Architecture](docs/architecture.md) for the mechanisms and their limits.

## Feature readiness

| Area | Backend | React storefront |
| --- | --- | --- |
| Username/password and sessions | Signup/login, cookie refresh/logout; usable without SMS | Signup/login and session restoration |
| Account and credentials | Profile/address reads/updates; current-password-verified Change Password | Account/address forms and Change Password |
| OTP and phone | Signup/login, profile-phone verification, initial Set Password, and recovery implemented; require operational SMS | Eligible setup/recovery are capability-gated; SMS signup/login stay disabled; phone verification UI is absent |
| Catalogue | Public active Products, filtering/search/ordering/pagination, ordered fragrance notes/images, shared non-staff cache; staff-only mutations/uploads | Catalogue and slug-addressed Product Detail/gallery |
| Cart | Authenticated owner-derived state, live prices/stock, synchronous writes; no guest Cart or reservation | Authenticated Cart with backend-authoritative totals/availability |
| Orders/inventory | Read-only customer history API, internal checkout snapshots/reservations, service-backed Admin fulfillment | Customer Order history, checkout, and Ticket screens are absent |
| Payments/Refunds | Provider-neutral attempts, verification, reconciliation and Refund obligations; disabled without a real adapter | Online payment control is unavailable; no completed payment-result flow |
| Notifications | Durable Order-SMS obligations and retry/manual-review processing; SMS disabled without a real adapter | No SMS delivery management UI |

Initial password setup requires an eligible OTP-only account with a phone and
existing username; recovery requires an active password account. Both require
operational SMS. Password signup/login/change do not. Backend capability does
not imply frontend exposure or operational provider readiness.

Contracts and workflows: [API](docs/api.md), [Authentication](docs/authentication.md),
and [Frontend](frontend/README.md).

## Technology stack

| Layer | Repository stack |
| --- | --- |
| Backend | Python 3.12, Django 6, Django REST Framework, Simple JWT, django-filter, Pillow |
| Data and background work | PostgreSQL 16, Redis 7, Celery Worker/Beat, Gunicorn |
| Frontend | Node 24 LTS, React 19, Vite 8, React Router 7, JavaScript/JSX and CSS |
| Verification | Pytest, pytest-django, pytest-cov, Ruff, Bandit; Vitest, Testing Library, ESLint |
| Packaging/delivery | Docker Compose, GitHub Actions, separate backend/frontend GHCR images |

Exact versions: [runtime requirements](requirements/requirements.txt),
[test requirements](requirements/requirements-test.txt),
[frontend manifest](frontend/package.json), and [npm lockfile](frontend/package-lock.json).
Use [`.nvmrc`](frontend/.nvmrc) for Node; the supported range is `>=24.15.0 <25`.

## Architecture overview

```text
React storefront → API client → Django View → Serializer
                                              ↓
                                   Service (write) / Selector (read)
                                              ↓
                                         PostgreSQL

Django/services ↔ Redis cache/security state
Committed work → Redis broker → Celery worker
One Celery Beat → scheduled recovery/maintenance tasks
```

Users, Products, Cart, Orders, Payments, and Notifications retain distinct domain
ownership. React Context coordinates authentication and Cart state; Django owns
permissions, prices, stock, and durable data. Celery handles suitable asynchronous
work; Cart writes remain synchronous. Post-commit enqueueing does not itself
make database writes and broker delivery atomic.

## Quick start

Install Git, Docker Engine/Desktop with the Compose plugin, and Node 24 LTS
(`nvm` is used below). Follow [Development](docs/development.md) for complete
prerequisites, service inspection, superusers, and daily commands.

From a fresh clone:

```bash
git clone https://github.com/Pursite/luxury-perfume.git
cd luxury-perfume

if [ ! -e .env ]; then
  cp docker/env/.env.development.example .env
fi

docker compose --env-file .env \
  -f docker/docker-compose.yml -f docker/docker-compose.dev.yml config -q

docker compose --env-file .env \
  -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d --build

docker compose --env-file .env \
  -f docker/docker-compose.yml -f docker/docker-compose.dev.yml \
  exec web python manage.py migrate
```

Django listens on loopback port 8000 by default. Inside Docker, PostgreSQL and
Redis resolve as `db` and `redis`; neither service is published to the host.
Host Python cannot reach them simply by setting `DB_HOST=localhost`. Optional
host execution needs independently reachable services; see the development guide.
Preserve existing `.env` values and use development credentials only.

Start Vite separately from the repository root:

```bash
cd frontend
nvm install
nvm use
npm ci
npm run dev
```

Open Vite's printed URL, normally `http://127.0.0.1:5173`. It proxies `/api/` and
`/media/` to Django at `http://localhost:8000`. For custom ports, align the proxy
and backend Origin allowlists as described in [Frontend](frontend/README.md).
The shared web healthcheck's production Host header differs from the development
allowlist, so Docker may mark web unhealthy while local requests succeed; see
[Troubleshooting](docs/troubleshooting.md#health-status-and-the-development-host-mismatch).

Stop Vite with Ctrl+C. To stop/remove development containers from the repository
root while retaining named volumes:

```bash
docker compose --env-file .env \
  -f docker/docker-compose.yml -f docker/docker-compose.dev.yml down
```

Do not add `-v` for routine shutdown: it deletes PostgreSQL/Redis volume data.

## Testing and release boundaries

The default backend suite uses SQLite/LocMem and an 85% branch-coverage gate;
CI invokes it with warnings as errors. Separate PostgreSQL/Redis integration
tests exercise real locks, constraints, and atomic operations. Ruff, Bandit,
Django system checks, and migration-drift checks complement behavioral tests.
Frontend CI runs ESLint, Vitest, and a production Vite build; image validation
checks production Compose, release structure, and a committed translation in
the final Python image. These checks do not establish live provider behavior.

For example, in an active Python 3.12 test environment at the repository root:

```bash
python -m pip install --requirement requirements/requirements-test.txt
python -W error -m pytest
python -m ruff check apps config tests
```

Use [Testing](docs/testing.md) for the complete backend/integration/frontend
commands and isolation requirements. Never target production or valuable shared
data with tests. This README reports verification design, not a current test run.

CI runs on pushes and pull requests; the Release gate requires backend, frontend,
integration, and image checks. Only qualifying successful pushes to `main`
publish the previously built images to GHCR. A documentation branch can pass
the gate without publication. The backend image jobs are `Application image`
and `Publish application image`; the latter requires the complete gate and main
push condition. Production CD is manual and separate: it resolves
matching image digests/revision labels, runs checks/migrations/static collection,
verifies web and worker/Beat conditions, then activates the prepared frontend.
It does not independently query the selected commit's CI conclusion.

See [CI/CD](docs/ci-cd.md) for pipeline behavior and [Deployment](docs/deployment.md)
for host setup and recovery. Workflow definitions do not prove a VPS is deployed.

## Documentation and contributions

Start with the [documentation hub](docs/README.md) for reader-oriented paths.

| Topic | Guide |
| --- | --- |
| Design and local setup | [Architecture](docs/architecture.md), [Development](docs/development.md) |
| HTTP and identity | [API](docs/api.md), [Authentication](docs/authentication.md) |
| Controls and limitations | [Security](docs/security.md) |
| Verification and diagnosis | [Testing](docs/testing.md), [Troubleshooting](docs/troubleshooting.md) |
| Release and operations | [CI/CD](docs/ci-cd.md), [Deployment](docs/deployment.md) |
| Browser application | [Frontend](frontend/README.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

Read the contribution guide before submitting changes. The
[PR template](.github/PULL_REQUEST_TEMPLATE.md),
[bug report](.github/ISSUE_TEMPLATE/bug_report.md), and
[feature request](.github/ISSUE_TEMPLATE/feature_request.md) help communicate
verification and impact. Issue chooser templates become available after merge
to the default branch; their presence on a working branch does not activate them.

## Status, security, and operational limits

The project has implemented domain logic, automated checks, and release tooling;
it does not claim a publicly available production shop. Real Payment/SMS adapters,
customer checkout/Order/Ticket UI, and broader frontend localization remain
unfinished. Backend human messages support English/Persian; machine contracts
stay stable.

Monitoring/alerting, external log aggregation, automated PostgreSQL/media backups,
and tested restore procedures are not managed by this repository. Nginx, TLS,
production secrets, capacity planning, and existing-schema compatibility require
operator preparation. Named volumes and Redis AOF persistence are not backups.
Code rollback requires schema compatibility and does not reverse data migrations
or external financial/delivery effects.

Controlled logging paths deliberately minimize sensitive data and provide
correlation IDs; they do not guarantee universal redaction across all loggers or
exceptions. The JSON formatter has a documented UUID `user_id` encoding limitation.
Never expose credentials, OTPs, tokens, or private data in logs/examples/screenshots.
See [Security](docs/security.md#logging-secrets-and-transport) and
[Deployment](docs/deployment.md#logs-and-retention) for scope and operational limits.

## License

Licensed under the [MIT License](LICENSE). Copyright © 2026 Armin Bahadori.
