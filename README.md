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

## Local setup

Requirements: Python 3.12+, PostgreSQL, Redis, and Git. A Celery worker is needed for queued OTP tasks; the current OTP task is a provider placeholder and does not deliver an SMS until a provider integration is implemented.

```bash
git clone https://github.com/Pursite/wine-shop.git
cd wine-shop
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.development.example .env
```

`.env.development.example` is the tracked direct-host development template. For deployment, copy `.env.production.example` to `.env` on the production host and replace every placeholder. `.env.example` points to both environment-specific templates. Do not commit any `.env` file.

Create a PostgreSQL database and role matching `DB_NAME`, `DB_USER`, and `DB_PASSWORD`, then apply migrations:

```bash
venv/bin/python manage.py migrate
```

Start Redis directly on the host using your operating system's service manager, then verify it:

```bash
redis-cli ping
```

Start the Celery worker in another terminal:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
venv/bin/celery -A config worker --loglevel=INFO
```

Start Django:

```bash
venv/bin/python manage.py runserver
```

`manage.py` defaults to `config.settings.development`; it uses PostgreSQL on
`localhost:5432` and Redis databases 0 through 3 on `localhost:6379`.

The API prefixes are `/api/v1/users/` and `/api/v1/products/`.

## Tests and checks

```bash
venv/bin/python -m pytest
venv/bin/python manage.py check
venv/bin/python manage.py makemigrations --check --dry-run
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

The repository contains a `Dockerfile` and `docker-compose.yml`, but it does not contain a complete, verified production deployment automation workflow.

## License

This project is licensed under the MIT License.  
Copyright © 2026 Armin Bahadori.