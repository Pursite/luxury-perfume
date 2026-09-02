# Luxury Perfume

A Django REST Framework backend and Luxury Perfume React storefront for a perfume,
cologne, and body-splash store. Django provides user authentication and profile
management, a public fragrance catalogue with staff-only mutations,
authenticated carts, server-owned Orders, Payments/Refunds, and an SMS outbox;
`frontend/` provides the customer experience.

## Implemented features

- Username/password signup and login; phone/OTP signup and login; password
  reset by OTP; authenticated phone verification for username/password users.
- JWT access tokens with a persistent HttpOnly rotating refresh cookie, explicit refresh rotation and blacklisting, password-change session revocation, and idempotent logout.
- Derived profile completion plus repeatable profile/address updates. Accounts
  remain active and usable while customer details are incomplete.
- Public product list and detail endpoints with fragrance concentration,
  audience, family, season, usage time, introduction year, and normalized
  top/heart/base notes whose submitted order is preserved; product types such
  as perfume and Body Splash remain categories. The catalogue also supports
  search, filtering, ordering, pagination, and Redis-backed anonymous-response
  caching shared with authenticated non-staff users. Staff catalogue requests
  bypass that shared cache.
- Staff-only product and image mutations, content-aware JPEG/PNG/WebP validation, category-cycle protection, and data-integrity constraints.
- Authenticated, owner-bound carts with live Product prices, stock, activity,
  and images. Cart writes are synchronous PostgreSQL transactions and never
  reserve stock or prices.
- A disabled-by-default Payments backend with immutable-price Payment attempts,
  full Refund obligations, provider-adapter contracts, owner-only status,
  Orders integration, reconciliation tasks, trusted initiator-IP evidence, and
  audit-data retention. No real gateway adapter is selected, so production
  Payments cannot yet be enabled.
- A disabled-by-default SMS outbox for paid-order confirmation, processing
  alerts to active superusers with valid account phones, and shipment notices.
  It has no public API and no real provider adapter yet; a future provider
  must be separately reviewed before SMS can be enabled.
- A responsive React storefront with a server-filtered catalogue,
  slug-addressed Product Detail gallery and fragrance pyramid,
  username/password JWT login, an authenticated Account Details experience,
  and the real authenticated Cart. SMS UI, Orders, Tickets, and
  online payment UI remain visibly unavailable and are not simulated.

See [authentication details](docs/authentication.md), the [API reference](docs/api.md), and the [security model](docs/security.md).

## Technology stack

- Python 3.12+, Django 6, Django REST Framework, and Simple JWT
- PostgreSQL, Redis, Celery, and Gunicorn
- Pytest, pytest-django, factory_boy, and Faker
- Node 24 LTS, React 19, Vite, React Router, Vitest, Testing Library, and ESLint

Runtime package versions are in
[requirements/requirements.txt](requirements/requirements.txt); test-only
tooling is layered on top through
[requirements/requirements-test.txt](requirements/requirements-test.txt).

## Architecture

Requests are coordinated by views, validated and represented by serializers,
then delegated to services for mutations or selectors for reusable reads.
Models and database constraints enforce persisted invariants; Celery handles
OTP delivery, image thumbnails, Order-expiry recovery, Payment/Refund recovery,
Notification delivery, and retention work through the worker and Beat.
`apps.cart` remains entirely
synchronous and database-backed. `apps.lib` contains shared infrastructure
such as cache, security-cache, logging, pagination, permissions, throttles,
and image validation.

The independent `frontend/` application uses a centralized browser API client,
React Context for authentication and Cart state, focused route/page components,
and a plain-CSS black/ivory/gold design system. It does not run inside Django
apps or require a Node container.

For the complete design, see [architecture.md](docs/architecture.md).

## Production logging

Application logs are JSON records written to container output: the `activity`
logger goes to stdout, while the `security`, `system`, and Django error loggers
go to stderr. Financial lifecycle records use the activity logger with a
separate allowlisted `financial` category. Every HTTP
response includes a server-generated `X-Request-ID`; the same value is present
as `request_id` and `correlation_id` in logs produced while that request is
handled. Tasks based on the shared correlated-task class use the Celery task ID
as `correlation_id`; OTP enqueue records also expose that safe `task_id`.

