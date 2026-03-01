"""Shared pytest configuration for backend tests.

Ensure backend top-level packages are always importable, regardless of whether
tests are launched via `pytest` or `python -m pytest`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def _enable_host_fallback_for_legacy_tests(monkeypatch):
    """Keep historical tests stable unless a test overrides isolation policy explicitly."""
    monkeypatch.setenv("LINX_ALLOW_HOST_EXECUTION_FALLBACK", "1")
    monkeypatch.setenv("LINX_ENFORCE_SANDBOX_ISOLATION", "0")
