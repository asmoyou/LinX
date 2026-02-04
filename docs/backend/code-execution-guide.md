# Code Execution Guide

Real code execution in secure Docker containers for LinX agents.

## Overview

This guide covers the code execution system that allows agents to run Python, JavaScript, and Bash code in isolated Docker containers with resource limits, security restrictions, and automatic dependency management.

## Quick Start

### Basic Python Execution

```python
from virtualization.code_execution_sandbox import get_code_execution_sandbox

sandbox = get_code_execution_sandbox()

code = """
print("Hello from Docker!")
result = 2 + 2
print(f"2 + 2 = {result}")
"""

result = await sandbox.execute_code(
    code=code,
    language="python",
    context={"user_id": "123"}
)

print(result.output)  # Output from code execution
```

### With Automatic Dependency Detection

```python
code = """
import requests
response = requests.get('https://api.example.com')
print(response.status_code)
"""

result = await sandbox.execute_code(
    code=code,
    language="python",
    # Dependencies are automatically detected and installed
)
```

### With Explicit Dependencies

```python
result = await sandbox.execute_code(
    code=code,
    language="python",
    explicit_dependencies=["requests==2.28.0", "numpy"]
)
```

## Architecture

### Components

1. **CodeExecutionSandbox** (`backend/virtualization/code_execution_sandbox.py`)
   - Main entry point for code execution
   - Validates code before execution
   - Manages container lifecycle
   - Handles dependency installation

2. **ContainerManager** (`backend/virtualization/container_manager.py`)
   - Creates and manages Docker containers
   - Executes commands in containers
   - Writes files to containers
   - Monitors resource usage

3. **DependencyManager** (`backend/virtualization/dependency_manager.py`)
   - Detects dependencies from code
   - Caches installed dependencies
   - Generates installation scripts
   - Supports Python and JavaScript

4. **CodeValidator** (`backend/virtualization/code_validator.py`)
   - Static analysis of code
   - Security checks
   - Dangerous pattern detection

## Execution Flow

```
1. Code Submission
   ↓
2. Security Validation (CodeValidator)
   ↓
3. Dependency Detection (DependencyManager)
   ↓
4. Check Cache (DependencyManager)
   ↓
5. Create Container (ContainerManager)
   ↓
6. Install Dependencies (if needed)
   ↓
7. Inject Code (write to container)
   ↓
8. Execute Code (run interpreter)
   ↓
9. Capture Output (stdout/stderr)
   ↓
10. Cleanup Container
   ↓
11. Return Results
```

## Supported Languages

### Python

- **Interpreter**: `python3`
- **File Extension**: `.py`
- **Package Manager**: `pip`
- **Dependency Detection**: Automatic via AST parsing

```python
result = await sandbox.execute_code(
    code="print('Hello Python')",
    language="python"
)
```

### JavaScript/Node.js

- **Interpreter**: `node`
- **File Extension**: `.js`
- **Package Manager**: `npm`
- **Dependency Detection**: Automatic via regex

```python
result = await sandbox.execute_code(
    code="console.log('Hello Node')",
    language="javascript"
)
```

### Bash

- **Interpreter**: `/bin/bash`
- **File Extension**: `.sh`
- **Package Manager**: N/A
- **Dependency Detection**: N/A

```python
result = await sandbox.execute_code(
    code="echo 'Hello Bash'",
    language="bash"
)
```

## Security Features

### Container Isolation

- **Read-only root filesystem**: Prevents modification of system files
- **No new privileges**: Prevents privilege escalation
- **Dropped capabilities**: Removes dangerous Linux capabilities
- **Network isolation**: Optional network disabling
- **Resource limits**: CPU, memory, and time constraints

### Code Validation

Before execution, code is checked for:
- Dangerous imports (`os.system`, `eval`, `exec`)
- File system access patterns
- Network operations
- Subprocess spawning

### Resource Limits

Default limits per execution:
- **CPU**: 1.0 cores
- **Memory**: 512 MB
- **Timeout**: 30 seconds
- **Disk**: 100 MB (tmpfs)

## Dependency Management

### Automatic Detection

Dependencies are automatically detected from:
- Python: `import` and `from ... import` statements
- JavaScript: `import ... from` and `require()` statements

Standard library modules are filtered out.

### Caching

Installed dependencies are cached with:
- **Cache Key**: SHA256 hash of dependency set
- **TTL**: 24 hours (configurable)
- **Persistence**: Saved to disk
- **Reuse**: Automatic cache lookup before installation

### Performance

- **Cache Hit**: ~100ms (no installation needed)
- **Cache Miss**: ~5-30s (depends on packages)
- **Typical Speedup**: 50-100x for cached dependencies

