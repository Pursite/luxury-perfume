# CI/CD pipeline

## Source verification, publication, and deployment

The repository separates verification, image publication, and production delivery.
[`Test suite`](../.github/workflows/ci.yml) runs on `push` and `pull_request`.
Only a push to `refs/heads/main` can publish images after the complete release
gate. [`Deploy production`](../.github/workflows/cd.yml) is a separate manual
`workflow_dispatch` workflow; CI never automatically deploys to the VPS.

```text
Push / pull request
  ├─ React storefront ─────────────────────────┐
  ├─ SQLite and LocMem ───┐                    │
  └─ PostgreSQL and Redis ┴─ Application image ─┴─ Release gate
                                                   │
                                      push to main only
                                         ├─ Publish application image
                                         └─ Publish frontend image
                                                   │
                                  operator selects published revision
                                                   │
                                 manual Deploy production workflow
```

A feature or documentation branch can pass the complete gate without publishing
anything. Pull-request builds use that event's `github.sha`; do not assume their
artifacts are a published `main` release. A successful build or publication does
not establish that the host was prepared or that a deployment succeeded.

This guide owns pipeline behavior. [Testing](testing.md) owns reproducible test
commands; [Deployment](deployment.md) owns host preparation, operations, and
recovery. Workflow files and scripts remain the implementation authority.

## CI jobs and dependencies

All jobs use Ubuntu runners. Actions are pinned to full action commit SHAs.
The workflow defaults to `contents: read`; registry-writing permissions are
limited to the publication jobs.

| Job name (YAML ID) | Dependencies | Work and success boundary |
| --- | --- | --- |
| React storefront (`frontend`) | None | npm install/lint/tests/build, release stamping/validation, frontend carrier build/export/upload |
| SQLite and LocMem (`default-tests`) | None | Default backend suite, coverage, lint/security patterns, Django checks and migration drift |
| PostgreSQL and Redis (`integration-tests`) | None | Real-service integration tests, Django checks and migration drift |
| Application image (`image`) | Both backend jobs | Production Compose validation, final Python image build/export, translation smoke check, artifact upload |
| Release gate (`release-gate`) | All four jobs above | Requires all upstream jobs to succeed; its step only confirms gate completion |
| Publish application image (`publish`) | Release gate; main push condition | Promotes the saved backend image to GHCR |
| Publish frontend image (`publish-frontend`) | Release gate; main push condition | Promotes the saved frontend carrier to GHCR |

Normal Actions dependency/step success rules apply: a failed required job skips
its downstream jobs; a failed step prevents later ordinary steps in that job.
Publication is also intentionally skipped for branch pushes and pull requests.
The release gate has `permissions: {}` and no additional deployment validation.

### Frontend verification

Node is read from [`frontend/.nvmrc`](../frontend/.nvmrc), currently `24.19.0`;
[`package.json`](../frontend/package.json) supports `>=24.15.0 <25`. In
`frontend/`, CI runs `npm ci`, `npm run lint`, `npm test`, then `npm run build`
with `VITE_API_BASE_URL=https://shop.exonplus.ir`.

Lint is ESLint with zero warnings allowed; tests are Vitest. Vite requires an
explicit HTTPS origin with a root pathname for builds. Release validation
additionally requires this repository's exact production API origin. These are
browser-visible build values, not runtime secrets. See [Frontend](../frontend/README.md).

### Backend verification

Both backend jobs install `requirements/requirements-test.txt` on Python 3.12.
The SQLite/LocMem job runs:

- `python -W error -m pytest`: ordinary addopts exclude `integration`, enforce
  strict configuration/markers and branch coverage over `apps`/`config`, and
  require at least 85% coverage through `.coveragerc`.
- `python -m ruff check apps config tests`.
- `python -m bandit -q -r apps config -x 'apps/**/tests/**,config/tests/**'`.
- Django system checks and `makemigrations --check --dry-run` with
  `config.settings.test`.

