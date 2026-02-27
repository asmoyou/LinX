# Code Execution and Skill Integration Improvement - Tasks

## Status Legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed
- `[~]` Queued

## Phase 1: Enhanced Bash Tool with PTY Support (Priority: High)

### 1.1 Core Bash Tool Implementation
- [x] 1.1.1 Create `BashToolConfig` dataclass
  - Fields: command, pty, workdir, background, timeout, elevated, env
  - Location: `backend/agent_framework/tools/bash_tool.py`

- [x] 1.1.2 Create `BashResult` dataclass
  - Fields: success, stdout, stderr, exit_code, session_id, execution_time
  - Location: `backend/agent_framework/tools/bash_tool.py`

- [x] 1.1.3 Implement `EnhancedBashTool` class
  - Method: `execute(config)` - main entry point
  - Method: `_execute_normal(config)` - standard execution
  - Method: `_execute_pty(config)` - PTY mode execution
  - Method: `_execute_background(config)` - background execution
  - Location: `backend/agent_framework/tools/bash_tool.py`

### 1.2 PTY Mode Implementation
- [x] 1.2.1 Implement PTY allocation
  - Use `pty.spawn()` or `pty.openpty()`
  - Set terminal size
  - Handle terminal signals

- [x] 1.2.2 Implement PTY output capture
  - Capture terminal output with ANSI codes
  - Handle colors and formatting
  - Buffer output efficiently

- [x] 1.2.3 Add PTY error handling
  - Handle PTY allocation failures
  - Handle process crashes
  - Clean up PTY resources

### 1.3 LangChain Tool Integration
- [x] 1.3.1 Create `create_bash_tool()` function
  - Wrap EnhancedBashTool as LangChain Tool
  - Define tool parameters and description
  - Add usage examples in docstring
  - Location: `backend/agent_framework/tools/bash_tool.py`

- [x] 1.3.2 Add bash tool to agent initialization
  - Update `BaseAgent.initialize()` method
  - Add bash tool to self.tools list
  - Location: `backend/agent_framework/base_agent.py`

- [x] 1.3.3 Test bash tool with agent
  - Test normal execution
  - Test PTY mode with interactive tool
  - Test error handling

## Phase 2: Background Process Management (Priority: High)

### 2.1 Process Manager Implementation
- [x] 2.1.1 Create `ProcessSession` dataclass
  - Fields: session_id, process, command, started_at, workdir, status
  - Location: `backend/agent_framework/tools/process_manager.py`

- [x] 2.1.2 Create `RingBuffer` class
  - Method: `write(data)` - append to buffer
  - Method: `read(offset, limit)` - read from buffer
  - Auto-truncate when exceeding max_size
  - Location: `backend/agent_framework/tools/process_manager.py`

- [x] 2.1.3 Implement `ProcessManager` class
  - Method: `start_process(config)` - start background process
  - Method: `poll(session_id)` - check if running
  - Method: `get_output(session_id, offset, limit)` - get output
  - Method: `write_input(session_id, data)` - send to stdin
  - Method: `kill(session_id)` - terminate process
  - Method: `list_sessions()` - list all sessions
  - Location: `backend/agent_framework/tools/process_manager.py`

### 2.2 Output Capture
- [x] 2.2.1 Implement output capture thread
  - Start thread for each background process
  - Read stdout/stderr continuously
  - Write to RingBuffer

- [x] 2.2.2 Implement output buffering
  - Use RingBuffer for efficient storage
  - Handle large outputs (>100KB)
  - Prevent memory leaks

- [x] 2.2.3 Add process cleanup
  - Periodic cleanup of completed processes
  - Remove old session data
  - Clean up zombie processes

### 2.3 Process Tool Integration
- [x] 2.3.1 Create `create_process_tool()` function
  - Wrap ProcessManager as LangChain Tool
  - Support actions: list, poll, log, write, submit, kill
  - Add usage examples
  - Location: `backend/agent_framework/tools/process_tool.py`

- [x] 2.3.2 Add process tool to agent
  - Update agent initialization
  - Test with background processes

## Phase 3: Skill Loader and Integration (Priority: High)

### 3.1 Skill Loader Implementation
- [x] 3.1.1 Create `SkillCode` dataclass
  - Fields: language, code, file_path, description
  - Location: `backend/skill_library/skill_loader.py`

- [x] 3.1.2 Implement `SkillLoader` class
  - Method: `load_skill(skill_name)` - load and parse skill
  - Method: `_extract_code_blocks(markdown)` - extract code from SKILL.md
  - Method: `get_code_by_language(skill_name, language)` - filter by language
  - Add caching for loaded skills
  - Location: `backend/skill_library/skill_loader.py`

