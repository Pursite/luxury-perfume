# Contributing

## Guiding principles

Contributions should make the project easier to trust and maintain. Prioritize
correctness and data integrity, security, reliability, API compatibility, and
maintainability. Optimize performance from real query patterns or measurements,
and prefer the smallest complete solution over speculative complexity.

Before changing behavior, inspect the implementation, affected callers, tests,
and documented contracts. Keep unrelated fixes and refactors separate. The
[architecture guide](docs/architecture.md) explains the design; [AGENTS.md](AGENTS.md)
contains detailed engineering instructions for coding agents and is a useful
reference for repository conventions.

## Getting started

1. Fork the repository if you do not have write access, then clone your fork.
   Contributors with access can clone `Pursite/luxury-perfume` directly. Start
   new work from an up-to-date `main` revision, or an explicitly agreed base for
   related work. Inspect and preserve local changes before updating a checkout.
2. Use a focused working branch and descriptive commits. These are recommended
   practices, not a prescribed branch-name or commit-message format.
3. Follow [Development](docs/development.md) for the supported Docker Engine/
   Docker Compose backend setup. The backend image and CI use Python 3.12; the
   supported Compose services use PostgreSQL 16 and Redis 7. A host Python 3.12
   virtual environment is useful for the backend verification commands below.
4. Create the ignored root `.env` from
   [`docker/env/.env.development.example`](docker/env/.env.development.example)
   only if it does not already exist. Preserve existing settings. Validate/start
   the shared Compose file followed by the development override as the guide
   describes; services include `web`, `db`, `redis`, `celery`, and `celery-beat`.
5. For frontend work, use Node 24 LTS from
   [`frontend/.nvmrc`](frontend/.nvmrc), currently 24.19.0; the package supports
   `>=24.15.0 <25`. Follow the [frontend guide](frontend/README.md) to install
   dependencies and start Vite separately on the host with `npm run dev`.

Docker is the recommended backend development path. Inside its network, `db`
and `redis` resolve to private services; they are not host DNS names. Run
application management commands inside `web` using Compose `exec`. Optional
host Django/Celery execution requires independently reachable PostgreSQL/Redis
and matching host, port, and credential settings. Changing `DB_HOST` to
`localhost` alone does not expose the private Compose database.

## Choose a focused change

| Change | What to establish |
| --- | --- |
| Bug fix | Reproduce or otherwise verify the root cause, add regression coverage, and preserve unrelated behavior |
| Backend feature | Define input/output, permissions, ownership, invariants, failure behavior, and the owning domain; test those boundaries |
| API change | Identify the deliberate contract change and compatibility impact; update contract tests and owning documentation |
| Frontend change | Follow the existing API client, session/Cart ownership, accessibility, and [design specification](frontend/DESIGN.md); test observable behavior |
| Model/schema change | Inspect migration history, constraints, existing data, locking, and compatibility before generating the necessary migration |
| Security-sensitive change | Review the controls and failure paths below; avoid public disclosure of vulnerability details |
| Documentation-only change | Verify claims against current implementation; check commands, links, paths, and the exact diff |
| Dependency/infrastructure change | Explain the need, affected runtime/build behavior, reproducibility, configuration, and deployment/recovery implications; keep manifests and lockfiles consistent where applicable |

An issue can help discuss a broad design change, but a PR does not require a
pre-existing issue. Explain the intended behavior and trade-offs early when a
change affects multiple domains or public contracts.

## Architecture and implementation practices

```text
Request → View → Serializer → Service (write) / Selector (read) → Model / PostgreSQL
```

| Layer | Responsibility |
| --- | --- |
| Views | HTTP methods, authentication/permissions/throttles, input/output coordination, and status mapping |
| Serializers | Input validation/normalization and explicit response representations |
| Services | Meaningful state changes and their transaction/lifecycle boundaries |
| Selectors | Reusable, visibility/owner-scoped reads with deliberate related-object loading |
| Models/PostgreSQL | Persistent structure, validation, constraints, and relationship protection |
| Celery | Suitable expensive or non-request-critical work, with retry/redelivery and commit-ordering considerations |

