# Agent Skills Redesign - Implementation Tasks

## Phase 0: Template Restructuring (CRITICAL - Based on Analysis)

### 0. Restructure Agent Skill Template

- [x] 0.1 Remove config.yaml from template
  - [x] 0.1.1 Delete `backend/skill_library/templates/agent_skill_template/config.yaml`
  - [x] 0.1.2 Update SKILL.md to remove config references
  - [x] 0.1.3 Update gating requirements (remove config checks)

- [x] 0.2 Reorganize Python code into scripts/
  - [x] 0.2.1 Create `scripts/` directory
  - [x] 0.2.2 Move `utils.py` → `scripts/utils.py`
  - [x] 0.2.3 Move `weather_helper.py` → `scripts/weather_helper.py`
  - [x] 0.2.4 Update SKILL.md paths to use `{baseDir}/scripts/`

- [x] 0.3 Add references/ directory
  - [x] 0.3.1 Create `references/` directory
  - [x] 0.3.2 Add `.gitkeep` file with explanation

- [x] 0.4 Update template generator
  - [x] 0.4.1 Update `_create_inline_template()` to reflect new structure
  - [x] 0.4.2 Remove config.yaml generation
  - [x] 0.4.3 Add scripts/ directory generation
  - [x] 0.4.4 Add example Python script
  - [x] 0.4.5 Update README.md with three modes (simple, complete, mixed)
  - [x] 0.4.6 Update `get_template_info()` with new structure info

- [x] 0.5 Update template documentation
  - [x] 0.5.1 Update README.md to explain three modes
  - [x] 0.5.2 Add examples from Moltbot and Claude Code
  - [x] 0.5.3 Document {baseDir} placeholder usage
  - [x] 0.5.4 Add configuration best practices (env vars)

## Phase 1: Backend Core Components (No Breaking Changes)

### 1. Database Schema Updates

- [x] 1.1 Create Alembic migration for new columns
  - [x] 1.1.1 Add `skill_md_content` TEXT column (nullable)
  - [x] 1.1.2 Add `homepage` VARCHAR(500) column (nullable)
  - [x] 1.1.3 Add `metadata` JSON column (nullable)
  - [x] 1.1.4 Add `gating_status` JSON column (nullable)
  - [x] 1.1.5 Test migration up and down

### 2. SKILL.md Parser

- [x] 2.1 Create `backend/skill_library/skill_md_parser.py`
  - [x] 2.1.1 Implement `SkillMetadata` dataclass
  - [x] 2.1.2 Implement `ParsedSkill` dataclass
  - [x] 2.1.3 Implement `SkillMdParser.parse()` method
    - Parse YAML frontmatter
    - Extract metadata JSON
    - Extract markdown instructions
  - [x] 2.1.4 Implement `SkillMdParser.validate()` method
    - Check required fields
    - Validate metadata structure
    - Validate instructions non-empty
  - [x] 2.1.5 Add error handling for invalid YAML
  - [x] 2.1.6 Add error handling for invalid JSON in metadata

- [x] 2.2 Write unit tests for SKILL.md parser
  - [x] 2.2.1 Test valid SKILL.md parsing
  - [x] 2.2.2 Test invalid YAML frontmatter
  - [x] 2.2.3 Test missing required fields
  - [x] 2.2.4 Test invalid metadata JSON
  - [x] 2.2.5 Test empty instructions
  - [x] 2.2.6 Test moltbot weather.md example

### 3. Gating Engine

- [x] 3.1 Create `backend/skill_library/gating_engine.py`
  - [x] 3.1.1 Implement `GatingResult` dataclass
  - [x] 3.1.2 Implement `GatingEngine.check_binary()` method
    - Use `shutil.which()`
    - Cache results
  - [x] 3.1.3 Implement `GatingEngine.check_env_var()` method
    - Check `os.environ`
    - Check config overrides
  - [x] 3.1.4 Implement `GatingEngine.check_config()` method
    - Parse dot-notation paths
    - Check against config.yaml
  - [x] 3.1.5 Implement `GatingEngine.check_eligibility()` method
    - Combine all checks
    - Return comprehensive result

