````markdown
# Deployment

## Overview

This document describes the deployment requirements and recommended production setup for the Wine Shop API.

The application currently depends on:

- Python
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery
- Gunicorn

A production deployment should run the following components separately:

```text
Reverse proxy
    ↓
Gunicorn
    ↓
Django application
    ↓
PostgreSQL

Django application
    ↓
Redis

Celery worker
    ↓
Redis broker
    ↓
PostgreSQL and external services
````

The repository does not currently define a complete container or orchestration setup.

This document therefore describes the required services and deployment sequence rather than assuming Docker, Kubernetes, or a specific hosting provider.

---

## Production Components

A complete production environment requires:

1. Django web application
2. PostgreSQL database
3. Redis server
4. Celery worker
5. reverse proxy such as Nginx
6. persistent media storage
7. static-file serving
8. process supervision
9. HTTPS termination

Optional future components may include:

* Celery Beat
* object storage
* monitoring
* centralized logging
* error tracking
* CDN

---

## System Requirements

Recommended minimum software:

```text
Python 3.12 or newer
PostgreSQL
Redis
Git
A virtual environment tool
A reverse proxy
```

Install system-level build dependencies required by Python packages and PostgreSQL.

On Debian or Ubuntu, a typical development or deployment host may require packages similar to:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-dev build-essential libpq-dev postgresql redis-server nginx
```

Exact package names may differ by operating system.

---

## Application Checkout

Clone the repository:

```bash
git clone <repository-url>
cd wine-shop
```

For production deployments, deploy a tested commit or release tag rather than an unreviewed working branch.

Example:

```bash
git switch main
git pull --ff-only
```

Before deployment, confirm the repository has no unexpected local changes:

```bash
git status
```

---

## Python Virtual Environment

Create a virtual environment:

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

Upgrade packaging tools:

```bash
python -m pip install --upgrade pip setuptools wheel
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

The project includes Gunicorn as the production WSGI server and `psycopg` as the PostgreSQL driver.

Do not install project packages globally into the system Python environment.

---

## Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Replace every placeholder value before starting the application.

The real `.env` file must not be committed to Git.

Recommended permissions:

```bash
chmod 600 .env
```

The application loads `.env` from the project root through `django-environ`.

---

## Required Environment Variables

At minimum, configure:

```env
SECRET_KEY=<long-random-secret>
DEBUG=False
ALLOWED_HOSTS=api.example.com

DB_NAME=wine_shop
DB_USER=wine_shop
DB_PASSWORD=<strong-database-password>
DB_HOST=127.0.0.1
DB_PORT=5432

REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2
```

The logical Redis database numbers above separate:

* Django cache
* Celery broker
* Celery result backend

They may still use the same Redis server.

---

## Security Environment Variables

Configure production security values explicitly:

```env
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=20
JWT_REFRESH_TOKEN_LIFETIME_DAYS=30

OTP_EXPIRY_SECONDS=120
OTP_VERIFICATION_MAX_ATTEMPTS=5
OTP_VERIFICATION_LOCK_SECONDS=300

PASSWORD_LOGIN_MAX_ATTEMPTS=5
PASSWORD_LOGIN_LOCK_SECONDS=300

AUTH_ANON_THROTTLE_RATE=100/day
AUTH_USER_THROTTLE_RATE=1000/day
OTP_REQUEST_THROTTLE_RATE=1/m
OTP_VERIFY_THROTTLE_RATE=10/m
SIGNUP_THROTTLE_RATE=5/hour
PASSWORD_LOGIN_THROTTLE_RATE=10/m
```

These values should be reviewed according to expected traffic and abuse patterns.

Do not weaken authentication limits merely to handle normal application traffic. Prefer capacity planning and endpoint-specific tuning.

---

## CORS and CSRF Configuration

Configure the allowed frontend origins:

```env
CORS_ALLOWED_ORIGINS=https://shop.example.com
```

If multiple origins are required, provide them using the format expected by `django-environ` list parsing.

Configure trusted CSRF origins where required:

```env
CSRF_TRUSTED_ORIGINS=https://shop.example.com
```

Do not use wildcard production origins unless there is a documented requirement and the security impact is understood.

---

## HTTPS and Cookie Security

Recommended production values:

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=False
```

Only enable HSTS preload after confirming:

* HTTPS works correctly on all required subdomains
* HTTP is no longer needed
* the domain is ready for long-term HTTPS enforcement

The application already supports proxy-aware HTTPS detection through:

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

The reverse proxy must set the forwarded protocol header correctly.

---

## Secret Key

Generate a long random Django secret key.

Example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Store it only in the deployment environment.

Do not:

* commit it
* place it in documentation
* expose it in logs
* reuse the development key in production

The same key is also used by the current JWT signing configuration, so changing it invalidates existing JWTs.

---

## PostgreSQL Setup

Create a production database and user.

Example:

```sql
CREATE DATABASE wine_shop;
CREATE USER wine_shop WITH PASSWORD '<strong-password>';
GRANT ALL PRIVILEGES ON DATABASE wine_shop TO wine_shop;
```

