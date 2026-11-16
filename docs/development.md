# Development Guide

This guide describes the supported local development workflow for **Luxury Perfume**.

The project consists of:

* a Django REST Framework backend;
* PostgreSQL for durable application data;
* Redis for caching, security-sensitive state, Celery transport, and task results;
* Celery workers for asynchronous jobs;
* Celery Beat for scheduled recovery and maintenance work;
* an independent React/Vite customer storefront.

Docker Compose is the primary and recommended backend development environment. The React storefront runs separately on the host with Node.js.

For testing-specific commands and environments, see [Testing](testing.md).

---

## Requirements

### Recommended workflow

Install:

* Docker Engine or Docker Desktop with Docker Compose v2;
* Git;
* Node.js through `nvm` for frontend development.

The backend container uses Python 3.12 and installs the pinned dependencies from `requirements/requirements.txt`.

The frontend uses the Node version declared in `frontend/.nvmrc`.

### Optional direct-host backend workflow

Running Django directly on the host additionally requires:

* Python 3.12+;
* PostgreSQL;
* Redis;
* a Python virtual environment.

Docker Compose remains the canonical development path unless host execution is specifically needed.

---

## Repository Layout

The main development-facing structure is:

```text
luxury-perfume/
├── apps/                       Django domain applications
│   ├── cart/
│   ├── lib/
│   ├── notifications/
│   ├── orders/
│   ├── payments/
│   ├── products/
│   └── users/
├── config/                     Django, Celery, URL, WSGI, and ASGI configuration
├── docker/
│   ├── env/                    tracked environment templates
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.dev.yml
├── docs/                       project documentation
├── frontend/                   independent React/Vite storefront
├── requirements/               Python dependency sets
├── manage.py
└── .env                        local environment configuration; ignored by Git
```

The backend follows the project's request-layer convention:

```text
HTTP request
    ↓
View
    ↓
Serializer
    ↓
Service for mutations / Selector for reads
    ↓
Model / PostgreSQL
    ↓
Response
```

For the complete architectural model, see [Architecture](architecture.md).

---

# Backend Development

## 1. Clone the Repository

```bash
git clone https://github.com/Pursite/luxury-perfume.git
cd luxury-perfume
```

---

## 2. Create the Development Environment File

Copy the tracked development template to the ignored root `.env` file:

```bash
cp docker/env/.env.development.example .env
```

The development template is designed for Docker Compose and already points Django and Celery to the internal Compose service names:

```dotenv
DB_HOST=db

CACHE_REDIS_URL=redis://redis:6379/0
SECURITY_REDIS_URL=redis://redis:6379/1
CELERY_BROKER_URL=redis://redis:6379/2
CELERY_RESULT_BACKEND=redis://redis:6379/3
```

Do not replace `db` or `redis` with `localhost` when the backend is running inside Docker Compose.

Django automatically reads the root `.env` file.

---

## Environment File Rules

The root `.env` is runtime configuration and must remain local.

Never commit:

* production credentials;
* database passwords;
* JWT signing keys;
* payment-provider secrets;
* SMS-provider credentials;
* API tokens;
* private infrastructure addresses;
* populated production environment files.

The tracked files under `docker/env/` are templates only.

Development values such as the included Django `SECRET_KEY`, JWT signing key, and database password are intentionally development-only and must never be reused in production.

---

## Development Service Topology

The Compose development stack contains:

```text
┌─────────────────────┐
│       Django        │
│       :8000         │
└─────────┬───────────┘
          │
     ┌────┴────┐
     │         │
     ▼         ▼
PostgreSQL    Redis
   :5432       :6379
                │
         ┌──────┴───────┐
         │              │
         ▼              ▼
      Celery       Celery Beat
      Worker        Scheduler
```

Only Django is published to the host by the development Compose override.

PostgreSQL and Redis remain inside the Docker network.

By default Django is available at:

```text
http://127.0.0.1:8000
```

---

## 3. Validate the Compose Configuration

Before starting the stack, validate the merged Compose configuration:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  config -q
```

A successful command produces no configuration error.

This is especially useful after changing `.env`, Docker configuration, or Compose files.

---

## 4. Start the Backend Stack

Build and start all backend development services:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  up --build
```

The stack starts:

```text
db
redis
web
celery
celery-beat
```

The Django source tree is bind-mounted into the application containers during development.

Changes to Python source files are therefore visible inside the running development containers without rebuilding the image for every edit.

---

