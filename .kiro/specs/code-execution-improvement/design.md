# Code Execution and Skill Integration Improvement - Design

## 1. Overview

This design document outlines the technical approach for implementing real code execution, proper skill integration, and code generation optimizations in LinX. The design is inspired by OpenClaw's bash-first approach with PTY mode and Claude Code's structured feature development workflow.

### 1.1 Design Goals

1. **Real Execution**: Replace placeholder implementations with actual code execution
2. **Skill Integration**: Enable agents to directly use code from agent skills
3. **Code Quality**: Improve code generation accuracy through validation and feedback
4. **Long File Support**: Enable segmented editing of large files
5. **Process Management**: Support interactive and background processes

### 1.2 Architecture Principles

- **Bash-First**: Use bash as primary execution mechanism (inspired by OpenClaw)
- **PTY Support**: Enable pseudo-terminals for interactive tools
- **Background Processes**: Support long-running tasks with monitoring
- **Validation Before Execution**: Check code syntax before running
- **Incremental Feedback**: Provide specific error messages for quick fixes
- **Segmented Operations**: Handle large files in chunks

## 2. System Architecture

### 2.1 Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        BaseAgent                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           LangChain Tool Integration                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ├─────────────────┬──────────────┬─────────────┐
                              │                 │              │             │
                              ▼                 ▼              ▼             ▼
                ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                │  BashTool    │  │ SkillLoader  │  │CodeValidator │  │FileSegmenter │
                │  (Enhanced)  │  │  (New)       │  │  (New)       │  │  (New)       │
                └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
                       │                 │                 │                 │
                       └─────────────────┴─────────────────┴─────────────────┘
                                              │
                                              ▼
                                ┌──────────────────────────┐
                                │  CodeExecutionSandbox    │
                                │  (Real Implementation)   │
                                └──────────────────────────┘
                                              │
                                              ▼
                                ┌──────────────────────────┐
                                │   Docker Container       │
                                │   (Isolated Execution)   │
                                └──────────────────────────┘
```

### 2.2 Component Responsibilities

**BashTool (Enhanced)**:
- Execute bash commands with PTY support
- Manage background processes
- Capture stdout/stderr
- Handle process lifecycle

**SkillLoader (New)**:
- Load skill code from storage
- Parse SKILL.md files
- Extract code blocks
- Cache loaded skills

**CodeValidator (New)**:
- Syntax checking (ast.parse, etc.)
- Import validation
- Type checking
- Linting

**FileSegmenter (New)**:
- Read file segments
- Edit specific line ranges
- Navigate large files
- Maintain file integrity

**CodeExecutionSandbox (Enhanced)**:
- Real code injection
- Real code execution
- Result extraction
- Error handling

## 3. Core Components Design

### 3.1 Enhanced BashTool

#### 3.1.1 Tool Interface

```python
@dataclass
class BashToolConfig:
    """Configuration for bash tool execution."""
    command: str
    pty: bool = False  # Allocate pseudo-terminal
    workdir: Optional[str] = None  # Working directory
    background: bool = False  # Run in background
    timeout: Optional[int] = None  # Timeout in seconds
    elevated: bool = False  # Run on host (if allowed)
    env: Optional[Dict[str, str]] = None  # Environment variables

@dataclass
class BashResult:
    """Result of bash command execution."""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    session_id: Optional[str] = None  # For background processes
    execution_time: float = 0.0

class EnhancedBashTool:
    """Enhanced bash tool with PTY and background support."""
    
    def execute(self, config: BashToolConfig) -> BashResult:
        """Execute bash command with enhanced features."""
        if config.background:
            return self._execute_background(config)
        elif config.pty:
            return self._execute_pty(config)
        else:
            return self._execute_normal(config)
    
    def _execute_pty(self, config: BashToolConfig) -> BashResult:
        """Execute with pseudo-terminal."""
        # Use pty.spawn() or similar
        # Capture terminal output
        # Handle ANSI escape codes
        pass
    
    def _execute_background(self, config: BashToolConfig) -> BashResult:
        """Execute in background, return session ID."""
        # Start process
        # Store in session manager
        # Return immediately with session_id
        pass
