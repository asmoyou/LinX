"""Helpers for loading local runtime environment variables consistently."""

from __future__ import annotations

from pathlib import Path
from typing import List

from dotenv import load_dotenv


def bootstrap_runtime_env() -> List[Path]:
    """Load runtime env with repo root `.env` as the canonical source."""
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    loaded: List[Path] = []

    root_env = repo_root / ".env"
    if root_env.exists():
        if load_dotenv(root_env, override=False):
            loaded.append(root_env)

    return loaded
