# Architecture

## Overview

Wine Shop API is a Django 6 and Django REST Framework application. Its current Django applications are `apps.users`, `apps.products`, and `apps.lib`.

```text
wine-shop/
├── apps/
│   ├── lib/          # shared infrastructure
│   ├── products/     # catalogue domain
│   └── users/        # identity and profile domain
├── config/           # Django, URL, WSGI, ASGI, and Celery configuration
├── docker/
│   ├── env/           # tracked environment templates
│   ├── Dockerfile
│   └── docker-compose*.yml
├── docs/
├── manage.py
└── requirements/
    ├── requirements.txt
    └── requirements-test.txt
```

## Request layers

```text
HTTP request
    ↓
APIView
    ↓
Input serializer
    ↓
Service (mutation) or selector (read)
    ↓
Model / PostgreSQL
    ↓
Output serializer and HTTP response
```

- **Views** orchestrate HTTP: select permissions and throttles, validate serializers, call the domain layer, and return responses.
- **Serializers** validate and normalize request data and define output representations. Product upload serializers also validate image content.
- **Services** implement state-changing workflows such as signup, OTP handling, password reset, logout, product writes, image writes, and post-commit cleanup/queueing.
- **Selectors** contain reusable read queries, including case-insensitive username lookups and filtered product queries.
- **Models** define durable state and model-level invariants. PostgreSQL constraints add final protection for active-user identities, case-insensitive username/email uniqueness, product discount prices, and primary product images.

## Applications

### `apps.users`

Owns the custom user and address models, user serializers and views, selectors, and services for username/password and phone/OTP authentication, password reset, profile completion/update, and logout. It queues the Celery OTP task.

### `apps.products`

Owns products, categories, brands, and product images. Public catalogue reads are filtered through selectors and can be cached. Product and image writes are staff-only at the API boundary. Category hierarchy validation prevents cycles; image services schedule thumbnail generation after commit.

### `apps.lib`

Contains shared base models, cache helpers, the security-cache guards, logging helpers, pagination, permissions, throttles, and reusable catalogue-image validation. It is for cross-application or project-wide infrastructure, not domain-specific business logic.

## Background work

Celery is configured in `config/celery.py` and discovers application tasks.

- User OTP requests store the code in the security cache and queue `send_otp_sms_task`. The task currently logs a placeholder result; an SMS-provider client is not implemented.
- Product-image creation queues `generate_product_image_thumbnail` after the database transaction commits. The task creates a WebP thumbnail from the uploaded image.

## Data, cache, and authentication

PostgreSQL stores durable users, addresses, catalogue records, product images, and Simple JWT outstanding/blacklist records. The identity migration checks for legacy case-fold conflicts before adding its functional unique constraints, so it stops without rewriting data if remediation is required.

Redis has two configured cache aliases with separate URLs:

- `default` uses `CACHE_REDIS_URL` for ordinary catalogue caching. It is configured to ignore cache exceptions, so a cache failure can fall back to the database.
- `security` uses `SECURITY_REDIS_URL` for OTP codes, attempt counters, locks, leases, password-login guard state, and OTP phone/IP throttle histories. It does not suppress exceptions; security-cache errors produce a 503 response instead of bypassing authentication protection.

JWT authentication is the DRF default. The custom refresh serializer validates Simple JWT's password-hash revocation claim while locking the user row, then rotates and blacklists the submitted refresh. Password changes use that same lock, blacklist all outstanding refresh tokens, and invalidate earlier access tokens. See [authentication.md](authentication.md).

## Configuration and logging

`config.settings.base` loads the root `.env` file with `django-environ`. Docker Compose also uses that file for interpolation and injects it into the `web` and `celery` services. Copy either tracked environment-specific example to `.env` to select the Django settings module. Production requires Django and JWT signing keys, PostgreSQL, separate cache URLs, Celery URLs, host/origin policy, and transport-hardening values.

Settings configure system, activity, and security loggers with rotating files beneath `logs/`. Logging helpers record messages plus an authenticated user ID when available. They must not receive passwords, OTP codes, JWTs, credentials, phone numbers, or sensitive internal errors.

## Testing

Pytest uses `config.settings.test`, which substitutes SQLite, separate
local-memory cache namespaces, eager Celery tasks, and in-memory email. The root
`conftest.py` clears every configured cache alias around each test. Coverage is
measured over production code with branch tracking, excludes tests and
migrations, and requires at least 85%.

```bash
venv/bin/python -m pytest
venv/bin/python manage.py check --settings=config.settings.test
venv/bin/python manage.py makemigrations --check --dry-run \
  --settings=config.settings.test
```

PostgreSQL row locking, case-insensitive identity constraints, concurrent
signup, real transaction behavior, Redis security-cache state, normalized
phone/IP throttle keys, and concurrent OTP consumption are covered by tests
explicitly marked `integration`. `config.settings.integration` reads test service endpoints from
the environment; `docker/docker-compose.integration.yml` supplies isolated
local defaults, and the CI integration job supplies PostgreSQL 16 and Redis 7.

```bash
docker compose -f docker/docker-compose.integration.yml up -d --wait
venv/bin/python -m pytest \
  -o addopts="--strict-config --strict-markers" \
  -m integration --ds=config.settings.integration -q
docker compose -f docker/docker-compose.integration.yml down
```

Keep views thin, put mutations in services, reads in selectors, and enforce critical invariants in models and database constraints. Preserve existing route and response contracts unless an explicit compatibility decision says otherwise.
