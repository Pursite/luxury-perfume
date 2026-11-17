# Production deployment and operations

## Scope and production topology

This runbook defines one VPS at `/srv/luxury-perfume`; it is not evidence that a
particular host, DNS record, certificate, or deployment is configured or reachable.
Commands below are operator guidance, not actions performed by reading this guide.
[CI/CD](ci-cd.md) owns verification, image publication, workflow secrets, and the
exact delivery orchestration. This guide owns host preparation, runtime checks,
data safety, and recovery.

```text
Browser → host Nginx / TLS
           ├─ www.exonplus.ir → frontend-current → static React release
           └─ shop.exonplus.ir
                ├─ /static/ and /media/ → persistent host asset directories
                └─ Django → 127.0.0.1:8000 → Compose web (Gunicorn)
                                                    ├─ db (PostgreSQL)
                                                    └─ redis
                    Compose celery worker ← broker ← one celery-beat scheduler
```

| Service/component | Production role |
| --- | --- |
| `web` | Published Python application image; Gunicorn `gthread`, one worker/two threads in the production override |
| `celery` | Same image, separate worker with concurrency 1; media mount for thumbnail work |
| `celery-beat` | Same image, exactly one scheduler; no embedded worker `-B` |
| `db` | PostgreSQL 16, private Docker network, named `postgres_data` volume |
| `redis` | Redis 7, private Docker network, named `redis_data` volume |
| Host Nginx/TLS | External to Compose; serves static assets and proxies Django |
| Frontend | Static release extracted from a scratch carrier; no running Vite, Node, or frontend container |

The project name is `luxury-perfume`; physical volume names normally become
`luxury-perfume_postgres_data` and `luxury-perfume_redis_data`. Web alone publishes
`127.0.0.1:8000:8000`. This is not a multi-host/high-availability design; no managed
database, object store, load balancer, or Kubernetes layer is defined here.
Services outside this repository are outside this deployment's scope.

### Compose selection

Always use the shared file first and the environment override second:

- [`docker/docker-compose.yml`](../docker/docker-compose.yml): service names,
  private dependencies, named volumes, restart policies, and healthchecks.
- [`docker/docker-compose.prod.yml`](../docker/docker-compose.prod.yml): required
  published `APP_IMAGE`, production process sizing, loopback port, asset bind
  mounts, and Docker log rotation. It has no application build configuration.
- [`docker/docker-compose.dev.yml`](../docker/docker-compose.dev.yml): local
  builds, source mounts, runserver, and configurable loopback development port.

PostgreSQL and Redis remain
internal during development as well as production. The separate integration
Compose stack is disposable test infrastructure, not a production override.
Follow [Development](development.md) for local onboarding; do not combine the
production and development overrides or share their data volumes on one host.

## First-deployment prerequisites

Use a dedicated deployment account that owns the checkout and can run this
Docker/Compose stack. General Docker access grants powerful host capabilities;
the workflow does not create a sandbox or configure account restrictions.
The account must have read access to the repository's `origin` (for example,
a read-only deploy key); Actions-to-VPS authentication is a separate credential.

Prepare the host through its operating-system administration process:

- Docker Engine and the `docker compose` plugin, supporting the commands used
  in the workflow. Install/update these outside the application deployment.
- Git, Bash, curl, CA certificates, OpenSSH, `flock` (commonly `util-linux`),
  and GNU coreutils/find/grep used by the release script.
- Host-managed Nginx and valid certificates for both application hosts, with
  an independently maintained certificate renewal process.
- POSIX ACL tools (`acl` on Debian/Ubuntu), sufficient disk/memory for images,
  extracted frontend releases, PostgreSQL, Redis/AOF rewrites, and persistent assets.
- Access to **both** GHCR packages and a reviewed source revision published by
  the qualifying `main` pipeline. Node/npm and a host Python environment are
  not required for normal production delivery.
