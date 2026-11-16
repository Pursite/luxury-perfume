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

## Requirements

### Recommended workflow

Install:

* Docker Engine or Docker Desktop with Docker Compose v2;
* Git;
* Node.js through `nvm` for frontend development.

The runtime versions are defined by the build and package files:

| Component | Repository runtime |
| --- | --- |
| Python | 3.12 in `docker/Dockerfile` |
| Django / DRF | 6.0.6 / 3.17.1 in `requirements/requirements.txt` |
| PostgreSQL | `postgres:16-alpine` |
| Redis | `redis:7-alpine` |
| Node.js | 24.19.0 in `frontend/.nvmrc`; engines require `>=24.15.0 <25` |

The backend image installs pinned dependencies from `requirements/requirements.txt`.

The frontend uses the Node version declared in `frontend/.nvmrc`.

### Optional direct-host backend workflow

Running Django directly on the host additionally requires:

* Python 3.12+;
* PostgreSQL;
* Redis;
* a Python virtual environment.

Docker Compose remains the canonical development path unless host execution is specifically needed.

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

## Backend Development

### 1. Clone the Repository

```bash
git clone https://github.com/Pursite/luxury-perfume.git
cd luxury-perfume
```

### 2. Create the Development Environment File

Run backend commands from the repository root. Create the ignored root `.env` only if it does not already exist; preserve existing local settings:

```bash
if [ ! -e .env ]; then
  cp docker/env/.env.development.example .env
fi
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

Django automatically reads the root `.env` file. Compose uses `--env-file .env` for interpolation and the service `env_file` entries to supply application-container settings.

### Environment File Rules

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

### Development Service Topology

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

| Service | Role |
| --- | --- |
| `web` | Django development server and HTTP API |
| `db` | PostgreSQL application data |
| `redis` | Cache, security state, Celery broker and results |
| `celery` | Background task worker |
| `celery-beat` | Periodic task scheduler |

Only Django is published to the host by the development Compose override, bound to `127.0.0.1:${DJANGO_HOST_PORT:-8000}`.

PostgreSQL and Redis remain inside the Docker network.

By default Django is available at:

```text
http://127.0.0.1:8000
```

### 3. Validate the Compose Configuration

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

### 4. Start the Backend Stack

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

Changes to Python source files are therefore visible inside the running development containers without rebuilding the image for every edit. Django runserver reloads Python changes; restart `celery` and `celery-beat` after changing task code. Rebuild the application services after dependency or image changes.

### Running Compose in the Background

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

### 5. Apply Database Migrations

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

### 6. Create a Local Administrator

When Django Admin access is needed:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  exec web python manage.py createsuperuser
```

#### Host commands versus container commands

The `exec web` commands above run Python **inside** the running Django container.
Docker's internal DNS resolves `db` and `redis` there. A host virtual environment
runs outside that network: activating it does not join Docker's DNS or network.
Inside a container, `localhost` means that container itself.

If you run `python manage.py createsuperuser` on the host with `DB_HOST=db`,
PostgreSQL may report `failed to resolve host 'db'`. Use the Compose
`exec web python manage.py createsuperuser` command above for this stack.
The same rule applies to migrations, shells, and other database-backed commands.

