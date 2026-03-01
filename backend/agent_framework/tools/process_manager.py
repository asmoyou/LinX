"""Process Manager for background process execution and monitoring.

This module provides background process management with output buffering,
session tracking, and process lifecycle management.

References:
- Requirements: .kiro/specs/code-execution-improvement/requirements.md
- Design: .kiro/specs/code-execution-improvement/design.md
- OpenClaw: examples-of-reference/openclaw/skills/coding-agent/SKILL.md
"""

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from agent_framework.sandbox_policy import allow_host_execution_fallback

logger = logging.getLogger(__name__)


class ProcessStatus(Enum):
    """Process status enumeration."""
    
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    NOT_FOUND = "not_found"


@dataclass
class ProcessSession:
    """Background process session."""
    
    session_id: str
    process: subprocess.Popen
    command: str
    started_at: datetime
    workdir: Optional[str] = None
    status: ProcessStatus = ProcessStatus.RUNNING
    exit_code: Optional[int] = None
    completed_at: Optional[datetime] = None


class RingBuffer:
    """Ring buffer for process output with size limit.
    
    Automatically truncates old data when exceeding max_size to prevent
    memory issues with long-running processes.
    """
    
    def __init__(self, max_size: int = 100000):
        """Initialize ring buffer.
        
        Args:
            max_size: Maximum buffer size in bytes (default: 100KB)
        """
        self.max_size = max_size
        self.buffer = ""
        self.lock = threading.Lock()
    
    def write(self, data: str) -> None:
        """Write data to buffer.
        
        Args:
            data: Data to append
        """
        with self.lock:
            self.buffer += data
            if len(self.buffer) > self.max_size:
                # Keep last max_size bytes
                self.buffer = self.buffer[-self.max_size:]
    
    def read(self, offset: int = 0, limit: int = 1000) -> str:
        """Read from buffer.
        
        Args:
            offset: Line offset (0-based)
            limit: Maximum number of lines to return
        
        Returns:
            Buffer content
        """
        with self.lock:
            lines = self.buffer.split('\n')
            selected_lines = lines[offset:offset + limit]
            return '\n'.join(selected_lines)
    
    def clear(self) -> None:
        """Clear buffer."""
        with self.lock:
            self.buffer = ""