- [x] 3.1.3 Test skill loading
  - Test with existing skills
  - Test code block extraction
  - Test caching behavior

### 3.2 Enhanced Read Skill Tool
- [x] 3.2.1 Create `create_enhanced_read_skill_tool()` function
  - Use SkillLoader to get code blocks
  - Return full code with language tags
  - Add usage instructions
  - Location: `backend/agent_framework/tools/read_skill_tool.py`

- [x] 3.2.2 Update agent initialization
  - Replace old read_skill tool with enhanced version
  - Pass SkillLoader instance
  - Location: `backend/agent_framework/base_agent.py`

- [x] 3.2.3 Test enhanced read_skill tool
  - Verify full code is returned
  - Test with multiple languages
  - Test agent can use code directly

### 3.3 Real Skill Execution
- [x] 3.3.1 Update `SkillExecutor._execute_skill_logic()`
  - Remove placeholder implementation
  - Use SkillLoader to get code
  - Execute code in sandbox
  - Return real results
  - Location: `backend/skill_library/skill_executor.py`

- [x] 3.3.2 Add skill execution error handling
  - Catch execution errors
  - Provide helpful error messages
  - Support retry logic

- [x] 3.3.3 Test real skill execution
  - Test with Python skills
  - Test with JavaScript skills
  - Test with Bash skills

## Phase 4: Code Validator (Priority: High)

### 4.1 Validator Implementation
- [x] 4.1.1 Create `ValidationResult` dataclass
  - Fields: valid, errors, warnings, suggestions
  - Location: `backend/agent_framework/tools/code_validator.py`

- [x] 4.1.2 Implement `CodeValidator` class
  - Method: `validate(code, language)` - main entry point
  - Method: `_validate_python(code)` - Python validation
  - Method: `_validate_javascript(code)` - JS validation
  - Method: `_validate_bash(code)` - Bash validation
  - Method: `_is_import_available(module)` - check imports
  - Location: `backend/agent_framework/tools/code_validator.py`

- [x] 4.1.3 Implement Python validation
  - Use `ast.parse()` for syntax checking
  - Check for dangerous patterns (eval, exec, os.system)
  - Validate imports
  - Provide specific error messages

- [x] 4.1.4 Implement JavaScript validation
  - Basic syntax checking
  - Check for common errors
  - Validate require/import statements

### 4.2 Validation Tool Integration
- [ ] 4.2.1 Create `create_code_validation_tool()` function
  - Wrap CodeValidator as LangChain Tool
  - Format validation results
  - Location: `backend/agent_framework/tools/code_validator.py`

- [ ] 4.2.2 Add validation tool to agent
  - Update agent initialization
  - Test validation before execution

## Phase 5: Enhanced Code Execution Sandbox (Priority: High)

### 5.1 Real Code Injection
- [x] 5.1.1 Implement `_inject_code()` method
  - Remove placeholder implementation
  - Write code to container filesystem
  - Set proper permissions
  - Handle multi-file projects
  - Location: `backend/virtualization/code_execution_sandbox.py`

- [x] 5.1.2 Add language-specific handling
  - Python: .py files
  - JavaScript: .js files
  - TypeScript: .ts files
  - Bash: .sh files with executable permission

- [x] 5.1.3 Add context injection
  - Write context as JSON file
  - Make context available to code
  - Handle environment variables

### 5.2 Real Code Execution
- [x] 5.2.1 Implement `_run_code()` method
  - Remove placeholder implementation
  - Detect language from file extension
  - Use appropriate interpreter (python3, node, bash)
  - Capture stdout/stderr separately
  - Extract return values
  - Location: `backend/virtualization/code_execution_sandbox.py`

- [x] 5.2.2 Add interpreter detection
  - Map file extensions to interpreters
  - Handle shebang lines
  - Support custom interpreters

- [x] 5.2.3 Add result extraction
  - Parse stdout for return values
  - Handle JSON output
  - Extract error messages from stderr
  - Capture exit codes

### 5.3 Dependency Management System
- [x] 5.3.1 Create `DependencyInfo` dataclass
  - Fields: name, version, language, install_command
  - Support hashable for use in sets
  - Location: `backend/virtualization/dependency_manager.py`

- [x] 5.3.2 Create `DependencyCache` dataclass
  - Fields: dependencies, installed_at, cache_key, image_tag
  - Method: `is_expired()` - check TTL
  - Location: `backend/virtualization/dependency_manager.py`