Changing only `DB_HOST` to `localhost` does not expose the private PostgreSQL
container. Neither PostgreSQL nor Redis publishes a host port in this development
stack. Direct-host Django requires independently reachable services and matching
host/port/credential settings; see [Optional Direct-Host Backend Execution](#optional-direct-host-backend-execution).

Use development-only credentials.

Do not reuse production passwords or customer identities locally.

### Useful Backend Commands

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

## Logs

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

## Stopping the Development Stack

Stop and remove the running containers:

```bash
docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  down
```

This does not remove the PostgreSQL or Redis named volumes.

### Resetting Local Docker Data

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

### Changing Development Database Credentials

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

## Redis Responsibilities

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

## Celery Development

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

## Payments and SMS in Development

The tracked development environment intentionally contains:

```dotenv
PAYMENTS_ENABLED=False
SMS_ENABLED=False
```

No production payment gateway or SMS provider is configured by default.

Do not enable either subsystem merely to make UI functionality appear available.

A real provider integration requires its own implementation, configuration, security review, error-handling behavior, idempotency strategy, and tests.

Provider secrets must never be committed.

## Frontend Development

The React storefront lives in:

```text
frontend/
```

It is a separate Vite application and does not run as a Django app or as a development Docker service.

Keep the Django backend running while developing the storefront.

### 1. Select the Supported Node Version

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

### 2. Install Frontend Dependencies

Use the committed lockfile:

```bash
npm ci
```

Prefer `npm ci` over `npm install` for reproducible installation from `package-lock.json`.

Do not regenerate the lockfile unless dependency changes are intentional.

### 3. Start Vite

```bash
npm run dev
```

Vite binds to `127.0.0.1` and requests port 5173. Open the URL printed by Vite (normally `http://127.0.0.1:5173`); it may choose another port if 5173 is occupied.

During local development, Vite proxies relative:

```text
/api/...
/media/...
```

requests to Django at:

```text
http://localhost:8000
```

Backend origins therefore do not need to be duplicated throughout React components. The proxy target is fixed in `frontend/vite.config.js`; changing `DJANGO_HOST_PORT` also requires aligning that target. If Vite chooses another port, align the backend origin allowlists before using cookie-backed authentication.

See the [frontend guide](../frontend/README.md) for routes, password management, browser session state, checks, and production build configuration.

### Django Origins for Local Vite

The development `.env` should permit both supported local Vite host spellings:

```dotenv
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

These values already exist in the tracked development template.

### Frontend Environment Variables

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

## Optional Direct-Host Backend Execution

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

PostgreSQL and Redis must already be independently reachable from the host
(for example, host-installed PostgreSQL 16 and Redis 7). The Compose services
above are private and cannot be reached through host loopback ports. Install
the PostgreSQL client library (`libpq`; for example, `libpq5` on Debian/Ubuntu),
and build dependencies if required by psycopg or Pillow on your platform.
Use database credentials for those separate services, not assumed credentials
from the Compose volume.

Because the normal development `.env` targets Docker service names, override the container-specific addresses in the current shell:

```bash
export DB_HOST=localhost
export DB_PORT=5432

export CACHE_REDIS_URL=redis://localhost:6379/0
export SECURITY_REDIS_URL=redis://localhost:6379/1
export CELERY_BROKER_URL=redis://localhost:6379/2
export CELERY_RESULT_BACKEND=redis://localhost:6379/3
```

Set `DB_NAME`, `DB_USER`, and `DB_PASSWORD` to match the reachable database. Adjust `DB_HOST`, `DB_PORT`, and every Redis URL to the actual services; `localhost` is only an example.

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

Repeat the environment overrides in each worker/scheduler terminal; shell exports are not shared between terminals. Run Celery Beat separately when scheduled tasks are required:

```bash
celery -A config beat --loglevel=INFO
```

The root `.env` is still loaded by Django. Exported shell variables take precedence over that file for the current shell. Activate the virtual environment and supply the same overrides in each terminal used for Django or Celery.

## Health Checks

The backend exposes three GET endpoints (without trailing slashes):

| Endpoint | Checks |
| --- | --- |
| `/health/live` | Django can handle an HTTP request |
| `/health/startup` | Django application registry is initialized |
| `/health/ready` | Database query and security-cache write succeed; returns 503 if either fails |

Readiness does not prove migrations are applied, workers are consuming jobs,
or a provider is operational. From the host, with the default Django port:

```bash
curl --fail http://127.0.0.1:8000/health/ready
```

The shared Compose web health check currently sends `Host: shop.exonplus.ir`,
which the development template's `ALLOWED_HOSTS` does not allow. Consequently,
`web` may be marked unhealthy even when the loopback readiness request succeeds.
Inspect the HTTP result and logs before interpreting that status as a dependency
failure; this guide does not change the Compose health-check configuration.

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

## Development Safety Rules

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

## Where to Go Next

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
