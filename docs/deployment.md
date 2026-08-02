# Docker Compose deployment

This deployment model is intended for one VPS. Docker Compose runs Django,
Celery, PostgreSQL, and Redis. Nginx is installed and managed directly on the
host; it terminates TLS, serves static/media files, and proxies Django only
through `127.0.0.1:8000`.

No Nginx, certificate, or Certbot container is used or required.

## Compose files

- `docker-compose.yml` is the shared service definition. It has no source-code
  mounts and publishes no service ports.
- `docker-compose.dev.yml` adds local source mounts and PostgreSQL/Redis ports
  for development.
- `docker-compose.prod.yml` binds Django to `127.0.0.1:8000` and mounts the
  host asset directories. PostgreSQL and Redis remain internal to Docker.

Always pass the base file first, followed by the intended override.

## Development

Create a local environment file from the tracked example. It contains only
development credentials and Docker service hostnames.

```bash
cd /path/to/wine-shop
cp .env.development.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Django is available at `http://localhost:8000`; PostgreSQL and Redis are also
published locally using `POSTGRES_HOST_PORT` and `REDIS_HOST_PORT` from `.env`.
Source bind mounts exist only in this development override.

## Production preparation

The production checkout and persistent host data paths below are fixed by this
deployment guide:

```bash
sudo mkdir -p /srv/wine-shop
sudo chown "$USER":"$USER" /srv/wine-shop
git clone <repository-url> /srv/wine-shop
cd /srv/wine-shop

cp .env.production.example .env
chmod 600 .env
# Edit .env and replace every replace-with-* value before continuing.

# UID/GID 10001 is the non-root application user in the image. Nginx needs
# read and traverse access; these modes provide that without granting writes.
sudo install -d -o 10001 -g 10001 -m 0755 \
  /srv/wine-shop/staticfiles /srv/wine-shop/media
```

Keep `.env` private and out of source control. The production sample sets
`DB_HOST=db` and Redis URLs to the internal `redis` service; do not replace
those with publicly reachable database or cache endpoints for this layout.

## Build, migrations, static files, and startup

Review the merged production configuration before each release:

```bash
cd /srv/wine-shop
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml config -q
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml build
```

Start only dependencies, then apply reviewed migrations and collect static
files explicitly. Neither action runs automatically when the web container
starts.

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d db redis
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml run --rm web python manage.py migrate
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The same image runs Django and Celery as UID/GID `10001`, not root. The web
service uses Gunicorn on container port `8000`; production publishes that port
only as `127.0.0.1:8000` for the host proxy. PostgreSQL and Redis have no host
port mappings in the production merge.

Static assets are written to `/srv/wine-shop/staticfiles` by `collectstatic`.
Uploaded media is stored at `/srv/wine-shop/media`. Both directories are bind
mounted into the application; Nginx reads them directly, so do not delete or
replace them during routine deployments.

## Host Nginx

Install and operate Nginx and TLS certificates on the host according to the
host operating system's security update process. The upstream is always
`http://127.0.0.1:8000`; do not expose Docker's Gunicorn port on a public host
interface.

Example site configuration (replace the hostname and certificate paths):

```nginx
server {
    listen 80;
    server_name api.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate     /etc/ssl/certs/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/ssl/private/api.example.com/privkey.pem;
    client_max_body_size 10m;

    location /static/ {
        alias /srv/wine-shop/staticfiles/;
        access_log off;
        expires 7d;
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
        proxy_redirect off;
    }
}
```

The production settings trust `X-Forwarded-Proto` when
`SECURE_PROXY_SSL_HEADER_ENABLED=True`. Only the local, host-managed Nginx
should be able to reach the Gunicorn listener. Restrict media further in Nginx
if uploaded product images must not be public.

After installing the site, validate and reload the host service using the
operating system's Nginx commands, then verify both paths:

```bash
curl --fail https://api.example.com/health/live
curl --fail https://api.example.com/health/ready
curl --fail https://api.example.com/health/startup
curl --fail -I https://api.example.com/static/admin/css/base.css
```

Health endpoints are plain Django views, so DRF authentication and throttling
do not apply. `/health/live` confirms only that the Django process handles an
HTTP request. `/health/ready` verifies PostgreSQL and the fail-closed security
Redis cache; the ordinary cache is intentionally omitted because it falls back
to PostgreSQL. `/health/startup` confirms only that Django's app registry is
initialized: this project has no long-running application startup phase.

The web container healthcheck calls `/health/ready` with the Python standard
library. Its 20-second `start_period`, 30-second interval, 5-second timeout,
and three retries allow Django to initialize without making startup duplicate
readiness. Docker Compose records an unhealthy result but does not
automatically restart a container that remains running and unhealthy; monitor
container health and restart or replace unhealthy containers operationally.

## Release, rollback, and backups

Before every migration, make a tested PostgreSQL backup and copy media to
separate storage. Docker named volumes and files on the same VPS are not a
backup. Never run `docker compose down -v` on production: it removes the
PostgreSQL and Redis volumes.

For example, write a database dump outside the checkout and archive media:

```bash
sudo install -d -m 0700 /srv/wine-shop-backups
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > /srv/wine-shop-backups/wine-shop-$(date +%F).sql
sudo tar -C /srv/wine-shop -czf /srv/wine-shop-backups/media-$(date +%F).tar.gz media
```

Store backup copies off the VPS, test restoration on a non-production system,
and protect backup files as carefully as the database credentials. Redis is
persisted for restart resilience but is not a replacement for a database or
media backup.

For a code-only rollback, deploy the previously tested Git revision or image,
run `collectstatic --noinput` from that revision, and recreate the application
containers with the same production Compose command. Do not automatically
reverse database migrations: verify reversibility, data loss, and compatibility
with the older application version first. If a release includes a destructive
or irreversible migration, restore the tested database backup instead.

Useful operational checks:

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml logs --tail=100 web celery
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml exec web python manage.py check --deploy
```