- Separately designed/protected backups and restore procedures before valuable
  data is accepted or migrations are applied. These are intentionally not implemented
  by this repository.

A differently named existing installation is not automatically migrated by
changing paths/project names. Inventory its database, volumes, mounts, and data
before preparing this layout. Never attach two PostgreSQL containers to the
same physical data volume. This is a compatibility warning, not an outstanding
repository-rename task: the repository already is `Pursite/luxury-perfume`.

### Prepare a fresh checkout and private environment

Run as the intended deployment account, using sudo only for host preparation.
These commands assume the target is a fresh, empty directory. For an existing
checkout, inspect it and preserve its `.env` and data instead of repeating clone
or replacing configuration.

```bash
sudo mkdir -p /srv/luxury-perfume
sudo chown "$USER":"$(id -gn)" /srv/luxury-perfume
git clone git@github.com:Pursite/luxury-perfume.git /srv/luxury-perfume
cd /srv/luxury-perfume

# Refuse to overwrite an existing .env; keep newly created content private.
(umask 077; set -o noclobber; cat docker/env/.env.production.example > .env)
chmod 600 .env
```

Edit private configuration with the account's normal secure editor. Never print
or paste the complete environment or rendered Compose configuration into tickets,
CI logs, or chat. CD requires `.env` to exist; it neither uploads nor rewrites it.

### Environment responsibilities

Use [`docker/env/.env.production.example`](../docker/env/.env.production.example)
as the inventory, not a ready-to-deploy secret file. Set required placeholders
for enabled functionality; keep disabled-provider placeholders inactive until a
separately reviewed integration exists.

| Area | Required policy for this layout |
| --- | --- |
| Django | `DJANGO_SETTINGS_MODULE=config.settings.production`, private random `SECRET_KEY`, `ALLOWED_HOSTS=shop.exonplus.ir` |
| JWT | Distinct cryptographically random `JWT_SIGNING_KEY`, at least 32 random bytes; never reuse development examples |
| Database | Private credentials; `DB_HOST=db`, `DB_PORT=5432`; host/container `localhost` is not the private database |
| Redis | Internal `redis:6379` URLs; separate ordinary/security/broker/result databases as below |
| HTTPS/cookies | Forwarded HTTPS scheme, redirect/HSTS, secure session/CSRF cookies; production refresh cookie is host-only Secure/HttpOnly/SameSite Lax |
| Origins | `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` include `https://www.exonplus.ir`; cookie-auth Origin permission uses the API origin/CORS allowlist |
| AUTH proxy trust | Defaults to disabled, even in the production template; enable only with actual reviewed connecting-proxy CIDRs |
| Payment/SMS | `PAYMENTS_ENABLED=False`, `SMS_ENABLED=False` until real reviewed adapters/configuration exist |
| Shipping | `ORDER_SHIPPING_FLAT_RATE_IRT=350000.00` tracked default; new Orders snapshot the exact non-negative two-decimal IRT value |

Choose HSTS duration/include-subdomains/preload policy deliberately for the real
host estate; the template sets these but does not provision HTTPS everywhere or
register a preload entry. Keep CORS/CSRF allowlists explicit and aligned with the
actual storefront. They do not replace backend authorization or the cookie-auth
Origin check. See [Authentication](authentication.md) and [Security](security.md).

Do not put `APP_IMAGE`, GHCR tokens, SSH credentials, or frontend secrets in
application `.env`. CD supplies digest-pinned `APP_IMAGE` to its own process;
`VITE_*` variables are public build configuration. Database initialization
credentials apply when the PostgreSQL volume is first initialized: editing
`.env` later does not change an existing database role/password. Coordinate any
credential change as a separate backed-up database operation; do not delete the
volume. See [Troubleshooting](troubleshooting.md).

Validate configuration without starting services or printing expanded values:

```bash
APP_IMAGE=ghcr.io/pursite/luxury-perfume:compose-validation docker compose \
  --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.prod.yml \
  config -q
```

