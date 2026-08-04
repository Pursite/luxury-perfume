from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_web_readiness_probe_marks_its_loopback_request_as_https():
    compose_config = (REPOSITORY_ROOT / "docker-compose.yml").read_text()

    assert "headers={'X-Forwarded-Proto': 'https'}" in compose_config
