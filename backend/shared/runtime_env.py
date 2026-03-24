"""Helpers for loading local runtime environment variables consistently."""

from __future__ import annotations

from pathlib import Path
from typing import List

from dotenv import load_dotenv


def bootstrap_runtime_env() -> List[Path]:
    """Load repo-local .env files for local development and CLI utilities."""
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    candidates = [
        repo_root / ".env",
        backend_root / ".env",
        Path.cwd() / ".env",
    ]

    loaded: List[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not candidate.exists():
            continue
        seen.add(resolved)
        if load_dotenv(candidate, override=False):
            loaded.append(candidate)

    return loaded