- [x] 3.2 Write unit tests for gating engine
  - [x] 3.2.1 Test binary existence check
  - [x] 3.2.2 Test environment variable check
  - [x] 3.2.3 Test config value check
  - [x] 3.2.4 Test OS compatibility check
  - [x] 3.2.5 Test combined gating logic
  - [x] 3.2.6 Test caching behavior

### 4. Package Handler

- [x] 4.1 Create `backend/skill_library/package_handler.py`
  - [x] 4.1.1 Implement `PackageInfo` dataclass
  - [x] 4.1.2 Implement `PackageHandler.extract_package()` method
    - Support ZIP format
    - Support tar.gz format
    - Find SKILL.md in package
    - Collect additional files
  - [x] 4.1.3 Implement `PackageHandler.validate_package()` method
    - Check package size
    - Verify SKILL.md exists
    - Check for malicious files
    - Validate file paths
  - [x] 4.1.4 Implement `PackageHandler.upload_package()` method
    - Upload to MinIO
    - Set metadata
    - Return storage path
  - [x] 4.1.5 Add size limit enforcement (50MB)

- [x] 4.2 Write unit tests for package handler
  - [x] 4.2.1 Test ZIP extraction
  - [x] 4.2.2 Test tar.gz extraction
  - [x] 4.2.3 Test package validation
  - [x] 4.2.4 Test size limit enforcement
  - [x] 4.2.5 Test MinIO upload
  - [x] 4.2.6 Test malicious file detection

### 5. Natural Language Tester

- [x] 5.1 Create `backend/skill_library/nl_tester.py`
  - [x] 5.1.1 Implement `TestCommand` dataclass
  - [x] 5.1.2 Implement `TestResult` dataclass
  - [x] 5.1.3 Implement `NaturalLanguageTester.parse_commands()` method
    - Extract code blocks from markdown
    - Identify command type (bash, API, Python)
    - Parse command descriptions
  - [x] 5.1.4 Implement `NaturalLanguageTester.simulate_execution()` method
    - Replace placeholders
    - Generate mock output
    - Estimate execution time
  - [x] 5.1.5 Implement `NaturalLanguageTester.test_skill()` method
    - Combine parsing and simulation
    - Support dry_run mode
    - Support actual execution

- [x] 5.2 Write unit tests for natural language tester
  - [x] 5.2.1 Test bash command parsing
  - [x] 5.2.2 Test API call parsing
  - [x] 5.2.3 Test Python code parsing
  - [x] 5.2.4 Test simulation logic
  - [x] 5.2.5 Test placeholder replacement
  - [x] 5.2.6 Test dry_run mode

## Phase 2: API Updates

### 6. Update Skill Model

- [x] 6.1 Update `backend/skill_library/skill_model.py`
  - [x] 6.1.1 Add `skill_md_content` parameter to `create_skill()`
  - [x] 6.1.2 Add `homepage` parameter to `create_skill()`
  - [x] 6.1.3 Add `metadata` parameter to `create_skill()`
  - [x] 6.1.4 Add `gating_status` parameter to `create_skill()`
  - [x] 6.1.5 Update `update_skill()` to support new fields

### 7. Update Skills API Router

- [x] 7.1 Update `backend/api_gateway/routers/skills.py`
  - [x] 7.1.1 Update `create_skill()` endpoint
    - Accept multipart/form-data
    - Handle package_file upload
    - Extract and parse SKILL.md
    - Check gating requirements
    - Upload to MinIO
    - Store in database
  - [x] 7.1.2 Update `test_skill()` endpoint
    - Accept natural_language_input for agent_skill
    - Use NaturalLanguageTester
    - Return parsed commands and output
  - [x] 7.1.3 Update `SkillResponse` model
    - Add skill_md_content field
    - Add homepage field
    - Add metadata field
    - Add gating_status field
  - [x] 7.1.4 Add validation for agent_skill requirements
    - Reject agent_skill without package_file
    - Reject agent_skill with inline storage

- [x] 7.2 Write integration tests for API updates
  - [x] 7.2.1 Test create agent_skill with valid package
  - [x] 7.2.2 Test create agent_skill with invalid package
  - [x] 7.2.3 Test create agent_skill without package (should fail)
  - [x] 7.2.4 Test test agent_skill with natural language
  - [x] 7.2.5 Test test agent_skill dry_run mode
  - [x] 7.2.6 Test gating status in response

