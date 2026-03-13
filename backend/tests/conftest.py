"""Shared pytest configuration for backend tests.

Ensure backend top-level packages are always importable, regardless of whether
tests are launched via `pytest` or `python -m pytest`.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import warnings
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

warnings.filterwarnings("ignore", message="PyPDF2 is deprecated.*", category=DeprecationWarning)
warnings.filterwarnings(
    "ignore",
    message="builtin type SwigPyPacked has no __module__ attribute",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message="builtin type SwigPyObject has no __module__ attribute",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message="builtin type swigvarlink has no __module__ attribute",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"Call to deprecated method __init__\..*Jaeger.*",
    category=DeprecationWarning,
)


def _clear_ephemeral_tmp_artifacts() -> None:
    """Delete pytest/tempfile artifacts while leaving optional caches alone."""
    if not STABLE_TMP_ROOT.exists():
        return

    for path in STABLE_TMP_ROOT.iterdir():
        if path.name == "data-gym-cache":
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _run_async_cleanup(coro) -> None:
    """Run async cleanup in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def pytest_configure(config: pytest.Config) -> None:
    """Pin pytest temp directories to a stable workspace-local path."""
    _clear_ephemeral_tmp_artifacts()
    if not getattr(config.option, "basetemp", None):
        config.option.basetemp = str(STABLE_BASETEMP)
    STABLE_BASETEMP.mkdir(parents=True, exist_ok=True)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Drop per-run temp artifacts after the suite completes."""
    del session, exitstatus
    _clear_ephemeral_tmp_artifacts()


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


@pytest.fixture(autouse=True)
def _reset_config_and_migration_singletons():
    """Prevent global config/migration singletons from leaking across tests."""
    import database.migrations as database_migrations
    import shared.config as shared_config

    def _reset_singletons() -> None:
        get_config = getattr(shared_config, "get_config", None)
        cache_clear = getattr(get_config, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()
        shared_config._config_instance = None
        database_migrations._migration_runner = None

    _reset_singletons()
    yield
    _reset_singletons()


@pytest.fixture(autouse=True)
def _close_global_llm_router():
    """Ensure singleton LLM router/providers do not leak aiohttp sessions across tests."""
    yield
    try:
        import llm_providers.router as llm_router_module

        router = getattr(llm_router_module, "_llm_router", None)
        if router is not None:
            close_fn = getattr(router, "close", None) or getattr(router, "close_all", None)
            if close_fn is not None:
                _run_async_cleanup(close_fn())
            llm_router_module._llm_router = None
    except Exception:
        pass


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