The production Compose override uses Docker's `local` driver with a 10 MiB
maximum file size and three files per service. Use `docker compose logs` to
inspect them; do not read Docker's internal log files. Log events deliberately
exclude request bodies, query strings, client IPs, phone numbers, OTPs,
passwords, JWTs, credentials, provider session/transaction/message
identifiers, and exception messages. Financial records may include the
configured provider label, public Payment/Order/Refund UUIDs, and a bounded
outcome code; they do not include provider payloads or transport evidence.

## Development setup

Docker Compose is the supported default development workflow. Copy the complete
development template to the local, ignored `.env`, validate the
merged Compose configuration, and start the stack:

```bash
cp docker/env/.env.development.example .env

docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  config -q

docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  up --build
```

Inside Docker, Django and Celery reach PostgreSQL as `db` and Redis as `redis`.
Do not replace those service names with `localhost` in `.env` when using
Compose. The development override publishes only Django on `127.0.0.1`;
PostgreSQL and Redis remain internal to Docker.

`.env` is always local and ignored.
`docker/env/.env.development.example` and
`docker/env/.env.production.example` are safe, tracked templates. Never put
real secrets in an example file or commit a populated runtime environment file.
The `luxury-perfume` development Compose project initializes database
credentials only when its local volume is first created. Do not replace an
existing local `.env` with renamed database values unless that volume is
disposable or you have migrated it deliberately.

Direct-host execution is optional. Install the Python dependencies and run
PostgreSQL and Redis on the host, then override only the container-specific
addresses in the current shell:

```bash
export DB_HOST=localhost
export CACHE_REDIS_URL=redis://localhost:6379/0
export SECURITY_REDIS_URL=redis://localhost:6379/1
export CELERY_BROKER_URL=redis://localhost:6379/2
export CELERY_RESULT_BACKEND=redis://localhost:6379/3

venv/bin/python manage.py migrate
venv/bin/celery -A config worker --loglevel=INFO
venv/bin/python manage.py runserver
```

Django automatically loads the root `.env` file. The shell overrides above
change only container-specific addresses for this optional host workflow.
Adjust `DB_PORT` and the Redis URL ports if the host services use non-default
ports.

The API prefixes are `/api/v1/users/`, `/api/v1/products/`, `/api/v1/cart/`,
`/api/v1/orders/`, and `/api/v1/payments/`. Payment handlers return 503 while
`PAYMENTS_ENABLED=False` after normal authentication, permission, and throttle
checks.

Authenticated customers can read their own serialized profile from
`GET /api/v1/users/profile/`. The endpoint accepts no user identifier and
returns the same safe user representation used by profile mutations.

### React storefront

Keep Django running at `http://localhost:8000`. Install Node 24 LTS, then run
the Vite application on the host:

```bash
cd frontend
nvm install 24
nvm use
npm ci
npm run dev
```

The storefront opens at `http://localhost:5173`. Vite proxies relative
`/api/...` and `/media/...` requests to Django, so backend origins are not
scattered through components. The tracked development environment example
already allows both `localhost:5173` and `127.0.0.1:5173`; do not overwrite a
working private `.env` merely to copy the example.

Frontend details, architecture, security trade-offs, and scripts are in
[frontend/README.md](frontend/README.md).

## Tests and checks

```bash
python -m pip install --requirement requirements/requirements-test.txt
venv/bin/python -m pytest
venv/bin/python -W error -m pytest
venv/bin/python -m ruff check apps config tests
venv/bin/python -m bandit -q -r apps config -x 'apps/**/tests/**,config/tests/**'
venv/bin/python manage.py check --settings=config.settings.test
venv/bin/python manage.py makemigrations --check --dry-run \
  --settings=config.settings.test
```

The default suite uses SQLite and LocMem, excludes tests marked `integration`,
measures production branch coverage, enforces an 85% minimum, and treats
warnings as errors in CI. Ruff checks Python lint rules and Bandit checks the
production source for common static-security issues. To run the marked
PostgreSQL/Redis checks with isolated loopback-only services:

```bash
docker compose -f docker/docker-compose.integration.yml up -d --wait
venv/bin/python -m pytest \
  -o addopts="--strict-config --strict-markers" \
  -m integration \
  --ds=config.settings.integration \
  -q
docker compose -f docker/docker-compose.integration.yml down
```