The integration job provides PostgreSQL 16 and Redis 7 service containers on
runner ports 5432/6379, with health probes. Its disposable database uses `trust`
authentication; this is not a production policy. Environment overrides select
`config.settings.integration`, loopback PostgreSQL, and Redis logical databases
14/15 for ordinary/security caches. It runs:

```bash
python -m pytest -o addopts="--strict-config --strict-markers" \
  -m integration --ds=config.settings.integration -q
```

Overriding addopts removes the normal `not integration` selector and coverage
gate. This command also does not add the default job's `-W error` option. The
job then runs system and migration-drift checks against integration settings.
Real services exercise locks, transactions, and Redis operations SQLite/LocMem
cannot establish. These are controlled integrations, not live SMS/Payment tests.
See [Testing](testing.md) for isolation, fixtures, exclusions, and limitations.

### Application image validation

After both backend jobs pass, CI copies the tracked production template to the
ephemeral runner's `.env`, supplies a non-secret validation `APP_IMAGE`, and
validates shared Compose followed by the production override with `config -q`.
It does not start that production stack.

Buildx builds the `final` target of [`docker/Dockerfile`](../docker/Dockerfile),
with GitHub Actions build caching, `push: false`, and Docker archive output.
CI loads that archive and starts an ephemeral test-settings container to assert
a known Persian translation from the committed binary catalogue. This verifies
that catalogue in the final image; it is not a live PostgreSQL/Redis readiness
or full production-startup test. Runtime gettext compilation is not required.

## Build products and transfer artifacts

### Python application image

The multi-stage Dockerfile installs pinned runtime requirements in a Python
3.12 builder and copies them into a Python 3.12 slim runtime with `libpq5`.
The final image contains the backend and committed translation catalogue and
runs as UID/GID `10001`. Its default command is Gunicorn; production Compose
uses the same image for `web`, `celery`, and `celery-beat` with separate commands.
The production host does not rebuild it.

`.dockerignore` excludes private environment files, local environments/caches,
runtime assets, frontend sources, documentation, and Git metadata. Build labels
set `org.opencontainers.image.source` to the repository URL and
`org.opencontainers.image.revision` to `github.sha`.

| Product | Local image tag | Actions artifact | Archive |
| --- | --- | --- | --- |
| Backend | `luxury-perfume:application` | `luxury-perfume-image-<commit-sha>` | `/tmp/luxury-perfume-application.tar` |
| Frontend | `luxury-perfume-frontend:application` | `luxury-perfume-frontend-image-<commit-sha>` | `/tmp/luxury-perfume-frontend-application.tar` |

Both uploads require the file to exist and set one-day retention. They transfer
the already-built images between CI jobs; they are not the production rollback
store and are not a backup of application data.

### Static frontend carrier

After the Vite build, CI runs:

```bash
bash scripts/frontend-release.sh stamp frontend/dist "$COMMIT_SHA"
```

The workflow sets `COMMIT_SHA` to `github.sha`. The script validates a lowercase
40-character SHA, `index.html`, a nonempty `assets/`, regular files/directories,
no symlinks, and only expected top-level entries. It requires the production
origin to occur in compiled assets and writes `.release-manifest.json` binding
schema version 1, the commit SHA, and `api_base_url`. These checks validate the
expected structure/origin, not every application's browser behavior or every
byte through an independent signature.

[`docker/Dockerfile.frontend`](../docker/Dockerfile.frontend) is `FROM scratch`
and copies only stamped `dist/` into `/frontend/`, with source/revision labels
assigned by CI. It has no Node runtime or web server and is never started as a
frontend service. CD creates a stopped carrier, copies the files, and removes
that container. Host-managed Nginx ultimately serves the static release.

## GHCR publication and release identity

Both publication jobs require the successful gate and this condition:

```text
github.event_name == 'push' && github.ref == 'refs/heads/main'
```