## Phase 3: Frontend Updates

### 8. Update Skill Type Selector

- [x] 8.1 Update `frontend/src/components/skills/SkillTypeSelector.tsx`
  - [x] 8.1.1 Update agent_skill description to "Natural language instructions"
  - [x] 8.1.2 Change agent_skill icon to BookOpen
  - [x] 8.1.3 Add "Instructions" badge to agent_skill
  - [x] 8.1.4 Update langchain_tool badge to "Executable"

### 9. Update Add Skill Modal

- [x] 9.1 Update `frontend/src/components/skills/AddSkillModalV2.tsx`
  - [x] 9.1.1 Remove `agentSkillMode` state
  - [x] 9.1.2 Remove mode selection UI for agent_skill
  - [x] 9.1.3 Show package upload for agent_skill (always)
  - [x] 9.1.4 Show code editor for langchain_tool (always)
  - [x] 9.1.5 Update form submission to use multipart/form-data for agent_skill
  - [x] 9.1.6 Add SKILL.md format help text
  - [x] 9.1.7 Update step navigation (skip template for agent_skill)

### 10. Fix Skill Card Display

- [x] 10.1 Update `frontend/src/components/skills/SkillCardV2.tsx`
  - [x] 10.1.1 Add skill type icon mapping (Code2 for langchain_tool, BookOpen for agent_skill)
  - [x] 10.1.2 Add skill type color mapping (blue for langchain_tool, purple for agent_skill)
  - [x] 10.1.3 Show skill type label ("LangChain Tool" or "Agent Skill")
  - [x] 10.1.4 Show gating requirements for agent_skill
    - Display required binaries
    - Display required env vars
    - Show eligibility status
  - [x] 10.1.5 Show homepage link for agent_skill (if provided)
  - [x] 10.1.6 Add distinct styling for agent_skill cards

### 11. Update Skill Tester Modal

- [x] 11.1 Update `frontend/src/components/skills/SkillTesterModal.tsx`
  - [x] 11.1.1 Add conditional UI based on skill_type
  - [x] 11.1.2 Show natural language input for agent_skill
    - Textarea for natural language
    - Dry run checkbox
    - Help text with examples
  - [x] 11.1.3 Show structured inputs for langchain_tool (existing)
  - [x] 11.1.4 Update result display for agent_skill
    - Show parsed commands
    - Show command descriptions
    - Show simulated/actual output
  - [x] 11.1.5 Update result display for langchain_tool (existing)

### 12. Update API Client

- [x] 12.1 Update `frontend/src/api/skills.ts`
  - [x] 12.1.1 Update `CreateSkillRequest` type
    - Add package_file field
    - Make code optional
  - [x] 12.1.2 Update `SkillResponse` type
    - Add skill_md_content field
    - Add homepage field
    - Add metadata field
    - Add gating_status field
  - [x] 12.1.3 Update `create()` method to support multipart/form-data
  - [x] 12.1.4 Update `test()` method to support natural_language_input

## Phase 4: Migration and Cleanup

### 13. Migrate Existing Skills

- [x] 13.1 Create migration script
  - [x] 13.1.1 Identify agent_skill with inline storage
  - [x] 13.1.2 Convert to langchain_tool (update skill_type)
  - [x] 13.1.3 Log migration actions
  - [x] 13.1.4 Generate migration report

- [x] 13.2 Run migration script
  - [x] 13.2.1 Backup database before migration
  - [x] 13.2.2 Run migration in transaction
  - [x] 13.2.3 Verify migration results
  - [x] 13.2.4 Notify users of changes

### 14. Add Database Constraints

- [x] 14.1 Create Alembic migration for constraints
  - [x] 14.1.1 Add constraint: agent_skill must have skill_md_content
  - [x] 14.1.2 Add constraint: agent_skill must use minio storage
  - [x] 14.1.3 Test constraint enforcement

### 15. Remove Deprecated Code

- [x] 15.1 Remove agent_skill single-file mode code
  - [x] 15.1.1 Remove mode selection from frontend
  - [x] 15.1.2 Remove inline storage support for agent_skill in backend
  - [x] 15.1.3 Update documentation
  - [x] 15.1.4 Update error messages

