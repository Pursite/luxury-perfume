from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_web_readiness_probe_marks_its_loopback_request_as_https():
    compose_config = (REPOSITORY_ROOT / "docker" / "docker-compose.yml").read_text()

    assert "headers={'X-Forwarded-Proto': 'https'}" in compose_config


def test_application_images_are_built_only_for_development():
    shared_compose_config = (
        REPOSITORY_ROOT / "docker" / "docker-compose.yml"
    ).read_text()
    development_compose_config = (
        REPOSITORY_ROOT / "docker" / "docker-compose.dev.yml"
    ).read_text()
    production_compose_config = (
        REPOSITORY_ROOT / "docker" / "docker-compose.prod.yml"
    ).read_text()

    assert "build:" not in shared_compose_config
    assert development_compose_config.count("context: ..") == 2
    assert development_compose_config.count("dockerfile: docker/Dockerfile") == 2
    assert development_compose_config.count("target: final") == 2
    assert production_compose_config.count(
        "image: ${APP_IMAGE:?APP_IMAGE is required}"
    ) == 2


def test_ci_application_image_job_is_read_only_and_publish_is_immutable():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "name: Application image" in workflow
    assert "needs: [default-tests, integration-tests]" in workflow
    assert "cp docker/env/.env.production.example .env" in workflow
    assert "docker compose --env-file .env" in workflow
    assert "contents: read" in workflow
    assert "docker/build-push-action@v6" in workflow
    assert "cache-from: type=gha" in workflow
    assert "cache-to: type=gha,mode=max" in workflow
    assert "push: false" in workflow

    assert "name: Publish application image" in workflow
    assert "needs: image" in workflow
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in workflow
    assert "group: ghcr-publish-${{ github.sha }}" in workflow
    assert "packages: write" in workflow
    assert "docker/login-action@v3" in workflow
    assert "docker buildx imagetools inspect \"$IMAGE_TAG\"" in workflow
    assert "org.opencontainers.image.source" in workflow
    assert "org.opencontainers.image.revision" in workflow
    assert "type=raw,value=${{ github.sha }}" in workflow


def test_cd_pulls_digest_pinned_image_with_ephemeral_credentials():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "cd.yml").read_text()

    assert "commit_sha:" in workflow
    assert "${{ inputs.commit_sha || github.sha }}" in workflow
    assert "GHCR_READ_TOKEN: ${{ secrets.GHCR_READ_TOKEN }}" in workflow
    assert "GHCR_USERNAME: ${{ github.repository_owner }}" in workflow
    assert '[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]]' in workflow
    assert "read -r -d" in workflow
    assert "mktemp -d" in workflow
    assert "DOCKER_CONFIG" in workflow
    assert (
        'docker login ghcr.io --username "$GHCR_USERNAME" --password-stdin'
        in workflow
    )
    assert "RepoDigests" in workflow
    assert "@sha256:" in workflow
    assert "python manage.py check --deploy --settings=config.settings.production" in workflow
    assert '"${compose[@]}" up -d --no-build --no-recreate db redis' in workflow
    assert (
        '"${compose[@]}" up -d --no-build --no-deps --force-recreate web celery'
        in workflow
    )
    assert '"${compose[@]}" build' not in workflow


def test_ghcr_delivery_documentation_covers_security_boundaries():
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    deployment_guide = (REPOSITORY_ROOT / "docs" / "deployment.md").read_text()

    assert "Application image" in readme
    assert "GHCR_READ_TOKEN" in deployment_guide
    assert "APP_IMAGE" in deployment_guide
    assert "digest" in deployment_guide
    assert "--no-build" in deployment_guide
    assert "intentionally not implemented" in deployment_guide
    assert "reverse migrations" in deployment_guide
    assert "Publish application image" in readme
    assert "Publish application image" in deployment_guide
