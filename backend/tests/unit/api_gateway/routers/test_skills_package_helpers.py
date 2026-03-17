"""Tests for agent-skill package fallback helpers."""

from api_gateway.routers.skills import _is_missing_skill_package_error


class _FakeStorageError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def test_is_missing_skill_package_error_supports_s3_no_such_key() -> None:
    assert _is_missing_skill_package_error(_FakeStorageError("NoSuchKey")) is True


def test_is_missing_skill_package_error_supports_mock_storage_keyerror() -> None:
    assert _is_missing_skill_package_error(KeyError(("agent-artifacts", "missing.zip"))) is True

