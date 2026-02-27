"""File operation tools for agent sandbox execution.

Provides Read, Edit, Write, Append, and ListFiles tools that operate on the session
workspace directory (/workspace in container, host workdir on filesystem).

Modeled after Claude Code's file tools:
- ReadFile: Read with offset/limit for large files
- EditFile: Exact string replacement (old_string -> new_string) with syntax validation
- WriteFile: Create or overwrite files with syntax validation
- AppendFile: Append content to an existing file (or create it if missing)
- ListFiles: List directory contents
"""

import ast
from contextvars import ContextVar
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Type

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_BINARY_DELIVERY_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}


# ---------------------------------------------------------------------------
# Shared workspace root – set by BaseAgent before each task execution
# ---------------------------------------------------------------------------

_workspace_root_ctx: ContextVar[Optional[Path]] = ContextVar(
    "agent_file_tools_workspace_root",
    default=None,
)


def set_workspace_root(path: Path) -> None:
    _workspace_root_ctx.set(path)


def clear_workspace_root() -> None:
    _workspace_root_ctx.set(None)


def get_workspace_root() -> Optional[Path]:
    return _workspace_root_ctx.get()


def _resolve_path(file_path: str) -> Path:
    """Resolve a file path relative to the workspace root.

    Accepts:
      - Absolute paths starting with /workspace/ (mapped to host workdir)
      - Relative paths (resolved against host workdir)
      - Absolute host paths within the workdir
    """
    root = get_workspace_root()
    if root is None:
        raise RuntimeError("Workspace root not set. Cannot perform file operations.")

    p = Path(file_path)

    # /workspace/... -> map to host workdir
    if file_path.startswith("/workspace/"):
        relative = file_path[len("/workspace/"):]
        resolved = root / relative
    elif file_path == "/workspace":
        resolved = root
    elif p.is_absolute():
        # Allow absolute paths within the workdir
        try:
            p.relative_to(root)
            resolved = p
        except ValueError:
            raise ValueError(
                f"Path {file_path} is outside the workspace. "
                f"Use paths relative to /workspace/."
            )
    else:
        resolved = root / file_path

    # Security: ensure resolved path is within workspace
    try:
        resolved.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError(
            f"Path {file_path} resolves outside the workspace (path traversal blocked)."
        )

    return resolved


# ---------------------------------------------------------------------------
# Syntax Validation
# ---------------------------------------------------------------------------

