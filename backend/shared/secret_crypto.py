"""Shared symmetric encryption helpers for persisted secrets and binding codes."""

from __future__ import annotations

import hashlib
import logging
import os

from cryptography.fernet import Fernet

from shared.runtime_env import bootstrap_runtime_env

logger = logging.getLogger(__name__)

_ENV_LOADED = False


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    bootstrap_runtime_env()
    _ENV_LOADED = True


def _get_encryption_key() -> bytes:
    _ensure_env_loaded()
    raw = os.getenv("LLM_ENCRYPTION_KEY")
    if not raw:
        logger.warning(
            "LLM_ENCRYPTION_KEY not set, using generated key for secret crypto (dev only)"
        )
        raw = Fernet.generate_key().decode()
        # Keep the generated key in-process so spawned workers can decrypt the same secrets.
        os.environ["LLM_ENCRYPTION_KEY"] = raw
    return raw.encode() if isinstance(raw, str) else raw


_cipher_suite = Fernet(_get_encryption_key())


def encrypt_text(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    return _cipher_suite.encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str | None) -> str | None:
    encrypted = str(value or "").strip()
    if not encrypted:
        return None
    try:
        return _cipher_suite.decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.error("Failed to decrypt persisted secret: %s", exc)
        return None


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()