They have `packages: write` and authenticate to GHCR using the run's
`GITHUB_TOKEN`. Each has its own per-SHA concurrency group with
`cancel-in-progress: false`. They inspect the target tag and fail if it already
exists rather than deliberately overwriting it. Each downloads/loads the saved
archive, retags it, and pushes without rebuilding.

| Package | Published tag |
| --- | --- |
| `ghcr.io/pursite/luxury-perfume` | Full `github.sha` |
| `ghcr.io/pursite/luxury-perfume-frontend` | The same full `github.sha` |

The frontend publisher checks the loaded image's OCI revision label against
`GITHUB_SHA`. The backend build assigns its revision label; that publisher does
not perform a separate loaded-label assertion. CD checks **both** labels before
deployment. No Git release tag, `latest` tag, or package retention rule is created
by these workflows.

| Identifier | Meaning |
| --- | --- |
| Commit SHA | Git source revision; labels/manifests bind artifacts to this value |
| Git tag | A Git reference; not the image selector used here |
| Image tag | Registry name such as `:<commit-sha>`; a reference, not a cryptographic content identity |
| Image digest | Content-addressed registry reference such as `@sha256:…`; used for actual deployment |

SHA-tag overwrite refusal is workflow policy, not a registry-wide immutability
guarantee. CD pulls both SHA tags, resolves their repository digests, validates
the expected package/digest format and revision labels, then uses those digests.
A revision label alone is a claim attached by a publisher, not an independent
provenance attestation. Registry access remains a trust boundary. No image
signing, SBOM/provenance publication, or vulnerability-scanning stage is defined
in these workflows.

## Manual production delivery

### Selection and control plane

`Deploy production` accepts optional `commit_sha`; empty input uses that run's
`github.sha`. The selected value must be 40 lowercase hexadecimal characters.
The job uses the `production` GitHub environment, a 30-minute timeout, and
`production-deploy` concurrency with cancellation disabled.

Configure environment reviewers and deployment-branch restrictions in GitHub
before use. YAML references the environment; it does not prove those protections
or repository branch protections are enabled. Operators should select an
already-published, reviewed revision whose CI/release checks they verified.

**CI gates image publication. CD does not independently query the selected
commit's successful GitHub Actions CI conclusion.** CD validates source ancestry,
matching published images/revisions, and runtime conditions. Neither ancestry
nor a label substitutes for review of the actual CI run.

### Secrets and trust boundaries

The workflow references these `production` environment secrets:

| Secret | Purpose |
| --- | --- |
| `VPS_HOST` | SSH destination |
| `VPS_PORT` | SSH port; defaults to 22, validated in range 1–65535 |
| `VPS_USER` | Deployment account owning the checkout and permitted to operate this Compose stack |
| `VPS_SSH_PRIVATE_KEY` | Runner-to-host authentication for that account |
| `VPS_KNOWN_HOSTS` | Pre-verified SSH host-key entries; verify fingerprints through a trusted channel |
| `GHCR_READ_TOKEN` | Package-read credential for both GHCR packages under the repository-owner registry username |

SSH uses batch mode, the explicit identity, and strict known-host verification.
It does not discover/trust keys with `ssh-keyscan`. Temporary runner key material
has restrictive permissions and an `always()` cleanup step. Use a dedicated
restricted account; membership in a general Docker-access group is itself
powerful host access and is not an isolation boundary supplied by this YAML.
The host separately needs read access to `origin` for Git fetches.

`GITHUB_TOKEN` writes packages in CI. `GHCR_READ_TOKEN` reads packages in CD;
a suitable classic PAT has `read:packages` and account access to both packages.
Actual token/package authorization must be verified by the operator. VPS `.env`
contains application secrets and is provisioned separately; CD does not upload
it. Public Vite values and release manifests contain no credentials.