class ProcessManager:
    """Manages background processes with output capture and monitoring.
    
    Features:
    - Start processes in background
    - Capture stdout/stderr in ring buffers
    - Monitor process status
    - Send input to stdin
    - Terminate processes
    - Automatic cleanup of old sessions
    """
    
    def __init__(self, max_processes: int = 50, buffer_size: int = 100000):
        """Initialize process manager.
        
        Args:
            max_processes: Maximum concurrent processes
            buffer_size: Output buffer size per process
        """
        self.max_processes = max_processes
        self.buffer_size = buffer_size
        self.sessions: Dict[str, ProcessSession] = {}
        self.output_buffers: Dict[str, RingBuffer] = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True
        )
        self.cleanup_thread.start()
    
    def start_process(self, config) -> str:
        """Start background process.
        
        Args:
            config: BashToolConfig with command and settings
        
        Returns:
            Session ID for monitoring
        
        Raises:
            RuntimeError: If max processes exceeded
        """
        if not allow_host_execution_fallback():
            raise RuntimeError(
                "Host background process execution is disabled by sandbox isolation policy."
            )

        with self.lock:
            # Check process limit
            active_count = sum(
                1 for s in self.sessions.values()
                if s.status == ProcessStatus.RUNNING
            )
            if active_count >= self.max_processes:
                raise RuntimeError(
                    f"Maximum processes ({self.max_processes}) exceeded"
                )
        
        session_id = str(uuid4())
        
        # Prepare environment
        env = os.environ.copy()
        if config.env:
            env.update(config.env)
        
        self.logger.info(
            f"Starting background process",
            extra={
                "session_id": session_id,
                "command": config.command[:100],
                "workdir": config.workdir
            }
        )
        
        try:
            # Start process
            process = subprocess.Popen(
                config.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                cwd=config.workdir,
                env=env,
                text=True,
                bufsize=1  # Line buffered
            )
            
            # Create session
            session = ProcessSession(
                session_id=session_id,
                process=process,
                command=config.command,
                started_at=datetime.now(),
                workdir=config.workdir
            )
            
            # Create output buffer
            output_buffer = RingBuffer(max_size=self.buffer_size)
            
            with self.lock:
                self.sessions[session_id] = session
                self.output_buffers[session_id] = output_buffer
            
            # Start output capture threads
            self._start_output_capture(session_id, process, output_buffer)
            
            self.logger.info(
                f"Background process started",
                extra={"session_id": session_id, "pid": process.pid}
            )
            
            return session_id
        
        except Exception as e:
            self.logger.error(f"Failed to start process: {e}")
            raise
    
    def _start_output_capture(
        self,
        session_id: str,
        process: subprocess.Popen,
        buffer: RingBuffer
    ) -> None:
        """Start threads to capture stdout and stderr.
        
        Args:
            session_id: Session ID
            process: Process to monitor
            buffer: Output buffer
        """
        def capture_stream(stream, prefix):
            """Capture output from stream."""
            try:
                for line in stream:
                    buffer.write(f"{prefix}{line}")
            except Exception as e:
                self.logger.error(f"Output capture error: {e}")
        
        # Start stdout capture thread
        stdout_thread = threading.Thread(
            target=capture_stream,
            args=(process.stdout, ""),
            daemon=True
        )
        stdout_thread.start()
        
        # Start stderr capture thread
        stderr_thread = threading.Thread(
            target=capture_stream,
            args=(process.stderr, "[STDERR] "),
            daemon=True
        )
        stderr_thread.start()
        
        # Start status monitor thread
        def monitor_status():
            """Monitor process completion."""
            exit_code = process.wait()
            
            with self.lock:
                if session_id in self.sessions:
                    session = self.sessions[session_id]
                    session.exit_code = exit_code
                    session.completed_at = datetime.now()
                    
                    if exit_code == 0:
                        session.status = ProcessStatus.COMPLETED
                    else:
                        session.status = ProcessStatus.FAILED
                    
                    self.logger.info(
                        f"Process completed",
                        extra={
                            "session_id": session_id,
                            "exit_code": exit_code,
                            "status": session.status.value
                        }
                    )
        
        monitor_thread = threading.Thread(
            target=monitor_status,
            daemon=True
        )
        monitor_thread.start()
    
    def poll(self, session_id: str) -> ProcessStatus:
        """Check if process is still running.
        
        Args:
            session_id: Session ID
        
        Returns:
            Process status
        """
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return ProcessStatus.NOT_FOUND
            return session.status
    
    def get_output(
        self,
        session_id: str,
        offset: int = 0,
        limit: int = 1000
    ) -> str:
        """Get process output.
        
        Args:
            session_id: Session ID
            offset: Line offset
            limit: Maximum lines to return
        
        Returns:
            Process output
        """
        buffer = self.output_buffers.get(session_id)
        if not buffer:
            return f"Session not found: {session_id}"
        
        return buffer.read(offset, limit)
    
    def write_input(self, session_id: str, data: str) -> bool:
        """Write to process stdin.
        
        Args:
            session_id: Session ID
            data: Data to write (without newline)
        
        Returns:
            True if successful
        """
        with self.lock:
            session = self.sessions.get(session_id)
            if not session or session.status != ProcessStatus.RUNNING:
                return False
        
        try:
            session.process.stdin.write(data)
            session.process.stdin.flush()
            return True
        except Exception as e:
            self.logger.error(f"Failed to write input: {e}")
            return False
    
    def submit_input(self, session_id: str, data: str) -> bool:
        """Submit data to stdin (with newline).
        
        Like typing text and pressing Enter.
        
        Args:
            session_id: Session ID
            data: Data to submit
        
        Returns:
            True if successful
        """
        return self.write_input(session_id, data + "\n")
    
    def kill(self, session_id: str) -> bool:
        """Terminate process.
        
        Args:
            session_id: Session ID
        
        Returns:
            True if successful
        """
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return False
        
        try:
            self.logger.info(
                f"Killing process",
                extra={"session_id": session_id}
            )
            
            session.process.terminate()
            
            # Wait up to 5 seconds for graceful termination
            try:
                session.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if still running
                session.process.kill()
                session.process.wait()
            
            with self.lock:
                session.status = ProcessStatus.KILLED
                session.completed_at = datetime.now()
            
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to kill process: {e}")
            return False
    
    def list_sessions(self) -> List[Dict]:
        """List all sessions.
        
        Returns:
            List of session information
        """
        with self.lock:
            sessions = []
            for session_id, session in self.sessions.items():
                sessions.append({
                    "session_id": session_id,
                    "command": session.command[:100],
                    "status": session.status.value,
                    "started_at": session.started_at.isoformat(),
                    "completed_at": (
                        session.completed_at.isoformat()
                        if session.completed_at else None
                    ),
                    "exit_code": session.exit_code,
                    "workdir": session.workdir
                })
            return sessions
    
    def _cleanup_loop(self) -> None:
        """Periodic cleanup of old sessions."""
        while True:
            try:
                time.sleep(3600)  # Run every hour
                self._cleanup_old_sessions()
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")
    
    def _cleanup_old_sessions(self) -> None:
        """Remove old completed sessions."""
        with self.lock:
            now = datetime.now()
            to_remove = []
            
            for session_id, session in self.sessions.items():
                # Remove sessions completed more than 24 hours ago
                if (session.status != ProcessStatus.RUNNING and
                    session.completed_at and
                    (now - session.completed_at).total_seconds() > 86400):
                    to_remove.append(session_id)
            
            for session_id in to_remove:
                del self.sessions[session_id]
                if session_id in self.output_buffers:
                    del self.output_buffers[session_id]
                
                self.logger.info(
                    f"Cleaned up old session",
                    extra={"session_id": session_id}
                )


# Global process manager instance
_process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """Get or create global process manager.
    
    Returns:
        ProcessManager instance
    """
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager
