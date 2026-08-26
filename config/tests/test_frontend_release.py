import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RELEASE_SCRIPT = REPOSITORY_ROOT / "scripts" / "frontend-release.sh"
FRONTEND_DOCKERFILE = REPOSITORY_ROOT / "docker" / "Dockerfile.frontend"
API_ORIGIN = "https://shop.exonplus.ir"


def run_release(*args, cwd=None):
    return subprocess.run(
        ["bash", str(RELEASE_SCRIPT), *map(str, args)],
        cwd=cwd or REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def make_dist(path, *, sha, api_origin=API_ORIGIN):
    (path / "assets").mkdir(parents=True)
    (path / "index.html").write_text(
        '<!doctype html><html><body><script src="/assets/app.js"></script></body></html>\n',
        encoding="utf-8",
    )
    (path / "assets" / "app.js").write_text(
        f'const apiOrigin = "{api_origin}";\n',
        encoding="utf-8",
    )
    result = run_release("stamp", path, sha)
    assert result.returncode == 0, result.stderr


def write_release(project, sha, digest):
    release = project / "frontend-releases" / sha
    make_dist(release, sha=sha)
    (release / ".frontend-image-digest").write_text(f"{digest}\n", encoding="utf-8")
    return release


def test_stamp_writes_commit_and_public_origin_manifest(tmp_path):
    sha = "a" * 40
    dist = tmp_path / "dist"
    dist.mkdir()

    make_dist(dist, sha=sha)

    manifest = json.loads((dist / ".release-manifest.json").read_text())
    assert manifest == {
        "schema": 1,
        "commit_sha": sha,
        "api_base_url": API_ORIGIN,
    }


def test_validate_rejects_wrong_commit_and_development_origin(tmp_path):
    sha = "b" * 40
    dist = tmp_path / "dist"
    dist.mkdir()
    make_dist(dist, sha=sha)

    wrong_sha = run_release("validate", dist, "c" * 40)
    assert wrong_sha.returncode != 0

    (dist / "assets" / "app.js").write_text(
        'const apiOrigin = "http://localhost:8000";\n', encoding="utf-8"
    )
    development_origin = run_release("validate", dist, sha)
    assert development_origin.returncode != 0


def test_prepare_rejects_a_missing_frontend_artifact(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    sha = "c" * 40
    digest = "ghcr.io/pursite/luxury-perfume-frontend@sha256:" + "3" * 64

    result = run_release("prepare", project, sha, digest)

    assert result.returncode != 0


def test_validate_rejects_source_dependencies_and_symlinks(tmp_path):
    sha = "d" * 40
    dist = tmp_path / "dist"
    dist.mkdir()
    make_dist(dist, sha=sha)
    (dist / "node_modules").mkdir()
    (dist / "src").mkdir()
    (dist / "linked-file").symlink_to(dist / "index.html")

    result = run_release("validate", dist, sha)

    assert result.returncode != 0


def test_activate_switches_atomically_and_rejects_conflicting_release(tmp_path):
    project = tmp_path / "project"
    (project / "frontend-releases").mkdir(parents=True)
    sha_x = "e" * 40
    sha_y = "f" * 40
    digest_x = "ghcr.io/pursite/luxury-perfume-frontend@sha256:" + "1" * 64
    digest_y = "ghcr.io/pursite/luxury-perfume-frontend@sha256:" + "2" * 64
    write_release(project, sha_x, digest_x)
    write_release(project, sha_y, digest_y)

    activate_x = run_release("activate", project, sha_x, digest_x)
    assert activate_x.returncode == 0, activate_x.stderr
    assert (project / "frontend-current").is_symlink()
    assert (project / "frontend-current").readlink() == Path("frontend-releases") / sha_x

    activate_y = run_release("activate", project, sha_y, digest_y)
    assert activate_y.returncode == 0, activate_y.stderr
    assert (project / "frontend-current").readlink() == Path("frontend-releases") / sha_y

    conflicting = run_release("activate", project, sha_y, digest_x)
    assert conflicting.returncode != 0
    assert (project / "frontend-current").readlink() == Path("frontend-releases") / sha_y


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is unavailable")
def test_scratch_frontend_image_can_be_created_and_copied_without_starting(tmp_path):
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.skip("Docker daemon is unavailable")

    sha = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    dist = tmp_path / "dist"
    dist.mkdir()
    make_dist(dist, sha=sha)
    image = f"luxury-perfume-frontend-test:{uuid.uuid4().hex}"
    container_id = None
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    try:
        build = subprocess.run(
            [
                "docker",
                "build",
                "--file",
                str(FRONTEND_DOCKERFILE),
                "--tag",
                image,
                str(dist),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert build.returncode == 0, build.stderr

        created = subprocess.run(
            ["docker", "create", image, "/frontend/index.html"],
            text=True,
            capture_output=True,
            check=False,
        )
        assert created.returncode == 0, created.stderr
        container_id = created.stdout.strip()
        assert container_id

        state = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}} {{.State.Running}}",
                container_id,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert state.stdout.strip() == "created false"

        copied = subprocess.run(
            ["docker", "cp", f"{container_id}:/frontend/.", f"{extracted}/"],
            text=True,
            capture_output=True,
            check=False,
        )
        assert copied.returncode == 0, copied.stderr
        assert (extracted / "index.html").exists()
        assert (extracted / ".release-manifest.json").exists()
    finally:
        if container_id:
            subprocess.run(["docker", "rm", "-f", container_id], check=False)
        subprocess.run(["docker", "rmi", "-f", image], check=False)