CD sends the GHCR token through SSH stdin, not a command-line argument. On the
host it uses `docker login --password-stdin` with a temporary `DOCKER_CONFIG`,
pulls both images, then unsets the token and removes registry state before
Compose work. An EXIT trap covers earlier ordinary failures. Do not persist
registry credentials in `.env` or the host's default Docker config; forced host
termination is outside shell cleanup guarantees.

### Ordered deployment stages

Within `/srv/luxury-perfume`, the remote script performs this sequence:

1. Require an existing Git checkout and `.env`. Acquire nonblocking
   `.git/deploy.lock` with `flock`; reject tracked/untracked source changes.
   Ignored runtime state is excluded from that cleanliness check.
2. Fetch `origin/main` (unshallow if necessary) and the selected SHA, require an
   exact commit match, and verify it is an ancestor of `origin/main`.
3. Authenticate temporarily, pull both matching published tags, resolve package
   digests, and compare both OCI revision labels with the selected SHA. Remove
   registry credentials and export digest-pinned backend `APP_IMAGE`.
4. Detach the source checkout at that SHA. Run `frontend-release.sh prepare`
   with the frontend digest: extract/validate a staged release, add/check its
   digest marker, and place it under `frontend-releases/<sha>/`. Reuse requires
   matching manifest/digest. No live frontend switch occurs yet.
5. Validate shared + production Compose. Start `db`/`redis` with `--no-build
   --no-recreate`; poll `pg_isready` and Redis PING up to 12 attempts, sleeping
   five seconds after unsuccessful attempts.
6. Run one-off `web` containers, without starting dependencies, for
   `check --deploy --settings=config.settings.production`, `migrate --noinput`,
   then `collectstatic --noinput`.
7. Force-recreate only `web` without building or dependencies. Poll loopback
   `/health/ready` with production Host and forwarded HTTPS headers, up to 12
   attempts with five-second pauses and five-second curl timeouts.
8. Force-recreate `celery` and `celery-beat`. For each, check the same container
   ID is running, not restarting, and has zero restarts for five samples with
   two-second gaps (eight seconds per service). This checks process stability,
   not task execution or scheduler correctness.
9. Run `frontend-release.sh activate` to revalidate the selected release and
   atomically rename the `frontend-current` symlink to it.

Full commands, filesystem permissions, health diagnostics, and recovery belong
in [Deployment](deployment.md). The workflow does not build on the VPS, install
host packages, manage Nginx/certificates, reset databases, or prune volumes.
It does mutate schema/data through migrations, static files through collection,
source checkout, application containers, and finally the frontend pointer.

## Failure boundaries and operational limits

Publication jobs are independent: one package may publish while the other fails.
A missing image prevents CD before source checkout/runtime deployment. Re-running
a publication that already succeeded can hit the existing-tag refusal; inspect
the failed stage and available artifacts rather than assuming a whole-workflow
rerun can overwrite the release. One-day transfer artifacts may have expired.

A deployment failure leaves whatever earlier stages completed. Before frontend
activation, the old symlink remains active, but migrations/static collection or
container recreation may already have changed the backend. No automatic rollback
trap restores containers, static files, source, or database. Atomic frontend
activation is not an atomic deployment across all stores/services.

An older published SHA can be selected explicitly only after assessing current
schema/data compatibility. Automated migrations remain forward-only; there is
no automatic database restore or reverse-migration procedure. External Payment,
Refund, and SMS obligations do not disappear on a code rollback.

A green gate does not prove backup/restore readiness, production availability,
security completeness, or provider operation. Host monitoring/alerting, external
log aggregation, automated backups and verified restore procedures are outside
the repository. Real Payment/SMS adapters are unregistered and disabled by
default. Use [Deployment](deployment.md#rollback-and-recovery) and
[Troubleshooting](troubleshooting.md#github-actions-and-release-diagnosis) for diagnosis
and operator-reviewed recovery; do not bypass checks to obtain a green release.