Respect domain ownership: Users handles identity/credentials; Products handles
the catalogue/images; Cart stores purchase intent; Orders owns checkout, stock
reservations, and fulfillment; Payments owns verification/Refund obligations;
Notifications owns delivery obligations. Avoid moving one domain's authority
into another or putting business workflows into views.

React pages/components own presentation and local form state. Auth Context and
Cart Context coordinate their shared client state; Django owns authorization,
prices, stock, and durable owner-bound data. A protected React route is not a
backend permission check. Use the existing client and design conventions rather
than inventing a second session or authoritative browser Cart model.

Review ORM changes for N+1 queries, repeated serializer queries, unnecessary
round trips, and unbounded results. Add indexes/caches for verified access
patterns. Use configured Ruff and ESLint checks; follow nearby code conventions.
See [Architecture](docs/architecture.md) and [Frontend](frontend/README.md).

## Data integrity and security

### Contended writes and asynchronous work

Changes to identity, OTP, Cart, stock, Orders, Payments, or other contested writes
need explicit reasoning about ownership, `transaction.atomic()`, row locking,
lock order, database constraints, race conditions, rollback, idempotency, and
retry behavior. Serializer validation alone cannot replace a database guarantee
under concurrency. Keep monetary values and historical snapshots server-owned.

Use real PostgreSQL/Redis integration tests for behavior SQLite/LocMem cannot
represent. Check durable outcomes, not merely that a lock method was called.
Keep fixtures deterministic and isolated. For Celery work, review duplicate
delivery, simple serializable task inputs, and `transaction.on_commit()` when
execution depends on committed data. Database commit and broker/provider I/O
are separate failure boundaries. See [Architecture](docs/architecture.md) and
[Testing](docs/testing.md).

### Security review and secrets

Do not commit populated `.env` files, credentials, signing keys, tokens, or private
user/production data. Tracked environment templates contain examples only;
ignored files still require care when staging. Never log passwords, OTPs, JWTs,
secrets, or sensitive provider payloads, or include them in PR text/screenshots.
Browser-visible `VITE_*` values must contain no secrets.

Review affected authentication/authorization, owner-scoped queries, cookie/
Origin/CORS/CSRF boundaries, uploads, Redis security-cache failure policy,
concurrency, external provider behavior, logs, and error exposure. Ordinary
catalogue cache failures and security-cache failures have different policies.
Do not weaken permissions, validation, throttles, or fail-closed protection to
make tests pass. Payment and SMS test doubles do not establish live integration;
real provider adapters are not currently registered.

For suspected vulnerabilities, do not publish exploit details, credentials, or
sensitive evidence in a public issue or PR. Use a private contact explicitly
published by the repository maintainer if available. No dedicated private
reporting address/channel is documented in this repository; if none is available,
ask for private reporting instructions without disclosing the vulnerability.
Do not assume a GitHub private advisory workflow is enabled. See
[Security](docs/security.md) for implemented controls and limitations.

## Testing and verification

Choose checks according to the affected behavior and report what actually ran.
The full commands, isolated integration services, fixtures, coverage rules, and
failure diagnosis belong in [Testing](docs/testing.md) and
[Troubleshooting](docs/troubleshooting.md).

| Change type | Verification to include where applicable |
| --- | --- |
| Backend behavior | Focused regressions, full default suite, Ruff/Bandit, and Django checks |
| PostgreSQL/Redis semantics | Relevant real-service integration tests for transactions, constraints, concurrency, cache atomicity, and failure/retry paths |
| Frontend behavior | ESLint, Vitest, production Vite build, and relevant manual browser/accessibility evidence |
| Models/schema | Reviewed migration, drift checks, schema/constraint tests, real-service tests, and compatibility assessment |
| Dependencies/infrastructure | Relevant suites plus affected build/configuration/release validation; disclose checks needing unavailable external infrastructure |
| Documentation only | Implementation-backed claims, valid links/paths, configuration-matched commands, and `git diff --check`; application tests need not run solely for prose |

### Backend commands

Run from the repository root in the intended Python 3.12 virtual environment.
Install the test dependency layer, which includes runtime requirements:

```bash
python -m pip install --requirement requirements/requirements-test.txt
```

For example, isolate Cart API tests during development:

```bash
python -W error -m pytest apps/cart/tests/test_api.py --no-cov -q
```

