# Wine Shop API

A Django REST Framework backend for a wine shop. It currently provides user authentication and profile management plus a public product catalogue with staff-only mutations.

## Implemented features

- Username/password signup and login; phone/OTP signup and login; password reset by OTP.
- JWT access and refresh tokens, refresh rotation and blacklisting, and logout token blacklisting.
- Profile completion and updates, including addresses.
- Public product list and detail endpoints, product search, filtering, ordering, pagination, and Redis-backed anonymous-response caching.
- Staff-only product and image mutations, content-aware JPEG/PNG/WebP validation, category-cycle protection, and data-integrity constraints.

See [authentication details](docs/authentication.md), the [API reference](docs/api.md), and the [security model](docs/security.md).

## Technology stack

- Python 3.12+, Django 6, Django REST Framework, and Simple JWT
- PostgreSQL, Redis, Celery, and Gunicorn
- Pytest, pytest-django, factory_boy, and Faker

Exact package versions are in [requirements.txt](requirements.txt).

## Architecture

Requests are coordinated by views, validated and represented by serializers, then delegated to services for mutations or selectors for reusable reads. Models and database constraints enforce persisted invariants; Celery handles OTP-task and image-thumbnail background work. `apps.lib` contains shared infrastructure such as cache, security-cache, logging, pagination, permissions, throttles, and image validation.

For the complete design, see [architecture.md](docs/architecture.md).

## Development setup

Docker Compose is the supported default development workflow. Copy the complete
development template to the local, ignored `.env.development`, validate the
merged Compose configuration, and start the stack:

```bash
cp .env.development.example .env.development

docker compose \
  --env-file .env.development \
  -f docker-compose.yml \
  -f docker-compose.dev.yml \
  config -q

docker compose \
  --env-file .env.development \
  -f docker-compose.yml \
  -f docker-compose.dev.yml \
  up --build
```

Inside Docker, Django and Celery reach PostgreSQL as `db` and Redis as `redis`.
Do not replace those service names with `localhost` in `.env.development` when using
Compose. The development override publishes the configured host ports only on
`127.0.0.1`.

`.env.development` and `.env.production` are always local and ignored.
`.env.development.example` and `.env.production.example` are safe, tracked
templates. Never put real secrets in an example file or commit a populated
runtime environment file.

Direct-host execution is optional. Install the Python dependencies and run
PostgreSQL and Redis on the host (or use the ports published by the development
stack), then override only the container-specific addresses in the current
shell:

```bash
set -a
. .env.development
set +a

export DJANGO_SETTINGS_MODULE=config.settings.development
export DB_HOST=localhost
export CACHE_REDIS_URL=redis://localhost:6379/0
export SECURITY_REDIS_URL=redis://localhost:6379/1
export CELERY_BROKER_URL=redis://localhost:6379/2
export CELERY_RESULT_BACKEND=redis://localhost:6379/3

venv/bin/python manage.py migrate
venv/bin/celery -A config worker --loglevel=INFO
venv/bin/python manage.py runserver
```

Django settings do not load an env file themselves. The shell above makes
`.env.development` process environment for this optional host workflow, then
overrides only container-specific addresses. Adjust `DB_PORT` and the Redis URL
ports too if the published host ports differ from their defaults.

The API prefixes are `/api/v1/users/` and `/api/v1/products/`.

## Tests and checks

```bash
docker compose \
  --env-file .env.development \
  -f docker-compose.yml \
  -f docker-compose.dev.yml \
  run --rm web python manage.py check

docker compose \
  --env-file .env.development \
  -f docker-compose.yml \
  -f docker-compose.dev.yml \
  run --rm --no-deps -e DJANGO_SETTINGS_MODULE=config.settings.test \
  web pytest config/tests/test_health.py
```

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

Planned, not implemented: inventory, cart, orders, payments, shipping, reviews, CI automation, a production health endpoint, object-storage integration, and an SMS-provider integration.

The repository includes a Docker Compose deployment layout for development and
a single VPS; see `docs/deployment.md` for production template preparation,
host-managed Nginx, and operations.

## License

This project is licensed under the MIT License.  
Copyright © 2026 Armin Bahadori.
