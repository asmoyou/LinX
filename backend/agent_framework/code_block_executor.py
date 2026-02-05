"""Code Block Executor - File-based execution of code from skills and LLM output.

Production-grade implementation that:
1. Writes code to files before execution (not inline -c)
2. Supports skill package code files (pre-existing scripts)
3. Falls back to LLM-generated code when no skill files exist
4. Integrates with sandbox for isolation

References:
- Design: .kiro/specs/code-execution-improvement/design.md
- Claude Code pattern: Write to file, then execute
- agenticSeek: examples-of-reference/agenticSeek/sources/tools/tools.py
"""

import asyncio
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass
class CodeBlock:
    """Represents a code block extracted from LLM output or skill package."""

    language: str  # python, bash, javascript, etc.
    code: str
    filename: Optional[str] = None
    description: Optional[str] = None
    source: str = "llm"  # "llm" or "skill_package"

    def __post_init__(self):
        """Normalize language names."""
        lang_map = {
            'py': 'python',
            'python3': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'sh': 'bash',
            'shell': 'bash',
            'zsh': 'bash',
        }
        self.language = lang_map.get(self.language.lower(), self.language.lower())

        # Generate filename if not provided
        if not self.filename:
            ext_map = {'python': '.py', 'bash': '.sh', 'javascript': '.js'}
            ext = ext_map.get(self.language, '.txt')
            self.filename = f"code_{uuid4().hex[:8]}{ext}"


@dataclass
class ExecutionResult:
    """Result of code execution."""

    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0
    execution_time: float = 0.0
    language: str = ""
    script_path: Optional[str] = None  # Path to executed script

    def to_feedback(self) -> str:
        """Format result as feedback for LLM."""
        if self.success:
            output_preview = self.output[:2000] if len(self.output) > 2000 else self.output
            return f"✅ 代码执行成功 ({self.execution_time:.2f}s):\n```\n{output_preview}\n```"
        else:
            error_preview = (self.error or self.output)[:2000]
            return f"❌ 代码执行失败 (exit code {self.exit_code}):\n```\n{error_preview}\n```"