- [x] 5.3.3 Implement `DependencyDetector` class
  - Method: `detect_python_dependencies()` - parse Python imports
  - Method: `detect_javascript_dependencies()` - parse JS imports
  - Method: `_is_stdlib_module()` - filter stdlib modules
  - Location: `backend/virtualization/dependency_manager.py`

- [x] 5.3.4 Implement `DependencyManager` class
  - Method: `get_dependencies()` - detect from code + explicit
  - Method: `get_cache_key()` - generate hash for deps
  - Method: `is_cached()` - check cache with TTL
  - Method: `cache_dependencies()` - cache with image tag
  - Method: `generate_install_script()` - create bash scripts
  - Persistent cache to disk with JSON
  - Location: `backend/virtualization/dependency_manager.py`

- [x] 5.3.5 Integrate with code execution sandbox
  - Add `enable_dependency_management` parameter
  - Detect dependencies before sandbox creation
  - Check cache and reuse images
  - Install dependencies in sandbox
  - Cache installed dependencies
  - Location: `backend/virtualization/code_execution_sandbox.py`

- [x] 5.3.6 Create comprehensive tests
  - Test dependency detection (Python, JavaScript)
  - Test cache management (TTL, persistence)
  - Test install script generation
  - Test full workflow integration
  - Location: `backend/tests/unit/test_dependency_manager.py`

- [x] 5.3.7 Create documentation
  - Architecture overview
  - Component descriptions
  - Usage examples
  - Performance metrics
  - Location: `docs/backend/dependency-management.md`

- [x] 5.3.8 Implement Docker image caching
  - Create Docker images with dependencies
  - Tag images with cache key
  - Reuse cached images in container creation
  - Clean up old images

- [x] 5.3.9 Implement real dependency installation
  - Execute install scripts in containers
  - Verify installation success
  - Handle installation errors
  - Support multiple languages

### 5.4 Container Manager Enhancement
- [x] 5.4.1 Add `exec_in_container()` method
  - Execute commands in running container
  - Capture output
  - Support stdin input
  - Location: `backend/virtualization/container_manager.py`

- [x] 5.4.2 Add `write_file_to_container()` method
  - Write files to container filesystem
  - Set proper permissions
  - Use base64 encoding for read-only filesystems
  - Location: `backend/virtualization/container_manager.py`

- [x] 5.4.3 Integrate real Docker API
  - Use docker-py SDK
  - Handle Docker availability gracefully
  - Fall back to simulation mode if Docker unavailable
  - Location: `backend/virtualization/container_manager.py`

- [x] 5.4.4 Test container execution
  - Test with Python code
  - Test with JavaScript code
  - Test with Bash scripts

## Phase 6: File Segmentation Tools (Priority: Medium)

### 6.1 FileSegmenter Implementation
- [ ] 6.1.1 Implement `FileSegmenter` class
  - Method: `read_segment(path, start, end)` - read line range
  - Method: `read_around(path, line, context)` - read with context
  - Method: `replace_lines(path, start, end, content)` - replace lines
  - Method: `insert_lines(path, after, content)` - insert lines
  - Method: `get_file_structure(path)` - get structure
  - Location: `backend/agent_framework/tools/file_segmenter.py`

- [ ] 6.1.2 Implement Python structure parsing
  - Use `ast.parse()` to get classes/functions
  - Extract line numbers
  - Return structured data

- [ ] 6.1.3 Add file backup
  - Create backup before editing
  - Support rollback
  - Clean up old backups

### 6.2 File Segment Tools
- [ ] 6.2.1 Create file segment tools
  - `read_file_segment` tool
  - `read_file_around` tool
  - `replace_file_lines` tool
  - `get_file_structure` tool
  - Location: `backend/agent_framework/tools/file_tools.py`

- [ ] 6.2.2 Add tools to agent
  - Update agent initialization
  - Test with large files

## Phase 7: Code Generation Optimization (Priority: Medium)

### 7.1 Enhanced System Prompt
- [ ] 7.1.1 Create code generation guidance
  - Add best practices section
  - Add common mistakes section
  - Add error handling guidance
  - Add skill usage instructions

- [ ] 7.1.2 Update `_create_system_prompt()` method
  - Append code guidance to base prompt
  - Make guidance configurable
  - Location: `backend/agent_framework/base_agent.py`

- [ ] 7.1.3 Test prompt effectiveness
  - Measure code quality improvement
  - Track first-try success rate

