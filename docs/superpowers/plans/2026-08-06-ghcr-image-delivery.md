# GHCR Application Image Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, publish, and deploy one digest-pinned GHCR application image for every verified `main` commit without exposing production secrets or retaining VPS registry credentials.

**Architecture:** The shared Compose file is a runtime topology only; the development override owns source builds and production consumes `APP_IMAGE`. CI adds one dependent Buildx job, while manual CD checks out the selected source commit, pulls its matching image with transient credentials, resolves its digest, and deploys that digest.

**Tech Stack:** GitHub Actions, GHCR, Docker Buildx, Docker Compose, Bash, Django, Pytest, Ruff, Bandit.

## Global Constraints

- Preserve `default-tests` and `integration-tests`; the dependent required check is exactly `Application image`.
- Publish exactly `ghcr.io/pursite/luxury-perfume:${{ github.sha }}` only for successful `main` pushes and publish no PR tag.
- Apply `org.opencontainers.image.source` and `org.opencontainers.image.revision` labels.
- Production `web` and `celery` each use `image: ${APP_IMAGE:?APP_IMAGE is required}`; dependency images and volumes remain unchanged.
- The VPS `.env` is runtime-only. Never write an image reference, token, or secret to it.
- `GHCR_READ_TOKEN` is a protected production-environment secret, sent only through SSH standard input. It never appears in logs, command arguments, `.env`, or persistent Docker configuration.
- Empty deployment SHA means `github.sha`; supplied input exactly matches `[0-9a-f]{40}`.
- Deployment uses the pulled image's SHA256 digest, `--no-build`, production `check --deploy`, forward migrations only, and no backup, restore, or reverse-migration automation.

---

### Task 1: Separate development builds from production image selection

**Files:**
- Modify: `docker/docker-compose.yml`
- Modify: `docker/docker-compose.dev.yml`
- Modify: `docker/docker-compose.prod.yml`
- Modify: `config/tests/test_deployment_compose.py`

**Interfaces:**
- Consumes: existing development `docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up --build`.
- Produces: development builds from `docker/Dockerfile` final stage and a production merge requiring an exported `APP_IMAGE`.

- [ ] **Step 1: Write the failing Compose contract test**

Add a test named `test_application_images_are_built_only_for_development` that asserts `docker/docker-compose.yml` contains no `build:`, `docker/docker-compose.dev.yml` contains both existing `context: ..`, `dockerfile: docker/Dockerfile`, and `target: final` mappings, and `docker/docker-compose.prod.yml` contains `image: ${APP_IMAGE:?APP_IMAGE is required}` twice.

- [ ] **Step 2: Verify red**

Run `venv/bin/python -m pytest config/tests/test_deployment_compose.py -q`. It must fail because shared Compose still defines application builds and production has no image requirement.

- [ ] **Step 3: Implement the minimum Compose move**

Delete only `web.build` and `celery.build` from the shared file. Add those exact mappings to the corresponding development services. Add the required `image` expression to both production services, leaving commands, mounts, health checks, ports, PostgreSQL, Redis, and volumes untouched.

- [ ] **Step 4: Verify green and functional merges**

Run `venv/bin/python -m pytest config/tests/test_deployment_compose.py -q`.

Run `docker compose --env-file docker/env/.env.development.example -f docker/docker-compose.yml -f docker/docker-compose.dev.yml config -q`.

Run `APP_IMAGE=ghcr.io/pursite/luxury-perfume:compose-validation docker compose --env-file docker/env/.env.production.example -f docker/docker-compose.yml -f docker/docker-compose.prod.yml config -q`.

- [ ] **Step 5: Commit**

Commit the four changed files with message `build: separate production image selection`.

### Task 2: Add dependent GHCR application-image CI

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `config/tests/test_deployment_compose.py`

**Interfaces:**
- Consumes: Task 1 production merge and job IDs `default-tests` / `integration-tests`.
- Produces: `Application image`, which validates Compose and builds on every PR/push, publishing only the immutable commit artifact on `main`.

- [ ] **Step 1: Write failing CI contract assertions**

Add `test_ci_application_image_job_is_dependent_and_cached`. Assert workflow text has `name: Application image`, `needs: [default-tests, integration-tests]`, `contents: read`, `packages: write`, `docker/login-action@v3`, `docker/build-push-action@v6`, `cache-from: type=gha`, `cache-to: type=gha,mode=max`, source/revision OCI labels, and a push expression requiring a `main` push.

- [ ] **Step 2: Verify red**

Run `venv/bin/python -m pytest config/tests/test_deployment_compose.py -q`. It must fail because no image job exists.

- [ ] **Step 3: Implement the CI job**

Append job ID `image`, name it `Application image`, set `needs: [default-tests, integration-tests]`, and grant only `contents: read` / `packages: write`. Set up Buildx; validate the production merge using `APP_IMAGE=ghcr.io/pursite/luxury-perfume:compose-validation`; authenticate with `${{ secrets.GITHUB_TOKEN }}` only on a main push; use metadata/build actions to build final stage, tag one raw `${{ github.sha }}` tag, label source/revision, cache with GHA, and conditionally push only on main.

- [ ] **Step 4: Verify green**

Run `venv/bin/python -m pytest config/tests/test_deployment_compose.py -q`.

Run `venv/bin/python -c "from pathlib import Path; import yaml; yaml.safe_load(Path('.github/workflows/ci.yml').read_text())"`.

- [ ] **Step 5: Commit**

Commit CI and test changes with message `ci: publish verified application image to ghcr`.

### Task 3: Deploy a transiently authenticated, digest-pinned image

**Files:**
- Modify: `.github/workflows/cd.yml`
- Modify: `config/tests/test_deployment_compose.py`