Database permissions should be limited to what the application requires.

Do not run the application as the PostgreSQL superuser.

Verify connectivity before migration:

```bash
venv/bin/python manage.py check
```

---

## Database Migrations

Before applying migrations, create a database backup.

Review migration status:

```bash
venv/bin/python manage.py showmigrations
```

Check for uncommitted model changes:

```bash
venv/bin/python manage.py makemigrations --check --dry-run
```

Apply migrations:

```bash
venv/bin/python manage.py migrate
```

Verify the result:

```bash
venv/bin/python manage.py showmigrations
```

Production deployments should not automatically generate migrations.

Migration files must be created, reviewed, tested, and committed before deployment.

---

## Redis Setup

Redis is required for:

* ordinary application cache
* authentication security cache
* OTP storage
* login failure counters
* temporary authentication locks
* Celery broker
* Celery result backend

Verify Redis:

```bash
redis-cli ping
```

Expected response:

```text
PONG
```

The security cache is fail-closed.

If Redis is unavailable, authentication-sensitive operations may return:

```text
503 Service Unavailable
```

This behavior is intentional.

Redis should therefore be treated as a required production dependency, not an optional performance optimization.

---

## Redis Security

Production Redis should not be exposed publicly.

Recommended controls:

* bind Redis to a private interface
* block public access with a firewall
* use authentication or ACLs
* use TLS when crossing untrusted networks
* restrict access to application hosts
* configure persistence according to operational requirements
* monitor memory usage and eviction

Security-cache keys must not be unexpectedly evicted under normal load.

Use an appropriate memory policy and capacity plan.

---

## Static Files

Collect static files during deployment:

```bash
venv/bin/python manage.py collectstatic --noinput
```

The current static root is:

```text
staticfiles/
```

A reverse proxy or static hosting service should serve the collected files.

Django should not serve static files directly in production.

---

## Media Files

Uploaded product images are stored under the configured media root.

The current local path is:

```text
media/
```

Production media storage must be persistent.

Do not rely on ephemeral application container storage.

Possible production approaches include:

* persistent server volume
* shared network filesystem
* object storage
* cloud media storage

If multiple application instances run concurrently, all instances must access the same media storage.

---

## Gunicorn

The project uses WSGI and includes Gunicorn.

A basic startup command is:

```bash
venv/bin/gunicorn config.wsgi:application
```

A more practical command may be:

```bash
venv/bin/gunicorn \
  --bind 127.0.0.1:8000 \
  --workers 3 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile - \
  config.wsgi:application
```

The correct worker count depends on:

* available CPU
* memory
* request characteristics
* database capacity
* expected concurrency

Do not choose a large worker count without measuring memory and database usage.

---

## Systemd Service for Gunicorn

Example service:

```ini
[Unit]
Description=Wine Shop Gunicorn
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=wine-shop
Group=www-data
WorkingDirectory=/srv/wine-shop
EnvironmentFile=/srv/wine-shop/.env
ExecStart=/srv/wine-shop/venv/bin/gunicorn \
    --bind 127.0.0.1:8000 \
    --workers 3 \
    --timeout 60 \
    config.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Adjust paths, user names, and service dependencies for the target server.

After creating the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wine-shop-gunicorn
sudo systemctl status wine-shop-gunicorn
```

---

## Celery Worker

Start a Celery worker using the project's Celery application module.

A typical command is:

```bash
venv/bin/celery -A config worker --loglevel=INFO
```

Confirm the actual Celery app import path before production deployment.

The worker must use the same environment variables as the Django application.

The worker is required for OTP message delivery.

Without a running worker:

* tasks may remain queued
* OTP delivery may not occur
* API requests may still appear successful after queuing

---

## Systemd Service for Celery

Example:

```ini
[Unit]
Description=Wine Shop Celery Worker
After=network.target redis-server.service postgresql.service

[Service]
Type=simple
User=wine-shop
Group=www-data
WorkingDirectory=/srv/wine-shop
EnvironmentFile=/srv/wine-shop/.env
ExecStart=/srv/wine-shop/venv/bin/celery \
    -A config worker \
    --loglevel=INFO
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wine-shop-celery
sudo systemctl status wine-shop-celery
```

---

## Reverse Proxy

A reverse proxy should:

* terminate HTTPS
* forward requests to Gunicorn
* serve static files
* serve or proxy media files
* set forwarded protocol headers
* enforce upload size limits
* apply suitable timeouts

Example Nginx configuration:

