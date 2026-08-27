# Docker Compose deployment

This deployment model is intended for one VPS. Docker Compose runs Django,
Celery, PostgreSQL, and Redis. Nginx is installed and managed directly on the
host; it terminates TLS, serves the React build plus Django static/media files,
and proxies Django only through `127.0.0.1:8000`.

No Nginx, certificate, or Certbot container is used or required.

## Compose files

- `docker/docker-compose.yml` is the shared runtime service definition. It has
  no source-code mounts, application build configuration, or published service
  ports. Its fixed project name is `luxury-perfume`, so production resources
  use one consistent operational identity.
- `docker/docker-compose.dev.yml` owns the local application build
  configuration, source mounts, the `luxury-perfume` development project name,
  and the loopback Django port for development.
- `docker/docker-compose.prod.yml` requires `APP_IMAGE` for both Django and
  Celery, binds Django to `127.0.0.1:8000`, and mounts host asset directories.
  PostgreSQL and Redis remain internal to Docker with their existing named
  volumes. It also configures Docker's `local` log driver for all four services
  with a 10 MiB maximum file size and three files per service.

Always pass the base file first, followed by the intended override.

## Development

Create a local environment file from the tracked example. It contains only
development credentials and Docker service hostnames.

```bash
cd /path/to/luxury-perfume
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

Django is available at `http://localhost:8000`; PostgreSQL and Redis remain
internal during development and have no host-port mappings. The Django port is
configurable with `DJANGO_HOST_PORT` and fixed to `127.0.0.1`, so it is not
reachable directly from the LAN. Source bind mounts exist only in this
development override.

Run the React storefront directly on the host with Node 24 LTS; it is not a
Compose service:

```bash
cd frontend
nvm install 24
nvm use
npm ci
npm run dev
```

Vite serves `http://localhost:5173` and proxies relative `/api/` and `/media/`
requests to Django at `http://localhost:8000`. The development environment
template allows the `localhost:5173` and `127.0.0.1:5173` browser origins. Keep
a correct private root `.env` intact rather than overwriting its unrelated
values; never commit it.

The development project uses named volumes. Docker does not rename or migrate
volumes from a differently named Compose project. Recreate local volumes only
when their data is known to be disposable; move valuable data with a separately
reviewed database procedure.

Docker containers resolve PostgreSQL as `db` and Redis as `redis`; `localhost`
inside a container refers to that same container. Optional direct-host Django
or Celery processes therefore need temporary shell overrides for `DB_HOST` and
the four Redis URLs, as shown in the README, instead of another tracked env
inventory.

## Production preparation

The production checkout is `/srv/luxury-perfume`, the Compose project is
`luxury-perfume`, its physical volumes are normally
`luxury-perfume_postgres_data` and `luxury-perfume_redis_data`, and static/media
paths live below that checkout. This contract assumes a new deployment with no
pre-rename production data. Docker does not move a differently named checkout,
bind mount, or volume automatically. If such an installation exists, stop and
design a reviewed downtime migration before using this workflow; never attach
old and new PostgreSQL containers to one physical volume concurrently.

Prepare the production checkout and persistent host paths as follows:

```bash
sudo mkdir -p /srv/luxury-perfume
sudo chown "$USER":"$USER" /srv/luxury-perfume
git clone <repository-url> /srv/luxury-perfume
cd /srv/luxury-perfume

cp docker/env/.env.production.example .env
chmod 600 .env
```

Edit `.env` and replace every `replace-with-*` value. Its tracked host/origin
policy already assigns `shop.exonplus.ir` to Django and
`https://www.exonplus.ir` to the storefront. Keep `DB_HOST=db`
and the Redis service hostnames unchanged for this Compose layout. Then validate
the selected production configuration with a non-secret image reference. The
deployment workflow supplies the actual digest-pinned `APP_IMAGE`; do not add
it to `.env`.

Production authentication uses a host-only, Secure, HttpOnly refresh cookie on
`shop.exonplus.ir`; no refresh token is placed in frontend storage. Keep the
explicit storefront CORS and CSRF origin values unchanged, because credentialed
refresh/logout requests require that allowlist. The unrelated
`api.exonplus.ir` host must not be added to it.

