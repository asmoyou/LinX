from unittest.mock import MagicMock

from virtualization.sandbox_runtime_env import (
    DEFAULT_INTERNAL_DEP_WORKDIR,
    DEFAULT_INTERNAL_PYTHON_DEPS_DIR,
    build_python_runtime_summary,
    build_sandbox_runtime_env,
    render_sandbox_runtime_env_script,
    write_sandbox_runtime_env_file,
)


def test_build_sandbox_runtime_env_enforces_authoritative_python_paths(monkeypatch):
    monkeypatch.setenv("PIP_INDEX_URL", "https://example.invalid/simple")

    env = build_sandbox_runtime_env({"TEST_VAR": "ok", "PYTHONPATH": "/custom/site-packages"})

    assert env["TEST_VAR"] == "ok"
    assert env["PIP_TARGET"] == DEFAULT_INTERNAL_PYTHON_DEPS_DIR
    assert env["PYTHONPATH"].startswith(f"{DEFAULT_INTERNAL_PYTHON_DEPS_DIR}:")
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PIP_USER"] == "0"
    assert env["LINX_DEP_WORKDIR"] == DEFAULT_INTERNAL_DEP_WORKDIR
    assert env["PIP_INDEX_URL"] == "https://example.invalid/simple"


def test_build_python_runtime_summary_uses_authoritative_env():
    summary = build_python_runtime_summary({"PYTHONPATH": "/workspace/custom"})

    assert summary["executable"] == "python3"
    assert summary["pip_target"] == DEFAULT_INTERNAL_PYTHON_DEPS_DIR
    assert summary["pythonpath"].startswith(DEFAULT_INTERNAL_PYTHON_DEPS_DIR)
    assert summary["python_nousersite"] is True


def test_render_sandbox_runtime_env_script_contains_exports():
    script = render_sandbox_runtime_env_script({"PYTHONPATH": "/x"})

    assert script.startswith("#!/bin/sh")
    assert 'export PIP_TARGET="/opt/linx_python_deps"' in script
    assert 'export PYTHONNOUSERSITE="1"' in script


def test_write_sandbox_runtime_env_file_materializes_shell_exports():
    manager = MagicMock()

    write_sandbox_runtime_env_file(
        "sandbox-1",
        container_manager=manager,
        raw_env={"PYTHONPATH": "/opt/custom"},
    )

    manager.exec_in_container.assert_called_once()
    _, kwargs = manager.write_file_to_container.call_args
    assert kwargs["container_id"] == "sandbox-1"
    assert kwargs["file_path"] == f"{DEFAULT_INTERNAL_DEP_WORKDIR}/env.sh"
    assert 'export PIP_TARGET="/opt/linx_python_deps"' in kwargs["content"]