That reference only satisfies interpolation; validation does not pull an image,
verify credentials, or establish a working database/provider.

## Persistent assets and host permissions

Web mounts `/srv/luxury-perfume/staticfiles` at `/app/staticfiles` and
`/srv/luxury-perfume/media` at `/app/media`. Celery mounts media for thumbnail
work; Beat has neither mount. The final application runs as UID/GID `10001`.
Django `collectstatic` writes static files and uploads/thumbnail tasks write
media. These are persistent runtime paths, not image content to replace on each
release. Host Nginx needs read/traverse access, never application-data write access.

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

### Frontend release paths

Prepare the release parent as the deployment account. Its directory must be
writable by that account and traversable by Nginx; adjust `www-data` if the host
uses another Nginx user.

```bash
sudo install -d -o "$USER" -g "$(id -gn)" -m 0750 \
  /srv/luxury-perfume/frontend-releases
sudo setfacl -m u:www-data:rx /srv/luxury-perfume/frontend-releases
```

The release script creates `frontend-releases/<commit-sha>/` from a validated
staging directory, then sets directories to 0555 and files to 0444. This is a
read-only serving convention, not protection against a privileged host operator.
Nginx's root is `/srv/luxury-perfume/frontend-current`, a relative symlink to one
release. Both project-parent traversal and release-parent permissions matter.
Do not replace that symlink with a real directory or copy partial bundles over
its target. `.release-manifest.json` binds SHA/API origin and
`.frontend-image-digest` binds the extracted carrier digest. Reuse requires both
to match. Old frontend releases are retained; CD implements no automatic pruning.

## Host Nginx and TLS

Configure DNS/certificates and the host reverse proxy outside Docker. The
storefront host is `www.exonplus.ir`; the API/Admin/health/static/media host is
`shop.exonplus.ir`. Gunicorn's upstream remains `http://127.0.0.1:8000` and must
not be published on a public interface. The scratch frontend image is a file
carrier, not an upstream server.