class CodeBlockExecutor:
    """File-based code executor for production use.

    Execution Strategy:
    1. If skill package has code files -> copy to workdir and execute
    2. If LLM generates code blocks -> write to file and execute
    3. All execution goes through file (not inline -c)
    4. Optional sandbox integration for isolation

    Features:
    - File-based execution (safer, debuggable)
    - Skill package code file support
    - Working directory isolation per execution
    - Automatic cleanup
    - Sandbox integration (Docker container execution)
    """

    EXECUTABLE_LANGUAGES = {'python', 'bash'}
    MAX_OUTPUT_LENGTH = 100000  # 100KB

    def __init__(
        self,
        sandbox=None,
        use_sandbox: bool = False,
        default_timeout: int = 60,
        base_workdir: Optional[str] = None
    ):
        """Initialize code block executor.

        Args:
            sandbox: Optional CodeExecutionSandbox instance
            use_sandbox: Whether to use sandbox for execution
            default_timeout: Default timeout in seconds
            base_workdir: Base directory for code execution (default: /tmp/agent_code)
        """
        self.sandbox = sandbox
        self.use_sandbox = use_sandbox
        self.default_timeout = default_timeout
        self.base_workdir = Path(base_workdir or "/tmp/agent_code")
        self.base_workdir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

        # Container manager for Docker execution (lazy loaded)
        self._container_manager = None

    def _get_container_manager(self):
        """Get container manager instance (lazy load)."""
        if self._container_manager is None:
            try:
                from virtualization.container_manager import get_container_manager
                self._container_manager = get_container_manager()
            except ImportError:
                self.logger.warning("ContainerManager not available")
        return self._container_manager

    # Common third-party packages that need pip install (not in stdlib)
    # Maps import name -> pip package name (when different)
    THIRD_PARTY_PACKAGES = {
        # Data science
        'numpy': 'numpy',
        'np': 'numpy',
        'pandas': 'pandas',
        'pd': 'pandas',
        'scipy': 'scipy',
        'sklearn': 'scikit-learn',
        'matplotlib': 'matplotlib',
        'plt': 'matplotlib',
        'seaborn': 'seaborn',
        'sns': 'seaborn',
        'plotly': 'plotly',
        # Web/HTTP
        'requests': 'requests',
        'httpx': 'httpx',
        'aiohttp': 'aiohttp',
        'fastapi': 'fastapi',
        'flask': 'flask',
        'django': 'django',
        'bs4': 'beautifulsoup4',
        'BeautifulSoup': 'beautifulsoup4',
        'lxml': 'lxml',
        # Database
        'sqlalchemy': 'sqlalchemy',
        'pymongo': 'pymongo',
        'redis': 'redis',
        'psycopg2': 'psycopg2-binary',
        # ML/AI
        'torch': 'torch',
        'tensorflow': 'tensorflow',
        'tf': 'tensorflow',
        'keras': 'keras',
        'transformers': 'transformers',
        'openai': 'openai',
        'langchain': 'langchain',
        # Utils
        'PIL': 'pillow',
        'Image': 'pillow',
        'cv2': 'opencv-python',
        'yaml': 'pyyaml',
        'dotenv': 'python-dotenv',
        'tqdm': 'tqdm',
        'rich': 'rich',
        'click': 'click',
        'typer': 'typer',
        'pydantic': 'pydantic',
        'pytest': 'pytest',
        'sympy': 'sympy',
        'networkx': 'networkx',
        'openpyxl': 'openpyxl',
        'xlrd': 'xlrd',
        'docx': 'python-docx',
        'PyPDF2': 'PyPDF2',
        'pypdf': 'pypdf',
        'chardet': 'chardet',
        'cryptography': 'cryptography',
        'jwt': 'pyjwt',
        'arrow': 'arrow',
        'pendulum': 'pendulum',
        'dateutil': 'python-dateutil',
    }

    def _extract_imports_from_code(self, code: str) -> set:
        """Extract import statements from Python code.

        Args:
            code: Python source code

        Returns:
            Set of top-level module names
        """
        imports = set()

        # Pattern for: import xxx, import xxx as yyy
        import_pattern = r'^import\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        # Pattern for: from xxx import yyy
        from_pattern = r'^from\s+([a-zA-Z_][a-zA-Z0-9_]*)'

        for line in code.split('\n'):
            line = line.strip()
            # Skip comments
            if line.startswith('#'):
                continue

            match = re.match(import_pattern, line)
            if match:
                imports.add(match.group(1))
                continue

            match = re.match(from_pattern, line)
            if match:
                imports.add(match.group(1))

        return imports

    def _get_packages_to_install(self, imports: set) -> List[str]:
        """Determine which packages need to be pip installed.

        Args:
            imports: Set of import names

        Returns:
            List of pip package names to install
        """
        packages = []
        for imp in imports:
            if imp in self.THIRD_PARTY_PACKAGES:
                pkg = self.THIRD_PARTY_PACKAGES[imp]
                if pkg not in packages:
                    packages.append(pkg)
        return packages

    async def _auto_install_dependencies(
        self,
        container_id: str,
        container_manager,
        workdir: Path,
        container_workdir: str,
        script_path: Path
    ) -> None:
        """Auto-detect and install Python dependencies.

        Strategy:
        1. If requirements.txt exists, use it (highest priority)
        2. Otherwise, parse imports from Python files and install known packages

        Args:
            container_id: Docker container ID
            container_manager: ContainerManager instance
            workdir: Host working directory
            container_workdir: Container working directory
            script_path: Path to the script being executed
        """
        packages_to_install = []

        # Strategy 1: Check for requirements.txt
        requirements_file = workdir / "requirements.txt"
        if requirements_file.exists():
            self.logger.info(
                "[CODE_BLOCK] Found requirements.txt, installing dependencies",
                extra={"container_id": container_id}
            )
            try:
                exit_code, stdout, stderr = container_manager.exec_in_container(
                    container_id,
                    f"pip install -q -r {container_workdir}/requirements.txt",
                )
                if exit_code == 0:
                    self.logger.info(
                        "[CODE_BLOCK] Dependencies installed from requirements.txt",
                        extra={"container_id": container_id}
                    )
                else:
                    self.logger.warning(
                        f"[CODE_BLOCK] Failed to install from requirements.txt: {stderr}",
                        extra={"container_id": container_id}
                    )
            except Exception as e:
                self.logger.warning(f"[CODE_BLOCK] Error installing requirements: {e}")
            return  # Don't do import analysis if requirements.txt exists

        # Strategy 2: Parse imports from all Python files
        all_imports = set()
        for py_file in workdir.glob("*.py"):
            try:
                code = py_file.read_text(encoding='utf-8')
                imports = self._extract_imports_from_code(code)
                all_imports.update(imports)
            except Exception as e:
                self.logger.debug(f"[CODE_BLOCK] Failed to parse {py_file.name}: {e}")

        # Determine packages to install
        packages_to_install = self._get_packages_to_install(all_imports)

        if not packages_to_install:
            self.logger.debug(
                "[CODE_BLOCK] No third-party packages detected",
                extra={"container_id": container_id, "imports": list(all_imports)}
            )
            return

        self.logger.info(
            f"[CODE_BLOCK] Auto-detected packages to install: {packages_to_install}",
            extra={"container_id": container_id, "imports": list(all_imports)}
        )

        # Install packages
        packages_str = " ".join(packages_to_install)
        try:
            exit_code, stdout, stderr = container_manager.exec_in_container(
                container_id,
                f"pip install -q {packages_str}",
            )
            if exit_code == 0:
                self.logger.info(
                    f"[CODE_BLOCK] Auto-installed packages: {packages_to_install}",
                    extra={"container_id": container_id}
                )
            else:
                self.logger.warning(
                    f"[CODE_BLOCK] Some packages failed to install: {stderr}",
                    extra={"container_id": container_id, "packages": packages_to_install}
                )
        except Exception as e:
            self.logger.warning(f"[CODE_BLOCK] Error auto-installing packages: {e}")

    def extract_blocks(self, text: str) -> List[CodeBlock]:
        """Extract code blocks from LLM output text.

        Recognizes markdown-style fenced code blocks:
        ```language [filename]
        code here
        ```

        Args:
            text: Text containing code blocks

        Returns:
            List of extracted CodeBlock objects
        """
        blocks = []

        # Pattern: ```language [filename]\ncode\n```
        pattern = r'```(\w+)(?:\s+([^\n]+\.[\w]+))?\s*\n(.*?)\n```'

        for match in re.finditer(pattern, text, re.DOTALL):
            language = match.group(1)
            filename = match.group(2).strip() if match.group(2) else None
            code = match.group(3)

            if not code or not code.strip():
                continue

            # Extract description from preceding text
            start_pos = match.start()
            preceding = text[max(0, start_pos - 200):start_pos]
            description = self._extract_description(preceding)

            block = CodeBlock(
                language=language,
                code=code,
                filename=filename,
                description=description,
                source="llm"
            )
            blocks.append(block)

            self.logger.debug(
                f"Extracted {language} code block ({len(code)} chars)",
                extra={"language": language, "script_name": block.filename}
            )

        return blocks

    def _extract_description(self, preceding_text: str) -> Optional[str]:
        """Extract description from text preceding a code block."""
        lines = preceding_text.strip().split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith('```'):
                line = re.sub(r'[#*_`]', '', line)
                return line.strip()[:100]
        return None

    def get_executable_blocks(self, text: str) -> List[CodeBlock]:
        """Extract only executable code blocks (python, bash)."""
        blocks = self.extract_blocks(text)
        return [b for b in blocks if b.language in self.EXECUTABLE_LANGUAGES]

    def create_workdir(self, session_id: Optional[str] = None) -> Path:
        """Create isolated working directory for execution.

        Args:
            session_id: Optional session ID for directory naming

        Returns:
            Path to working directory
        """
        session_id = session_id or uuid4().hex[:8]
        workdir = self.base_workdir / f"session_{session_id}"
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    async def execute_skill_code(
        self,
        skill_code_files: Dict[str, str],
        entry_point: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        session_id: Optional[str] = None
    ) -> ExecutionResult:
        """Execute code from skill package files.

        This is the preferred execution method when skill has code files.

        Args:
            skill_code_files: Dict mapping filename -> code content
            entry_point: Main file to execute (e.g., "main.py")
            args: Command line arguments
            env: Environment variables
            timeout: Execution timeout
            session_id: Session ID for workdir

        Returns:
            ExecutionResult
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()

        # Create isolated workdir
        workdir = self.create_workdir(session_id)

        self.logger.info(
            f"[CODE_EXEC] Executing skill code: {entry_point}",
            extra={
                "entry_point": entry_point,
                "file_count": len(skill_code_files),
                "workdir": str(workdir)
            }
        )

        try:
            # Write all code files to workdir
            for filename, content in skill_code_files.items():
                file_path = workdir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding='utf-8')

                # Make shell scripts executable
                if filename.endswith('.sh'):
                    file_path.chmod(0o755)

                self.logger.debug(f"Wrote file: {file_path}")

            # Determine execution command
            entry_path = workdir / entry_point
            if not entry_path.exists():
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Entry point not found: {entry_point}",
                    exit_code=-1,
                    execution_time=time.time() - start_time
                )

            # Execute based on file type
            if entry_point.endswith('.py'):
                result = await self._execute_python_file(
                    entry_path, args, env, timeout, workdir
                )
            elif entry_point.endswith('.sh'):
                result = await self._execute_bash_file(
                    entry_path, args, env, timeout, workdir
                )
            else:
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Unsupported file type: {entry_point}",
                    exit_code=-1,
                    execution_time=time.time() - start_time
                )

            result.execution_time = time.time() - start_time
            result.script_path = str(entry_path)
            return result

        except Exception as e:
            self.logger.error(f"[CODE_EXEC] Skill execution error: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                execution_time=time.time() - start_time
            )

    async def execute(
        self,
        block: CodeBlock,
        timeout: Optional[int] = None,
        workdir: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None,
        container_id: Optional[str] = None
    ) -> ExecutionResult:
        """Execute a code block by writing to file first.

        Args:
            block: CodeBlock to execute
            timeout: Execution timeout in seconds
            workdir: Working directory (created if None)
            env: Environment variables
            session_id: Session ID for workdir naming
            container_id: Docker container ID for sandbox execution

        Returns:
            ExecutionResult with output
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()

        # Create workdir if not provided
        if workdir is None:
            workdir = self.create_workdir(session_id)

        execution_mode = "container" if container_id else "subprocess"
        self.logger.info(
            f"[CODE_BLOCK] Executing {block.language} block -> {block.filename} (mode: {execution_mode})",
            extra={
                "language": block.language,
                "script_name": block.filename,
                "code_length": len(block.code),
                "workdir": str(workdir),
                "source": block.source,
                "execution_mode": execution_mode,
                "container_id": container_id
            }
        )

        try:
            # Write code to file
            script_path = workdir / block.filename
            script_path.write_text(block.code, encoding='utf-8')

            # Make bash scripts executable
            if block.language == 'bash':
                script_path.chmod(0o755)

            self.logger.debug(f"Wrote code to: {script_path}")

            # Execute file - use container if provided
            if container_id:
                # Docker sandbox execution
                result = await self._execute_in_container(
                    container_id, block.language, script_path, env, timeout, workdir
                )
            elif block.language == 'python':
                result = await self._execute_python_file(
                    script_path, None, env, timeout, workdir
                )
            elif block.language == 'bash':
                result = await self._execute_bash_file(
                    script_path, None, env, timeout, workdir
                )
            else:
                result = ExecutionResult(
                    success=False,
                    output="",
                    error=f"Unsupported language: {block.language}",
                    exit_code=-1,
                    language=block.language
                )

            result.execution_time = time.time() - start_time
            result.language = block.language
            result.script_path = str(script_path)

            self.logger.info(
                f"[CODE_BLOCK] Execution {'success' if result.success else 'failed'}",
                extra={
                    "language": block.language,
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "execution_time": result.execution_time,
                    "script_path": str(script_path)
                }
            )

            return result

        except Exception as e:
            self.logger.error(f"[CODE_BLOCK] Execution error: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                execution_time=time.time() - start_time,
                language=block.language
            )

    async def _execute_in_container(
        self,
        container_id: str,
        language: str,
        script_path: Path,
        env: Optional[Dict[str, str]],
        timeout: int,
        workdir: Path
    ) -> ExecutionResult:
        """Execute code in a Docker container.

        This method:
        1. Copies the script file to the container
        2. Auto-detects and installs dependencies (requirements.txt or imports)
        3. Executes the script inside the container
        4. Returns the output

        Args:
            container_id: Docker container ID
            language: Programming language (python, bash)
            script_path: Path to script file on host
            env: Environment variables
            timeout: Execution timeout in seconds
            workdir: Working directory on host

        Returns:
            ExecutionResult with output
        """
        start_time = time.time()

        container_manager = self._get_container_manager()
        if container_manager is None or not container_manager.docker_available:
            self.logger.warning(
                "[CODE_BLOCK] Docker not available, falling back to subprocess",
                extra={"container_id": container_id}
            )
            # Fallback to subprocess execution
            if language == 'python':
                return await self._execute_python_file(script_path, None, env, timeout, workdir)
            elif language == 'bash':
                return await self._execute_bash_file(script_path, None, env, timeout, workdir)
            else:
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Unsupported language: {language}",
                    exit_code=-1,
                    language=language
                )

        try:
            # Container workdir - uses /workspace which is volume-mounted from host workdir
            # Files (skills, scripts) written to host workdir are immediately available here
            container_workdir = "/workspace"
            container_script_name = script_path.name

            # No need to create workdir or copy files - volume mount makes
            # host workdir available at /workspace automatically.
            # Scripts and skill files written to host workdir are immediately visible.

            # Auto-install dependencies for Python scripts
            if language == 'python':
                await self._auto_install_dependencies(
                    container_id, container_manager, workdir, container_workdir, script_path
                )

            # Build execution command
            container_script_path = f"{container_workdir}/{container_script_name}"

            if language == 'python':
                cmd = f"cd {container_workdir} && python3 {container_script_path}"
            elif language == 'bash':
                cmd = f"cd {container_workdir} && bash {container_script_path}"
            else:
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Unsupported language for container execution: {language}",
                    exit_code=-1,
                    language=language
                )

            # Add environment variables to command
            if env:
                env_exports = " ".join([f"{k}='{v}'" for k, v in env.items()])
                cmd = f"export {env_exports} && {cmd}"

            self.logger.info(
                f"[CODE_BLOCK] Executing in container: {cmd[:100]}...",
                extra={
                    "container_id": container_id,
                    "language": language,
                    "script": container_script_name
                }
            )

            # Execute in container
            # Note: container_manager.exec_in_container is synchronous, wrap for async
            loop = asyncio.get_event_loop()
            exit_code, stdout, stderr = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: container_manager.exec_in_container(
                        container_id,
                        cmd,
                        workdir=container_workdir,
                        environment=env
                    )
                ),
                timeout=timeout
            )

            # Truncate output if needed
            if len(stdout) > self.MAX_OUTPUT_LENGTH:
                stdout = stdout[:self.MAX_OUTPUT_LENGTH] + "\n... [output truncated]"

            execution_time = time.time() - start_time

            self.logger.info(
                f"[CODE_BLOCK] Container execution completed",
                extra={
                    "container_id": container_id,
                    "exit_code": exit_code,
                    "execution_time": execution_time,
                    "output_length": len(stdout)
                }
            )

            return ExecutionResult(
                success=exit_code == 0,
                output=stdout,
                error=stderr if stderr else None,
                exit_code=exit_code,
                language=language,
                execution_time=execution_time,
                script_path=str(script_path)
            )

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            self.logger.warning(
                f"[CODE_BLOCK] Container execution timed out after {timeout}s",
                extra={"container_id": container_id, "timeout": timeout}
            )
            return ExecutionResult(
                success=False,
                output="",
                error=f"⏱️ Execution timed out after {timeout} seconds in container.",
                exit_code=-1,
                language=language,
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(
                f"[CODE_BLOCK] Container execution error: {e}",
                extra={"container_id": container_id},
                exc_info=True
            )
            return ExecutionResult(
                success=False,
                output="",
                error=f"Container execution error: {str(e)}",
                exit_code=-1,
                language=language,
                execution_time=execution_time
            )

    async def _execute_python_file(
        self,
        script_path: Path,
        args: Optional[List[str]],
        env: Optional[Dict[str, str]],
        timeout: int,
        workdir: Path
    ) -> ExecutionResult:
        """Execute Python script file with proper process group management."""
        import signal

        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        # Add workdir to PYTHONPATH for local imports
        pythonpath = exec_env.get('PYTHONPATH', '')
        exec_env['PYTHONPATH'] = f"{workdir}:{pythonpath}" if pythonpath else str(workdir)

        cmd = ['python3', str(script_path)]
        if args:
            cmd.extend(args)

        try:
            # Create process in new process group for proper cleanup
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workdir),
                env=exec_env,
                start_new_session=True  # Creates new process group
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                stdout_str = stdout.decode('utf-8', errors='replace')
                stderr_str = stderr.decode('utf-8', errors='replace')

                if len(stdout_str) > self.MAX_OUTPUT_LENGTH:
                    stdout_str = stdout_str[:self.MAX_OUTPUT_LENGTH] + "\n... [output truncated]"

                return ExecutionResult(
                    success=process.returncode == 0,
                    output=stdout_str,
                    error=stderr_str if stderr_str else None,
                    exit_code=process.returncode,
                    language="python"
                )

            except asyncio.TimeoutError:
                # Kill entire process group to ensure all child processes are terminated
                try:
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    await asyncio.sleep(0.5)
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                except (ProcessLookupError, PermissionError):
                    process.kill()

                await process.wait()

                self.logger.warning(
                    f"[CODE_BLOCK] Python execution timed out after {timeout}s, process group killed",
                    extra={"script_path": str(script_path), "timeout": timeout}
                )

                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"⏱️ Execution timed out after {timeout} seconds. Process terminated.",
                    exit_code=-1,
                    language="python"
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                language="python"
            )

    async def _execute_bash_file(
        self,
        script_path: Path,
        args: Optional[List[str]],
        env: Optional[Dict[str, str]],
        timeout: int,
        workdir: Path
    ) -> ExecutionResult:
        """Execute Bash script file with proper process group management."""
        import signal

        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        cmd = ['bash', str(script_path)]
        if args:
            cmd.extend(args)

        try:
            # Create process in new process group for proper cleanup
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workdir),
                env=exec_env,
                start_new_session=True  # Creates new process group
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                stdout_str = stdout.decode('utf-8', errors='replace')
                stderr_str = stderr.decode('utf-8', errors='replace')

                if len(stdout_str) > self.MAX_OUTPUT_LENGTH:
                    stdout_str = stdout_str[:self.MAX_OUTPUT_LENGTH] + "\n... [output truncated]"

                return ExecutionResult(
                    success=process.returncode == 0,
                    output=stdout_str,
                    error=stderr_str if stderr_str else None,
                    exit_code=process.returncode,
                    language="bash"
                )

            except asyncio.TimeoutError:
                # Kill entire process group to ensure all child processes are terminated
                try:
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    # Give processes a moment to terminate gracefully
                    await asyncio.sleep(0.5)
                    # Force kill if still running
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # Already terminated
                except (ProcessLookupError, PermissionError):
                    # Fallback to regular kill
                    process.kill()

                await process.wait()

                self.logger.warning(
                    f"[CODE_BLOCK] Bash execution timed out after {timeout}s, process group killed",
                    extra={"script_path": str(script_path), "timeout": timeout}
                )

                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"⏱️ Execution timed out after {timeout} seconds. Process terminated.",
                    exit_code=-1,
                    language="bash"
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                language="bash"
            )

    async def execute_all(
        self,
        blocks: List[CodeBlock],
        stop_on_error: bool = True,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[ExecutionResult]:
        """Execute multiple code blocks in same workdir.

        Args:
            blocks: List of CodeBlocks to execute
            stop_on_error: Stop execution if a block fails
            session_id: Shared session ID for all blocks
            **kwargs: Additional arguments passed to execute()

        Returns:
            List of ExecutionResults
        """
        results = []
        session_id = session_id or uuid4().hex[:8]
        workdir = self.create_workdir(session_id)

        for block in blocks:
            result = await self.execute(block, workdir=workdir, session_id=session_id, **kwargs)
            results.append(result)

            if stop_on_error and not result.success:
                self.logger.warning(
                    f"[CODE_BLOCK] Stopping execution due to error in {block.filename}"
                )
                break

        return results

    def cleanup_workdir(self, session_id: str) -> None:
        """Clean up working directory for a session.

        Args:
            session_id: Session ID to clean up
        """
        import shutil
        workdir = self.base_workdir / f"session_{session_id}"
        if workdir.exists():
            try:
                shutil.rmtree(workdir)
                self.logger.debug(f"Cleaned up workdir: {workdir}")
            except Exception as e:
                self.logger.warning(f"Failed to cleanup workdir {workdir}: {e}")


# Singleton instance
_code_block_executor: Optional[CodeBlockExecutor] = None


def get_code_block_executor(
    sandbox=None,
    use_sandbox: bool = False,
    base_workdir: Optional[str] = None
) -> CodeBlockExecutor:
    """Get or create the code block executor singleton.

    Args:
        sandbox: Optional sandbox instance
        use_sandbox: Whether to use sandbox
        base_workdir: Base working directory

    Returns:
        CodeBlockExecutor instance
    """
    global _code_block_executor
    if _code_block_executor is None:
        _code_block_executor = CodeBlockExecutor(
            sandbox=sandbox,
            use_sandbox=use_sandbox,
            base_workdir=base_workdir
        )
    return _code_block_executor