```bash
APP_IMAGE=ghcr.io/pursite/luxury-perfume:compose-validation docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.prod.yml \
  config -q
```

On Debian or Ubuntu, install POSIX ACL support and prepare the asset paths as
follows. The application and Celery worker run as UID/GID `10001`; `www-data`
is the usual host Nginx worker user. If the `user` directive in
`/etc/nginx/nginx.conf` names another account, substitute that account in the
three `setfacl` commands.

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends acl

sudo install -d -o 10001 -g 10001 -m 0750 \
  /srv/luxury-perfume/staticfiles /srv/luxury-perfume/media
sudo chown -R 10001:10001 \
  /srv/luxury-perfume/staticfiles /srv/luxury-perfume/media
sudo find /srv/luxury-perfume/staticfiles /srv/luxury-perfume/media \
  -type d -exec chmod 0750 {} +
sudo find /srv/luxury-perfume/staticfiles /srv/luxury-perfume/media \
  -type f -exec chmod 0640 {} +

# Nginx may traverse the parent paths and read existing assets, but cannot
# write application data.
sudo setfacl -m u:www-data:--x /srv /srv/luxury-perfume
sudo setfacl -R -m u:www-data:rX \
  /srv/luxury-perfume/staticfiles /srv/luxury-perfume/media

# New files and directories inherit owner write access and Nginx
# read/traverse access. File creation modes remove execute permission on files.
sudo find /srv/luxury-perfume/staticfiles /srv/luxury-perfume/media -type d \
  -exec setfacl \
  -m d:u::rwx,d:u:www-data:rx,d:g::r-x,d:m::r-x,d:o::--- {} +
