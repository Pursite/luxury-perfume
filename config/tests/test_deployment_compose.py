from pathlib import Path

import yaml

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
    assert development_compose_config.count("context: ..") == 3
    assert development_compose_config.count("dockerfile: docker/Dockerfile") == 3
    assert development_compose_config.count("target: final") == 3
    assert production_compose_config.count(
        "image: ${APP_IMAGE:?APP_IMAGE is required}"
    ) == 3


def test_development_dependencies_remain_internal_without_host_port_settings():
    compose_config = (REPOSITORY_ROOT / "docker" / "docker-compose.yml").read_text()
    development_compose_config = (
        REPOSITORY_ROOT / "docker" / "docker-compose.dev.yml"
    ).read_text()
    development_environment = (
        REPOSITORY_ROOT / "docker" / "env" / ".env.development.example"
    ).read_text()
    deployment_guide = (REPOSITORY_ROOT / "docs" / "deployment.md").read_text()
    readme = (REPOSITORY_ROOT / "README.md").read_text()

    assert "POSTGRES_HOST_PORT" not in development_environment
    assert "REDIS_HOST_PORT" not in development_environment
    assert "  db:\n" in compose_config
    assert "  redis:\n" in compose_config
    assert "  db:\n" not in development_compose_config
    assert "  redis:\n" not in development_compose_config
    assert "PostgreSQL and Redis remain\ninternal during development" in deployment_guide
    assert "ports published by the development stack" not in readme


def test_ci_application_image_job_is_read_only_and_publish_is_immutable():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    application_image_job, publish_job = workflow.split("\n  publish:\n", maxsplit=1)

    assert "name: Application image" in application_image_job
    assert "needs: [default-tests, integration-tests]" in application_image_job
    assert "cp docker/env/.env.production.example .env" in application_image_job
    assert "docker compose --env-file .env" in application_image_job
    assert "packages: write" not in application_image_job
    assert application_image_job.count(
        "docker/build-push-action@10e90e3645eae34f1e60eeb005ba3a3d33f178e8"
    ) == 1
    assert "cache-from: type=gha" in application_image_job
    assert "cache-to: type=gha,mode=max" in application_image_job
    assert "push: false" in application_image_job
    assert (
        "outputs: type=docker,dest=/tmp/luxury-perfume-application.tar"
        in application_image_job
    )
    assert "docker load --input /tmp/luxury-perfume-application.tar" in application_image_job
    assert "DJANGO_SETTINGS_MODULE=config.settings.test" in application_image_job
    assert "Username or password is incorrect." in application_image_job
    assert "نام کاربری یا رمز عبور نادرست است." in application_image_job
    assert "APP_IMAGE: ghcr.io/pursite/luxury-perfume" in application_image_job
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in application_image_job
    assert "name: luxury-perfume-image-${{ github.sha }}" in application_image_job

    assert "name: Publish application image" in publish_job
    assert "needs: [release-gate]" in publish_job
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in publish_job
    assert "group: ghcr-publish-${{ github.sha }}" in publish_job
    assert "packages: write" in publish_job
    assert "docker/login-action@c94ce9fb468520275223c153574b00df6fe4bcc9" in publish_job
    assert "docker buildx imagetools inspect \"$IMAGE_TAG\"" in publish_job
    assert "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093" in publish_job
    assert "name: luxury-perfume-image-${{ github.sha }}" in publish_job
    assert "docker load --input /tmp/luxury-perfume-application.tar" in publish_job
    assert "docker tag luxury-perfume:application \"$IMAGE_TAG\"" in publish_job
    assert "docker push \"$IMAGE_TAG\"" in publish_job
    assert "docker/build-push-action@v6" not in publish_job


def test_frontend_release_is_gated_and_published_from_the_ci_artifact():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "release-gate:" in workflow
    assert "needs: [frontend, default-tests, integration-tests, image]" in workflow
    assert "permissions: {}" in workflow
    assert "name: Publish frontend image" in workflow
    assert "needs: [release-gate]" in workflow
    assert "ghcr.io/pursite/luxury-perfume-frontend:${{ github.sha }}" in workflow
    assert "luxury-perfume-frontend-image-${{ github.sha }}" in workflow
    assert "docker load --input /tmp/luxury-perfume-frontend-application.tar" in workflow
    assert "test \"$revision\" = \"$GITHUB_SHA\"" in workflow
    assert "docker push \"$IMAGE_TAG\"" in workflow
    assert "retention-days: 1" in workflow
    assert "Dockerfile.frontend" in workflow
    assert "VITE_API_BASE_URL: https://shop.exonplus.ir" in workflow