```

#### 3.1.2 Process Management

```python
class ProcessManager:
    """Manages background processes."""
    
    def __init__(self):
        self.sessions: Dict[str, ProcessSession] = {}
        self.output_buffers: Dict[str, RingBuffer] = {}
    
    def start_process(self, config: BashToolConfig) -> str:
        """Start background process, return session ID."""
        session_id = str(uuid4())
        process = subprocess.Popen(
            config.command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=config.workdir,
            env=config.env
        )
        
        self.sessions[session_id] = ProcessSession(
            session_id=session_id,
            process=process,
            command=config.command,
            started_at=datetime.now()
        )
        
        # Start output capture thread
        self._start_output_capture(session_id, process)
        
        return session_id
    
    def poll(self, session_id: str) -> ProcessStatus:
        """Check if process is still running."""
        session = self.sessions.get(session_id)
        if not session:
            return ProcessStatus.NOT_FOUND
        
        if session.process.poll() is None:
            return ProcessStatus.RUNNING
        else:
            return ProcessStatus.COMPLETED
    
    def get_output(self, session_id: str, offset: int = 0, limit: int = 1000) -> str:
        """Get process output."""
        buffer = self.output_buffers.get(session_id)
        if not buffer:
            return ""
        return buffer.read(offset, limit)
    
    def write_input(self, session_id: str, data: str) -> bool:
        """Write to process stdin."""
        session = self.sessions.get(session_id)
        if not session or session.process.poll() is not None:
            return False
        
        session.process.stdin.write(data.encode())
        session.process.stdin.flush()
        return True
    
    def kill(self, session_id: str) -> bool:
        """Terminate process."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.process.terminate()
        try:
            session.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            session.process.kill()
        
        return True
```

### 3.2 SkillLoader Component

```python
@dataclass
class SkillCode:
    """Extracted code from skill."""
    language: str
    code: str
    file_path: Optional[str] = None
    description: Optional[str] = None

class SkillLoader:
    """Loads and parses agent skills."""
    
    def __init__(self, skills_dir: str = "backend/skill_library/skills/"):
        self.skills_dir = Path(skills_dir)
        self.cache: Dict[str, List[SkillCode]] = {}
    
    def load_skill(self, skill_name: str) -> List[SkillCode]:
        """Load skill and extract code blocks."""
        if skill_name in self.cache:
            return self.cache[skill_name]
        
        skill_path = self.skills_dir / skill_name / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill not found: {skill_name}")
        
        content = skill_path.read_text()
        code_blocks = self._extract_code_blocks(content)
        
        self.cache[skill_name] = code_blocks
        return code_blocks
    
    def _extract_code_blocks(self, markdown: str) -> List[SkillCode]:
        """Extract code blocks from markdown."""
        pattern = r'```(\w+)\n(.*?)```'
        matches = re.findall(pattern, markdown, re.DOTALL)
        
        code_blocks = []
        for language, code in matches:
            code_blocks.append(SkillCode(
                language=language,
                code=code.strip()
            ))
        
        return code_blocks
    
    def get_code_by_language(self, skill_name: str, language: str) -> List[str]:
        """Get all code blocks for a specific language."""
        code_blocks = self.load_skill(skill_name)
        return [block.code for block in code_blocks if block.language == language]
```

### 3.3 CodeValidator Component

```python
@dataclass
class ValidationResult:
    """Result of code validation."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

