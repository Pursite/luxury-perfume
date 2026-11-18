# Troubleshooting

Use this guide to diagnose local development, automated checks, and release
failures. Configuration facts come from the repository; possible runtime causes
below are diagnostic hypotheses, not claims that each failure was reproduced.
For initial setup, use [Development](development.md); for complete verification
commands and test boundaries, use [Testing](testing.md).

## Command conventions and safe diagnosis

Run backend commands from the repository root. To keep examples readable,
define this Bash function in each troubleshooting terminal:

```bash
dc() {
  docker compose --env-file .env \
    -f docker/docker-compose.yml \
    -f docker/docker-compose.dev.yml "$@"
}
```

`dc` always selects the **development** stack, whose services are `web`, `db`,
`redis`, `celery`, and `celery-beat`. Integration commands below explicitly use
the separate integration Compose file. Do not use this function on production.

Start with state and bounded logs. Keep diagnostic output private and redact
sensitive errors before sharing. Do not print `.env`, full environment dumps,
complete rendered Compose configuration, tokens, OTP values, or task arguments.
Use `config -q` rather than `config` to validate without rendering secrets.

Development PostgreSQL and Redis use persistent named volumes. Container
removal does not reset credentials or data. Volume deletion permanently loses
data and is not a routine troubleshooting step. Back up valuable data and agree
on a recovery plan before database, credential, or schema changes. Never point
tests at production services, disable security controls, or expose PostgreSQL
or Redis publicly to resolve a local connectivity problem.

## Docker and Compose

### Docker daemon cannot be reached

**Symptom:** Compose reports that it cannot connect to the Docker daemon,
a socket is missing, or access is denied.

**Likely causes:** Docker Engine/Desktop is stopped, the selected Docker context
is wrong, or the current account lacks access to the configured daemon.

**Diagnose:**

```bash
docker version
docker context show
docker compose version
```

**Correct:** Start the intended local daemon/Desktop and select the intended
context through your Docker installation. Resolve account permissions through
the host's supported setup; do not make the Docker socket world-writable.

**Verify:** `docker version` reports both client and server, and `dc ps` can
query the development project. An empty service list means nothing is running,
not necessarily a daemon error.

### Compose validation fails or environment values are missing

**Symptom:** Compose reports a missing `.env`, a required `DB_*` variable, or
an invalid merged service definition; Django may separately raise a missing
setting error.

**Likely causes:** Wrong working directory, missing/incomplete local `.env`,
only the base Compose file selected, or a shell variable overriding the intended
interpolation value. Compose requires `DB_NAME`, `DB_USER`, and `DB_PASSWORD`;
Django also needs settings such as signing keys and Redis URLs.

**Diagnose:**

```bash
pwd
test -f .env
dc config -q
dc config --services
```

The base file has no application build/image definition; the development
override supplies the build. `--env-file .env` controls interpolation, while
service `env_file` entries populate application containers. Shell variables
can affect interpolation; inspect their presence privately without dumping values.