```

These commands are safe to repeat when host asset permissions need repair. Do
not use `chmod 777`: Django uploads, `collectstatic`, and Celery thumbnail
tasks write as UID `10001`, while Nginx receives only read/traverse ACLs. After
running `collectstatic`, verify that the Nginx worker can traverse both mounts,
read a static file, and cannot write media:

```bash
sudo -u www-data test -x /srv/luxury-perfume/staticfiles
sudo -u www-data test -x /srv/luxury-perfume/media
sudo -u www-data test -r /srv/luxury-perfume/staticfiles/admin/css/base.css
sudo -u www-data test ! -w /srv/luxury-perfume/media
```

Keep `.env` private and out of source control. The production sample sets
`DB_HOST=db` and Redis URLs to the internal `redis` service; do not replace
those with publicly reachable database or cache endpoints for this layout.

## Repository and package identity

The intended GitHub repository is `Pursite/luxury-perfume`. Repository renaming
requires GitHub administrator access and is not performed by the application
or deployment workflow. If the GitHub-side rename has not been completed, an
administrator must do it and then update development and VPS checkout remotes:

```bash
git remote set-url origin git@github.com:Pursite/luxury-perfume.git
```

The GHCR packages are `ghcr.io/pursite/luxury-perfume` (Django/Celery) and
`ghcr.io/pursite/luxury-perfume-frontend` (the static React carrier image).
Before the first deployment, publish the selected commit and verify that the
protected `GHCR_READ_TOKEN` account can read both packages. The repository does
not migrate images, VPS paths, or Docker volumes from a differently named
installation.

## Manual GitHub Actions deployment

`.github/workflows/cd.yml` is deliberately manual-only. The complete release
gate requires the frontend install/lint/tests/build, the backend unit and
integration checks, production Compose validation, and both read-only image
builds. The backend jobs are named `Application image` and `Publish application image`; the frontend publication job is `Publish frontend image`. For a push to
`main`, the backend and frontend publication jobs both depend on that gate,
reject an existing SHA tag, and promote the archived artifacts without
rebuilding them to their matching GHCR packages. The
frontend image is a `FROM scratch` carrier containing only the stamped static
release; it is never run as a service. Run **Deploy production** from that
reviewed `main` commit for a normal release. Its empty **Commit SHA** input
defaults to that workflow run's `github.sha`.

To deploy or roll back application code to an earlier published release, enter
its full, lowercase 40-character commit SHA. The workflow rejects all other
values and fails safely if the corresponding GHCR image was never published.
It checks out that exact source revision on the VPS and deploys the matching
image by its resolved content digest, not by the mutable tag alone.

The job uses GitHub's `production` environment and serializes deployments, so
configure that environment with required reviewers and branch restrictions
before its first use. Add these environment secrets to `production`; do not
add them as repository secrets:

- `VPS_HOST`: the VPS hostname or address.
- `VPS_PORT`: the SSH port; leave it unset to use `22`.
- `VPS_USER`: the restricted VPS account that owns `/srv/luxury-perfume` and is
  allowed to use Docker Compose for this project.
- `VPS_SSH_PRIVATE_KEY`: the Actions-to-VPS private key. It needs only the
  restricted account's SSH access.
- `VPS_KNOWN_HOSTS`: the exact, pre-verified SSH host-key entry for the VPS.
  Obtain and verify the server fingerprint through a trusted channel before
  saving it; the workflow never uses `ssh-keyscan` or disables host checking.
- `GHCR_READ_TOKEN`: a classic GitHub personal access token with only
  `read:packages`, owned by an account that can read
  `ghcr.io/pursite/luxury-perfume`. This is not an application setting and must not
  be written to the VPS `.env`.

The existing VPS checkout's `origin` must already be readable by `VPS_USER`,
for example with a read-only deploy key stored on the VPS. The workflow does
not copy source, write `.env`, or install host software. It refuses to run if
the checkout has tracked or untracked source changes; ignored state such as
the private `.env`, static files, media, and Compose volumes is left
untouched.

For every deployment, the GitHub runner sends that token only through the SSH
standard-input stream. The VPS creates a temporary `DOCKER_CONFIG`, authenticates
with `docker login --password-stdin`, pulls the SHA-tagged image, resolves its
digest, then removes the temporary credentials with a trap before Compose is
called. Do not run `docker login` manually or persist GHCR credentials on the
VPS.

For the first deployment, complete the production preparation, create the
protected `GHCR_READ_TOKEN`, push the reviewed release to `main`, wait for the
complete release gate and both image publication jobs, then dispatch **Deploy
production** from that commit. Normal deployments follow the same process; no
application or frontend image is built on the VPS and Node/npm is not required
there.

Within `/srv/luxury-perfume`, the workflow acquires the non-blocking
`/srv/luxury-perfume/.git/deploy.lock` for the entire operation, rejects a dirty
checkout, fetches sufficient history for `origin/main` and the selected SHA,
and verifies that the SHA is an ancestor of `origin/main`. It pulls both
matching images, resolves and validates their immutable digests and OCI
revision labels, checks out the exact source commit, and prepares the frontend
release in `frontend-releases/<commit-sha>/` through a stopped scratch carrier
container. The artifact is structurally and origin validated before activation.
The existing `db` and `redis` services are started without recreating them;
after they are healthy, `check --deploy`, forward migrations, and `collectstatic`
run. Only then is `web` recreated and its readiness endpoint checked. Celery is
recreated separately and must remain running, with no restart, for five samples
over eight seconds. Finally `frontend-current` is switched with one atomic
symlink rename. It never runs `docker compose down`, removes volumes, prunes
Docker resources, uses `git clean`, or modifies Nginx, VPN services, database
data, media, static files, or the server's `.env`. A failure before the symlink
switch leaves the previous frontend release active; a backend failure leaves
the previous containers and frontend symlink active unless migrations or a
container recreation had already changed runtime state, which is why rollback
is an explicit deployment of a compatible prior SHA.

## Published images, migrations, static files, and startup

Production never builds application images with Compose. CD exports a
digest-pinned `APP_IMAGE` only for its deployment process, then uses
`--no-build` for every Compose `up`. Neither migrations nor static collection
runs automatically when a web container starts.

For an emergency, operator-reviewed manual operation, use an image digest from
an already published release and keep it out of `.env`:

```bash
cd /srv/luxury-perfume
export APP_IMAGE=ghcr.io/pursite/luxury-perfume@sha256:<published-image-digest>
export FRONTEND_IMAGE=ghcr.io/pursite/luxury-perfume-frontend@sha256:<matching-frontend-digest>
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml config -q
./scripts/frontend-release.sh prepare /srv/luxury-perfume <matching-commit-sha> "$FRONTEND_IMAGE"
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml up -d --no-build db redis
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml run --rm --no-deps web python manage.py check --deploy --settings=config.settings.production
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml run --rm --no-deps web python manage.py migrate --noinput
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml run --rm --no-deps web python manage.py collectstatic --noinput
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml up -d --no-build --no-deps --force-recreate web celery
./scripts/frontend-release.sh activate /srv/luxury-perfume <matching-commit-sha> "$FRONTEND_IMAGE"
```

Obtain both images using the same ephemeral-token procedure as CD. Do not
configure a persistent `docker login` on the VPS, and do not place either
digest or token in `.env`. The emergency sequence is operator-controlled and
must preserve the same frontend readiness and Celery stability checks as the
normal workflow before switching `frontend-current`.

Before deploying the product slug URL cutover, audit the target database with
these read-only queries:

```sql
SELECT id, slug
FROM products_product
WHERE slug <> lower(slug);

