"""Unit tests for Enhanced Bash Tool.

Tests cover:
- Normal execution mode
- PTY mode for interactive terminals
- Background process execution
- Error handling
"""

import pytest
import time
from pathlib import Path
from agent_framework.tools.bash_tool import (
    BashToolConfig,
    BashResult,
    EnhancedBashTool,
    create_bash_tool
)
from agent_framework.tools.file_tools import clear_workspace_root, set_workspace_root
from agent_framework.tools.process_manager import ProcessManager
from uuid import uuid4


@pytest.fixture(autouse=True)
def _reset_workspace_root():
    """Avoid cross-test workspace root leakage via ContextVar."""
    clear_workspace_root()
    yield
    clear_workspace_root()


class TestBashToolConfig:
    """Test BashToolConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = BashToolConfig(command="echo hello")
        
        assert config.command == "echo hello"
        assert config.pty is False
        assert config.workdir is None
        assert config.background is False
        assert config.timeout is None
        assert config.elevated is False
        assert config.env is None


class TestEnhancedBashTool:
    """Test EnhancedBashTool class."""
    
    def test_normal_execution_success(self):
        """Test successful normal execution."""
        tool = EnhancedBashTool()
        config = BashToolConfig(command="echo 'Hello World'")
        
        result = tool.execute(config)
        
        assert result.success is True
        assert "Hello World" in result.stdout
        assert result.exit_code == 0
        assert result.execution_time > 0
    
    def test_normal_execution_failure(self):
        """Test failed normal execution."""
        tool = EnhancedBashTool()
        config = BashToolConfig(command="exit 1")
        
        result = tool.execute(config)
        
        assert result.success is False
        assert result.exit_code == 1
    
    def test_normal_execution_with_stderr(self):
        """Test execution with stderr output."""
        tool = EnhancedBashTool()
        config = BashToolConfig(command="echo 'error' >&2")
        
        result = tool.execute(config)
        
        assert result.success is True
        assert "error" in result.stderr
    
    def test_normal_execution_timeout(self):
        """Test execution timeout."""
        tool = EnhancedBashTool()
        config = BashToolConfig(
            command="sleep 10",
            timeout=1
        )
        
        result = tool.execute(config)
        
        assert result.success is False
        assert "timeout" in result.stderr.lower() or "timeout" in result.error_message.lower()
        assert result.execution_time < 3  # Should timeout quickly
    
    def test_normal_execution_with_workdir(self):
        """Test execution with working directory."""
        tool = EnhancedBashTool()
        config = BashToolConfig(
            command="pwd",
            workdir="/tmp"
        )
        
        result = tool.execute(config)
        
        assert result.success is True
        assert "/tmp" in result.stdout
    
    def test_normal_execution_with_env(self):
        """Test execution with environment variables."""
        tool = EnhancedBashTool()
        config = BashToolConfig(
            command="echo $TEST_VAR",
            env={"TEST_VAR": "test_value"}
        )
        
        result = tool.execute(config)
        
        assert result.success is True
        assert "test_value" in result.stdout

    def test_normal_execution_defaults_to_session_workspace_root(self, tmp_path: Path):
        """When workspace root is set, bash without workdir should run there."""
        set_workspace_root(tmp_path)
        tool = EnhancedBashTool()
        config = BashToolConfig(command="pwd")

        result = tool.execute(config)

        assert result.success is True
        assert str(tmp_path) in result.stdout.strip()

    def test_normal_execution_maps_workspace_workdir(self, tmp_path: Path):
        """/workspace/... workdir should map to host session workspace path."""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        set_workspace_root(tmp_path)

        tool = EnhancedBashTool()
        config = BashToolConfig(command="pwd", workdir="/workspace/output")

        result = tool.execute(config)

        assert result.success is True
        assert str(output_dir) in result.stdout.strip()

    def test_normal_execution_rewrites_workspace_paths_in_command(self, tmp_path: Path):
        """/workspace file paths in command should be rewritten to host workspace path."""
        report_path = tmp_path / "output" / "gold_price_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("report-ok", encoding="utf-8")
        set_workspace_root(tmp_path)

        tool = EnhancedBashTool()
        config = BashToolConfig(
            command=(
                "python3 -c \"from pathlib import Path; "
                "print(Path('/workspace/output/gold_price_report.md').read_text())\""
            )
        )

        result = tool.execute(config)

        assert result.success is True
        assert "report-ok" in result.stdout
    
    def test_pty_execution_success(self):
        """Test successful PTY execution."""
        tool = EnhancedBashTool()
        config = BashToolConfig(
            command="echo 'PTY Test'",
            pty=True
        )
        
        result = tool.execute(config)
        
        assert result.success is True
        assert "PTY Test" in result.stdout
        assert result.exit_code == 0
    
    def test_pty_execution_with_colors(self):
        """Test PTY execution preserves ANSI codes."""
        tool = EnhancedBashTool()
        # Use printf to output ANSI color codes
        config = BashToolConfig(
            command="printf '\\033[31mRed Text\\033[0m'",
            pty=True
        )
        
        result = tool.execute(config)
        
        assert result.success is True
        # PTY should preserve ANSI codes
        assert "Red Text" in result.stdout
    
    def test_pty_execution_timeout(self):
        """Test PTY execution timeout."""
        tool = EnhancedBashTool()
        config = BashToolConfig(
            command="sleep 10",
            pty=True,
            timeout=1
        )
        
        result = tool.execute(config)
        
        assert result.success is False
        assert "Timeout" in result.stdout or result.exit_code != 0
    
    def test_background_execution_without_manager(self):
        """Test background execution fails without ProcessManager."""
        tool = EnhancedBashTool(process_manager=None)
        config = BashToolConfig(
            command="echo 'background'",
            background=True
        )
        
        result = tool.execute(config)
        
        assert result.success is False
        assert "ProcessManager" in result.stderr or "ProcessManager" in result.error_message
    
    def test_background_execution_with_manager(self):
        """Test background execution with ProcessManager."""
        process_manager = ProcessManager()
        tool = EnhancedBashTool(process_manager=process_manager)
        config = BashToolConfig(
            command="echo 'background test'",
            background=True
        )
        
        result = tool.execute(config)

        assert result.success is True
        assert result.session_id is not None
        assert "session id" in result.stdout.lower()
        
        # Verify session exists
        status = process_manager.poll(result.session_id)
        assert status.value in ["running", "completed"]

    def test_background_execution_rewrites_workspace_paths(self, tmp_path: Path):
        """Background command should receive workspace-mapped command and workdir."""
        class MockProcessManager:
            def __init__(self):
                self.captured_config = None

            def start_process(self, config):
                self.captured_config = config
                return "session-1"

        mock_process_manager = MockProcessManager()
        set_workspace_root(tmp_path)
        tool = EnhancedBashTool(process_manager=mock_process_manager)
        config = BashToolConfig(
            command="cat /workspace/output/file.txt",
            workdir="/workspace/output",
            background=True,
        )

        result = tool.execute(config)

        assert result.success is True
        assert result.session_id == "session-1"
        assert mock_process_manager.captured_config is not None
        assert mock_process_manager.captured_config.workdir == str(
            (tmp_path / "output").resolve()
        )
        assert str((tmp_path / "output" / "file.txt").resolve()) in (
            mock_process_manager.captured_config.command
        )


class TestCreateBashTool:
    """Test create_bash_tool function."""
    
    def test_create_tool_without_process_manager(self):
        """Test creating tool without ProcessManager."""
        agent_id = uuid4()
        user_id = uuid4()
        
        tool = create_bash_tool(agent_id, user_id)
        
        assert tool.name == "bash"
        assert "Execute bash commands" in tool.description
    
    def test_create_tool_with_process_manager(self):
        """Test creating tool with ProcessManager."""
        agent_id = uuid4()
        user_id = uuid4()
        process_manager = ProcessManager()
        
        tool = create_bash_tool(agent_id, user_id, process_manager)
        
        assert tool.name == "bash"
        assert "Execute bash commands" in tool.description
    
    def test_tool_execution_normal(self):
        """Test tool execution in normal mode."""
        agent_id = uuid4()
        user_id = uuid4()
        tool = create_bash_tool(agent_id, user_id)
        
        result = tool.func(command="echo 'test'")
        
        assert "test" in result
    
    def test_tool_execution_pty(self):
        """Test tool execution in PTY mode."""
        agent_id = uuid4()
        user_id = uuid4()
        tool = create_bash_tool(agent_id, user_id)
        
        result = tool.func(command="echo 'pty test'", pty=True)
        
        assert "pty test" in result
    
    def test_tool_execution_background(self):
        """Test tool execution in background mode."""
        agent_id = uuid4()
        user_id = uuid4()
        process_manager = ProcessManager()
        tool = create_bash_tool(agent_id, user_id, process_manager)
        
        result = tool.func(command="sleep 1", background=True)
        
        assert "Background process started" in result or "Session ID" in result
    
    def test_tool_execution_error(self):
        """Test tool execution with error."""
        agent_id = uuid4()
        user_id = uuid4()
        tool = create_bash_tool(agent_id, user_id)
        
        result = tool.func(command="exit 1")
        
        assert "failed" in result.lower() or "error" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