Override the dedicated `INTEGRATION_DB_*`,
`INTEGRATION_CACHE_REDIS_URL`, and `INTEGRATION_SECURITY_REDIS_URL`
environment variables when using existing test services. The integration suite
covers case-insensitive identity constraints and concurrent signup, Cart
creation and increment races, unrelated-user Cart lock isolation, Orders
stock/reservation transactions, Payment transaction and reconciliation races,
Notification delivery concurrency, Redis OTP-consumption races, and
security-throttle keys. Never point integration
tests at production databases or Redis databases.

Run the frontend checks with Node 24 LTS:

```bash
cd frontend
npm ci
npm run lint
npm test
VITE_API_BASE_URL=https://shop.exonplus.ir npm run build
```

## CI and production images

The React storefront, SQLite/LocMem, and PostgreSQL/Redis jobs run for every
pull request and push. Frontend CI explicitly uses Node 24 LTS and performs a
clean install, lint, tests, and production build. The complete release gate
also requires the backend unit/integration checks, production Compose
validation, and read-only backend and frontend image builds. Pull requests and
pushes stop after those checks. On successful pushes to `main`, the backend and
frontend publication jobs both depend on that gate, verify that their SHA tags
do not already exist, then promote the archived build artifacts—without a
second Docker build—to `ghcr.io/pursite/luxury-perfume:<commit SHA>` and
`ghcr.io/pursite/luxury-perfume-frontend:<commit SHA>`, each with OCI source and
revision labels. The backend jobs are named `Application image` and `Publish application image`; the corresponding frontend publication job is
`Publish frontend image`. The frontend image is only a scratch filesystem
carrier; it is not a production runtime.

Production deploys the same backend image for Django, Celery, and Celery Beat, pinned to its
resolved content digest, alongside the matching frontend carrier artifact. The
VPS extracts that artifact into an immutable SHA-addressed release and
atomically switches `frontend-current`; no Node/npm build occurs on the VPS.
The backend image contains application code and dependencies only; the VPS
keeps the production `.env`, PostgreSQL data, Redis data, static files, and
media at runtime. See [deployment.md](docs/deployment.md) for the protected
GHCR pull token, release ordering, first deployment, normal deployment, and
the limitations of code-only rollback.

## Documentation

| Document | Contents |
| --- | --- |
| [architecture.md](docs/architecture.md) | Layers, infrastructure, configuration, and testing |
| [authentication.md](docs/authentication.md) | Identity rules, OTP flows, JWTs, and profile behavior |
| [api.md](docs/api.md) | Verified endpoint contract |
| [security.md](docs/security.md) | Implemented controls and limitations |
| [deployment.md](docs/deployment.md) | Deployment guidance and template caveats |
| [frontend/README.md](frontend/README.md) | React workflow, source map, design, and browser-state architecture |
| [AGENTS.md](AGENTS.md) | Durable repository-change expectations |

Update the relevant document whenever routes, configuration, authentication behavior, architecture, or deployment requirements change.

## Project status and roadmap

The users, authentication, profiles, fragrance products, categories, brands,
reusable fragrance notes, product-image, Cart domain, and first customer React
storefront are implemented. The project remains under active development.

Orders, stock reservations, customer Order history, manual Admin fulfillment,
the provider-independent Payments/Refunds backend, and the durable SMS-outbox
architecture are implemented. New Orders snapshot the single server-owned flat
shipping rate, `350000.00 IRT` (350,000 toman), and set `total = subtotal +
shipping_amount`. Payments define decimal prices as toman (`IRT`) and remain
disabled by default because no real gateway adapter is registered. SMS remains
disabled because no real provider adapter is registered.

The backend can negotiate human-readable API messages in English (`en`) and
Persian (`fa`). JSON keys, status values, codes, URLs, and other machine
contracts remain stable. The current React storefront remains English (apart
from its existing Persian development notice); frontend localization is
deferred.

Deferred production hardening includes real Payment and SMS providers,
monitoring/alerting, PostgreSQL/media backup and tested restores, production
migration-history/schema reconciliation, and provider-specific localization.
Host monitoring, backup scheduling, backup storage, and restore drills are
external production operations; this repository does not configure or claim
to run them.

The repository includes a Docker Compose deployment layout for development and
a single VPS, plus a manual GitHub Actions production deployment workflow; see
`docs/deployment.md` for production template preparation, environment secrets,
host-managed Nginx, and operations.

## License

This project is licensed under the MIT License.  
Copyright © 2026 Armin Bahadori.
