from unittest.mock import MagicMock

from virtualization.sandbox_capability_probe import (
    DEFAULT_CAPABILITY_SNAPSHOT_PATH,
    build_document_toolchain_summary,
    probe_and_write_sandbox_capabilities,
    probe_sandbox_capabilities,
)


def _fake_exec_in_container(*, command, **kwargs):
    del kwargs
    if command.startswith("mkdir -p "):
        return 0, "", ""
    if "command -v python3" in command:
        return 0, "/usr/bin/python3\nPython 3.12.0\n", ""
    if "command -v pip" in command:
        return 0, "/usr/bin/pip\npip 24.0\n", ""
    if "command -v fc-list" in command:
        return 0, "/usr/bin/fc-list\nfontconfig 2.14\n", ""
    if "command -v pandoc" in command:
        return 0, "/usr/bin/pandoc\npandoc 3.1\n", ""
    if "command -v libreoffice" in command:
        return 0, "/usr/bin/libreoffice\nLibreOffice 24.2\n", ""
    if command.startswith("python3 -c") and "reportlab" in command:
        return 0, '{"version": "4.0.0"}\n', ""
    if command.startswith("python3 -c") and "pypdf" in command:
        return 0, '{"version": "5.0.0"}\n', ""
    if command.startswith("python3 -c") and "pdfplumber" in command:
        return 0, '{"version": "0.11.0"}\n', ""
    if "fc-list : family" in command:
        return 0, "Noto Sans CJK SC\nWenQuanYi Micro Hei\nNoto Serif CJK SC\n", ""
    raise AssertionError(f"Unexpected command: {command}")


def test_probe_sandbox_capabilities_builds_expected_snapshot():
    manager = MagicMock()
    manager.exec_in_container.side_effect = _fake_exec_in_container

    snapshot = probe_sandbox_capabilities(
        "sandbox-1",
        container_manager=manager,
        runtime_environment={"PYTHONPATH": "/custom"},
    )

    assert snapshot["version"] == "1"
    assert snapshot["python_runtime"]["pip_target"] == "/opt/linx_python_deps"
    assert snapshot["commands"]["pandoc"]["available"] is True
    assert snapshot["python_modules"]["reportlab"]["available"] is True
    assert snapshot["fonts"]["recommended_sans"]
    assert snapshot["renderers"]["libreoffice_pdf"]["available"] is True
    assert snapshot["renderers"]["reportlab_text_pdf"]["input_extensions"] == [".txt", ".json", ".csv"]
    assert "pypdf" in snapshot["verifiers"]["pdf_text_extractors"]


def test_probe_and_write_sandbox_capabilities_persists_json_snapshot():
    manager = MagicMock()
    manager.exec_in_container.side_effect = _fake_exec_in_container

    snapshot = probe_and_write_sandbox_capabilities(
        "sandbox-1",
        container_manager=manager,
        runtime_environment={"PYTHONPATH": "/custom"},
    )

    _, kwargs = manager.write_file_to_container.call_args
    assert kwargs["file_path"] == DEFAULT_CAPABILITY_SNAPSHOT_PATH
    assert "renderers" in kwargs["content"]
    assert snapshot["commands"]["libreoffice"]["available"] is True


def test_build_document_toolchain_summary_uses_available_entries():
    summary = build_document_toolchain_summary(
        {
            "renderers": {
                "libreoffice_pdf": {"available": True},
                "pandoc_docx_bridge": {"available": False},
            },
            "commands": {
                "python3": {"available": True},
                "pandoc": {"available": False},
            },
            "fonts": {
                "recommended_sans": ["Noto Sans CJK SC"],
            },
        }
    )

    assert summary == {
        "renderers": ["libreoffice_pdf"],
        "preferred_cjk_fonts": ["Noto Sans CJK SC"],
        "commands": ["python3"],
    }