### 7.2 Execution Feedback Loop
- [ ] 7.2.1 Implement `CodeExecutionFeedback` class
  - Method: `analyze_error(error, code, language)` - analyze errors
  - Method: `_analyze_python_error(error, code)` - Python errors
  - Method: `_analyze_javascript_error(error, code)` - JS errors
  - Method: `_extract_module_name(error)` - parse error messages
  - Location: `backend/agent_framework/tools/code_feedback.py`

- [ ] 7.2.2 Integrate feedback with error recovery
  - Use feedback in error recovery system
  - Provide specific fix suggestions
  - Track error patterns

- [ ] 7.2.3 Test feedback effectiveness
  - Measure error recovery rate
  - Track retry counts

### 7.3 Metrics Collection
- [ ] 7.3.1 Create `CodeGenerationMetrics` dataclass
  - Track total attempts
  - Track successful first try
  - Track successful after retry
  - Calculate success rates
  - Location: `backend/agent_framework/metrics.py`

- [ ] 7.3.2 Add metrics to agent
  - Track code generation attempts
  - Log metrics
  - Expose via API

## Phase 8: Testing (Priority: High)

### 8.1 Unit Tests
- [x] 8.1.1 Test EnhancedBashTool
  - Test normal execution
  - Test PTY mode
  - Test background mode
  - Test error handling
  - Location: `backend/tests/unit/test_bash_tool.py`

- [x] 8.1.2 Test ProcessManager
  - Test process creation
  - Test output capture
  - Test process termination
  - Test session management
  - Location: `backend/tests/unit/test_process_manager.py`

- [x] 8.1.3 Test SkillLoader
  - Test code extraction
  - Test caching
  - Test error handling
  - Location: `backend/tests/unit/test_skill_loader.py`

- [x] 8.1.4 Test CodeValidator
  - Test Python validation
  - Test JavaScript validation
  - Test error messages
  - Location: `backend/tests/unit/test_code_validator.py`

- [ ] 8.1.5 Test FileSegmenter
  - Test segment reading
  - Test line replacement
  - Test structure parsing
  - Location: `backend/tests/unit/test_file_segmenter.py`

### 8.2 Integration Tests
- [ ] 8.2.1 Test end-to-end skill execution
  - Load skill → Extract code → Execute → Verify
  - Test with multiple languages
  - Test error recovery
  - Location: `backend/tests/integration/test_skill_execution.py`

- [ ] 8.2.2 Test code generation workflow
  - Generate → Validate → Execute → Handle errors
  - Test retry logic
  - Test feedback loop
  - Location: `backend/tests/integration/test_code_generation.py`

- [ ] 8.2.3 Test background process workflow
  - Start → Monitor → Get output → Kill
  - Test with long-running processes
  - Test concurrent processes
  - Location: `backend/tests/integration/test_background_processes.py`

- [ ] 8.2.4 Test file segmentation workflow
  - Read structure → Read segment → Edit → Verify
  - Test with large files (>1000 lines)
  - Test concurrent edits
  - Location: `backend/tests/integration/test_file_segmentation.py`

### 8.3 Performance Tests
- [ ] 8.3.1 Test skill loading performance
  - Target: <100ms per skill
  - Test with cache hit/miss
  - Location: `backend/tests/performance/test_skill_loading.py`

- [ ] 8.3.2 Test code execution performance
  - Target: <10s for typical code
  - Test with different languages
  - Location: `backend/tests/performance/test_code_execution.py`

- [ ] 8.3.3 Test file operations performance
  - Target: <1s for segment operations
  - Test with large files
  - Location: `backend/tests/performance/test_file_operations.py`

## Phase 9: Documentation (Priority: Medium)

### 9.1 Technical Documentation
- [ ] 9.1.1 Create code-execution-guide.md
  - Document enhanced bash tool
  - Document process management
  - Document PTY mode
  - Location: `docs/backend/code-execution-guide.md`

- [ ] 9.1.2 Create skill-integration-guide.md
  - Document skill loading
  - Document skill execution
  - Document best practices
  - Location: `docs/backend/skill-integration-guide.md`

- [ ] 9.1.3 Create file-segmentation-guide.md
  - Document file tools
  - Document large file editing
  - Provide examples
  - Location: `docs/backend/file-segmentation-guide.md`

### 9.2 API Documentation
- [ ] 9.2.1 Document bash tool API
  - Parameters and return values
  - Usage examples
  - Location: `docs/api/bash-tool.md`