```nginx
server {
    listen 80;
    server_name api.example.com;

    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    client_max_body_size 6M;

    location /static/ {
        alias /srv/wine-shop/staticfiles/;
    }

    location /media/ {
        alias /srv/wine-shop/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

The project accepts catalogue images up to 5 MB, so the reverse proxy upload limit must be higher than that validation limit.

---

## Logging

The current settings write rotating log files under:

```text
logs/
```

Current categories include:

* system logs
* activity logs
* security logs

The deployment user must have permission to create and write this directory.

Example:

```bash
sudo mkdir -p /srv/wine-shop/logs
sudo chown -R wine-shop:www-data /srv/wine-shop/logs
```

For multi-instance or container deployments, centralized logging is preferable to instance-local files.

Never log:

* passwords
* OTP codes
* JWTs
* secret keys
* database credentials

---

## Pre-Deployment Verification

Run the complete test suite:

```bash
venv/bin/python -m pytest
```

Run Django checks:

```bash
venv/bin/python manage.py check
```

Run production deployment checks:

```bash
venv/bin/python manage.py check --deploy
```

Check migration consistency:

```bash
venv/bin/python manage.py makemigrations --check --dry-run
```

Collect static files:

```bash
venv/bin/python manage.py collectstatic --noinput
```

Do not deploy when tests or deployment checks fail without understanding and documenting the reason.

---

## Recommended Deployment Sequence

A safe deployment sequence is:

```text
1. Select a tested commit
2. Back up PostgreSQL
3. Pull the new code
4. Activate the virtual environment
5. Install dependencies
6. Validate environment variables
7. Run tests or smoke tests
8. Run Django checks
9. Apply migrations
10. Collect static files
11. Restart Gunicorn
12. Restart Celery
13. Verify health and logs
```

Example commands:

```bash
git pull --ff-only
venv/bin/python -m pip install -r requirements.txt
venv/bin/python manage.py check
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart wine-shop-gunicorn
sudo systemctl restart wine-shop-celery
```

---

## Post-Deployment Verification

Verify:

```text
Django application starts
PostgreSQL connection succeeds
Redis connection succeeds
Celery worker is online
Static files load
Media files load
Public product endpoints respond
Protected endpoints reject anonymous requests
Username/password login works
OTP task reaches the worker
JWT refresh works
Logout blacklists refresh tokens
```

Inspect services:

```bash
sudo systemctl status wine-shop-gunicorn
sudo systemctl status wine-shop-celery
sudo systemctl status postgresql
sudo systemctl status redis-server
```

Inspect recent logs:

```bash
sudo journalctl -u wine-shop-gunicorn -n 100
sudo journalctl -u wine-shop-celery -n 100
```

---

## Rollback

A rollback plan should exist before deployment.

Code rollback:

```bash
git switch --detach <previous-tested-commit>
```

or redeploy the previous release artifact.

Database rollback must be handled cautiously.

Before reversing a migration:

1. inspect whether it is reversible
2. determine whether data loss is possible
3. restore from backup when reversal is unsafe
4. test the rollback outside production first

Do not blindly run:

```bash
python manage.py migrate <app> <older-migration>
```

on production data.

---

## Database Backups

PostgreSQL backups should run automatically.

Example manual backup:

```bash
pg_dump \
  --format=custom \
  --file=wine_shop_backup.dump \
  --dbname=wine_shop
```

Example restore:

```bash
pg_restore \
  --clean \
  --if-exists \
  --dbname=wine_shop \
  wine_shop_backup.dump
```

Backup credentials and destination paths must be protected.

Periodically test restore procedures. A backup that has never been restored is not fully verified.

---

## Health Monitoring

At minimum, monitor:

* HTTP availability
* response latency
* application error rate
* PostgreSQL availability
* Redis availability
* Celery queue depth
* Celery worker health
* disk usage
* memory usage
* database connection usage
* failed OTP delivery tasks

A dedicated health endpoint is not currently documented.

Do not expose internal dependency details through an unauthenticated health response.

---

## Scaling Considerations

When running multiple Django instances:

* all instances must use the same PostgreSQL database
* all instances must use the same Redis security cache
* all instances must access shared media storage
* JWT signing configuration must be identical
* environment security values must be consistent
* migrations must run only once per release

Celery workers may be scaled independently from Gunicorn workers.

---

## Production Checklist

Before first production launch:

```text
[ ] DEBUG=False
[ ] Strong SECRET_KEY configured
[ ] Correct ALLOWED_HOSTS configured
[ ] PostgreSQL uses a dedicated non-superuser account
[ ] Redis is not publicly exposed
[ ] HTTPS is enabled
[ ] Secure cookies are enabled
[ ] CORS origins are restricted
[ ] CSRF trusted origins are configured
[ ] Migrations are applied
[ ] Static files are collected
[ ] Media storage is persistent
[ ] Gunicorn is supervised
[ ] Celery worker is supervised
[ ] Database backups are automated
[ ] Logs are writable and monitored
[ ] Tests pass
[ ] `manage.py check --deploy` is reviewed
[ ] Authentication and OTP smoke tests pass
```

---

## Current Limitations

The current repository does not yet provide:

* Dockerfile
* Docker Compose configuration
* Kubernetes manifests
* CI/CD deployment workflow
* managed object-storage configuration
* dedicated application health endpoint
* automated backup scripts

These may be introduced later as separate, reviewed deployment features.