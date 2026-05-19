"""Release metadata guard for the Docker companion."""
from __future__ import annotations

import pytest

from app import __version__


def test_fastapi_metadata_and_health_use_package_version() -> None:
    pytest.importorskip("fastapi")
    from app import main as docker_main

    assert docker_main.app.version == __version__
    assert docker_main.healthz()["version"] == __version__