SELECT lower(slug) AS canonical_slug, array_agg(slug ORDER BY slug) AS variants
FROM products_product
GROUP BY lower(slug)
HAVING count(*) > 1;

SELECT id, slug
FROM products_product
WHERE slug ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
```

All three result sets must be empty. If any query returns rows, stop the
release and assign reviewed lowercase, non-UUID-shaped unique slugs before
retrying. Do not automatically lowercase data because case-only variants can
collide. This is an immediate URL cutover: clients must construct product
detail, mutation, and image-upload URLs from the response `slug`; UUID product
URLs return 404 after deployment.

The users and products migration histories have been reset and each currently
starts with `0001_initial.py`. Those initial migrations define the current
schema and constraints directly; there are no legacy identity,
fragrance-domain, or ordered-note data migrations or release gates in this
repository. This runbook therefore applies to the new-deployment database
contract described above. Do not apply these initial migrations blindly to an
older installation with a different migration history; such an installation
requires an explicitly reviewed schema-reconciliation or data-import plan.

The same image runs Django and Celery as UID/GID `10001`, not root. The web
image defaults to Gunicorn on container port `8000`, while Compose overrides
the command only for development Django and the Celery worker. Production
publishes Gunicorn only as `127.0.0.1:8000` for the host proxy. PostgreSQL and
Redis have no host port mappings in the production merge.

## Production logs

Application processes do not create log files in the image or persistent
mounts. Django activity events are JSON on stdout; security and system events,
including Django errors, are JSON on stderr. Gunicorn writes access logs to
stdout and error logs to stderr. Its access records contain the response
`X-Request-ID`, method, path without a query string, status, duration, response
size, and process ID; they intentionally omit query strings, client IPs,
referrers, and user agents.

`RequestIDMiddleware` creates the opaque `X-Request-ID` server-side for every
HTTP request. It is also the request's application-log correlation ID. OTP
enqueue records contain a Celery `task_id`; the worker uses that task ID as the
correlation ID while it runs the task. Do not send secrets, tokens, passwords,
OTP values, phone numbers, email addresses, request bodies, cache keys, or
sensitive exception text to any logger.

The production Compose override applies Docker's `local` logging driver with
`max-size=10m` and `max-file=3` to PostgreSQL, Redis, web, and Celery. Docker
rotates and compresses these internal files; use Compose instead of reading
the Docker data directory directly:

```bash
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml \
  logs --tail=100 web celery