The following example preserves SPA fallback, immutable hashed-asset caching,
Django static/media aliases, and forwarded scheme/client-IP behavior. Certificate
paths are examples: use paths matching the actual certificate installation,
renewal process, and host Nginx version. Install it through normal host change
review; it is not applied by CD.

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
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
```

The example serves uploaded Product media publicly and directly; Django object
permissions are not evaluated for `/media/`. Do not use this alias for private
uploads without a separately reviewed access design. Nginx has read-only ACLs;
application upload validation does not make arbitrary media private.

`SECURE_PROXY_SSL_HEADER_ENABLED=True` makes Django trust the configured
forwarded-scheme header; the example overwrites incoming forwarding headers.
For project AUTH IP extraction, `AUTH_TRUST_PROXY_HEADERS=True` additionally
requires valid `AUTH_TRUSTED_PROXY_CIDRS`. Verify the connecting peer address as
seen **inside** the container; Docker port forwarding may make it differ from
the host's loopback address. Do not guess a gateway address or trust broad
private networks. With AUTH trust disabled, auth controls use the peer/proxy IP.
Ordinary DRF throttles use separate `DRF_NUM_PROXIES` logic (template: 1), not
this CIDR policy. Payment has separate `PAYMENT_TRUST_PROXY_HEADERS` and
`PAYMENT_TRUSTED_PROXY_CIDRS`, required when that subsystem is enabled.

Validate the host configuration before reloading, after certificates/site files
are in place. The reload changes host state and requires operator approval:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

On a fresh host the frontend pointer/backend may not exist until the first CD
run succeeds; a configured TLS listener alone is not application readiness.

## First release and normal execution

Complete these prerequisites before dispatching production delivery:

1. Prepare the host, checkout access, private `.env`, persistent paths/ACLs,
   Nginx/TLS, and separately verified data recovery arrangements.
2. Configure the `production` GitHub environment, reviewed branch restrictions/
   reviewers, and the six workflow secrets listed in [CI/CD](ci-cd.md#secrets-and-trust-boundaries).
   YAML cannot prove account-level protection rules are configured.
3. Ensure the `GHCR_READ_TOKEN` account can read **both**
   `ghcr.io/pursite/luxury-perfume` and
   `ghcr.io/pursite/luxury-perfume-frontend`, under the registry username used by
   CD. Keep registry authentication ephemeral as the workflow does; do not run
   a persistent default `docker login` on the VPS or put that token in `.env`.
4. Publish the reviewed release through a qualifying push to `main`. Verify the
   complete Release gate and both `Publish application image` and
   `Publish frontend image` jobs succeeded for the intended SHA. Passing CI on
   a documentation branch does not publish these images.
5. Manually dispatch **Deploy production** with the full lowercase 40-character
   published commit SHA. Empty input instead selects that workflow run's
   `github.sha`; use an explicit SHA when selecting an older release.
6. Inspect the workflow result and perform the runtime/frontend checks below.
   Do not assume success from image publication or a reachable TLS endpoint.

CD does not independently query CI conclusions for the selected commit. It
requires source ancestry under `origin/main`, both published tags, matching
OCI revisions/digests, and deployment conditions. Operators still verify review
and CI/publication results. The host checkout must have no tracked/untracked
source edits; `.env`, assets, and frontend release state are ignored by Git.
Do not erase local changes to make the deployment pass.

### Deployment order and mutation boundary

The implementation in [cd.yml](../.github/workflows/cd.yml) serializes the job
and takes a nonblocking `.git/deploy.lock`. It validates source ancestry/cleanliness,
pulls both SHA-tagged images with temporary credentials, resolves and validates
their package digests/revision labels, then removes registry auth. It detaches
source at the selected revision and **prepares** the frontend from its stopped
carrier before touching runtime services.

Next it validates shared + production Compose, starts existing `db`/`redis`
without recreation, and checks PostgreSQL/Redis readiness. One-off application
containers run deployment checks, forward migrations, and static collection in
that order. Web is recreated first and must pass readiness; worker and Beat are
then recreated and sampled for stable running state. Only after those checks
is `frontend-current` **activated** with an atomic symlink rename.

No application/frontend build runs on the VPS; Compose `up` uses `--no-build`.
Neither migrations nor static collection is an automatic web-startup action.
No `down`, volume deletion, resource pruning, Nginx modification, or `.env`
rewrite occurs in CD. Migrations can change database schema/data, collectstatic
changes the shared static directory, and recreation changes runtime containers.
A failure before frontend activation preserves the old pointer, **not** a promise
that the backend/database/static files remain unchanged. There is no automatic
cross-component rollback. Exact retries/sample timing are in [CI/CD](ci-cd.md#ordered-deployment-stages).

## Runtime inspection and verification

### Select the active backend image for operational commands

CD exports `APP_IMAGE` only in its remote shell; a later host shell must select
it again. On an already-running deployment, inspect the container's configured
digest before issuing Compose commands. From `/srv/luxury-perfume`, in Bash:

```bash
cd /srv/luxury-perfume
web_container_id=$(docker ps -q \
  --filter label=com.docker.compose.project=luxury-perfume \
  --filter label=com.docker.compose.service=web)
[[ "$web_container_id" =~ ^[0-9a-f]+$ ]]
APP_IMAGE=$(docker inspect --format '{{.Config.Image}}' "$web_container_id")
[[ "$APP_IMAGE" =~ ^ghcr\.io/pursite/luxury-perfume@sha256:[0-9a-f]{64}$ ]]
export APP_IMAGE