def test_frontend_carrier_and_release_state_are_source_controlled_safely():
    dockerfile = (REPOSITORY_ROOT / "docker" / "Dockerfile.frontend").read_text()
    release_script = (REPOSITORY_ROOT / "scripts" / "frontend-release.sh").read_text()
    dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text()
    gitignore = (REPOSITORY_ROOT / ".gitignore").read_text()

    assert dockerfile == "FROM scratch\n\nCOPY . /frontend/\n"
    assert 'docker create "$image_digest" /frontend/index.html' in release_script
    assert 'docker cp "$container_id:/frontend/." "$staging_directory/"' in release_script
    assert 'docker rm -f "$container_id"' in release_script
    assert "frontend/\n" in dockerignore
    assert "frontend-releases/" in gitignore
    assert "frontend-current" in gitignore


def test_cd_pulls_digest_pinned_image_with_ephemeral_credentials():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "cd.yml").read_text()

    assert "commit_sha:" in workflow
    assert "${{ inputs.commit_sha || github.sha }}" in workflow
    assert "GHCR_READ_TOKEN: ${{ secrets.GHCR_READ_TOKEN }}" in workflow
    assert "GHCR_USERNAME: ${{ github.repository_owner }}" in workflow
    assert "ghcr.io/pursite/luxury-perfume:${DEPLOY_SHA}" in workflow
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
    assert '"${compose[@]}" up -d --no-build --no-deps --force-recreate web' in workflow
    assert '"${compose[@]}" up -d --no-build --no-deps --force-recreate celery' in workflow
    assert 'exec 9>"$project_directory/.git/deploy.lock"' in workflow
    assert 'flock -n 9' in workflow
    assert 'git fetch --no-tags --unshallow origin "+refs/heads/main:$main_ref"' in workflow
    assert 'git fetch --no-tags origin "+refs/heads/main:$main_ref"' in workflow
    assert 'git fetch --no-tags origin "$DEPLOY_SHA"' in workflow
    assert 'git merge-base --is-ancestor "$DEPLOY_SHA" "$main_ref"' in workflow
    assert 'frontend-release.sh prepare' in workflow
    assert 'frontend-release.sh activate' in workflow
    assert 'docker inspect --format' in workflow
    assert '"${compose[@]}" build' not in workflow


def test_operational_identity_uses_luxury_perfume_everywhere():
    shared_compose = yaml.safe_load(
        (REPOSITORY_ROOT / "docker" / "docker-compose.yml").read_text()
    )
    integration_compose = yaml.safe_load(
        (REPOSITORY_ROOT / "docker" / "docker-compose.integration.yml").read_text()
    )
    development_compose = yaml.safe_load(
        (REPOSITORY_ROOT / "docker" / "docker-compose.dev.yml").read_text()
    )
    development_environment = (
        REPOSITORY_ROOT / "docker" / "env" / ".env.development.example"
    ).read_text()
    production_compose = yaml.safe_load(
        (REPOSITORY_ROOT / "docker" / "docker-compose.prod.yml").read_text()
    )
    deployment_workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "cd.yml"
    ).read_text()

    assert shared_compose["name"] == "luxury-perfume"
    assert integration_compose["name"] == "luxury-perfume-integration"
    assert development_compose["name"] == "luxury-perfume"
    assert integration_compose["services"]["integration-db"]["environment"][
        "POSTGRES_DB"
    ] == "luxury_perfume_test"
    assert "DB_NAME=luxury_perfume" in development_environment
    assert "DB_USER=luxury_perfume" in development_environment
    assert set(shared_compose["volumes"]) == {"postgres_data", "redis_data"}
    bind_sources = {
        volume["source"]
        for service in ("web", "celery")
        for volume in production_compose["services"][service]["volumes"]
    }
    assert bind_sources == {
        "/srv/luxury-perfume/staticfiles",
        "/srv/luxury-perfume/media",
    }
    assert "project_directory=/srv/luxury-perfume" in deployment_workflow


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


def test_production_logging_uses_docker_rotation_and_no_application_log_files():
    settings = (REPOSITORY_ROOT / "config" / "settings" / "base.py").read_text()
    dockerfile = (REPOSITORY_ROOT / "docker" / "Dockerfile").read_text()
    gunicorn_config = (REPOSITORY_ROOT / "docker" / "gunicorn.conf.py").read_text()
    production_compose = yaml.safe_load(
        (REPOSITORY_ROOT / "docker" / "docker-compose.prod.yml").read_text()
    )

    assert "RotatingFileHandler" not in settings
    assert "LOG_DIR" not in settings
    assert '"apps.lib.logging.JsonFormatter"' in settings
    assert '"apps.lib.middleware.RequestIDMiddleware"' in settings
    assert "/app/logs" not in dockerfile
    assert '"--config"' in dockerfile
    assert '"docker/gunicorn.conf.py"' in dockerfile
    assert 'accesslog = "-"' in gunicorn_config
    assert 'errorlog = "-"' in gunicorn_config
    assert "%(U)s" in gunicorn_config
    assert "%(q)s" not in gunicorn_config

    expected_log_config = {
        "driver": "local",
        "options": {"max-size": "10m", "max-file": "3"},
    }
    for service in ("db", "redis", "web", "celery"):
        assert production_compose["services"][service]["logging"] == expected_log_config
