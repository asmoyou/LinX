"""Shared pytest configuration for backend tests.

Ensure backend top-level packages are always importable, regardless of whether
tests are launched via `pytest` or `python -m pytest`.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from _pytest.fixtures import FixtureDef
from _pytest.tmpdir import TempPathFactory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
STABLE_TMP_ROOT = BACKEND_ROOT / ".pytest_tmp"
STABLE_BASETEMP = STABLE_TMP_ROOT / "basetemp"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

STABLE_TMP_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["TMPDIR"] = str(STABLE_TMP_ROOT)
tempfile.tempdir = str(STABLE_TMP_ROOT)
os.environ["PYTEST_DEBUG_TEMPROOT"] = str(STABLE_TMP_ROOT)


def pytest_configure(config: pytest.Config) -> None:
    """Pin pytest temp directories to a stable workspace-local path."""
    if not getattr(config.option, "basetemp", None):
        config.option.basetemp = str(STABLE_BASETEMP)
    STABLE_BASETEMP.mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def _enable_host_fallback_for_legacy_tests(monkeypatch):
    """Keep historical tests stable unless a test overrides isolation policy explicitly."""
    monkeypatch.setenv("LINX_ALLOW_HOST_EXECUTION_FALLBACK", "1")
    monkeypatch.setenv("LINX_ENFORCE_SANDBOX_ISOLATION", "0")


@pytest.fixture(autouse=True)
def _ensure_stable_tmp_root(monkeypatch):
    """Recreate the shared temp root in case another test deletes it."""
    STABLE_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    STABLE_BASETEMP.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TMPDIR", str(STABLE_TMP_ROOT))
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(STABLE_TMP_ROOT))
    tempfile.tempdir = str(STABLE_TMP_ROOT)


@pytest.fixture(autouse=True)
def _reset_database_connection_pool():
    """Keep the global SQLAlchemy pool from leaking state across tests."""
    from database.connection import close_connection_pool

    close_connection_pool()
    yield
    close_connection_pool()


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(fixturedef: FixtureDef, request: pytest.FixtureRequest):
    """Repair pytest temp dirs before any tmp_path fixture is created."""
    if fixturedef.argname == "tmp_path":
        STABLE_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        STABLE_BASETEMP.mkdir(parents=True, exist_ok=True)
        factory = getattr(request.config, "_tmp_path_factory", None)
        if isinstance(factory, TempPathFactory):
            basetemp = getattr(factory, "_basetemp", None)
            if basetemp is not None:
                Path(basetemp).mkdir(parents=True, exist_ok=True)
    return (yield)
