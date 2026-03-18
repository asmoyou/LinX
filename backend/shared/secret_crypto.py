"""Shared symmetric encryption helpers for persisted secrets and binding codes."""

from __future__ import annotations

import hashlib
import logging
import os

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    raw = os.getenv("LLM_ENCRYPTION_KEY")
    if not raw:
        logger.warning(
            "LLM_ENCRYPTION_KEY not set, using generated key for secret crypto (dev only)"
        )
        raw = Fernet.generate_key().decode()
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
