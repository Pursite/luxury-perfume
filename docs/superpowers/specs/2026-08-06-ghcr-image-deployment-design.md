# GHCR Application Image Delivery Design

## Goal

Publish one verified, immutable application artifact for each successful
`main` commit and deploy that artifact to the VPS without building application
code or retaining registry credentials there.

## Scope and constraints

- The same final Django image runs both `web` and `celery`.
- CI preserves the current `default-tests` and `integration-tests` jobs. The
  stable dependent check is named `Application image`.
- Pull requests build and verify the image without publishing. Successful
  pushes to `main` publish one `ghcr.io/pursite/luxury-perfume:<40-char SHA>` tag.
- The deployment pins the pulled image by its resolved `sha256` digest, not by
  the mutable tag alone.
- Application source uses development builds only through the development
  Compose override. Production consumes `APP_IMAGE`; PostgreSQL, Redis, and
  their named volumes remain unchanged.
- The production `.env` stays on the VPS and contains runtime configuration
  only. No production secret is copied, generated, logged, or baked into the
  image.
- The protected GitHub `production` environment supplies a classic PAT with
  only `read:packages` as `GHCR_READ_TOKEN`. It is delivered to the remote
  shell over standard input for one deployment only, never as a process
  argument or in `.env`.
- No database/media backup, restore automation, or automatic reverse migration
  is added.

## CI artifact flow

`default-tests` and `integration-tests` run unchanged. A new `image` job named
`Application image` needs both. It validates the production Compose merge with
a non-secret placeholder `APP_IMAGE`, then builds `docker/Dockerfile`'s
`final` stage via Buildx with GitHub Actions cache.

The job has the minimum repository permissions required to publish:
`contents: read` and `packages: write`. It logs in with `GITHUB_TOKEN` only on
a push to `main`; pull requests do not push. The image has exactly one
commit-SHA tag and OCI source and revision labels. Deployment subsequently
resolves that tag to a content digest, so a tag cannot alter a deployed
artifact even if it were later retagged.

## Compose design

The shared Compose file retains service networking, health checks, runtime
environment loading, and persistent dependency volumes but no application
build configuration. The development override owns the existing `build`
configuration and source mounts. The production override sets both application
services to:

```yaml
image: ${APP_IMAGE:?APP_IMAGE is required}
```

The deployment exports a digest-pinned `APP_IMAGE` before calling Compose, so
the VPS `.env` never needs an image reference or registry secret.

## Manual deployment and rollback flow

The manual workflow accepts an optional full commit SHA. An empty input uses
`github.sha`; a non-empty value must match lowercase hexadecimal
`[0-9a-f]{40}`. The VPS rejects a dirty checkout, fetches and detaches at that
exact commit, and derives the corresponding GHCR SHA tag.

The runner sends the GHCR token over the SSH standard-input stream before the
remote script. A small static remote bootstrap reads the NUL-delimited token
and sources the remaining script; the token is never interpolated into the SSH
command. The remote script creates a `mktemp -d` Docker configuration,
authenticates using `docker login --password-stdin`, pulls the SHA tag, obtains
its image digest from local Docker metadata, sets `APP_IMAGE` to
`ghcr.io/pursite/luxury-perfume@sha256:…`, unsets the token, and removes the
temporary configuration through a trap before Compose deployment proceeds.

The retained production gates are: strict host-key verification, protected
environment, serialized deployments, source dirty-check rejection,
configuration validation, dependency health checks, forward migrations,
static collection, and readiness checks. A `manage.py check --deploy` runs in
the pulled image with the VPS `.env` after dependencies are healthy and before
the running `web` and `celery` containers are replaced. All service starts use
`--no-build`.

A requested older SHA is a code rollback only. It is valid only when its
already-published image exists and its code remains compatible with the current
database schema and data. The workflow never reverses migrations or restores
data automatically.

## Documentation and verification

README and deployment documentation will describe CI publishing, first and
normal deployment, protected `GHCR_READ_TOKEN` setup, digest pinning, the
temporary credential lifecycle, and code-only rollback limitations. They will
explicitly state that backup and restore automation is intentionally outside
the repository for now.

Verification includes the full Python test suite, Ruff, Bandit, Django checks,
migration-drift checks, both Compose merges, a local final-image Docker build,
and static workflow syntax/behavior assertions. Docker-dependent checks are
reported separately if the local Docker daemon is unavailable.