## Running Compose in the Background

To run the stack detached:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  up --build -d
```

Inspect service status with:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  ps
```

---

## 5. Apply Database Migrations

After the database is available, apply the current migrations:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  exec web python manage.py migrate
```

Migrations are production-sensitive application history.

Do not create or rewrite migrations merely to make local state convenient.

Schema changes should reflect intentional model changes and must be reviewed together with existing migration history and data constraints.

---

## 6. Create a Local Administrator

When Django Admin access is needed:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  exec web python manage.py createsuperuser
```

Use development-only credentials.

Do not reuse production passwords or customer identities locally.

---

## Useful Backend Commands

Open a Django shell:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  exec web python manage.py shell
```

Run a Django system check:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  exec web python manage.py check
```

Inspect migrations:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  exec web python manage.py showmigrations
```

Generate migrations after an intentional model/schema change:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  exec web python manage.py makemigrations
```

Review generated migrations before applying or committing them.

---

# Logs

When the stack is running in detached mode, inspect all service logs with:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  logs -f
```

Inspect an individual service:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  logs -f web
```

For example:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  logs -f celery
```

Application logging must not expose credentials, passwords, OTP values, JWTs, refresh tokens, provider secrets, or sensitive request data.

See [Security](security.md) for the logging and sensitive-data model.

---

# Stopping the Development Stack

Stop and remove the running containers:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  down
```

This does not remove the PostgreSQL or Redis named volumes.

---

## Resetting Local Docker Data

PostgreSQL and Redis use persistent named Docker volumes.

Removing containers does not reset their data.

If the local development database is intentionally disposable and a complete reset is required:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  down -v
```

This deletes local Compose volumes and their data.

Use this only when the local data is intentionally disposable.

Never apply destructive reset commands to production infrastructure.

---

## Changing Development Database Credentials

PostgreSQL initializes its configured database credentials when its data directory is first created.

Changing values such as:

```dotenv
DB_NAME=
DB_USER=
DB_PASSWORD=
```

in an existing `.env` does not automatically rewrite credentials inside an already initialized PostgreSQL volume.

If credentials are changed, either migrate the existing local database intentionally or recreate the disposable local PostgreSQL volume.

Do not assume editing `.env` alone modifies an existing database cluster.

---

# Redis Responsibilities

Development uses one Redis service with separate logical databases:

| Redis database | Purpose                         |
| -------------- | ------------------------------- |
| `/0`           | ordinary application/cache data |
| `/1`           | security-sensitive cache state  |
| `/2`           | Celery broker                   |
| `/3`           | Celery result backend           |

The separation is intentional.

The ordinary application cache may tolerate some failures where explicitly designed to fail open.

Security-sensitive Redis state must not silently degrade in the same way.

Do not merge these URLs casually or treat Redis as the durable source of application truth.

PostgreSQL remains authoritative for persistent application state.

---

# Celery Development

The Compose stack starts both:

```text
celery
celery-beat
```

The worker executes asynchronous work such as OTP delivery orchestration, image thumbnail processing, payment/refund recovery, notification delivery, and other background tasks defined by the current application.

Celery Beat runs the configured periodic recovery and maintenance schedules.

When debugging asynchronous behavior, inspect both services:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  logs -f celery celery-beat
```

Background tasks must not be treated as the authoritative state store.

Durable state and lifecycle invariants remain in PostgreSQL.

---

# Payments and SMS in Development

The tracked development environment intentionally contains:

```dotenv
PAYMENTS_ENABLED=False
SMS_ENABLED=False
```

No production payment gateway or SMS provider is configured by default.

Do not enable either subsystem merely to make UI functionality appear available.

A real provider integration requires its own implementation, configuration, security review, error-handling behavior, idempotency strategy, and tests.

Provider secrets must never be committed.

---

# Frontend Development

The React storefront lives in:

```text
frontend/
```

It is a separate Vite application and does not run as a Django app or as a development Docker service.

Keep the Django backend running while developing the storefront.

---

## 1. Select the Supported Node Version

Enter the frontend directory:

```bash
cd frontend
```

With `nvm` installed:

```bash
nvm install
nvm use
```

The repository's `.nvmrc` is the source of truth for the preferred Node runtime.

Verify the active version:

```bash
node --version
```

Do not fall back to an older workstation Node version when it does not satisfy the frontend engine requirement.

---

## 2. Install Frontend Dependencies

Use the committed lockfile:

```bash
npm ci
```