def _validate_syntax(file_path: Path, content: str) -> Tuple[bool, Optional[str]]:
    """Validate syntax of code files after edit/write.

    Returns:
        (is_valid, error_message) - error_message is None if valid
    """
    suffix = file_path.suffix.lower()

    # Python syntax check
    if suffix == ".py":
        try:
            ast.parse(content)
            return True, None
        except SyntaxError as e:
            return False, f"Python syntax error at line {e.lineno}: {e.msg}"

    # JSON syntax check
    if suffix == ".json":
        try:
            json.loads(content)
            return True, None
        except json.JSONDecodeError as e:
            return False, f"JSON syntax error at line {e.lineno}: {e.msg}"

    # JavaScript/TypeScript - basic brace/bracket matching
    if suffix in (".js", ".ts", ".jsx", ".tsx"):
        # Simple bracket matching (not a full parser, but catches obvious issues)
        stack = []
        pairs = {")": "(", "]": "[", "}": "{"}
        line_num = 1
        for char in content:
            if char == "\n":
                line_num += 1
            elif char in "([{":
                stack.append((char, line_num))
            elif char in ")]}":
                if not stack:
                    return False, f"Unmatched '{char}' at line {line_num}"
                if stack[-1][0] != pairs[char]:
                    return False, f"Mismatched bracket: expected '{pairs[char]}' but found '{char}' at line {line_num}"
                stack.pop()
        if stack:
            char, line = stack[-1]
            return False, f"Unclosed '{char}' starting at line {line}"
        return True, None

    # YAML - try to parse if pyyaml is available
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
            yaml.safe_load(content)
            return True, None
        except yaml.YAMLError as e:
            return False, f"YAML syntax error: {e}"
        except ImportError:
            pass  # pyyaml not installed, skip validation

    # Shell scripts - check with bash -n if available
    if suffix in (".sh", ".bash"):
        try:
            result = subprocess.run(
                ["bash", "-n"],
                input=content,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return False, f"Bash syntax error: {result.stderr.strip()}"
            return True, None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # bash not available or timeout, skip validation

    # No validation for other file types
    return True, None


def _validate_text_tool_target(tool_name: str, file_path: str, resolved: Path) -> Optional[str]:
    """Ensure text file tools are not used to fake binary office/pdf outputs."""
    suffix = resolved.suffix.lower()
    if suffix not in _BINARY_DELIVERY_EXTENSIONS:
        return None

    return (
        f"Error: {tool_name} cannot create a real binary {suffix} file at {file_path}. "
        "Use code_execution with an appropriate package to generate this format "
        "(for example: python-docx/python-pptx/openpyxl/reportlab), "
        "then save the produced file."
    )


# ---------------------------------------------------------------------------
# ReadFile Tool
# ---------------------------------------------------------------------------

class ReadFileInput(BaseModel):
    file_path: str = Field(description="Path to the file to read (relative to /workspace/ or absolute)")
    offset: Optional[int] = Field(default=None, description="Line number to start reading from (1-based). Omit to start from the beginning.")
    limit: Optional[int] = Field(default=None, description="Maximum number of lines to read. Omit to read all lines (up to 2000).")


class ReadFileTool(BaseTool):
    """Read file contents with optional offset/limit for large files."""

    name: str = "read_file"
    description: str = """Read the contents of a file in the workspace.

Supports reading large files in segments using offset and limit parameters.
- offset: Start reading from this line number (1-based)
- limit: Read at most this many lines

Example: Read lines 100-200 of a large file:
  {"tool": "read_file", "file_path": "/workspace/data.py", "offset": 100, "limit": 100}

Returns file contents with line numbers prefixed.
"""
    args_schema: Type[BaseModel] = ReadFileInput

    def _run(
        self,
        file_path: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        try:
            resolved = _resolve_path(file_path)

            if not resolved.exists():
                return f"Error: File not found: {file_path}"
            if resolved.is_dir():
                return f"Error: {file_path} is a directory. Use list_files instead."

            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            total_lines = len(lines)

            start = (offset - 1) if offset and offset > 0 else 0
            end = start + (limit if limit and limit > 0 else 2000)
            selected = lines[start:end]

            # Format with line numbers (like cat -n)
            result_lines = []
            for i, line in enumerate(selected, start=start + 1):
                result_lines.append(f"{i:>6}\t{line.rstrip()}")

            header = f"File: {file_path} ({total_lines} lines total)"
            if start > 0 or end < total_lines:
                header += f" [showing lines {start + 1}-{min(end, total_lines)}]"

            return header + "\n" + "\n".join(result_lines)

        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"ReadFile error: {e}", exc_info=True)
            return f"Error reading file: {e}"


# ---------------------------------------------------------------------------
# EditFile Tool
# ---------------------------------------------------------------------------

class EditFileInput(BaseModel):
    file_path: str = Field(description="Path to the file to edit")
    old_string: str = Field(description="The exact text to find and replace")
    new_string: str = Field(description="The replacement text")
    replace_all: bool = Field(default=False, description="If true, replace all occurrences. If false, the old_string must be unique.")


class EditFileTool(BaseTool):
    """Edit a file by exact string replacement."""

    name: str = "edit_file"
    description: str = """Edit a file by replacing an exact string with a new string.

The old_string must match exactly (including whitespace and indentation).
By default, old_string must appear exactly once in the file. Use replace_all=true
to replace all occurrences.

Example:
  {"tool": "edit_file", "file_path": "/workspace/app.py", "old_string": "def hello():", "new_string": "def hello(name):"}
"""
    args_schema: Type[BaseModel] = EditFileInput

    def _run(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        try:
            resolved = _resolve_path(file_path)

            if not resolved.exists():
                return f"Error: File not found: {file_path}"

            content = resolved.read_text(encoding="utf-8")
            count = content.count(old_string)

            if count == 0:
                return f"Error: old_string not found in {file_path}. Make sure it matches exactly (including whitespace)."

            if count > 1 and not replace_all:
                return (
                    f"Error: old_string appears {count} times in {file_path}. "
                    f"Provide more context to make it unique, or set replace_all=true."
                )

            new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

            # Validate syntax before writing
            is_valid, error_msg = _validate_syntax(resolved, new_content)
            if not is_valid:
                return f"Error: Edit would create invalid syntax in {file_path}:\n{error_msg}\n\nThe file was NOT modified."

            resolved.write_text(new_content, encoding="utf-8")

            replacements = count if replace_all else 1
            result = f"Successfully edited {file_path}: {replacements} replacement(s) made."

            # Add validation info for code files
            if resolved.suffix.lower() in (".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml", ".sh"):
                result += " ✓ Syntax validated."

            return result

        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"EditFile error: {e}", exc_info=True)
            return f"Error editing file: {e}"


# ---------------------------------------------------------------------------
# WriteFile Tool
# ---------------------------------------------------------------------------

class WriteFileInput(BaseModel):
    file_path: str = Field(description="Path where the file should be written")
    content: str = Field(description="Content to write to the file")


class WriteFileTool(BaseTool):
    """Create or overwrite a file."""

    name: str = "write_file"
    description: str = """Write content to a file in the workspace. Creates parent directories if needed.
If the file already exists, it will be overwritten.

Example:
  {"tool": "write_file", "file_path": "/workspace/utils.py", "content": "def greet(name):\\n    return f'Hello, {name}!'"}
"""
    args_schema: Type[BaseModel] = WriteFileInput

    def _run(
        self,
        file_path: str,
        content: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        try:
            resolved = _resolve_path(file_path)

            target_error = _validate_text_tool_target(self.name, file_path, resolved)
            if target_error:
                return target_error

            # Validate syntax before writing
            is_valid, error_msg = _validate_syntax(resolved, content)
            if not is_valid:
                return f"Error: Content has invalid syntax for {file_path}:\n{error_msg}\n\nThe file was NOT written."

            # Create parent directories
            resolved.parent.mkdir(parents=True, exist_ok=True)

            resolved.write_text(content, encoding="utf-8")

            lines = content.count("\n") + 1
            size = len(content.encode("utf-8"))
            result = f"Successfully wrote {file_path} ({lines} lines, {size} bytes)."

            # Add validation info for code files
            if resolved.suffix.lower() in (".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml", ".sh"):
                result += " ✓ Syntax validated."

            return result

        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"WriteFile error: {e}", exc_info=True)
            return f"Error writing file: {e}"


# ---------------------------------------------------------------------------
# AppendFile Tool
# ---------------------------------------------------------------------------

class AppendFileInput(BaseModel):
    file_path: str = Field(description="Path where content should be appended")
    content: str = Field(description="Content to append")


class AppendFileTool(BaseTool):
    """Append content to a file."""

    name: str = "append_file"
    description: str = """Append content to a file in the workspace. Creates parent directories if needed.
If the file does not exist, it will be created.

Example:
  {"tool": "append_file", "file_path": "/workspace/output.md", "content": "\\n## Section 2\\nMore content..."}
"""
    args_schema: Type[BaseModel] = AppendFileInput

    def _run(
        self,
        file_path: str,
        content: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        try:
            resolved = _resolve_path(file_path)

            target_error = _validate_text_tool_target(self.name, file_path, resolved)
            if target_error:
                return target_error

            # Create parent directories if needed
            resolved.parent.mkdir(parents=True, exist_ok=True)

            with resolved.open("a", encoding="utf-8") as handle:
                handle.write(content)

            appended_bytes = len(content.encode("utf-8"))
            total_size = resolved.stat().st_size if resolved.exists() else appended_bytes
            result = (
                f"Successfully appended to {file_path} "
                f"({appended_bytes} bytes added, {total_size} bytes total)."
            )
            return result
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"AppendFile error: {e}", exc_info=True)
            return f"Error appending file: {e}"


# ---------------------------------------------------------------------------
# ListFiles Tool
# ---------------------------------------------------------------------------

class ListFilesInput(BaseModel):
    path: str = Field(default="/workspace", description="Directory path to list (default: /workspace)")
    recursive: bool = Field(default=False, description="If true, list files recursively")


class ListFilesTool(BaseTool):
    """List files in a directory."""

    name: str = "list_files"
    description: str = """List files and directories in the workspace.

Example:
  {"tool": "list_files", "path": "/workspace"}
  {"tool": "list_files", "path": "/workspace/src", "recursive": true}
"""
    args_schema: Type[BaseModel] = ListFilesInput

    def _run(
        self,
        path: str = "/workspace",
        recursive: bool = False,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        try:
            resolved = _resolve_path(path)

            if not resolved.exists():
                return f"Error: Path not found: {path}"
            if not resolved.is_dir():
                return f"Error: {path} is not a directory."

            entries = []
            if recursive:
                for item in sorted(resolved.rglob("*")):
                    rel = item.relative_to(resolved)
                    if item.is_dir():
                        entries.append(f"  {rel}/")
                    else:
                        size = item.stat().st_size
                        entries.append(f"  {rel}  ({size} bytes)")
            else:
                for item in sorted(resolved.iterdir()):
                    if item.is_dir():
                        entries.append(f"  {item.name}/")
                    else:
                        size = item.stat().st_size
                        entries.append(f"  {item.name}  ({size} bytes)")

            if not entries:
                return f"{path}: (empty directory)"

            return f"{path}:\n" + "\n".join(entries)

        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"ListFiles error: {e}", exc_info=True)
            return f"Error listing files: {e}"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_file_tools() -> list:
    """Create all file operation tools.

    Returns:
        List of [ReadFileTool, EditFileTool, WriteFileTool, AppendFileTool, ListFilesTool]
    """
    return [
        ReadFileTool(),
        EditFileTool(),
        WriteFileTool(),
        AppendFileTool(),
        ListFilesTool(),
    ]