## Container Management

### Docker API Integration

The system uses the Docker Python SDK (`docker-py`) to:
- Create containers with security configurations
- Start and stop containers
- Execute commands in running containers
- Write files to container filesystem
- Monitor resource usage
- Clean up containers

### Graceful Degradation

If Docker is not available:
- System falls back to simulation mode
- Logs warnings
- Returns mock results
- Allows development without Docker

## Error Handling

### Validation Errors

```python
result = await sandbox.execute_code(code="import os; os.system('rm -rf /')")
# result.success = False
# result.status = ExecutionStatus.FAILED
# result.error = "Security validation failed: dangerous import 'os.system'"
```

### Execution Errors

```python
result = await sandbox.execute_code(code="print(undefined_variable)")
# result.success = False
# result.error = "NameError: name 'undefined_variable' is not defined"
```

### Timeout Errors

```python
result = await sandbox.execute_code(
    code="import time; time.sleep(100)",
    timeout=5
)
# result.status = ExecutionStatus.TIMEOUT
# result.error = "Execution timeout after 5 seconds"
```

## Agent Integration

### CodeExecutionTool

Agents have access to code execution via the `code_execution` tool:

```python
from agent_framework.tools.code_execution_tool import create_code_execution_tool

tool = create_code_execution_tool(
    agent_id=agent.id,
    user_id=user.id
)

# Agent can now use the tool
result = tool.run(code="print('Hello')", language="python")
```

### Usage in Agent Prompts

Agents are instructed to use the tool like this:

```json
{
  "tool": "code_execution",
  "code": "import math\nprint(math.sqrt(16))",
  "language": "python"
}
```

## Testing

### Manual Testing

Run the test script:

```bash
cd backend
python test_real_execution.py
```

This will test:
- Basic Python execution
- Python with dependencies
- Bash script execution

### Unit Tests

```bash
cd backend
pytest tests/unit/test_dependency_manager.py -v
pytest tests/unit/virtualization/test_code_execution.py -v
```

## Configuration

### Environment Variables

```bash
# Docker settings
DOCKER_HOST=unix:///var/run/docker.sock

# Resource limits
CODE_EXECUTION_TIMEOUT=30
CODE_EXECUTION_MEMORY_MB=512
CODE_EXECUTION_CPU_CORES=1.0

# Dependency cache
DEPENDENCY_CACHE_DIR=/tmp/linx_dependency_cache
DEPENDENCY_CACHE_TTL_HOURS=24
```

### Container Image

Default image: `python:3.11-slim`

To use a custom image:

```python
from virtualization.container_manager import ContainerConfig

config = ContainerConfig(
    image="my-custom-image:latest",
    # ... other settings
)
```

## Troubleshooting

### Docker Not Available

**Symptom**: "Docker not available" warning in logs

**Solution**: 
- Install Docker: https://docs.docker.com/get-docker/
- Start Docker daemon
- Verify: `docker ps`

### Permission Denied

**Symptom**: "Permission denied" when accessing Docker

**Solution**:
- Add user to docker group: `sudo usermod -aG docker $USER`
- Restart session
- Or run with sudo (not recommended for production)

### Container Creation Fails

**Symptom**: "Container creation failed"

**Solution**:
- Check Docker is running: `docker info`
- Check available resources: `docker system df`
- Pull base image: `docker pull python:3.11-slim`

### Dependency Installation Fails

**Symptom**: "Dependency installation failed"

**Solution**:
- Check network connectivity in container
- Verify package names are correct
- Check pip/npm logs in error output
- Try with explicit versions

## Performance Optimization

### Tips for Faster Execution

1. **Use Dependency Caching**: Let the system cache dependencies
2. **Minimize Dependencies**: Only import what you need
3. **Reuse Containers**: Future enhancement (not yet implemented)
4. **Optimize Code**: Reduce execution time
5. **Use Explicit Dependencies**: Faster than auto-detection

### Benchmarks

Typical execution times:
- **Simple Python**: 100-500ms
- **Python with cached deps**: 200-800ms
- **Python with new deps**: 5-30s
- **Bash script**: 50-200ms

## Future Enhancements

Planned improvements:
- Docker image caching for dependencies
- Container reuse for multiple executions
- Support for more languages (Ruby, Go, Rust)
- Distributed caching with Redis
- GPU support for ML workloads
- Persistent storage volumes

## References

- Specification: `.kiro/specs/code-execution-improvement/`
- Dependency Management: `docs/backend/dependency-management.md`
- Container Manager: `backend/virtualization/container_manager.py`
- Code Execution Sandbox: `backend/virtualization/code_execution_sandbox.py`
- Docker SDK: https://docker-py.readthedocs.io/