docker inspect -f '{{.HostConfig.LogConfig.Type}}' luxury-perfume-web-1
```

The rotation cap bounds local retention, so it is not an audit archive. This
single-VPS deployment intentionally has no external log aggregation; collect
or retain logs through a separately reviewed host process if operational or
compliance requirements need longer retention.

Static assets are written to `/srv/luxury-perfume/staticfiles` by `collectstatic`.
Uploaded media is stored at `/srv/luxury-perfume/media`. Both directories are bind
mounted into the application; Nginx reads them directly, so do not delete or
replace them during routine deployments.

## Production storefront artifact

Production serves a static React build; it never runs Vite, npm, or a permanent
Node process. The release gate runs Node 24 LTS, `npm ci`, lint, tests, and
`VITE_API_BASE_URL=https://shop.exonplus.ir npm run build` from the reviewed
commit. CI stamps the output with the commit SHA and public API origin,
validates that it contains only the expected build files, and packages it in a
`FROM scratch` OCI carrier labeled with that same SHA. CD pulls the exact
frontend SHA tag, resolves its digest, extracts it with `docker create` and
`docker cp` without starting the container, and validates it again before
placing it in the immutable `frontend-releases/<commit-sha>/` directory.

The active release is `/srv/luxury-perfume/frontend-current`, an atomic symlink
to one immutable release directory. The deployment never copies partial files
over the live build. `VITE_API_BASE_URL` is public build configuration, not a
secret; never place Django, JWT, database, Redis, future payment, or VPN
credentials in a `VITE_*` variable. `frontend/dist/` is reproducible CI output
and is not committed. Releases are retained for rollback according to the
operator's disk policy; CD does not automatically delete old releases.

## Redis durability and capacity

One Redis instance currently provides four logical databases: ordinary cache,
fail-closed authentication security state, Celery broker data, and Celery
results. Compose enables AOF and explicitly uses `appendfsync everysec` so a
normal process or container restart can recover persisted state. On abrupt
host or power failure this policy typically limits lost acknowledged writes to
about one second, but it is not a durability guarantee and does not protect
against storage loss.

AOF persistence writes every Redis value to the `redis_data` named volume,
including temporary OTP values, cache entries, and Celery payloads. Deleted or
expired values can remain in historical AOF commands until a rewrite, so treat
the volume and any copy of it as sensitive data. Restrict host access, do not
publish Redis, and do not include the volume in broadly accessible backups.
Monitor free space and AOF size: cache churn and Celery traffic can grow the
file until Redis rewrites it, and a rewrite needs additional disk and memory
headroom. AOF improves restart recovery but is not a backup.

Compose explicitly sets `maxmemory-policy noeviction` because all logical
databases share one instance-wide policy; an evicting policy could silently
discard fail-closed OTP, lockout, or verification state. Compose does not set a
host-independent `maxmemory` value or a container memory limit. Do not assume
that this leaves Redis safely bounded: choose a ceiling only from measured
peak usage and the VPS memory budget, leaving headroom for Redis overhead, AOF
rewrites, PostgreSQL, Django, and Celery. With a positive `maxmemory`,
`noeviction` rejects writes at the limit rather than discarding security state,
so alert on memory usage and rejected writes. Workloads that require cache
eviction independently of security and queue data need separate Redis
instances, which are outside this single-VPS layout.

Confirm the effective production policy after startup rather than relying on
image defaults:

```bash
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml \
  exec redis redis-cli CONFIG GET appendonly appendfsync maxmemory maxmemory-policy
```

Celery results expire after `CELERY_RESULT_EXPIRES_SECONDS` (86400 seconds by
default). Ordinary cache entries default to ten minutes; product-list and
product-detail responses use one- and five-minute TTLs, and the catalogue cache
version uses seven days. These expirations bound normal cache/result retention,
but capacity and disk monitoring are still required.

## Host Nginx

Install and operate Nginx and TLS certificates on the host according to the
host operating system's security update process. The upstream is always
`http://127.0.0.1:8000`; do not expose Docker's Gunicorn port on a public host
interface.

The public responsibilities are intentionally separate:

- `www.exonplus.ir` serves only the React storefront and uses `index.html` as
  the fallback for client routes such as `/products/<slug>` and `/cart`.
- `shop.exonplus.ir` serves the Django API, health endpoints, Admin, static
  assets, and uploaded Product media through the existing loopback Gunicorn
  topology.
- `api.exonplus.ir` remains the existing VPN/3x-ui service. Do not add it to
  Django, proxy it to Gunicorn, or change its configuration for this project.

