# Wine Shop API

A Django REST Framework backend for a wine shop. It currently provides user authentication and profile management plus a public product catalogue with staff-only mutations.

## Implemented features

- Username/password signup and login; phone/OTP signup and login; password reset by OTP.
- JWT access and refresh tokens, an explicit refresh endpoint with rotation and blacklisting, password-change session revocation, and owner-bound logout.
- Profile completion and updates, including addresses.
- Public product list and detail endpoints, product search, filtering, ordering, pagination, and Redis-backed anonymous-response caching.
- Staff-only product and image mutations, content-aware JPEG/PNG/WebP validation, category-cycle protection, and data-integrity constraints.

See [authentication details](docs/authentication.md), the [API reference](docs/api.md), and the [security model](docs/security.md).

## Technology stack

- Python 3.12+, Django 6, Django REST Framework, and Simple JWT
- PostgreSQL, Redis, Celery, and Gunicorn
- Pytest, pytest-django, factory_boy, and Faker

Runtime package versions are in
[requirements/requirements.txt](requirements/requirements.txt); test-only
tooling is layered on top through
[requirements/requirements-test.txt](requirements/requirements-test.txt).

## Architecture

Requests are coordinated by views, validated and represented by serializers, then delegated to services for mutations or selectors for reusable reads. Models and database constraints enforce persisted invariants; Celery handles OTP-task and image-thumbnail background work. `apps.lib` contains shared infrastructure such as cache, security-cache, logging, pagination, permissions, throttles, and image validation.

For the complete design, see [architecture.md](docs/architecture.md).

## Production logging

Application logs are JSON records written to container output: activity events
go to stdout, while security and system errors go to stderr. Every HTTP
response includes a server-generated `X-Request-ID`; the same value is present
as `request_id` and `correlation_id` in logs produced while that request is
handled. Queued OTP task activity records include `task_id`, and the worker
uses that task ID as its correlation ID.

The production Compose override uses Docker's `local` driver with a 10 MiB
maximum file size and three files per service. Use `docker compose logs` to
inspect them; do not read Docker's internal log files. Log events deliberately
exclude request bodies, query strings, client IPs, phone numbers, OTPs,
passwords, JWTs, credentials, and exception messages.

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

The API prefixes are `/api/v1/users/` and `/api/v1/products/`.

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
covers case-insensitive identity constraints and concurrent signup, Redis
OTP-consumption races, and security-throttle keys. Never point integration
tests at production databases or Redis databases.

## CI and production images

The existing SQLite/LocMem and PostgreSQL/Redis jobs run for every pull
request and push. After both succeed, the required `Application image` check
copies the safe production template to the ignored root `.env`, validates the
production Compose merge, and builds the final application image without
registry access. Pull requests and pushes stop there. On successful pushes to
`main`, the separate `Publish application image` job verifies that the SHA tag
does not already exist, then promotes the archived build artifact—without a
second Docker build—to exactly `ghcr.io/pursite/wine-shop:<commit SHA>` with
OCI source and revision labels.

Production deploys the same image for Django and Celery, pinned to its resolved
content digest. The image contains application code and dependencies only;
the VPS keeps the production `.env`, PostgreSQL data, Redis data, static files,
and media at runtime. See [deployment.md](docs/deployment.md) for the required
protected GHCR pull token, first deployment, normal deployment, and the
limitations of code-only rollback.

## Documentation

| Document | Contents |
| --- | --- |
| [architecture.md](docs/architecture.md) | Layers, infrastructure, configuration, and testing |
| [authentication.md](docs/authentication.md) | Identity rules, OTP flows, JWTs, and profile behavior |
| [api.md](docs/api.md) | Verified endpoint contract |
| [security.md](docs/security.md) | Implemented controls and limitations |
| [deployment.md](docs/deployment.md) | Deployment guidance and template caveats |
| [AGENTS.md](AGENTS.md) | Durable repository-change expectations |

Update the relevant document whenever routes, configuration, authentication behavior, architecture, or deployment requirements change.

## Project status and roadmap

The users, authentication, profiles, products, categories, brands, and product-image domains are implemented. The project remains under active development.

Planned, not implemented: inventory, cart, orders, payments, shipping, reviews,
object-storage integration, and an SMS-provider integration.

The repository includes a Docker Compose deployment layout for development and
a single VPS, plus a manual GitHub Actions production deployment workflow; see
`docs/deployment.md` for production template preparation, environment secrets,
host-managed Nginx, and operations.

## License

This project is licensed under the MIT License.  
Copyright © 2026 Armin Bahadori.