- [ ] 9.2.2 Document process tool API
  - Actions and parameters
  - Usage examples
  - Location: `docs/api/process-tool.md`

- [ ] 9.2.3 Document file tools API
  - Tool descriptions
  - Usage examples
  - Location: `docs/api/file-tools.md`

### 9.3 User Guide
- [ ] 9.3.1 Create user guide for code execution
  - How to use bash tool
  - How to run background processes
  - How to use agent skills
  - Location: `docs/user-guide/code-execution.md`

- [ ] 9.3.2 Create troubleshooting guide
  - Common issues and solutions
  - Error messages explained
  - Location: `docs/user-guide/troubleshooting-code-execution.md`

## Phase 10: Deployment and Monitoring (Priority: Low)

### 10.1 Configuration
- [ ] 10.1.1 Add environment variables
  - CODE_EXECUTION_TIMEOUT
  - CODE_VALIDATION_ENABLED
  - MAX_BACKGROUND_PROCESSES
  - etc.

- [ ] 10.1.2 Update config.yaml
  - Add code_execution section
  - Add process_management section
  - Add file_operations section

- [ ] 10.1.3 Add configuration validation
  - Validate timeout ranges
  - Validate buffer sizes
  - Validate file paths

### 10.2 Monitoring
- [ ] 10.2.1 Add Prometheus metrics
  - code_execution_duration_seconds
  - skill_execution_success_total
  - background_processes_active
  - code_validation_errors_total

- [ ] 10.2.2 Add structured logging
  - Log skill executions
  - Log code executions
  - Log process lifecycle

- [ ] 10.2.3 Create monitoring dashboard
  - Code execution metrics
  - Skill usage metrics
  - Process metrics

### 10.3 Gradual Rollout
- [ ] 10.3.1 Deploy to test environment
  - Test with real workloads
  - Monitor performance
  - Collect feedback

- [ ] 10.3.2 Enable for test users
  - A/B test improvements
  - Measure success metrics
  - Tune configuration

- [ ] 10.3.3 Enable for all users
  - Monitor error rates
  - Track success metrics
  - Optimize performance

## Summary

**Total Tasks**: 120
**Completed**: 25 (Phases 1-3, Phase 5.1-5.4 complete)
**Remaining**: 95
**Estimated Effort**: 3 weeks (1 developer)

**Completed Phases**:
- ✅ Phase 1: Enhanced Bash Tool with PTY (10/10 tasks)
- ✅ Phase 2: Background Process Management (10/10 tasks)
- ✅ Phase 3: Skill Loader and Integration (9/9 tasks)
- ✅ Phase 5.1-5.4: Enhanced Sandbox & Container Manager (13/14 tasks)
- ✅ Phase 5.3: Dependency Management System (9/10 tasks)

**Remaining Phases**:
- ⏳ Phase 4: Code Validator (0/6 tasks)
- ⏳ Phase 5.3.8: Docker image caching (1 task)
- ⏳ Phase 6: File Segmentation Tools (0/5 tasks)
- ⏳ Phase 7: Code Generation Optimization (0/9 tasks)
- ⏳ Phase 8: Testing (0/15 tasks)
- ⏳ Phase 9: Documentation (0/9 tasks)
- ⏳ Phase 10: Deployment and Monitoring (0/9 tasks)

**Critical Path**:
1. ✅ Phase 1: Enhanced Bash Tool - DONE
2. ✅ Phase 2: Process Management - DONE
3. ✅ Phase 3: Skill Integration - DONE
4. ⏳ Phase 4: Code Validator - NEXT
5. ✅ Phase 5: Sandbox Enhancement - MOSTLY DONE
6. ⏳ Phase 6: File Segmentation
7. ⏳ Phase 7: Code Optimization
8. ⏳ Phase 8: Testing

**Dependencies**:
- Phase 2 depends on Phase 1 (bash tool needed for processes) ✅
- Phase 3 depends on Phase 5 (sandbox needed for skill execution) ✅
- Phase 7 depends on Phase 4 (validator needed for feedback)
- Phase 8 depends on all previous phases

**Success Metrics**:
- Code quality: 30% → 80% first-try success rate
- Skill usage: 0% → 90% execution success rate
- Error recovery: 0% → 70% automatic fix rate
- Token efficiency: 5 → 3 average rounds per task

**Risk Areas**:
- PTY mode complexity (may need platform-specific code) ✅ Resolved
- Container execution performance (may need optimization) ✅ Resolved
- Large file handling (memory usage concerns)
- Background process cleanup (zombie process prevention) ✅ Resolved