Minimal example configuration (adjust certificate paths and the active
frontend release path to match the host):

```nginx
server {
    listen 80;
    server_name www.exonplus.ir shop.exonplus.ir;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name www.exonplus.ir;

    ssl_certificate     /etc/ssl/certs/www.exonplus.ir/fullchain.pem;
    ssl_certificate_key /etc/ssl/private/www.exonplus.ir/privkey.pem;

    root /srv/luxury-perfume/frontend-current;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location = /index.html {
        add_header Cache-Control "no-cache";
    }

    location /assets/ {
        try_files $uri =404;
        access_log off;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}

server {
    listen 443 ssl http2;
    server_name shop.exonplus.ir;

    ssl_certificate     /etc/ssl/certs/shop.exonplus.ir/fullchain.pem;
    ssl_certificate_key /etc/ssl/private/shop.exonplus.ir/privkey.pem;
    client_max_body_size 10m;

    location /static/ {
        alias /srv/luxury-perfume/staticfiles/;
        access_log off;
        expires 7d;
    }

    location /media/ {
        alias /srv/luxury-perfume/media/;
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
`SECURE_PROXY_SSL_HEADER_ENABLED=True` and one forwarding proxy for DRF client
IP throttling through `DRF_NUM_PROXIES=1`. Only the local, host-managed Nginx
should be able to reach the Gunicorn listener; otherwise a client could forge
the forwarded address used by OTP limits. Restrict media further in Nginx if
uploaded product images must not be public.

After installing the site, validate and reload the host service using the
operating system's Nginx commands, then verify the storefront SPA fallback and
backend paths:

```bash
curl --fail -I https://www.exonplus.ir/
curl --fail -I https://www.exonplus.ir/products/example-slug
curl --fail https://shop.exonplus.ir/health/live
curl --fail https://shop.exonplus.ir/health/ready
curl --fail https://shop.exonplus.ir/health/startup
curl --fail -I https://shop.exonplus.ir/static/admin/css/base.css
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

## Release and rollback limits

Before deploying a release with migrations, confirm the production `.env` has a
dedicated JWT signing key with at least 32 random bytes,
`DRF_NUM_PROXIES=1` for the documented Nginx topology, and explicit phone/IP
OTP throttle rates. CD runs `python manage.py check --deploy` before it
replaces web or Celery, but application readiness does not establish a data
recovery strategy.

Database/media backup and restore automation is intentionally not implemented
in this repository yet. Design, operate, protect, and regularly test those
procedures separately before relying on production migrations. Docker volumes
and files on the same VPS are not a backup; never run `docker compose down -v`
on production because it removes PostgreSQL and Redis volumes.

For a code-only rollback, dispatch **Deploy production** with an already
published, previously tested full commit SHA. The workflow checks out that
revision, pulls both matching backend and frontend images, extracts or reuses
the SHA-addressed frontend release, runs `collectstatic`, recreates the
application containers without rebuilding, and atomically switches the
frontend symlink. It never automatically reverses database migrations. A
rollback is therefore safe only when the older code is compatible with the
current database schema and data. Assess reversibility, data loss, and
operational recovery manually; reverse migrations and restore logic are
intentionally not implemented by this workflow. GHCR Actions artifacts are
short-lived build intermediates; the immutable SHA image tags are the rollback
retention boundary, so do not delete a release image that may be needed for
rollback.

In particular, application images from before the fragrance-domain migration
expect columns that the forward migration removes and are not valid code-only
rollback targets afterward. Roll back only to a published `luxury-perfume`
image whose code is compatible with the applied schema; any older recovery
requires a separately designed database restore or schema procedure.
Database/media backup and restore automation remains intentionally
unimplemented.

Useful operational checks:

```bash
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml ps
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml logs --tail=100 web celery
docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml exec web python manage.py check --deploy
```

Orders adds a separate `celery-beat` service. Run exactly one Beat process; it
schedules the Orders expiry sweep every 60 seconds and must not be replaced by
`worker -B`. The database `reservation_expires_at` deadline remains
authoritative if Beat, workers, or the broker are delayed.