**Interfaces:**
- Consumes: matching `ghcr.io/pursite/luxury-perfume:<commit SHA>` image and `GHCR_READ_TOKEN` environment secret.
- Produces: remote `APP_IMAGE=ghcr.io/pursite/luxury-perfume@sha256:<64 lowercase hex>` without retained credentials.

- [ ] **Step 1: Write failing CD contract assertions**

Add `test_cd_pulls_digest_pinned_image_with_ephemeral_credentials`. Assert `commit_sha`, `${{ inputs.commit_sha || github.sha }}`, `[0-9a-f]{40}`, `${{ github.repository_owner }}`, `read -r -d`, `docker login ghcr.io --username "$GHCR_USERNAME" --password-stdin`, `DOCKER_CONFIG`, `mktemp -d`, `trap`, `RepoDigests`, `@sha256:`, `check --deploy`, `--no-build`, and absence of `${compose[@]} build`.

- [ ] **Step 2: Verify red**

Run `venv/bin/python -m pytest config/tests/test_deployment_compose.py -q`. It must fail because CD builds on the VPS.

- [ ] **Step 3: Implement secure CD**

Give `workflow_dispatch` an optional string `commit_sha` input. Set runner `DEPLOY_SHA` from `${{ inputs.commit_sha || github.sha }}`, `GHCR_USERNAME` from `${{ github.repository_owner }}`, and `GHCR_READ_TOKEN` from the protected environment secret. Validate the input SHA and username before SSH. Send NUL-delimited token then remote Bash source text over SSH stdin; use a static remote command to `read -r -d '' GHCR_READ_TOKEN` and source the rest. Keep strict SSH, dirty-check, exact checkout, production environment, concurrency, dependency polling, migrations, collectstatic, and readiness code.

On the VPS create `docker_config_directory=$(mktemp -d)`, trap unsetting the token and deleting that directory, login through `printf '%s' "$GHCR_READ_TOKEN" | DOCKER_CONFIG="$docker_config_directory" docker login ghcr.io --username "$GHCR_USERNAME" --password-stdin`, pull the commit tag, resolve a `RepoDigests` value, require `@sha256:[0-9a-f]{64}`, clean up credentials immediately, export the digest-pinned `APP_IMAGE`, validate Compose, start dependencies with `--no-build`, run `python manage.py check --deploy`, migrate, collect static, then recreate only web/celery with `--no-build`.

- [ ] **Step 4: Verify green**

Run `venv/bin/python -m pytest config/tests/test_deployment_compose.py -q`.

Run `venv/bin/python -c "from pathlib import Path; import yaml; yaml.safe_load(Path('.github/workflows/cd.yml').read_text())"`.

- [ ] **Step 5: Commit**

Commit CD and test changes with message `ci: deploy digest-pinned ghcr images`.

### Task 4: Document image delivery and rollback limits

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment.md`
- Modify: `config/tests/test_deployment_compose.py`

**Interfaces:**
- Consumes: Task 1 `APP_IMAGE`, Task 2 publishing policy, Task 3 credential flow.
- Produces: a first/normal deployment runbook with no persistent VPS login and explicit code-only rollback constraints.

- [ ] **Step 1: Write failing documentation assertions**

Add `test_ghcr_delivery_documentation_covers_security_boundaries`. Assert README and deployment guide contain `Application image`, `GHCR_READ_TOKEN`, `APP_IMAGE`, `digest`, `--no-build`, `not implemented`, and `reverse migrations`.

- [ ] **Step 2: Verify red**

Run `venv/bin/python -m pytest config/tests/test_deployment_compose.py -q`. It must fail because docs say the VPS builds application images and include a repository backup procedure.

- [ ] **Step 3: Update runbooks**

Document PR/main CI behavior, GHCR SHA labels, protected read-only classic PAT, first deployment, normal manual deployment, runtime-only `.env`, temporary credential removal, and code-only rollback. Delete repository backup/restore instructions and instead state that backup/restore automation and reverse migrations are intentionally not implemented here.

- [ ] **Step 4: Verify green**

Run `venv/bin/python -m pytest config/tests/test_deployment_compose.py -q`.

- [ ] **Step 5: Commit**

Commit documentation and tests with message `docs: document ghcr production delivery`.

### Task 5: Verify the complete delivery path

**Files:**
- Verify: `.github/workflows/ci.yml`, `.github/workflows/cd.yml`, `docker/docker-compose*.yml`, `README.md`, `docs/deployment.md`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: fresh evidence for code, static security, workflow, Compose, and Docker image correctness.

- [ ] **Step 1: Inspect diff**

Run `git diff --check` and `git status --short`; expect no whitespace errors and only scoped changes.

- [ ] **Step 2: Run Python quality gate**

Run `venv/bin/python -W error -m pytest`, `venv/bin/python -m ruff check apps config tests`, `venv/bin/python -m bandit -q -r apps config -x 'apps/**/tests/**,config/tests/**'`, `venv/bin/python manage.py check --settings=config.settings.test`, and `venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test`; expect exit zero for each.

- [ ] **Step 3: Run Docker checks**

Run the development Compose merge, production Compose merge with non-secret placeholder `APP_IMAGE`, and `docker build --file docker/Dockerfile --target final --tag luxury-perfume:ghcr-validation .`; expect exit zero. If Docker is unavailable, report the exact blocking output without claiming these checks passed.

- [ ] **Step 4: Verify workflow parsing and contract tests**

Run Python YAML parsing against both workflow files and `venv/bin/python -m pytest config/tests/test_deployment_compose.py -q`; expect exit zero.

- [ ] **Step 5: Commit**

Commit the specification and plan with message `docs: plan ghcr image delivery` if they are not already committed.
