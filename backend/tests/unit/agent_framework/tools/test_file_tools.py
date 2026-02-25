"""Tests for agent file tools."""

from agent_framework.tools.file_tools import (
    AppendFileTool,
    clear_workspace_root,
    create_file_tools,
    get_workspace_root,
    set_workspace_root,
)


def test_create_file_tools_includes_append_file() -> None:
    """Factory should expose append_file alongside existing file tools."""
    tool_names = [tool.name for tool in create_file_tools()]
    assert "append_file" in tool_names


def test_append_file_tool_appends_existing_file(tmp_path) -> None:
    """append_file should append bytes to an existing file."""
    set_workspace_root(tmp_path)
    target = tmp_path / "notes.md"
    target.write_text("# title", encoding="utf-8")

    tool = AppendFileTool()
    result = tool._run("/workspace/notes.md", "\nline-2")

    assert "Successfully appended" in result
    assert target.read_text(encoding="utf-8") == "# title\nline-2"


def test_append_file_tool_creates_file_when_missing(tmp_path) -> None:
    """append_file should create missing files and parent directories."""
    set_workspace_root(tmp_path)
    target = tmp_path / "output" / "draft.md"

    tool = AppendFileTool()
    result = tool._run("/workspace/output/draft.md", "hello")

    assert "Successfully appended" in result
    assert target.read_text(encoding="utf-8") == "hello"


def test_clear_workspace_root_prevents_stale_path_writes(tmp_path) -> None:
    """clear_workspace_root should disable file writes until a new root is set."""
    set_workspace_root(tmp_path)
    assert get_workspace_root() == tmp_path

    clear_workspace_root()
    assert get_workspace_root() is None

    tool = AppendFileTool()
    result = tool._run("/workspace/output/draft.md", "hello")
    assert "Workspace root not set" in result