**Correct:** If `.env` is absent, create it using the guarded copy in
[Development](development.md#2-create-the-development-environment-file).
If it exists, compare required **variable names** with
[`docker/env/.env.development.example`](../docker/env/.env.development.example)
and repair only the relevant local values. Preserve unrelated settings and
initialized database credentials.

**Verify:** `dc config -q` exits successfully and `dc config --services` lists
all five services. This establishes configuration validity, not connectivity or
provider readiness.

### Backend exits, restarts, or cannot bind port 8000

**Symptom:** `web` is absent/exited/restarting, `exec` says the service is not
running, or Compose reports an address already in use.

**Likely causes:** Startup/import/configuration error, unhealthy dependencies,
an outdated image, or another host process using the Django publication port.

**Diagnose:**

```bash
dc ps -a
dc logs --tail=100 web db redis
```

On Linux, identify a listener without stopping it blindly:

```bash
ss -ltnp 'sport = :8000'
```

**Correct:** Fix the specific local setup problem shown by logs. `web` waits
for healthy `db` and `redis`. For a port conflict, stop the conflicting local
service only after identifying it, or choose an unused loopback port through
`DJANGO_HOST_PORT` in the private development `.env`. Align the Vite proxy
target with that port. Do not publish database/cache ports as a workaround.

After configuration/dependency changes, rebuild/recreate the relevant local
application services:

```bash
dc up -d --build web celery celery-beat
```

This can interrupt local requests/tasks; finish important work first. It does
not migrate the database or reset data. `restart` alone does not rebuild an
image or apply changed container environment settings.

**Verify:** `dc ps -a` shows stable processes, startup errors stop recurring,
and the loopback health requests below respond. A running process and a healthy
container are separate signals.

### Source edits appear stale

**Symptom:** Python changes are not reflected in requests or background jobs.

**Likely causes:** Wrong Compose override/checkout, a long-lived Celery process,
or dependencies baked into an older image.

**Diagnose:** Confirm the development files with `dc config --services` and
inspect `dc logs --tail=100 web celery celery-beat`. The development override
bind-mounts the source into `/app`; Django uses autoreloading `runserver`, while
worker/Beat processes do not automatically reload edited Python task code.

**Correct:** Restart local worker/scheduler processes after task changes:

```bash
dc restart celery celery-beat
```

Restarting interrupts task execution; retry/redelivery may occur. Rebuild with
the command above after dependency or Dockerfile changes. Source visibility
alone does not install a new dependency.

**Verify:** Exercise the changed request or supported task workflow and inspect
its outcome and bounded service logs, not only the presence of a running process.

## Django and PostgreSQL

### Host `manage.py` fails to resolve `db`

**Symptom:** A Host virtual environment running `python manage.py createsuperuser`
or `migrate` reports `failed to resolve host 'db'` (wording varies by driver).

**Cause:** `DB_HOST=db` is Docker-internal DNS. Activating a Host virtual
environment does not place Python on the Compose network. Inside a container,
`localhost` instead refers to that container.

**Diagnose:** Confirm whether the failing command ran on the Host or through
`dc exec web`; check `dc ps` for the running Django service.

**Correct:** For the normal development stack, run:

```bash
docker compose --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  exec web python manage.py createsuperuser
```

Use `dc exec web python manage.py ...` for other management commands. Changing
only `DB_HOST=localhost` does not make the private PostgreSQL container reachable:
the development stack publishes neither PostgreSQL nor Redis. Optional Host
execution requires independently reachable services, matching host/port and
database credentials, and all four Redis URL overrides. Follow the
[direct-host workflow](development.md#optional-direct-host-backend-execution).

**Verify:** The management command reaches the intended development database
inside `web`; use development-only administrator credentials.

### PostgreSQL connection is refused or authentication fails

**Symptom:** Django cannot connect, readiness reports `database: unavailable`,
or logs show password/database-role errors.

**Likely causes:** `db` is unhealthy/not started, Django has the wrong hostname
or port, or `.env` credentials no longer match the initialized PostgreSQL volume.
The image initializes credentials only when its data directory is first created.
Editing `DB_NAME`, `DB_USER`, or `DB_PASSWORD` later does not rewrite that volume.

**Diagnose:**

```bash
dc ps -a
dc logs --tail=100 db web
dc exec db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
dc exec web python manage.py shell -c 'from django.conf import settings; d=settings.DATABASES["default"]; print({k:d[k] for k in ("ENGINE", "HOST", "PORT")})'
```

The last command prints only database engine/host/port. Do not print
`settings.DATABASES`, passwords, full settings, or cache URLs. `pg_isready`
checks server availability; it does not prove that Django's credentials work.

**Correct:** Restore the intended Docker service host/port values. For an
initialized volume, use the known matching local credentials or arrange an
intentional database administration procedure with a backup. Do not delete the
volume to bypass an authentication failure. If `web` cannot start, use the
configuration/startup diagnostics first rather than expecting `exec` to work.

**Verify:** A loopback `/health/ready` request reports `database: ok`; that check
runs a real query using Django's configured connection.

### Missing tables, columns, or pending migrations

**Symptom:** Requests report missing schema objects, or Django warns of
unapplied migrations.

**Likely causes:** The correct database has not been migrated, the process uses
the wrong database/settings, or code/schema versions differ.

**Diagnose:**

```bash
dc exec web python manage.py showmigrations
dc exec web python manage.py migrate --plan
```

**Correct:** Confirm the target is the intended local development database and
review the plan. Back up valuable local data before applying schema changes.
Then apply the repository's existing migrations:

```bash
dc exec web python manage.py migrate
```

Do not generate unrelated migrations or fake application state just to hide a
missing table. Migration generation/drift is a separate issue below.

**Verify:** `showmigrations` marks the expected migrations applied, and the
previously failing request succeeds. Readiness alone does not check schema completeness.

## Health status and the development Host mismatch

**Symptom:** Django works through loopback, but Docker marks `web` unhealthy.

**Confirmed configuration mismatch:** The shared Compose health check calls
`/health/ready` with `Host: shop.exonplus.ir` and `X-Forwarded-Proto: https`.
The tracked development `.env` permits only `localhost,127.0.0.1` through
`ALLOWED_HOSTS`. Django may therefore reject that health request with HTTP 400.
Actual impact depends on the local settings; verify it rather than assuming a
PostgreSQL or Redis failure.

**Diagnose:** With the default published Django port (adjust if customized):

```bash
dc ps -a
curl -sS -i http://127.0.0.1:8000/health/live
curl -sS -i http://127.0.0.1:8000/health/ready
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Host: shop.exonplus.ir' -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8000/health/ready
dc logs --tail=100 web
```

Only retain the status of the disallowed-Host request; a Django debug error
page can expose internal details. Interpret the signals separately:

| Signal | Meaning |
| --- | --- |
| `/health/live` returns 200 | Django handles HTTP; no dependency query |
| `/health/startup` returns 200 | Django's app registry is initialized |
| `/health/ready` returns 200 with both fields `ok` | Database query and security-cache write work |
| `/health/ready` returns 503 | Inspect `database` and `security_cache` fields for the failing dependency |
| Local readiness 200, health-check Host request 400 | Consistent with Host validation mismatch; confirm logs |
| Container is running but unhealthy | Process is alive but Docker's health command fails |

These are GET endpoints without trailing slashes. Readiness does not verify
workers, migrations, or provider delivery. Compose does not automatically
restart an otherwise running container just because its health is unhealthy.

**Correct:** Treat a verified Host mismatch as a configuration defect requiring
a separately reviewed development health-check fix. Preserve Django Host
validation; do not use `ALLOWED_HOSTS=*` or disable checks. This guide does not
change Compose. Use loopback readiness and dependency diagnostics to identify
other failures while the mismatch remains unresolved.

**Verify:** For a later reviewed fix, the configured Docker health request must
succeed under the intended development Host policy and `dc ps` must become
healthy. Loopback HTTP success alone does not resolve Docker's health status.

## Redis, Celery, and OTP

### Redis errors or authentication operations return 503

**Symptom:** Security-sensitive requests fail, readiness reports
`security_cache: unavailable`, or workers cannot reach Redis.

**Likely causes:** Redis is unhealthy, the process uses Host addresses inside
Docker (or Docker names on the Host), URLs target the wrong service, or writes
are rejected because of a runtime capacity/storage problem.

**Diagnose:**

```bash
dc ps -a
dc logs --tail=100 redis web celery
dc exec redis redis-cli ping
dc exec web python manage.py shell -c 'from django.conf import settings; print({alias:cfg["BACKEND"] for alias,cfg in settings.CACHES.items()})'
```

`PONG` verifies that Redis answers inside its container; the application
readiness check also verifies a write through Django's security alias. Do not
dump Redis keys, values, or full cache settings to debug OTPs.

**Correct:** Restore the configured connectivity. Development uses Redis
service name `redis` with logical databases `/0` for ordinary cache, `/1` for
security, `/2` for broker, and `/3` for results. Ordinary catalogue caching may
fail open where designed; the security cache must fail closed, so catalogue
success is not evidence that authentication infrastructure works. Do not catch
security-cache errors to let requests through or clear throttle/OTP state to
force success.

**Verify:** Redis responds, loopback readiness reports `security_cache: ok`, and
a legitimate supported request succeeds subject to its normal limits.

### Worker or Beat is not processing expected work

**Symptom:** A supported asynchronous operation remains pending or periodic
recovery does not occur.

**Likely causes:** Worker/Beat stopped, stale task code, wrong broker URL,
worker import errors, or no eligible durable work. SMS/provider-dependent work
may deliberately be unavailable.

**Diagnose:**

```bash
dc ps -a
dc logs --tail=100 celery celery-beat redis
dc exec celery celery -A config inspect ping --timeout=5
```

Ping confirms a worker responds to control messages; it does not prove a task
completed. Avoid dumping active/reserved task arguments because they can contain
sensitive OTP delivery data. Beat schedules work; workers execute it. Only one
Beat process should run for this project.

**Correct:** Resolve broker/import/configuration errors first. For edited task
code, use the worker/Beat restart procedure above. After dependency changes,
rebuild the relevant application images. For delayed domain work, inspect the
supported owner/Admin state and relevant service logs; do not manually enqueue
arbitrary tasks or change statuses to bypass the workflow.

**Verify:** The expected durable state transition occurs once and logs show
normal processing. Eager unit-test success does not prove a running worker or
Beat is healthy.

### OTP setup/recovery is unavailable even though Django runs

**Symptom:** OTP-dependent API calls return 503, initial Set Password is
unavailable, or `/forgot-password` displays an unavailable message.

**Confirmed defaults and possible cause:** The development template sets
`SMS_ENABLED=False`; no real SMS provider adapter is registered in this
repository. The Users capability check also requires a registered, configured
provider. A separate security-cache outage can also cause 503.

**Diagnose:**

```bash
curl -sS http://127.0.0.1:8000/api/v1/users/auth-capabilities/
curl -sS http://127.0.0.1:8000/health/ready
dc logs --tail=100 web celery
```

**Correct:** Under the default configuration, use supported username/password
login/signup and authenticated password change. Initial setup and recovery
require SMS; SMS sign-in/signup remain disabled in the frontend regardless of
capability. A real reviewed provider integration is separate work: enabling the
flag alone is not delivery. Test adapters belong only in isolated tests.
Do not bypass OTP, throttles, or capability checks.

**Verify:** Without a provider, `sms_available=false` and the unavailable UI are
expected. With a future configured adapter, capability alone still does not
prove handset delivery; verify the supported provider workflow separately.
See [Authentication](authentication.md) and the [frontend guide](../frontend/README.md).

## Backend test failures

### Missing packages, wrong interpreter, or wrong settings

**Symptom:** `No module named pytest`, unknown pytest options, Django import
errors, or tests unexpectedly request development infrastructure.

**Likely causes:** Wrong virtual environment, only runtime dependencies
installed, missing pytest plugins, or an explicit settings/environment override.

**Diagnose:**

```bash
python -c 'import sys; print(sys.executable); print(sys.version)'
python -m pip --version
python -m pytest --version
```

Check the pytest session's settings header without publishing environment dumps.
The default settings are `config.settings.test`, with SQLite and LocMem;
integration requires explicit settings and a marker selection.

**Correct:** Activate the intended Python 3.12 environment and install
`requirements/requirements-test.txt` with that interpreter. Review local
`DJANGO_SETTINGS_MODULE` and pytest command overrides privately. Do not change
the test environment to point at production or copy production secrets.

**Verify:** Re-run the smallest failed module/node ID with the correct settings,
then run the relevant full sequence in [Testing](testing.md).

### Integration tests are missing, use SQLite, or cannot connect

**Symptom:** No integration tests run, SQLite produces locking errors, Redis
connections fail, or integration Compose cannot bind `55432` / `56379`.

**Likely causes:** Default pytest excludes integration tests; changing only the
settings does not select them. The integration settings must replace SQLite
and LocMem. Services may also be stopped or their fixed loopback ports occupied.

**Diagnose:**

```bash
docker compose -f docker/docker-compose.integration.yml ps -a
docker compose -f docker/docker-compose.integration.yml logs --tail=100 integration-db integration-redis
```

On Linux:

```bash
ss -ltnp '( sport = :55432 or sport = :56379 )'
```

**Correct:** Identify any conflicting service before stopping it. Start the
isolated integration services and run the exact explicit integration command
in [Testing](testing.md#postgresql-and-redis-integration-suite). If using other
dedicated test services, set `INTEGRATION_DB_*` and both `INTEGRATION_*_REDIS_URL`
values accordingly; overrides do not change the tracked Compose port mappings.
The database role must be able to create a Django test database. Tests clear
both configured Redis databases: never reuse valuable cache/security state.

**Verify:** The pytest header identifies `config.settings.integration`, marked
tests execute, and service failures disappear. SQLite success cannot establish
PostgreSQL row-lock behavior, and LocMem success cannot establish Redis atomicity.

### Coverage, warning, assertion, or migration checks fail

**Symptom:** Assertions pass but coverage is below 85%; CI fails on a warning;
or `makemigrations --check --dry-run` reports missing migrations.

**Likely causes:** A focused run still measures the entire configured source,
a meaningful branch lacks coverage, a dependency/application warning is newly
exposed, or models and migration state differ.

**Diagnose:** Use the first failing test ID and coverage's missing-line report.
For example, this diagnostic run omits coverage to isolate assertions:

```bash
python -m pytest apps/users/tests/test_password_management.py --no-cov -x -q
python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

For a focused integration failure, append its module/node ID to the explicit
integration invocation; retain its settings, marker, and `addopts` replacement.

**Correct:** Inspect the implementation and intended contract before changing
assertions. Add regression coverage for verified defects; investigate warnings
rather than disabling them. For actual schema changes, review migration history
and create only the necessary migration in the implementation change. Do not
lower coverage, suppress all warnings, fake migrations, or weaken constraints.
A failing diagnostic run and a failed coverage gate are different findings.

**Verify:** Return to the full warnings-as-errors suite and all applicable
checks. A focused `--no-cov` pass is not a passing coverage result. Run PostgreSQL
integration checks for behavior SQLite cannot represent.

## Frontend and Vite

### Unsupported Node or failed dependency installation

**Symptom:** npm reports an unsupported engine, `npm ci` fails, or tooling fails
to start under an old Node runtime.

**Likely causes:** Node outside `>=24.15.0 <25`, wrong directory, package/lockfile
mismatch, or registry/connectivity problems.

**Diagnose:** From `frontend/`:

```bash
node --version
npm --version
```

**Correct:** Use `nvm install` and `nvm use` to select `.nvmrc` (24.19.0), then
`npm ci`. Inspect the first installation error; resolve connectivity separately
from a manifest/lockfile mismatch. Do not regenerate the lockfile or bypass
engine checks just to hide the failure.

**Verify:** Installation succeeds with the committed lockfile, then frontend
lint/tests run under the supported Node version.

### Vite changes ports or API/media requests fail

**Symptom:** Port 5173 is unavailable, proxy errors appear, or the storefront
loads but cookie-backed authentication fails.

**Likely causes:** Vite selected another port, Django is stopped, the backend
port differs from the fixed proxy target, a local API-base override skips the
proxy, or the browser Origin is not allowed.

**Diagnose:** Inspect the Vite terminal's actual URL and browser Network status
without copying cookies or bearer headers. Check backend state and readiness
from the repository root:

```bash
dc ps
curl -sS -i http://127.0.0.1:8000/health/ready
```

**Correct:** `vite.config.js` binds `127.0.0.1`, requests 5173, and proxies
`/api` and `/media` to `http://localhost:8000`. Align that target with
`DJANGO_HOST_PORT` if customized. Local proxy-based development needs no
`VITE_API_BASE_URL`; inspect any local override privately. For cookie-backed
authentication, align `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` with the
actual Vite origin; the template allows only `localhost:5173` and
`127.0.0.1:5173`. `ALLOWED_HOSTS` contains hostnames, not URL origins.
Apply changed backend container environment through recreation, not only restart.

**Verify:** Browser requests reach the intended Django instance, expected API
responses return, and session restoration/login work under the exact configured
Origin. Do not broaden allowlists to wildcards.

### Frontend lint, tests, or production build fail

**Symptom:** ESLint reports warnings/errors, Vitest fails, or Vite says
`VITE_API_BASE_URL` is required/invalid.

**Likely causes:** Source/test regression, stale fixture contracts, unsupported
Node, or missing/invalid build-time API origin.

**Diagnose:** From `frontend/`, run the failing stage separately:

```bash
npm run lint
npm test -- src/components/PasswordManagement.test.jsx
VITE_API_BASE_URL=https://shop.exonplus.ir npm run build
```

**Correct:** Inspect the first lint error or failing assertion against the
current API/UI contract. Vitest uses jsdom and mocked API responses; a fixture
failure does not itself establish a live-backend defect. Vite builds require
HTTPS and a root pathname; supply an origin without `/api/v1` or another path.
All `VITE_*` values are public; never insert secrets. The release validator also
expects `https://shop.exonplus.ir`, even if another HTTPS origin compiles.

**Verify:** Run the full frontend lint/test/build sequence in
[Testing](testing.md#frontend-verification), rather than relying on the focused
Vitest run. Do not commit generated `dist/` output.

## GitHub Actions and release diagnosis

**Symptom:** A pull request/push has failing checks, images are not published,
or manual deployment/release validation fails.

**Likely causes:** Identify the failing job and first failed step before
classifying it. CI test/build success, image publication, and manual production
deployment are distinct stages.

**Diagnose:** Open the commit's Actions run on GitHub. With an authenticated
GitHub CLI, these are read-only entry points (replace `RUN_ID` with the run ID):

```bash
gh run list --repo Pursite/luxury-perfume --limit 10
gh run view RUN_ID --repo Pursite/luxury-perfume
gh run view RUN_ID --repo Pursite/luxury-perfume --log-failed
```

Keep failure logs private until checked for sensitive content.

| Job/stage | Start investigation with |
| --- | --- |
| SQLite and LocMem | First pytest, coverage, warning, Ruff/Bandit, system-check, or migration failure |
| PostgreSQL and Redis | Service health, integration settings/ports, and the failing transaction/cache test |
| React storefront | npm install, ESLint, Vitest, Vite build, stamp/validation, or carrier build step |
| Application image | Production Compose validation, Docker build, or final-image translation smoke check |
| Release gate | Upstream failed/skipped jobs; it depends on all four above |
| Publish application/frontend image | Gate result and publication step; these jobs run only for pushes to `main` |
| Deploy to VPS | Manual workflow configuration, selected published SHA/digests, dependency/readiness checks, or frontend release validation |

**Correct:** Reproduce the failing non-destructive local check using
[Testing](testing.md). For release validation, inspect the error from
[`scripts/frontend-release.sh`](../scripts/frontend-release.sh): it requires
`index.html`, nonempty `assets`, the expected production origin and manifest,
and matching SHA/digest markers where applicable; it rejects unexpected entries
and symlinks. Do not hand-edit a release manifest or live files to bypass these
checks. A missing image for a feature branch can be expected because only
`main` publishes images.

Production corrective actions require the separate [Deployment](deployment.md)
runbook and operator review. CI does not automatically deploy; a green run
establishes neither backups nor host monitoring. [CI/CD](ci-cd.md) is currently
an empty placeholder for the next documentation phase; the workflow files remain
the source of truth until that guide is written.

**Verify:** The original failed stage passes for the intended commit, then its
required downstream checks pass. Do not treat a rerun or a manual deployment as
a substitute for fixing the verified cause.
