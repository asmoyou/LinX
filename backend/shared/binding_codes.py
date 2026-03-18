"""Helpers for durable external-account binding codes."""

from __future__ import annotations

import secrets
import string

from shared.secret_crypto import sha256_text

_BINDING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_BINDING_CODE_PREFIX = "LXU"
_BINDING_CODE_PART_LENGTH = 4
_BINDING_CODE_PARTS = 4


def generate_user_binding_code() -> str:
    parts = [
        "".join(secrets.choice(_BINDING_CODE_ALPHABET) for _ in range(_BINDING_CODE_PART_LENGTH))
        for _ in range(_BINDING_CODE_PARTS)
    ]
    return f"{_BINDING_CODE_PREFIX}-" + "-".join(parts)


def normalize_user_binding_code(raw_code: str) -> str:
    filtered = "".join(ch for ch in str(raw_code or "").upper() if ch in string.ascii_uppercase + string.digits)
    if filtered.startswith(_BINDING_CODE_PREFIX):
        filtered = filtered[len(_BINDING_CODE_PREFIX) :]
    if len(filtered) != _BINDING_CODE_PART_LENGTH * _BINDING_CODE_PARTS:
        return str(raw_code or "").strip().upper()
    parts = [
        filtered[index : index + _BINDING_CODE_PART_LENGTH]
        for index in range(0, len(filtered), _BINDING_CODE_PART_LENGTH)
    ]
    return f"{_BINDING_CODE_PREFIX}-" + "-".join(parts)


def hash_user_binding_code(raw_code: str) -> str:
    canonical = "".join(ch for ch in str(raw_code or "").upper() if ch in string.ascii_uppercase + string.digits)
    return sha256_text(canonical)