class CodeValidator:
    """Validates code before execution."""
    
    def validate(self, code: str, language: str) -> ValidationResult:
        """Validate code for given language."""
        if language == "python":
            return self._validate_python(code)
        elif language in ["javascript", "typescript"]:
            return self._validate_javascript(code)
        elif language == "bash":
            return self._validate_bash(code)
        else:
            return ValidationResult(valid=True)  # No validation for unknown languages
    
    def _validate_python(self, code: str) -> ValidationResult:
        """Validate Python code."""
        errors = []
        warnings = []
        suggestions = []
        
        # Syntax check
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
            return ValidationResult(valid=False, errors=errors)
        
        # Check for dangerous patterns
        if "eval(" in code or "exec(" in code:
            warnings.append("Using eval() or exec() is dangerous")
        
        if "os.system(" in code:
            warnings.append("Consider using subprocess instead of os.system()")
        
        # Check imports
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not self._is_import_available(alias.name):
                        errors.append(f"Module not available: {alias.name}")
        
        valid = len(errors) == 0
        return ValidationResult(valid=valid, errors=errors, warnings=warnings, suggestions=suggestions)
    
    def _is_import_available(self, module_name: str) -> bool:
        """Check if module is available."""
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False
```

### 3.4 FileSegmenter Component

```python
class FileSegmenter:
    """Handles segmented file operations."""
    
    def read_segment(self, path: str, start_line: int, end_line: int) -> str:
        """Read specific line range from file."""
        with open(path, 'r') as f:
            lines = f.readlines()
        
        # Validate line numbers
        if start_line < 1 or end_line > len(lines):
            raise ValueError(f"Invalid line range: {start_line}-{end_line}")
        
        # Return segment (1-indexed)
        return ''.join(lines[start_line-1:end_line])
    
    def read_around(self, path: str, line_number: int, context_lines: int = 10) -> str:
        """Read lines around a specific line."""
        start = max(1, line_number - context_lines)
        end = line_number + context_lines
        return self.read_segment(path, start, end)
    
    def replace_lines(self, path: str, start_line: int, end_line: int, new_content: str) -> None:
        """Replace specific line range with new content."""
        with open(path, 'r') as f:
            lines = f.readlines()
        
        # Validate line numbers
        if start_line < 1 or end_line > len(lines):
            raise ValueError(f"Invalid line range: {start_line}-{end_line}")
        
        # Replace lines
        new_lines = new_content.split('\n')
        if not new_content.endswith('\n'):
            new_lines = [line + '\n' for line in new_lines[:-1]] + [new_lines[-1]]
        else:
            new_lines = [line + '\n' for line in new_lines]
        
        lines[start_line-1:end_line] = new_lines
        
        # Write back
        with open(path, 'w') as f:
            f.writelines(lines)
    
    def insert_lines(self, path: str, after_line: int, content: str) -> None:
        """Insert lines after specific line."""
        with open(path, 'r') as f:
            lines = f.readlines()
        
        new_lines = content.split('\n')
        if not content.endswith('\n'):
            new_lines = [line + '\n' for line in new_lines[:-1]] + [new_lines[-1]]
        else:
            new_lines = [line + '\n' for line in new_lines]
        
        lines[after_line:after_line] = new_lines
        
        with open(path, 'w') as f:
            f.writelines(lines)
    
    def get_file_structure(self, path: str) -> Dict[str, Any]:
        """Get file structure (classes, functions, etc.)."""
        with open(path, 'r') as f:
            content = f.read()
        
        if path.endswith('.py'):
            return self._parse_python_structure(content)
        else:
            return {"line_count": len(content.split('\n'))}
    
    def _parse_python_structure(self, code: str) -> Dict[str, Any]:
        """Parse Python file structure."""
        tree = ast.parse(code)
        structure = {
            "classes": [],
            "functions": [],
            "line_count": len(code.split('\n'))
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                structure["classes"].append({
                    "name": node.name,
                    "line": node.lineno
                })
            elif isinstance(node, ast.FunctionDef):
                structure["functions"].append({
                    "name": node.name,
                    "line": node.lineno
                })
        
        return structure
```

### 3.5 Enhanced CodeExecutionSandbox

```python
class EnhancedCodeExecutionSandbox(CodeExecutionSandbox):
    """Enhanced sandbox with real code execution."""
    
    async def _inject_code(
        self,
        sandbox_id: str,
        code: str,
        context: Dict[str, Any],
        language: str,
    ) -> None:
        """Inject code into sandbox (REAL IMPLEMENTATION)."""
        # Determine file extension
        ext_map = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "bash": ".sh"
        }
        ext = ext_map.get(language, ".txt")
        
        # Create temp file in container
        code_file = f"/tmp/code_{uuid4().hex}{ext}"
        
        # Write code to container
        self.container_manager.exec_in_container(
            sandbox_id,
            f"cat > {code_file}",
            stdin=code
        )
        
        # Set executable permission for scripts
        if language == "bash":
            self.container_manager.exec_in_container(
                sandbox_id,
                f"chmod +x {code_file}"
            )
        
        # Write context as JSON if provided
        if context:
            context_file = "/tmp/context.json"
            self.container_manager.exec_in_container(
                sandbox_id,
                f"cat > {context_file}",
                stdin=json.dumps(context)
            )
        
        # Store file path for execution
        self._code_files[sandbox_id] = code_file
    
    async def _run_code(self, sandbox_id: str, language: str) -> Dict[str, Any]:
        """Run code in sandbox (REAL IMPLEMENTATION)."""
        code_file = self._code_files.get(sandbox_id)
        if not code_file:
            raise RuntimeError("Code not injected")
        
        # Determine command
        cmd_map = {
            "python": f"python3 {code_file}",
            "javascript": f"node {code_file}",
            "typescript": f"ts-node {code_file}",
            "bash": f"bash {code_file}"
        }
        command = cmd_map.get(language, f"cat {code_file}")
        
        # Execute in container
        result = self.container_manager.exec_in_container(
            sandbox_id,
            command,
            capture_output=True
        )
        
        return {
            "output": result.stdout,
            "error": result.stderr,
            "return_value": result.exit_code
        }