dc() {
  docker compose --env-file .env \
    -f docker/docker-compose.yml -f docker/docker-compose.prod.yml "$@"
}
```

Proceed only if all checks succeed and exactly one web container was selected;
this is for inspecting the running release, not choosing a new deployment.
If web is absent or a partial deployment mixed versions, determine the intended
validated release from deployment records first. Do not use a placeholder/latest
image for recovery. `APP_IMAGE` in this shell does not prove worker/Beat use it;
inspect those containers when diagnosing a partial release.

### Non-destructive runtime diagnostics

```bash
dc ps -a
dc logs --tail=100 web celery celery-beat
dc exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
dc exec -T redis redis-cli ping
dc exec -T web python manage.py showmigrations

docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
  "$web_container_id"
docker inspect --format '{{.HostConfig.LogConfig.Type}}' "$web_container_id"
curl --fail --silent --show-error --max-time 5 \
  -H 'Host: shop.exonplus.ir' -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8000/health/ready
```

Review logs privately; do not publish secret-filled settings, task arguments,
provider payloads, or complete environment values. `pg_isready`/PING do not prove
application migrations, correct credentials for every caller, or worker behavior.
Health/readiness probes are bounded diagnostics; readiness writes a short-lived
security-cache key as part of its check.

### Health endpoint meanings

All three paths are GET-only plain Django views, outside DRF authentication and
throttling. Host/TLS validation still applies. They have **no trailing slash**.

| Path | Check | Does not establish |
| --- | --- | --- |
| `/health/live` | Django can respond to an HTTP request | Database/cache/task readiness |
| `/health/startup` | Django app registry is initialized | Dependency readiness or completion of migrations |
| `/health/ready` | PostgreSQL `SELECT 1` and a security-cache write; 200 if both succeed, otherwise bounded 503 fields | Schema compatibility, ordinary cache, broker, worker/Beat, filesystem capacity, external providers |

The ordinary cache is intentionally omitted: catalogue caching can fail open.
The web Docker probe uses loopback readiness with `Host: shop.exonplus.ir` and
`X-Forwarded-Proto: https`; this matches production's tracked host policy. It has
a 20-second start period, 30-second interval, five-second timeout, and three
retries. Running and healthy are different states; `restart: unless-stopped`
does not restart a still-running process merely because it becomes unhealthy.
Worker and Beat have no Docker healthchecks; CD samples process stability,
which is not proof that tasks execute. The development template has a separate
Host/probe mismatch described in [Troubleshooting](troubleshooting.md).

After CD and host setup, verify externally as an operator:

```bash
curl --fail -I https://www.exonplus.ir/
curl --fail -I https://www.exonplus.ir/products/example-slug
curl --fail https://shop.exonplus.ir/health/live
curl --fail https://shop.exonplus.ir/health/ready
curl --fail https://shop.exonplus.ir/health/startup
curl --fail -I https://shop.exonplus.ir/static/admin/css/base.css
```

The product-shaped frontend URL checks SPA fallback, not that a Product exists.
Also inspect the browser for asset loading, API requests, and allowed-Origin
cookie-backed login/refresh; a status-only curl check does not establish those.
Verify Nginx read/no-write checks from the asset section after static collection.

## Logs and retention

Django's configured `activity` logger emits JSON to stdout; `system`, `security`,
and Django errors go to stderr. Financial and Notification audit helpers use
bounded event fields rather than provider payloads. `RequestIDMiddleware`
generates a new opaque `X-Request-ID` and request correlation context; shared
correlated tasks use their Celery task ID. Gunicorn access/error logs use
stdout/stderr; its access format includes response request ID, method, path
without query, status, duration, byte count, and process ID, omitting IP, referrer,
and user agent.

These controls minimize data; they are not a guarantee that every logger safely
formats every value. The existing UUID `user_id` encoding limitation is documented
in [Security](security.md#logging-secrets-and-transport). Never deliberately
log credentials, JWTs, OTPs, phone/email values, request bodies, cache keys,
provider evidence, or sensitive exception text. Keep diagnostic exports private.

All five services use Docker's `local` log driver with `max-size=10m` and
`max-file=3`. Use `dc logs`, not direct reads under Docker's data directory.
Rotation bounds local retention; it is not an audit archive, external collection,
or an alert. External log aggregation and host monitoring/alerting are
intentionally not implemented in this repository.

## Redis durability and capacity

One Redis instance currently provides four logical databases: ordinary cache,
fail-closed authentication security state, Celery broker data, and Celery
results. The tracked URL mapping is:

| Setting | Redis URL / role |
| --- | --- |
| `CACHE_REDIS_URL` | `redis://redis:6379/0` — ordinary cache/default throttles |
| `SECURITY_REDIS_URL` | `redis://redis:6379/1` — fail-closed authentication state |
| `CELERY_BROKER_URL` | `redis://redis:6379/2` — task transport, including actual phone/OTP payloads |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/3` — expiring task results |

These logical databases separate keys, not availability, capacity, or access
control. Compose enables AOF and explicitly uses `appendfsync everysec` so a
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

## Scheduled work and disabled providers

Run exactly one `celery-beat`, separate from the worker. It schedules Order
reservation expiry, Payment reconciliation, pending Refund execution, and due
Notification delivery every 60 seconds; Payment audit-metadata and terminal SMS
recipient scrubbing run daily. [Architecture](architecture.md#asynchronous-processing)
owns the schedule/transaction details. Database deadlines and durable state
remain authoritative if the scheduler or worker is delayed.

Keep Payment and SMS disabled by default: neither has a real registered adapter.
Enabling them is a separate implementation/configuration review, not a production
readiness shortcut. Deployment system checks validate registered methods, HTTPS
URLs/redirect policy and Payment proxy trust, and SMS timeout/retry/configuration
budgets where enabled. Sandbox verification and operational monitoring remain
necessary; test doubles are not live integrations. Before provider enablement,
review private credential configuration, fixed network timeouts, response
validation, HTTPS/redirect rules, idempotent client references, and Payment
create/lookup/verify/full-refund behavior in the provider sandbox. Coordinate
matching web/worker/Beat recreation; changing a flag does not supply an adapter
or implement the currently absent frontend checkout/payment-result UI.

With SMS enabled, processing creates customer and eligible active-superuser
obligations; only valid canonical account phones qualify, not ordinary staff or
a business-phone env value. Shipping creates a customer obligation. Disabled SMS
creates no new transition outbox rows and pauses sends/sweeps without deleting
unresolved obligations. Payments disablement stops HTTP handlers, not financial
history or existing Payment/Refund obligations. Manual-review Payments require
explicit audited recovery rather than automatic reconciliation.

## Rollback and recovery

### Diagnose before changing state

Inspect the failed workflow stage, selected SHA/digests, running container images,
health/logs, migration state, and active frontend link/manifest. Use the bounded
checks above and [Troubleshooting](troubleshooting.md). Do not hide a failure by
editing the manifest, bypassing readiness, broadening trust, or deleting state.

For the frontend alone, these inspect/validate existing files and do not activate
another release. Set `RELEASE_SHA` and `FRONTEND_IMAGE` from reviewed release
records; the latter must be the matching package `@sha256:` digest:

```bash
cd /srv/luxury-perfume
readlink frontend-current
: "${RELEASE_SHA:?Set the reviewed full commit SHA}"
: "${FRONTEND_IMAGE:?Set the matching published frontend digest}"
./scripts/frontend-release.sh validate \
  "/srv/luxury-perfume/frontend-releases/$RELEASE_SHA" \
  "$RELEASE_SHA" "$FRONTEND_IMAGE"
