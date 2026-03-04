"""Unit-test specific pytest configuration."""

from __future__ import annotations

import pytest
from docker.errors import DockerException

import virtualization.container_manager as container_manager_module


@pytest.fixture(autouse=True)
def _force_container_simulation(monkeypatch):
    """Prevent unit tests from creating real Docker sandboxes on the host."""

    def _raise_docker_unavailable(*_args, **_kwargs):
        raise DockerException("Docker is disabled for backend unit tests")

    monkeypatch.setattr(
        container_manager_module.docker,
        "from_env",
        _raise_docker_unavailable,
    )

    # Reset singletons so every test re-reads the patched docker availability.
    container_manager_module._container_manager = None
    container_manager_module._docker_cleanup_manager = None
    yield
    container_manager_module._container_manager = None
    container_manager_module._docker_cleanup_manager = None