```

## 4. LangChain Tool Integration

### 4.1 Enhanced Bash Tool

```python
def create_bash_tool(agent_id: UUID, user_id: UUID) -> Tool:
    """Create enhanced bash tool for agent."""
    
    bash_executor = EnhancedBashTool()
    
    def bash_execute(
        command: str,
        pty: bool = False,
        workdir: Optional[str] = None,
        background: bool = False,
        timeout: Optional[int] = None
    ) -> str:
        """Execute bash command with enhanced features.
        
        Args:
            command: Shell command to execute
            pty: Allocate pseudo-terminal (for interactive tools)
            workdir: Working directory
            background: Run in background, returns session ID
            timeout: Timeout in seconds
        
        Returns:
            Command output or session ID (if background)
        """
        config = BashToolConfig(
            command=command,
            pty=pty,
            workdir=workdir,
            background=background,
            timeout=timeout
        )
        
        result = bash_executor.execute(config)
        
        if background:
            return f"Started background process: {result.session_id}"
        else:
            if result.success:
                return result.stdout
            else:
                return f"Error (exit {result.exit_code}):\n{result.stderr}"
    
    return Tool(
        name="bash",
        description="Execute bash commands. Use pty=true for interactive tools. Use background=true for long-running processes.",
        func=bash_execute
    )
```

### 4.2 Process Management Tool

```python
def create_process_tool(agent_id: UUID, user_id: UUID) -> Tool:
    """Create process management tool."""
    
    process_manager = ProcessManager()
    
    def process_action(
        action: str,
        session_id: Optional[str] = None,
        data: Optional[str] = None,
        offset: int = 0,
        limit: int = 1000
    ) -> str:
        """Manage background processes.
        
        Args:
            action: Action to perform (list, poll, log, write, submit, kill)
            session_id: Session ID (required for most actions)
            data: Data to write (for write/submit actions)
            offset: Output offset (for log action)
            limit: Output limit (for log action)
        
        Returns:
            Action result
        """
        if action == "list":
            sessions = process_manager.list_sessions()
            return json.dumps(sessions, indent=2)
        
        elif action == "poll":
            status = process_manager.poll(session_id)
            return f"Status: {status.value}"
        
        elif action == "log":
            output = process_manager.get_output(session_id, offset, limit)
            return output
        
        elif action == "write":
            success = process_manager.write_input(session_id, data)
            return "Written" if success else "Failed"
        
        elif action == "submit":
            success = process_manager.write_input(session_id, data + "\n")
            return "Submitted" if success else "Failed"
        
        elif action == "kill":
            success = process_manager.kill(session_id)
            return "Killed" if success else "Failed"
        
        else:
            return f"Unknown action: {action}"
    
    return Tool(
        name="process",
        description="Manage background processes. Actions: list, poll, log, write, submit, kill",
        func=process_action
    )
```

### 4.3 Enhanced Read Skill Tool

```python
def create_enhanced_read_skill_tool(agent_id: UUID, user_id: UUID, skill_manager) -> Tool:
    """Create enhanced read_skill tool that returns full code."""
    
    skill_loader = SkillLoader()
    
    def read_skill_with_code(skill_name: str, language: Optional[str] = None) -> str:
        """Read agent skill with full code blocks.
        
        Args:
            skill_name: Name of the skill to read
            language: Optional language filter (python, javascript, bash)
        
        Returns:
            Skill documentation with full code blocks
        """
        try:
            # Load skill metadata
            skill_info = skill_manager.get_skill_by_name(skill_name)
            if not skill_info:
                return f"Skill not found: {skill_name}"
            
            # Load code blocks
            code_blocks = skill_loader.load_skill(skill_name)
            
            # Filter by language if specified
            if language:
                code_blocks = [b for b in code_blocks if b.language == language]
            
            # Format output
            output = f"# {skill_name}\n\n"
            output += f"{skill_info.description}\n\n"
            
            if code_blocks:
                output += "## Code Examples\n\n"
                for block in code_blocks:
                    output += f"### {block.language}\n\n"
                    output += f"```{block.language}\n{block.code}\n```\n\n"
                    if block.description:
                        output += f"*{block.description}*\n\n"
            
            output += "\n**Usage**: Copy the code above directly. Only modify if execution fails.\n"
            
            return output
            
        except Exception as e:
            return f"Error reading skill: {str(e)}"
    
    return Tool(
        name="read_skill",
        description="Read agent skill documentation with full code examples. Returns complete code blocks that can be used directly.",
        func=read_skill_with_code
    )