## Phase 5: Documentation and Testing

### 16. Documentation

- [x] 16.1 Create user documentation
  - [x] 16.1.1 Write "Creating Agent Skills" guide
  - [x] 16.1.2 Write "SKILL.md Format Reference"
  - [x] 16.1.3 Write "Gating Requirements Guide"
  - [x] 16.1.4 Write "Testing Agent Skills Guide"
  - [x] 16.1.5 Add examples (weather skill, API skill, etc.)

- [x] 16.2 Create developer documentation
  - [x] 16.2.1 Document SKILL.md parser API
  - [x] 16.2.2 Document gating engine API
  - [x] 16.2.3 Document package handler API
  - [x] 16.2.4 Document natural language tester API
  - [x] 16.2.5 Add architecture diagrams

### 17. End-to-End Testing

- [x] 17.1 Create E2E test suite
  - [x] 17.1.1 Test create agent_skill from package
  - [x] 17.1.2 Test view agent_skill in UI
  - [x] 17.1.3 Test test agent_skill with natural language
  - [x] 17.1.4 Test activate/deactivate agent_skill
  - [x] 17.1.5 Test delete agent_skill
  - [x] 17.1.6 Test gating requirements display
  - [x] 17.1.7 Test skill card display (icon, label, styling)

### 18. Property-Based Testing

- [x] 18.1 Write property tests
  - [x] 18.1.1 Property: SKILL.md format validity
    - **Validates: Requirements 1.1**
  - [x] 18.1.2 Property: Gating consistency
    - **Validates: Requirements 1.1**
  - [x] 18.1.3 Property: Package integrity
    - **Validates: Requirements 4.1**
  - [x] 18.1.4 Property: Type separation
    - **Validates: Requirements 2.1**

## Phase 6: Polish and Optimization

### 19. Performance Optimization

- [x] 19.1 Optimize package upload
  - [x] 19.1.1 Stream upload to MinIO
  - [x] 19.1.2 Add progress feedback
  - [x] 19.1.3 Implement async processing

- [x] 19.2 Optimize SKILL.md parsing
  - [x] 19.2.1 Cache parsed results
  - [x] 19.2.2 Lazy load instructions
  - [x] 19.2.3 Index metadata for search

- [x] 19.3 Optimize gating checks
  - [x] 19.3.1 Cache binary existence checks
  - [x] 19.3.2 Batch environment variable checks
  - [x] 19.3.3 Implement periodic refresh

### 20. Security Hardening

- [x] 20.1 Package validation
  - [x] 20.1.1 Scan for malicious content
  - [x] 20.1.2 Validate file extensions
  - [x] 20.1.3 Check for path traversal
  - [x] 20.1.4 Limit package size

- [x] 20.2 Command execution
  - [x] 20.2.1 Sandbox all executions
  - [x] 20.2.2 Add timeout limits
  - [x] 20.2.3 Add resource limits
  - [x] 20.2.4 Audit logging

### 21. UI Polish

- [x] 21.1 Improve agent_skill card styling
  - [x] 21.1.1 Add purple gradient for agent_skill
  - [x] 21.1.2 Add gating status indicator
  - [x] 21.1.3 Add homepage link button
  - [x] 21.1.4 Add emoji display (if provided)

- [x] 21.2 Improve test modal UX
  - [x] 21.2.1 Add example inputs
  - [x] 21.2.2 Add syntax highlighting for commands
  - [x] 21.2.3 Add copy button for output
  - [x] 21.2.4 Add execution time display

## Success Criteria

- [x] All unit tests pass (>80% coverage)
- [x] All integration tests pass
- [x] All E2E tests pass
- [x] All property tests pass
- [x] Agent skill cards display correctly (icon, label, gating)
- [x] Agent skills can be created from packages
- [x] Agent skills can be tested with natural language
- [x] No breaking changes to langchain_tool
- [x] Documentation is complete and accurate
- [x] Performance meets requirements (<5s upload, <100ms parsing)
- [x] Security validation passes

## Notes

- Each task should be completed and tested before moving to the next
- Update tasks.md status as tasks are completed
- Run full test suite after each phase
- Document any issues or blockers
- Get user feedback after Phase 3 (frontend updates)