`--no-cov` is useful for focused diagnosis; it does not satisfy the full coverage
gate. For backend behavior changes, complete the applicable CI-equivalent checks:

```bash
python -W error -m pytest
python -m ruff check apps config tests
python -m bandit -q -r apps config -x 'apps/**/tests/**,config/tests/**'
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

The default suite uses SQLite/LocMem, excludes `integration`, and enforces 85%
branch coverage. `-W error` makes warnings fail as in CI. Test settings are
self-contained; this is different from running ordinary development management
commands against `DB_HOST=db` on the host. The real PostgreSQL/Redis integration
suite uses separate settings/services and overrides ordinary pytest addopts;
follow [its setup and commands](docs/testing.md#postgresql-and-redis-integration-suite).
Never point tests at production or shared databases/caches: fixtures clear state.

### Frontend commands

From the repository root, using the Node version in `frontend/.nvmrc`:

```bash
cd frontend
npm ci
npm run lint
npm test
VITE_API_BASE_URL=https://shop.exonplus.ir npm run build
```

`npm ci` installs the committed lockfile; reinstall when needed rather than
regenerating it during an unrelated edit. The API origin is public build-time
configuration. A successful static check/build is not proof of vulnerability
freedom, live provider behavior, or production readiness.

In the PR, record exact commands and outcomes. Mark checks as **not run** with
the reason (for example, missing local integration services), **not applicable**
with the scope rationale, or **failed** with the unresolved failure. Do not mark
a check passed based on an earlier revision or silently hide/skip a failure.

## API, migrations, documentation, and delivery

Preserve existing URLs/methods, authentication/permissions, schemas, status codes,
error semantics, pagination, filtering/ordering, visibility, and ownership rules.
For an intentional contract change, explain the compatibility impact and update
tests and relevant [API](docs/api.md)/[Authentication](docs/authentication.md)
documentation. English/Persian human messages may be localized; JSON keys, enum/
status values, codes, URLs, and other machine contracts remain stable through
translation.

Treat migrations as production operations. Inspect current history and existing
data, generate a migration only for an intentional schema change, and review
constraints, indexes, locks, forward/rollback behavior, and old/new code
compatibility. Drift checks do not prove a migration is safe for an existing
production database. Include appropriate schema/integration tests. Automated CD
does not reverse migrations or restore data.

Update only documentation affected by the change, using the owning guide:
[Development](docs/development.md), [Testing](docs/testing.md),
[Architecture](docs/architecture.md), [Security](docs/security.md),
[API](docs/api.md), [Authentication](docs/authentication.md),
[CI/CD](docs/ci-cd.md), [Deployment](docs/deployment.md), or
[Frontend](frontend/README.md). Keep explanations with their owner and link to
them rather than copying entire guides. `AGENTS.md` remains the detailed agent
instruction file.

CI runs on pushes and pull requests. The release gate requires frontend,
backend, PostgreSQL/Redis integration, and application-image verification.
Feature-branch success does not publish images; publication requires the
successful gate on a qualifying push to `main`. Production CD is manual and
separate. Contributing does not require VPS access or production credentials,
and a normal PR does not authorize production deployment. See
[CI/CD](docs/ci-cd.md) and [Deployment](docs/deployment.md).

## Pull requests and review

1. Keep the PR focused and explain the concrete problem and resulting behavior.
   For a bug fix, describe the verified root cause and regression coverage.
2. Reference an issue if one exists; explain important changes/affected areas
   and trade-offs for a reviewer unfamiliar with the implementation.
3. Use the [PR template](.github/PULL_REQUEST_TEMPLATE.md) to record exact check
   results, skipped/unavailable checks, relevant risks, and known limitations.
4. Describe relevant API, security, data, concurrency, browser, configuration,
   deployment, and backward-compatibility impacts. Include sanitized screenshots
   or examples when they help assess a visual or behavioral change.
5. Update affected documentation, run `git diff --check`, and inspect the final
   diff for secrets, unintended files, and unrelated edits before submitting.
6. Review the CI results, investigate failures, and respond to review feedback.
   A green run supports review; it does not replace design/security/concurrency
   analysis or establish production readiness.

## License

This project is licensed under the [MIT License](LICENSE).