```

### 4.4 File Segment Tools

```python
def create_file_segment_tools(agent_id: UUID, user_id: UUID) -> List[Tool]:
    """Create file segmentation tools."""
    
    segmenter = FileSegmenter()
    
    def read_file_segment(path: str, start_line: int, end_line: int) -> str:
        """Read specific line range from file."""
        try:
            content = segmenter.read_segment(path, start_line, end_line)
            return f"Lines {start_line}-{end_line} of {path}:\n\n{content}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def read_file_around(path: str, line_number: int, context_lines: int = 10) -> str:
        """Read lines around a specific line."""
        try:
            content = segmenter.read_around(path, line_number, context_lines)
            start = max(1, line_number - context_lines)
            return f"Lines around {line_number} in {path}:\n\n{content}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def replace_file_lines(path: str, start_line: int, end_line: int, new_content: str) -> str:
        """Replace specific line range with new content."""
        try:
            segmenter.replace_lines(path, start_line, end_line, new_content)
            return f"Replaced lines {start_line}-{end_line} in {path}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def get_file_structure(path: str) -> str:
        """Get file structure (classes, functions, line count)."""
        try:
            structure = segmenter.get_file_structure(path)
            return json.dumps(structure, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"
    
    return [
        Tool(
            name="read_file_segment",
            description="Read specific line range from file. Use for large files.",
            func=read_file_segment
        ),
        Tool(
            name="read_file_around",
            description="Read lines around a specific line number with context.",
            func=read_file_around
        ),
        Tool(
            name="replace_file_lines",
            description="Replace specific line range with new content. Use for editing large files.",
            func=replace_file_lines
        ),
        Tool(
            name="get_file_structure",
            description="Get file structure (classes, functions, line count).",
            func=get_file_structure
        )
    ]
```

### 4.5 Code Validation Tool

```python
def create_code_validation_tool(agent_id: UUID, user_id: UUID) -> Tool:
    """Create code validation tool."""
    
    validator = CodeValidator()
    
    def validate_code(code: str, language: str) -> str:
        """Validate code before execution.
        
        Args:
            code: Source code to validate
            language: Programming language (python, javascript, bash)
        
        Returns:
            Validation result with errors and suggestions
        """
        result = validator.validate(code, language)
        
        if result.valid:
            output = "✅ Code is valid\n"
        else:
            output = "❌ Code has errors:\n"
            for error in result.errors:
                output += f"  - {error}\n"
        
        if result.warnings:
            output += "\n⚠️ Warnings:\n"
            for warning in result.warnings:
                output += f"  - {warning}\n"
        
        if result.suggestions:
            output += "\n💡 Suggestions:\n"
            for suggestion in result.suggestions:
                output += f"  - {suggestion}\n"
        
        return output
    
    return Tool(
        name="validate_code",
        description="Validate code syntax and imports before execution. Use this before running code.",
        func=validate_code
    )
```

## 5. Code Generation Optimization

### 5.1 Enhanced System Prompt


The system prompt should be enhanced to include code generation best practices:

```python
def _create_system_prompt_with_code_guidance(self) -> str:
    """Create system prompt with code generation guidance."""
    
    base_prompt = self._create_system_prompt()  # Existing method
    
    code_guidance = """

## Code Generation Best Practices

When writing code:

1. **Validate Before Execution**: Always use validate_code tool before running code
2. **Use Agent Skills**: Check read_skill tool for existing code examples - use them directly
3. **Incremental Development**: Write small, testable pieces of code
4. **Error Handling**: Include try-except blocks for error-prone operations
5. **Clear Variable Names**: Use descriptive names, not single letters
6. **Type Hints**: Include type hints for Python functions
7. **Comments**: Add comments for complex logic
8. **Test Immediately**: Run code after writing to verify it works

## Common Mistakes to Avoid

- ❌ Don't use eval() or exec() - security risk
- ❌ Don't use os.system() - use subprocess instead
- ❌ Don't ignore import errors - validate imports first
- ❌ Don't write long functions - break into smaller pieces
- ❌ Don't skip error handling - always handle exceptions

## When Code Fails

1. Read the error message carefully
2. Identify the line number and error type
3. Fix the specific issue (don't rewrite everything)
4. Validate the fix before re-running
5. If stuck after 2 attempts, ask for help or try a different approach

## Using Agent Skills

Agent skills contain pre-written, tested code. When a skill is available:
1. Use read_skill tool to get the code
2. Copy the code directly (don't rewrite it)
3. Only modify if execution fails
4. Skills are your best resource - use them first!
"""
    
    return base_prompt + code_guidance
```

### 5.2 Execution Feedback Loop


```python
class CodeExecutionFeedback:
    """Provides intelligent feedback on code execution errors."""
    
    def analyze_error(self, error_message: str, code: str, language: str) -> str:
        """Analyze execution error and provide specific fix suggestions."""
        
        feedback = "## Execution Error Analysis\n\n"
        
        # Parse error message
        if language == "python":
            feedback += self._analyze_python_error(error_message, code)
        elif language in ["javascript", "typescript"]:
            feedback += self._analyze_javascript_error(error_message, code)
        elif language == "bash":
            feedback += self._analyze_bash_error(error_message, code)
        
        return feedback
    
    def _analyze_python_error(self, error: str, code: str) -> str:
        """Analyze Python error."""
        feedback = ""
        
        # ImportError
        if "ImportError" in error or "ModuleNotFoundError" in error:
            module = self._extract_module_name(error)
            feedback += f"**Issue**: Module '{module}' not found\n"
            feedback += f"**Fix**: Install with `pip install {module}` or use a different approach\n"
            feedback += f"**Alternative**: Check if module is available in read_skill tool\n\n"
        
        # NameError
        elif "NameError" in error:
            var_name = self._extract_variable_name(error)
            feedback += f"**Issue**: Variable '{var_name}' not defined\n"
            feedback += f"**Fix**: Define the variable before using it\n"
            feedback += f"**Check**: Verify spelling and scope\n\n"
        
        # SyntaxError
        elif "SyntaxError" in error:
            line_num = self._extract_line_number(error)
            feedback += f"**Issue**: Syntax error at line {line_num}\n"
            feedback += f"**Fix**: Check for missing colons, parentheses, or quotes\n"
            feedback += f"**Tip**: Use validate_code tool before execution\n\n"
        
        # TypeError
        elif "TypeError" in error:
            feedback += f"**Issue**: Type mismatch\n"
            feedback += f"**Fix**: Check argument types and function signatures\n"
            feedback += f"**Tip**: Add type hints to catch these earlier\n\n"
        
        # Generic
        else:
            feedback += f"**Error**: {error}\n"
            feedback += f"**Tip**: Read error message carefully and fix the specific issue\n\n"
        
        return feedback
    
    def _extract_module_name(self, error: str) -> str:
        """Extract module name from import error."""
        import re
        match = re.search(r"No module named '([^']+)'", error)
        if match:
            return match.group(1)
        return "unknown"
    
    def _extract_line_number(self, error: str) -> str:
        """Extract line number from error."""
        import re
        match = re.search(r"line (\d+)", error)
        if match:
            return match.group(1)
        return "unknown"
```

## 6. Implementation Workflow

### 6.1 Skill Execution Workflow


```
┌─────────────────────────────────────────────────────────────┐
│ 1. Agent receives task requiring skill                      │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Agent uses read_skill tool to get skill code             │
│    - Returns full code blocks with language tags            │
│    - Includes usage instructions                            │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Agent copies code directly (no modification)             │
│    - Preserves exact code from skill                        │
│    - Adds minimal wrapper if needed                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Agent validates code (optional but recommended)          │
│    - Uses validate_code tool                                │
│    - Checks syntax and imports                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Agent executes code in sandbox                           │
│    - Uses bash tool or code_execution tool                  │
│    - Captures output and errors                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
                    ┌─────┴─────┐
                    │  Success? │
                    └─────┬─────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
        ┌─────────┐           ┌─────────────┐
        │   YES   │           │     NO      │
        └─────────┘           └─────────────┘
              │                       │
              │                       ▼
              │           ┌─────────────────────────┐
              │           │ 6. Analyze error        │
              │           │    - Parse error msg    │
              │           │    - Identify issue     │
              │           └─────────────────────────┘
              │                       │
              │                       ▼
              │           ┌─────────────────────────┐
              │           │ 7. Fix specific issue   │
              │           │    - Don't rewrite all  │
              │           │    - Target the error   │
              │           └─────────────────────────┘
              │                       │
              │                       ▼
              │           ┌─────────────────────────┐
              │           │ 8. Retry execution      │
              │           │    (max 2-3 attempts)   │
              │           └─────────────────────────┘
              │                       │
              └───────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. Return result to agent                                   │
│    - Success: output and return value                       │
│    - Failure: error message and suggestions                 │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Code Generation Workflow


```
┌─────────────────────────────────────────────────────────────┐
│ 1. Agent receives coding task                               │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Check for relevant agent skills                          │
│    - Search skill library                                   │
│    - Read skill if found                                    │
└─────────────────────────────────────────────────────────────┘
                          │
                    ┌─────┴─────┐
                    │ Skill     │
                    │ found?    │
                    └─────┬─────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
        ┌─────────┐           ┌─────────────┐
        │   YES   │           │     NO      │
        └─────────┘           └─────────────┘
              │                       │
              ▼                       ▼
    ┌─────────────────┐     ┌─────────────────┐
    │ Use skill code  │     │ Write new code  │
    │ (see workflow   │     │ from scratch    │
    │  above)         │     └─────────────────┘
    └─────────────────┘               │
              │                       │
              └───────────┬───────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Validate code before execution                           │
│    - Use validate_code tool                                 │
│    - Fix any syntax errors                                  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Execute code in sandbox                                  │
│    - Capture output and errors                              │
└─────────────────────────────────────────────────────────────┘
                          │
                    ┌─────┴─────┐
                    │  Success? │
                    └─────┬─────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
        ┌─────────┐           ┌─────────────┐
        │   YES   │           │     NO      │
        └─────────┘           └─────────────┘
              │                       │
              │                       ▼
              │           ┌─────────────────────────┐
              │           │ 5. Get execution        │
              │           │    feedback             │
              │           │    - Analyze error      │
              │           │    - Get suggestions    │
              │           └─────────────────────────┘
              │                       │
              │                       ▼
              │           ┌─────────────────────────┐
              │           │ 6. Apply targeted fix   │
              │           │    - Fix specific issue │
              │           │    - Don't rewrite all  │
              │           └─────────────────────────┘
              │                       │
              │                       ▼
              │           ┌─────────────────────────┐
              │           │ 7. Validate fix         │
              │           └─────────────────────────┘
              │                       │
              │                       ▼
              │           ┌─────────────────────────┐
              │           │ 8. Retry execution      │
              │           │    (max 3 attempts)     │
              │           └─────────────────────────┘
              │                       │
              └───────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. Return result                                            │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 Long File Editing Workflow


```
┌─────────────────────────────────────────────────────────────┐
│ 1. Agent needs to edit large file (>500 lines)              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Get file structure                                       │
│    - Use get_file_structure tool                            │
│    - See classes, functions, line numbers                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Identify target location                                 │
│    - Find class/function to edit                            │
│    - Note line number                                       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Read segment around target                               │
│    - Use read_file_around tool                              │
│    - Get context (10-20 lines before/after)                 │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Make targeted edit                                       │
│    - Use replace_file_lines tool                            │
│    - Only edit specific lines                               │
│    - Preserve surrounding code                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Verify edit                                              │
│    - Read segment again to confirm                          │
│    - Run tests if available                                 │
└─────────────────────────────────────────────────────────────┘
```

## 7. Data Models

### 7.1 Core Data Structures


```python
@dataclass
class ProcessSession:
    """Background process session."""
    session_id: str
    process: subprocess.Popen
    command: str
    started_at: datetime
    workdir: Optional[str] = None
    status: str = "running"  # running, completed, failed, killed

@dataclass
class RingBuffer:
    """Ring buffer for process output."""
    max_size: int = 100000  # 100KB
    buffer: str = ""
    
    def write(self, data: str) -> None:
        """Write data to buffer."""
        self.buffer += data
        if len(self.buffer) > self.max_size:
            # Keep last max_size bytes
            self.buffer = self.buffer[-self.max_size:]
    
    def read(self, offset: int = 0, limit: int = 1000) -> str:
        """Read from buffer."""
        lines = self.buffer.split('\n')
        return '\n'.join(lines[offset:offset+limit])

@dataclass
class SkillExecutionRecord:
    """Record of skill execution."""
    skill_name: str
    execution_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = False
    output: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0

@dataclass
class CodeGenerationMetrics:
    """Metrics for code generation quality."""
    total_attempts: int = 0
    successful_first_try: int = 0
    successful_after_retry: int = 0
    failed: int = 0
    avg_retry_count: float = 0.0
    
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_attempts == 0:
            return 0.0
        return (self.successful_first_try + self.successful_after_retry) / self.total_attempts
    
    def first_try_rate(self) -> float:
        """Calculate first-try success rate."""
        if self.total_attempts == 0:
            return 0.0
        return self.successful_first_try / self.total_attempts
```

## 8. Configuration

### 8.1 Environment Variables


```bash
# Code Execution Settings
CODE_EXECUTION_TIMEOUT=300  # Max execution time in seconds
CODE_VALIDATION_ENABLED=true  # Enable pre-execution validation
SKILL_CODE_CACHE_SIZE=100  # Number of skills to cache

# Process Management
MAX_BACKGROUND_PROCESSES=50  # Max concurrent background processes
PROCESS_OUTPUT_BUFFER_SIZE=100000  # Output buffer size in bytes
PROCESS_CLEANUP_INTERVAL=3600  # Cleanup interval in seconds

# File Segmentation
MAX_FILE_SEGMENT_SIZE=1000  # Max lines per segment
FILE_EDIT_BACKUP_ENABLED=true  # Create backups before editing

# Code Generation
CODE_GENERATION_MAX_RETRIES=3  # Max retry attempts for code execution
CODE_FEEDBACK_ENABLED=true  # Enable intelligent error feedback
SKILL_FIRST_STRATEGY=true  # Prefer skills over generating new code
```

### 8.2 Configuration File (config.yaml)


```yaml
code_execution:
  timeout_seconds: ${CODE_EXECUTION_TIMEOUT:-300}
  validation_enabled: ${CODE_VALIDATION_ENABLED:-true}
  skill_cache_size: ${SKILL_CODE_CACHE_SIZE:-100}

process_management:
  max_background_processes: ${MAX_BACKGROUND_PROCESSES:-50}
  output_buffer_size: ${PROCESS_OUTPUT_BUFFER_SIZE:-100000}
  cleanup_interval_seconds: ${PROCESS_CLEANUP_INTERVAL:-3600}

file_operations:
  max_segment_size: ${MAX_FILE_SEGMENT_SIZE:-1000}
  backup_enabled: ${FILE_EDIT_BACKUP_ENABLED:-true}

code_generation:
  max_retries: ${CODE_GENERATION_MAX_RETRIES:-3}
  feedback_enabled: ${CODE_FEEDBACK_ENABLED:-true}
  skill_first_strategy: ${SKILL_FIRST_STRATEGY:-true}
```

## 9. Testing Strategy

### 9.1 Unit Tests

**SkillLoader Tests**:
- Test code block extraction from markdown
- Test language filtering
- Test caching behavior
- Test error handling for missing skills

**CodeValidator Tests**:
- Test Python syntax validation
- Test import checking
- Test dangerous pattern detection
- Test error message formatting

**FileSegmenter Tests**:
- Test segment reading
- Test line replacement
- Test file structure parsing
- Test boundary conditions

**ProcessManager Tests**:
- Test process creation
- Test output capture
- Test process termination
- Test session management

### 9.2 Integration Tests

**End-to-End Skill Execution**:
- Load skill → Extract code → Execute → Verify result
- Test with Python, JavaScript, Bash skills
- Test error recovery

**Code Generation with Validation**:
- Generate code → Validate → Execute → Handle errors
- Test retry logic
- Test feedback loop

**Long File Editing**:
- Read structure → Read segment → Edit → Verify
- Test with files >1000 lines
- Test concurrent edits

### 9.3 Performance Tests

- Skill loading time (target: <100ms)
- Code execution time (target: <10s)
- File segment operations (target: <1s)
- Background process spawn (target: <500ms)

## 10. Migration Plan

### Phase 1: Core Infrastructure (Week 1)
1. Implement EnhancedBashTool with PTY support
2. Implement ProcessManager
3. Add bash and process tools to agent
4. Test with simple commands

### Phase 2: Skill Integration (Week 2)
1. Implement SkillLoader
2. Enhance read_skill tool
3. Update skill_executor to use SkillLoader
4. Test skill code execution

### Phase 3: Code Validation (Week 2)
1. Implement CodeValidator
2. Add validate_code tool
3. Implement CodeExecutionFeedback
4. Test validation and feedback

### Phase 4: Sandbox Enhancement (Week 3)
1. Implement real code injection
2. Implement real code execution
3. Test with multiple languages
4. Add error handling

### Phase 5: File Segmentation (Week 3)
1. Implement FileSegmenter
2. Add file segment tools
3. Test with large files
4. Add backup functionality

### Phase 6: System Prompt Enhancement (Week 4)
1. Add code generation guidance
2. Update agent initialization
3. Test code quality improvements
4. Measure success metrics

### Phase 7: Testing & Documentation (Week 4)
1. Write comprehensive tests
2. Update documentation in `docs/backend/`
3. Create user guide
4. Performance tuning

## 11. Success Criteria

### Functional Criteria
- ✅ Skills execute real code (not placeholders)
- ✅ Code runs in actual sandbox (not simulated)
- ✅ Agent uses skill code directly
- ✅ PTY mode works for interactive tools
- ✅ Background processes can be monitored
- ✅ Large files can be edited in segments

### Performance Criteria
- ✅ 80%+ code works on first try (up from 30%)
- ✅ 90%+ skills execute successfully
- ✅ 70%+ errors fixed automatically
- ✅ Average 3 rounds per task (down from 5)
- ✅ Skill loading <100ms
- ✅ Code execution <10s

### Quality Criteria
- ✅ 80%+ test coverage
- ✅ No security vulnerabilities
- ✅ Comprehensive error handling
- ✅ Clear documentation
- ✅ User satisfaction >80%

## 12. References

### Internal References
- `.kiro/specs/agent-error-recovery/` - Error recovery system
- `backend/virtualization/code_execution_sandbox.py` - Current sandbox
- `backend/skill_library/skill_executor.py` - Current executor
- `backend/agent_framework/base_agent.py` - Agent implementation

### External References
- OpenClaw: `examples-of-reference/openclaw/skills/coding-agent/SKILL.md`
- Claude Code: `examples-of-reference/claude-code/plugins/feature-dev/`
- LangChain Tools: https://python.langchain.com/docs/modules/agents/tools/
- Docker SDK: https://docker-py.readthedocs.io/

### Documentation
- All implementation guides will be in `docs/backend/`
- User guides will be in `docs/user-guide/`
- API documentation will be in `docs/api/`
