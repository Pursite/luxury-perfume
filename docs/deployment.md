# Deployment

> **Important:** The Nginx, systemd, Gunicorn, Celery, and deployment examples are templates. They must be adapted and tested for the target host and are not guaranteed production-ready repository configuration.

## Repository-provided behavior

The application uses PostgreSQL, Redis, Celery, and Gunicorn. `config/settings.py` loads `.env`, writes logs beneath `logs/`, uses `staticfiles/` as `STATIC_ROOT`, and uses `media/` as `MEDIA_ROOT`. Redis is required both for the ordinary cache and the fail-closed authentication security cache; Celery also uses configured Redis broker/result URLs.

The repository includes a `Dockerfile` and `docker-compose.yml`, but they are not a complete production deployment solution. The compose file expects an untracked `.env.docker`, exposes development-oriented host ports/volumes, and must be reviewed before any production use. No CI/CD deployment workflow, Kubernetes configuration, health endpoint, object-storage configuration, or backup automation is present.

The current OTP Celery task is a placeholder and does not call an SMS provider. Running a worker lets it process queued tasks but does not make OTP delivery real.

## Prepare the host

Recommended production practice is to run a dedicated non-root deployment user, PostgreSQL role, Redis service, application virtual environment, Gunicorn process, Celery worker, reverse proxy, persistent media storage, and TLS termination. Keep PostgreSQL and Redis off public networks.

Clone a tested commit and install the pinned dependencies:

```bash
git clone <repository-url> wine-shop
cd wine-shop
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy the environment template and replace every placeholder:

```bash
cp .env.example .env
chmod 600 .env
```

`SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` are required by settings. Set `DEBUG=False`, a correct `ALLOWED_HOSTS` value, and production values for JWT, OTP, login-lock, throttle, CORS, CSRF, and HTTPS-related settings. The values in `.env.example` are examples and defaults, not a production policy.

## Database, Redis, and static files

Back up the database before migrations. Review and apply only committed migrations:

```bash
venv/bin/python manage.py showmigrations
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
```

Use a dedicated PostgreSQL role with only the privileges the application needs. Redis must be private, authenticated or ACL-protected where supported, capacity-managed to avoid security-state eviction, and protected with TLS when traffic crosses an untrusted network.

`media/` stores uploaded product images in the current configuration. It must be persistent and shared by every application instance; object storage is not configured by this repository.

## Process examples

The repository-supported executable entry points are:

```bash
venv/bin/gunicorn --bind 127.0.0.1:8000 config.wsgi:application
venv/bin/celery -A config worker --loglevel=INFO
```

Example systemd unit fragments (adapt paths, users, groups, dependencies, resource limits, and restart policy):

```ini
[Service]
User=wine-shop
WorkingDirectory=/srv/wine-shop
EnvironmentFile=/srv/wine-shop/.env
ExecStart=/srv/wine-shop/venv/bin/gunicorn --bind 127.0.0.1:8000 config.wsgi:application
Restart=on-failure
```

```ini
[Service]
User=wine-shop
WorkingDirectory=/srv/wine-shop
EnvironmentFile=/srv/wine-shop/.env
ExecStart=/srv/wine-shop/venv/bin/celery -A config worker --loglevel=INFO
Restart=on-failure
```

An Nginx template should terminate TLS, forward `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto`, proxy requests to Gunicorn, serve `staticfiles/` and appropriately protected media, and set `client_max_body_size` above the application's 5 MB image limit. The settings trust `X-Forwarded-Proto` through `SECURE_PROXY_SSL_HEADER`, so only a trusted proxy may set it.

## Verification and operations

Before deployment, run checks in an environment with the intended settings and dependencies:

```bash
venv/bin/python -m pytest
venv/bin/python manage.py check
venv/bin/python manage.py check --deploy
venv/bin/python manage.py makemigrations --check --dry-run
```

After deployment, verify a public product request, protected-route rejection without a JWT, staff authorization, PostgreSQL and Redis connectivity, worker availability, static/media serving, JWT refresh and logout behavior, and logs. Treat `check --deploy` findings as review items, not proof that the host configuration is secure.

Maintain tested database backups and a rollback procedure before applying migrations. The repository does not supply automation for either. Do not automatically reverse migrations on production data without verifying reversibility and data impact.