```

### Operator-approved recovery

Prefer dispatching CD with a previously published, reviewed, full commit SHA
with both images still available. It reuses the same ancestry, digest,
revision, preparation, migration/static, readiness, and stability checks. Do not
substitute a shorter manual sequence that activates frontend before verifying
web/worker/Beat or ignores the clean-source/deployment lock boundary.

An older application must work with the **current** schema and data. Automated
migrations are forward-only in the delivery sequence; no automatic database
rollback, reverse migrations, or restore is implemented. Code rollback does not
undo earlier migrations, shared static collection, user uploads, captures,
Refund obligations, or SMS delivery state. Keep operational compatibility and
unresolved external obligations under review. Atomic frontend switching is not
an atomic database/container rollback.

For a separately authorized maintenance operation, after backups/compatibility
review and selection of the correct image/source, these are the same one-off
mutations used by CD (the `dc` function above must be configured appropriately):

```bash
dc run --rm --no-deps web python manage.py check --deploy --settings=config.settings.production
dc run --rm --no-deps web python manage.py migrate --noinput
dc run --rm --no-deps web python manage.py collectstatic --noinput
```

`check --deploy` is validation; migrations and collection change persisted state.
These commands are not a complete emergency deployment: preserve the workflow's
lock, image/revision validation, dependency readiness, process checks, and final
frontend activation ordering. Never use a mismatched source/image pair.

Back up PostgreSQL and persistent media with a reviewed consistent procedure,
protect Redis/AOF copies as sensitive, and verify restoration separately.
Database/media backup and restore automation is intentionally not implemented.
Docker volumes and files on the same VPS do not replace backups. Never delete
live volumes or run `docker compose down -v` on production. Retain both GHCR
release images and extracted frontend files needed for recovery; Actions image
archives expire after one day. SHA tags are workflow-protected references,
not cryptographically immutable content; record their resolved digests too.

## Migration inventory and one-time compatibility work

Current Users migrations are `0001_initial` and `0002_otpchallenge`. Products,
Cart, and Orders each have `0001_initial`. Payments additionally has
`0002_manual_review_stops_automatic_reconciliation`; Notifications additionally
has `0002_remove_smsdelivery_notifications_order_event_unique_and_more`.
See [Architecture](architecture.md#migration-state) for the model/history boundary.
A fresh database applies the current inventory through normal `migrate`.
This is not an automatic reconciliation strategy for a pre-existing older schema
or migration history; that requires its own reviewed plan and backup.

The following are **historical cutover precautions**, not steps to repeat on
every current-format release:

- For a pre-slug-URL installation, audit Product slugs before its first URL
  cutover. The read-only PostgreSQL queries below must return no rows. Resolve
  collisions/invalid values through a reviewed data plan, never blind lowercasing.
  Current clients use response slugs; UUID Product URLs have no compatibility alias.
- For a pre-durable-OTP installation, drain old web/workers, apply
  `users.0002_otpchallenge`, and use matching code. Legacy codes need reissuance.
  Reverting to code without durable redemption requires drained traffic and
  invalidated outstanding challenges; do not drop active redemption state.

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

Ongoing optional maintenance `python manage.py cleanup_otp_challenges` deletes
expired challenge records without reading codes. Run only through reviewed
maintenance using the correct application container; it is not an automatic CD
step or a way to bypass a valid OTP.

### Translation catalogue maintenance boundary

The image consumes committed `locale/fa/LC_MESSAGES/django.po` and `django.mo`;
it does not install runtime gettext or compile catalogues on startup. For source
maintenance in a suitable developer environment with GNU gettext, exclude docs
(including current decisions/archive paths), dependencies, and frontend output:

```bash
python manage.py makemessages -l fa --ignore 'venv/*' --ignore '.venv/*' \
  --ignore 'frontend/node_modules/*' --ignore 'frontend/dist/*' --ignore 'docs/*'
python manage.py compilemessages -l fa
```

Review translations and commit both catalogue files through the normal source
workflow. This is not a command to run against the production checkout during CD.
CI's final-image translation smoke check verifies that a known committed Persian
message is present. Pipeline ownership and failure stages are in [CI/CD](ci-cd.md).
