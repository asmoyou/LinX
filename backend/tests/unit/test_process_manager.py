"""Unit tests for Process Manager.

Tests cover:
- Process creation and lifecycle
- Output capture
- Process termination
- Session management
"""

import pytest
import time
from agent_framework.tools.process_manager import (
    ProcessManager,
    ProcessStatus,
    ProcessSession,
    RingBuffer
)
from agent_framework.tools.bash_tool import BashToolConfig


class TestRingBuffer:
    """Test RingBuffer class."""
    
    def test_write_and_read(self):
        """Test basic write and read operations."""
        buffer = RingBuffer(max_size=100)
        
        buffer.write("line 1\n")
        buffer.write("line 2\n")
        buffer.write("line 3\n")
        
        content = buffer.read()
        assert "line 1" in content
        assert "line 2" in content
        assert "line 3" in content
    
    def test_auto_truncate(self):
        """Test automatic truncation when exceeding max_size."""
        buffer = RingBuffer(max_size=50)
        
        # Write more than max_size
        for i in range(20):
            buffer.write(f"line {i}\n")
        
        content = buffer.read()
        
        # Should only keep last ~50 bytes
        assert len(content) <= 50
        # Should have recent lines
        assert "line 19" in content or "line 18" in content
    
    def test_read_with_offset_and_limit(self):
        """Test reading with offset and limit."""
        buffer = RingBuffer(max_size=1000)
        
        for i in range(10):
            buffer.write(f"line {i}\n")
        
        # Read lines 2-4
        content = buffer.read(offset=2, limit=3)
        lines = content.split('\n')
        
        assert len(lines) <= 4  # 3 lines + possible empty line
        assert "line 2" in content
        assert "line 3" in content
        assert "line 4" in content
    
    def test_clear(self):
        """Test buffer clearing."""
        buffer = RingBuffer(max_size=100)
        
        buffer.write("test data\n")
        buffer.clear()
        
        content = buffer.read()
        assert content == ""


class TestProcessManager:
    """Test ProcessManager class."""
    
    def test_start_process_simple(self):
        """Test starting a simple process."""
        manager = ProcessManager()
        config = BashToolConfig(command="echo 'test'")
        
        session_id = manager.start_process(config)
        
        assert session_id is not None
        assert len(session_id) > 0
        
        # Wait a bit for process to complete
        time.sleep(0.5)
        
        # Check status
        status = manager.poll(session_id)
        assert status in [ProcessStatus.RUNNING, ProcessStatus.COMPLETED]
    
    def test_start_process_with_workdir(self):
        """Test starting process with working directory."""
        manager = ProcessManager()
        config = BashToolConfig(
            command="pwd",
            workdir="/tmp"
        )
        
        session_id = manager.start_process(config)
        
        # Wait for completion
        time.sleep(0.5)
        
        # Get output
        output = manager.get_output(session_id)
        assert "/tmp" in output
    
    def test_poll_running_process(self):
        """Test polling a running process."""
        manager = ProcessManager()
        config = BashToolConfig(command="sleep 2")
        
        session_id = manager.start_process(config)
        
        # Should be running immediately
        status = manager.poll(session_id)
        assert status == ProcessStatus.RUNNING
    
    def test_poll_completed_process(self):
        """Test polling a completed process."""
        manager = ProcessManager()
        config = BashToolConfig(command="echo 'done'")
        
        session_id = manager.start_process(config)
        
        # Wait for completion
        time.sleep(1)
        
        status = manager.poll(session_id)
        assert status == ProcessStatus.COMPLETED
    
    def test_poll_nonexistent_session(self):
        """Test polling non-existent session."""
        manager = ProcessManager()
        
        status = manager.poll("nonexistent-id")
        assert status == ProcessStatus.NOT_FOUND
    
    def test_get_output(self):
        """Test getting process output."""
        manager = ProcessManager()
        config = BashToolConfig(command="echo 'output test'")
        
        session_id = manager.start_process(config)
        
        # Wait for output
        time.sleep(0.5)
        
        output = manager.get_output(session_id)
        assert "output test" in output
    
    def test_get_output_with_stderr(self):
        """Test getting output with stderr."""
        manager = ProcessManager()
        config = BashToolConfig(command="echo 'error' >&2")
        
        session_id = manager.start_process(config)
        
        # Wait for output
        time.sleep(0.5)
        
        output = manager.get_output(session_id)
        # stderr should be prefixed with [STDERR]
        assert "[STDERR]" in output and "error" in output
    
    def test_write_input(self):
        """Test writing to process stdin."""
        manager = ProcessManager()
        # Use cat to echo input
        config = BashToolConfig(command="cat")
        
        session_id = manager.start_process(config)
        
        # Write input
        time.sleep(0.2)
        success = manager.write_input(session_id, "test input\n")
        assert success is True
        
        # Give it time to process
        time.sleep(0.3)
        
        # Kill the process (cat runs forever)
        manager.kill(session_id)
        
        # Check output
        output = manager.get_output(session_id)
        assert "test input" in output
    
    def test_submit_input(self):
        """Test submitting input (with newline)."""
        manager = ProcessManager()
        config = BashToolConfig(command="cat")
        
        session_id = manager.start_process(config)
        
        # Submit input (automatically adds newline)
        time.sleep(0.2)
        success = manager.submit_input(session_id, "submitted")
        assert success is True
        
        time.sleep(0.3)
        manager.kill(session_id)
        
        output = manager.get_output(session_id)
        assert "submitted" in output
    
    def test_kill_process(self):
        """Test killing a process."""
        manager = ProcessManager()
        config = BashToolConfig(command="sleep 100")
        
        session_id = manager.start_process(config)
        
        # Verify it's running
        time.sleep(0.2)
        status = manager.poll(session_id)
        assert status == ProcessStatus.RUNNING
        
        # Kill it
        success = manager.kill(session_id)
        assert success is True
        
        # Wait a bit
        time.sleep(0.5)
        
        # Verify it's killed
        status = manager.poll(session_id)
        assert status == ProcessStatus.KILLED
    
    def test_list_sessions(self):
        """Test listing all sessions."""
        manager = ProcessManager()
        
        # Start a few processes
        config1 = BashToolConfig(command="echo 'test1'")
        config2 = BashToolConfig(command="echo 'test2'")
        
        session_id1 = manager.start_process(config1)
        session_id2 = manager.start_process(config2)
        
        # List sessions
        sessions = manager.list_sessions()
        
        assert len(sessions) >= 2
        session_ids = [s["session_id"] for s in sessions]
        assert session_id1 in session_ids
        assert session_id2 in session_ids
    
    def test_max_processes_limit(self):
        """Test maximum process limit."""
        manager = ProcessManager(max_processes=2)
        
        # Start max processes
        config = BashToolConfig(command="sleep 10")
        session_id1 = manager.start_process(config)
        session_id2 = manager.start_process(config)
        
        # Try to start one more (should fail)
        with pytest.raises(RuntimeError, match="Maximum processes"):
            manager.start_process(config)
        
        # Clean up
        manager.kill(session_id1)
        manager.kill(session_id2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