Prefer `npm ci` over `npm install` for reproducible installation from `package-lock.json`.

Do not regenerate the lockfile unless dependency changes are intentional.

---

## 3. Start Vite

```bash
npm run dev
```

The storefront is available at:

```text
http://localhost:5173
```

During local development, Vite proxies relative:

```text
/api/...
/media/...
```

requests to Django at:

```text
http://localhost:8000
```

Backend origins therefore do not need to be duplicated throughout React components.

---

## Django Origins for Local Vite

The development `.env` should permit both supported local Vite host spellings:

```dotenv
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

These values already exist in the tracked development template.

---

## Frontend Environment Variables

Frontend environment values prefixed with:

```text
VITE_
```

are browser-visible configuration.

They are not secrets.

Never place any of the following in Vite environment variables:

```text
Django SECRET_KEY
JWT signing keys
database credentials
Redis credentials
payment-provider credentials
SMS-provider credentials
private API tokens
infrastructure secrets
```

Anything embedded into a frontend build must be considered public.

---

# Optional Direct-Host Backend Execution

Docker Compose is the recommended development environment.

Direct-host execution is supported when needed for debugging or local tooling.

Create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install backend dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install --requirement requirements/requirements.txt
```

PostgreSQL and Redis must already be running locally.

Because the normal development `.env` targets Docker service names, override the container-specific addresses in the current shell:

```bash
export DB_HOST=localhost

export CACHE_REDIS_URL=redis://localhost:6379/0
export SECURITY_REDIS_URL=redis://localhost:6379/1
export CELERY_BROKER_URL=redis://localhost:6379/2
export CELERY_RESULT_BACKEND=redis://localhost:6379/3
```

Adjust ports when the local PostgreSQL or Redis services use non-default values.

Apply migrations:

```bash
python manage.py migrate
```

Run Django:

```bash
python manage.py runserver
```

Run a Celery worker in another terminal:

```bash
celery -A config worker --loglevel=INFO
```

Run Celery Beat separately when scheduled tasks are required:

```bash
celery -A config beat --loglevel=INFO
```

The root `.env` is still loaded by Django. The exported shell variables above only override the container-specific hostnames for the current shell.

---

# Health Checks

The backend exposes a readiness endpoint used by the container health check:

```text
/health/ready
```

The Compose stack also defines native health checks for PostgreSQL and Redis.

When startup fails, inspect service health before changing application code:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  ps
```

Then inspect the relevant service logs.

---

# Development Safety Rules

Keep development behavior aligned with the production architecture even when working locally.

In particular:

* PostgreSQL is the durable source of truth.
* Redis must not become authoritative persistent storage.
* security-sensitive cache failures must not silently fail open;
* business mutations belong in services rather than views;
* reusable database reads belong in selectors;
* durable invariants belong in models and PostgreSQL constraints;
* asynchronous tasks must be safe under retry or redelivery where applicable;
* tasks depending on committed database state should be queued after commit;
* API contracts should not be changed accidentally while refactoring;
* secrets and sensitive authentication material must never be logged;
* local convenience must not weaken authorization, validation, throttling, or concurrency guarantees.

See [Architecture](architecture.md), [Authentication](authentication.md), and [Security](security.md) before changing these areas.

---

# Where to Go Next

Use the documentation according to the task:

| Need                                     | Document                              |
| ---------------------------------------- | ------------------------------------- |
| Understand system boundaries             | [Architecture](architecture.md)       |
| Work with API endpoints                  | [API Reference](api.md)               |
| Understand login, OTP, JWT, or profiles  | [Authentication](authentication.md)   |
| Run or extend automated checks           | [Testing](testing.md)                 |
| Review security-sensitive behavior       | [Security](security.md)               |
| Deploy production                        | [Deployment](deployment.md)           |
| Resolve recurring setup/runtime problems | [Troubleshooting](troubleshooting.md) |
| Contribute a repository change           | [CONTRIBUTING.md](../CONTRIBUTING.md) |

---

## Documentation Maintenance

Update this document whenever the supported development workflow changes, including changes to:

* required runtime versions;
* development environment variables;
* Docker or Compose topology;
* local service dependencies;
* backend startup procedures;
* frontend startup procedures;
* Celery development requirements;
* local ports or proxy behavior.

Testing procedures belong in `testing.md`.

Production-specific procedures belong in `deployment.md`.

API behavior belongs in `api.md`.

Avoid duplicating those documents here.
