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
├── docs/
├── .env.development.example
├── .env.production.example
├── manage.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
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
- **Models** define durable state and model-level invariants. PostgreSQL constraints add final protection for active-user identities, product discount prices, and primary product images.

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

PostgreSQL stores durable users, addresses, catalogue records, product images, and Simple JWT blacklist records.

Redis has two configured cache aliases with separate URLs:

- `default` uses `CACHE_REDIS_URL` for ordinary catalogue caching. It is configured to ignore cache exceptions, so a cache failure can fall back to the database.
- `security` uses `SECURITY_REDIS_URL` for OTP codes, attempt counters, locks, leases, and password-login guard state. It does not suppress exceptions; security-cache errors produce a 503 response instead of bypassing authentication protection.

JWT authentication is the DRF default. Simple JWT uses Bearer access tokens, refresh-token rotation, and blacklist-after-rotation. See [authentication.md](authentication.md).

## Configuration and logging

`config.settings.base` reads process environment variables with `django-environ`; it does not select or load a runtime env file. Docker Compose selects `.env.development` with the development override and `.env.production` with the production override, then injects the selected values into Django and Celery. The two environment-specific examples are tracked templates. Production requires Django and JWT signing keys, PostgreSQL, separate cache URLs, Celery URLs, host/origin policy, SMTP, and transport-hardening values.

Settings configure system, activity, and security loggers with rotating files beneath `logs/`. Logging helpers record messages plus an authenticated user ID when available. They must not receive passwords, OTP codes, JWTs, credentials, or sensitive internal errors. The current services do include phone numbers in some log messages, so treat those files as sensitive operational data.

## Testing

Pytest uses `config.settings.test`, which substitutes SQLite, separate local-memory cache namespaces, eager Celery tasks, and in-memory email. The repository tests authentication, profile flows, permissions, OTP and login hardening, product reads/writes, category integrity, uploads, and cache behavior.

```bash
venv/bin/python -m pytest
venv/bin/python manage.py check
venv/bin/python manage.py makemigrations --check --dry-run
```

Keep views thin, put mutations in services, reads in selectors, and enforce critical invariants in models and database constraints. Preserve existing route and response contracts unless an explicit compatibility decision says otherwise.
