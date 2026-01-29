# Agent Skills Redesign - Technical Design

## Architecture Overview

Agent Skills are fundamentally different from LangChain Tools:

- **LangChain Tools**: Executable Python functions with `@tool` decorator, structured input/output
- **Agent Skills**: SKILL.md (instructions) + Executable tools (scripts/src/) that teach agents HOW to use tools

**Key Understanding:** Agent Skills = Instructions + Executable Code

```
┌─────────────────────────────────────────────────────────────┐
│                        Agent System                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐         ┌──────────────────┐          │
│  │  LangChain Tools │         │  Agent Skills    │          │
│  │  (Executable)    │         │  (Instructions + │          │
│  │                  │         │   Executable)    │          │
│  ├──────────────────┤         ├──────────────────┤          │
│  │ • Python code    │         │ • SKILL.md       │          │
│  │ • @tool decorator│         │ • scripts/       │          │
│  │ • Structured I/O │         │ • src/           │          │
│  │ • Direct exec    │         │ • references/    │          │
│  └──────────────────┘         │ • Agent reads    │          │
│           │                   │   then executes  │          │
│           │                   └──────────────────┘          │
│           └────────────┬───────────────┘                     │
│                        │                                     │
│                   ┌────▼────┐                                │
│                   │  Agent  │                                │
│                   │ Executor│                                │
│                   └─────────┘                                │
└─────────────────────────────────────────────────────────────┘
```

### Agent Skills Package Structure

Based on Moltbot and Claude Code best practices:

```
agent-skill-package/
├── SKILL.md           # Instructions: HOW to use the tools
├── README.md          # Package documentation (optional)
├── requirements.txt   # Python dependencies (if has Python code)
├── scripts/           # Executable scripts (Python, Shell, etc.)
│   ├── main.py
│   ├── helper.py
│   └── setup.sh
├── src/               # Complete Python package (optional, for complex skills)
│   └── skill_name/
│       ├── __init__.py
│       ├── api.py
│       └── utils.py
├── references/        # Reference documentation (optional)
│   └── api-docs.md
└── assets/            # Output resources (optional)
    └── template.html
```

## Component Design

### 1. SKILL.md Parser

**Location:** `backend/skill_library/skill_md_parser.py`

**Purpose:** Parse and validate SKILL.md files

**Interface:**
```python
from dataclasses import dataclass
from typing import Optional, Dict, List

@dataclass
class SkillMetadata:
    """Parsed skill metadata from frontmatter."""
    name: str
    description: str
    homepage: Optional[str] = None
    emoji: Optional[str] = None
    requires_bins: List[str] = None
    requires_env: List[str] = None
    requires_config: List[str] = None
    os_filter: Optional[List[str]] = None  # darwin, linux, win32

@dataclass
class ParsedSkill:
    """Parsed SKILL.md content."""
    metadata: SkillMetadata
    instructions: str  # Markdown content after frontmatter
    raw_content: str  # Full SKILL.md content

class SkillMdParser:
    """Parser for SKILL.md files."""
    
    def parse(self, content: str) -> ParsedSkill:
        """Parse SKILL.md content.
        
        Args:
            content: Raw SKILL.md file content
            
        Returns:
            Parsed skill with metadata and instructions
            
        Raises:
            ValueError: If SKILL.md format is invalid
        """
        pass
    
    def validate(self, parsed: ParsedSkill) -> List[str]:
        """Validate parsed skill.
        
        Args:
            parsed: Parsed skill
            
        Returns:
            List of validation errors (empty if valid)
        """
        pass
```

**Implementation Details:**

1. **Frontmatter Parsing:**
   - Use `python-frontmatter` library
   - Extract YAML between `---` delimiters
   - Parse metadata JSON from `metadata` field
   - Support single-line JSON format (moltbot compatibility)

2. **Validation Rules:**
   - Required fields: `name`, `description`
   - Optional fields: `homepage`, `metadata`
   - Metadata structure: `{"requires": {"bins": [], "env": [], "config": []}, "emoji": "🔧", "os": []}`
   - Instructions must be non-empty markdown

3. **Error Handling:**
   - Invalid YAML: Clear error message
   - Missing required fields: List missing fields
   - Invalid metadata JSON: Show parsing error

### 2. Gating Engine

**Location:** `backend/skill_library/gating_engine.py`

**Purpose:** Check if skill requirements are met

**Interface:**
```python
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class GatingResult:
    """Result of gating check."""
    eligible: bool
    missing_bins: List[str]
    missing_env: List[str]
    missing_config: List[str]
    os_compatible: bool
    reason: Optional[str] = None

class GatingEngine:
    """Check skill eligibility based on requirements."""
    
    def check_eligibility(self, metadata: SkillMetadata) -> GatingResult:
        """Check if skill requirements are met.
        
        Args:
            metadata: Skill metadata with requirements
            
        Returns:
            Gating result with eligibility status
        """
        pass
    
    def check_binary(self, binary_name: str) -> bool:
        """Check if binary exists on PATH."""
        pass
    
    def check_env_var(self, var_name: str) -> bool:
        """Check if environment variable is set."""
        pass
    
    def check_config(self, config_path: str) -> bool:
        """Check if config value is truthy."""
        pass
```

**Implementation Details:**

1. **Binary Check:**
   - Use `shutil.which()` to check PATH
   - Cache results for performance
   - Support platform-specific binaries

2. **Environment Variable Check:**
   - Check `os.environ`
   - Also check config file for env overrides
   - Support `skills.entries.<name>.env` config

3. **Config Check:**
   - Parse dot-notation paths (e.g., `browser.enabled`)
   - Check against `config.yaml`
   - Support nested config structures

4. **OS Compatibility:**
   - Check `platform.system()` against `os` filter
   - Map: `darwin` → macOS, `linux` → Linux, `win32` → Windows

### 3. Package Handler

**Location:** `backend/skill_library/package_handler.py`

**Purpose:** Handle skill package upload and extraction

**Interface:**
```python
from pathlib import Path
from typing import Optional
import zipfile
import tarfile

@dataclass
class PackageInfo:
    """Information about uploaded package."""
    skill_md_path: Path
    additional_files: List[Path]
    total_size: int
    format: str  # 'zip' or 'tar.gz'

class PackageHandler:
    """Handle skill package upload and extraction."""
    
    def __init__(self, minio_client):
        self.minio_client = minio_client
        self.max_size = 50 * 1024 * 1024  # 50MB
    
    async def upload_package(
        self,
        file_data: bytes,
        skill_name: str,
        version: str
    ) -> str:
        """Upload package to MinIO.
        
        Args:
            file_data: Package file bytes
            skill_name: Skill name
            version: Skill version
            
        Returns:
            MinIO storage path
            
        Raises:
            ValueError: If package is invalid or too large
        """
        pass
    
    def extract_package(self, file_data: bytes) -> PackageInfo:
        """Extract and validate package.
        
        Args:
            file_data: Package file bytes
            
        Returns:
            Package information
            
        Raises:
            ValueError: If package format is invalid
        """
        pass
    
    def validate_package(self, package_info: PackageInfo) -> List[str]:
        """Validate package contents.
        
        Args:
            package_info: Package information
            
        Returns:
            List of validation errors (empty if valid)
        """
        pass
```

**Implementation Details:**

1. **Package Extraction:**
   - Support ZIP and tar.gz formats
   - Extract to temporary directory
   - Find SKILL.md (must be at root or in subdirectory)
   - Collect additional files (configs, scripts, etc.)

2. **Validation:**
   - Check package size (max 50MB)
   - Verify SKILL.md exists
   - Check for malicious files (no executables, no hidden files)
   - Validate file paths (no path traversal)

3. **MinIO Storage:**
   - Path format: `skills/{skill_name}/{version}/package.zip`
   - Store original package (not extracted)
   - Set metadata: skill_name, version, upload_date
   - Generate presigned URL for download

### 4. Natural Language Tester

**Location:** `backend/skill_library/nl_tester.py`

**Purpose:** Test Agent Skills with natural language input

**Interface:**
```python
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class TestCommand:
    """Parsed command from skill instructions."""
    command_type: str  # 'bash', 'api', 'python'
    command: str
    description: str

@dataclass
class TestResult:
    """Result of skill test."""
    success: bool
    input: str
    parsed_commands: List[TestCommand]
    simulated_output: str
    actual_output: Optional[str] = None  # If dry_run=False
    execution_time: float = 0.0

class NaturalLanguageTester:
    """Test Agent Skills with natural language."""
    
    def test_skill(
        self,
        skill: ParsedSkill,
        natural_input: str,
        dry_run: bool = True
    ) -> TestResult:
        """Test skill with natural language input.
        
        Args:
            skill: Parsed skill
            natural_input: Natural language test input
            dry_run: If True, simulate execution without running commands
            
        Returns:
            Test result with parsed commands and output
        """
        pass
    
    def parse_commands(self, instructions: str) -> List[TestCommand]:
        """Parse commands from skill instructions.
        
        Args:
            instructions: Skill instructions markdown
            
        Returns:
            List of parsed commands
        """
        pass
    
    def simulate_execution(
        self,
        commands: List[TestCommand],
        natural_input: str
    ) -> str:
        """Simulate command execution.
        
        Args:
            commands: Parsed commands
            natural_input: Natural language input
            
        Returns:
            Simulated output
        """
        pass
```

**Implementation Details:**

1. **Command Parsing:**
   - Extract code blocks from markdown (```bash, ```python, etc.)
   - Parse command descriptions from surrounding text
   - Identify command type (bash, API call, Python)
   - Extract parameters and placeholders

2. **Simulation:**
   - Replace placeholders with values from natural input
   - Generate mock output based on command type
   - Show what would be executed
   - Estimate execution time

3. **Actual Execution (if dry_run=False):**
   - Run commands in sandbox
   - Capture stdout/stderr
   - Handle timeouts and errors
   - Return actual output

### 5. Database Schema Updates

**Migration:** `backend/alembic/versions/XXX_agent_skills_redesign.py`

```python
def upgrade():
    # Add new columns for agent_skill
    op.add_column('skills', sa.Column('skill_md_content', sa.Text(), nullable=True))
    op.add_column('skills', sa.Column('homepage', sa.String(500), nullable=True))
    op.add_column('skills', sa.Column('metadata', sa.JSON(), nullable=True))
    op.add_column('skills', sa.Column('gating_status', sa.JSON(), nullable=True))
    
    # Add constraint: agent_skill must have skill_md_content
    op.create_check_constraint(
        'agent_skill_has_md',
        'skills',
        "skill_type != 'agent_skill' OR skill_md_content IS NOT NULL"
    )
    
    # Add constraint: agent_skill must use minio storage
    op.create_check_constraint(
        'agent_skill_uses_minio',
        'skills',
        "skill_type != 'agent_skill' OR storage_type = 'minio'"
    )

def downgrade():
    op.drop_constraint('agent_skill_uses_minio', 'skills')
    op.drop_constraint('agent_skill_has_md', 'skills')
    op.drop_column('skills', 'gating_status')
    op.drop_column('skills', 'metadata')
    op.drop_column('skills', 'homepage')
    op.drop_column('skills', 'skill_md_content')
```

### 6. API Endpoint Updates

**Create Skill (agent_skill):**

```python
@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    name: str = Form(...),
    description: str = Form(...),
    skill_type: str = Form(...),
    version: str = Form(default="1.0.0"),
    package_file: Optional[UploadFile] = File(None),
    code: Optional[str] = Form(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new skill.
    
    For agent_skill: package_file is required
    For langchain_tool: code is required
    """
    if skill_type == "agent_skill":
        if not package_file:
            raise HTTPException(400, "Package file required for agent_skill")
        
        # Read package
        file_data = await package_file.read()
        
        # Extract and validate
        handler = PackageHandler(get_minio_client())
        package_info = handler.extract_package(file_data)
        
        # Parse SKILL.md
        parser = SkillMdParser()
        with open(package_info.skill_md_path) as f:
            parsed = parser.parse(f.read())
        
        # Validate
        errors = parser.validate(parsed)
        if errors:
            raise HTTPException(400, f"Invalid SKILL.md: {', '.join(errors)}")
        
        # Check gating
        gating = GatingEngine()
        gating_result = gating.check_eligibility(parsed.metadata)
        
        # Upload to MinIO
        storage_path = await handler.upload_package(file_data, name, version)
        
        # Create skill
        skill = registry.register_skill(
            name=name,
            description=description,
            skill_type="agent_skill",
            storage_type="minio",
            storage_path=storage_path,
            skill_md_content=parsed.raw_content,
            homepage=parsed.metadata.homepage,
            metadata=asdict(parsed.metadata),
            gating_status=asdict(gating_result),
            version=version,
            created_by=str(current_user.user_id),
        )
        
        return SkillResponse.from_skill_info(skill)
    
    elif skill_type == "langchain_tool":
        # Existing langchain_tool logic
        pass
```

**Test Skill (agent_skill):**

```python
@router.post("/{skill_id}/test")
async def test_skill(
    skill_id: str,
    request: Union[StructuredTestRequest, NaturalLanguageTestRequest] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Test skill execution.
    
    For langchain_tool: Use StructuredTestRequest with inputs dict
    For agent_skill: Use NaturalLanguageTestRequest with natural_language_input
    """
    skill = get_skill_by_id(skill_id)
    
    if skill.skill_type == "agent_skill":
        # Natural language testing
        parser = SkillMdParser()
        parsed = parser.parse(skill.skill_md_content)
        
        tester = NaturalLanguageTester()
        result = tester.test_skill(
            parsed,
            request.natural_language_input,
            dry_run=request.get("dry_run", True)
        )
        
        return {
            "success": result.success,
            "input": result.input,
            "parsed_commands": [asdict(cmd) for cmd in result.parsed_commands],
            "simulated_output": result.simulated_output,
            "actual_output": result.actual_output,
            "execution_time": result.execution_time,
        }
    
    elif skill.skill_type == "langchain_tool":
        # Existing structured testing logic
        pass
```

### 7. Frontend Updates

**SkillTypeSelector.tsx:**

Remove single-file mode for agent_skill:

```typescript
export default function SkillTypeSelector({ selectedType, onTypeChange }: Props) {
  const types: SkillTypeOption[] = [
    {
      id: 'langchain_tool',
      name: 'LangChain Tool',
      description: 'Executable Python function with @tool decorator',
      icon: Code2,
      color: 'blue',
      badge: 'Executable',
    },
    {
      id: 'agent_skill',
      name: 'Agent Skill',
      description: 'Natural language instructions (SKILL.md) that teach agents how to use tools',
      icon: BookOpen,
      color: 'purple',
      badge: 'Instructions',
    },
  ];
  
  // ... rest of component
}
```

**AddSkillModalV2.tsx:**

Remove agent_skill single-file mode:

```typescript
// Remove agentSkillMode state
// Remove mode selection UI
// For agent_skill, always show package upload
// For langchain_tool, always show code editor

{skillType === 'agent_skill' && (
  <div>
    <label>Upload SKILL.md Package *</label>
    <input
      type="file"
      accept=".zip,.tar.gz"
      onChange={handleFileUpload}
      required
    />
    <p className="text-sm text-gray-600">
      Package must contain SKILL.md at root level
    </p>
  </div>
)}

{skillType === 'langchain_tool' && (
  <CodeEditor
    value={formData.code}
    onChange={(value) => setFormData({ ...formData, code: value })}
  />
)}
```

**SkillCardV2.tsx:**

Fix agent_skill display:

```typescript
// Add icon mapping
const skillTypeIcons = {
  langchain_tool: Code2,
  agent_skill: BookOpen,
};

const skillTypeColors = {
  langchain_tool: 'blue',
  agent_skill: 'purple',
};

// In card render
<div className="flex items-center gap-2">
  {React.createElement(skillTypeIcons[skill.skill_type] || Code2, {
    className: `w-5 h-5 text-${skillTypeColors[skill.skill_type]}-500`
  })}
  <span className={`text-sm font-medium text-${skillTypeColors[skill.skill_type]}-600`}>
    {skill.skill_type === 'agent_skill' ? 'Agent Skill' : 'LangChain Tool'}
  </span>
</div>

// Show gating requirements for agent_skill
{skill.skill_type === 'agent_skill' && skill.metadata?.requires && (
  <div className="mt-2 space-y-1">
    {skill.metadata.requires.bins?.length > 0 && (
      <div className="text-xs text-gray-600">
        Requires: {skill.metadata.requires.bins.join(', ')}
      </div>
    )}
    {!skill.gating_status?.eligible && (
      <div className="text-xs text-red-600">
        ⚠️ Requirements not met
      </div>
    )}
  </div>
)}
```

**SkillTesterModal.tsx:**

Different UI for agent_skill:

```typescript
{skill.skill_type === 'agent_skill' ? (
  // Natural language input
  <div>
    <label>Natural Language Input</label>
    <textarea
      value={testInput}
      onChange={(e) => setTestInput(e.target.value)}
      placeholder="e.g., Get the weather for London"
      rows={3}
    />
    <label className="flex items-center gap-2 mt-2">
      <input
        type="checkbox"
        checked={dryRun}
        onChange={(e) => setDryRun(e.target.checked)}
      />
      Dry run (simulate without executing)
    </label>
  </div>
) : (
  // Structured parameter inputs (existing)
  <div>
    {/* Parameter inputs */}
  </div>
)}

{/* Show test results */}
{testResult && skill.skill_type === 'agent_skill' && (
  <div className="space-y-3">
    <div>
      <h4>Parsed Commands:</h4>
      {testResult.parsed_commands.map((cmd, i) => (
        <div key={i} className="p-2 bg-gray-100 rounded">
          <div className="font-mono text-sm">{cmd.command}</div>
          <div className="text-xs text-gray-600">{cmd.description}</div>
        </div>
      ))}
    </div>
    <div>
      <h4>Output:</h4>
      <pre className="p-3 bg-gray-100 rounded text-sm">
        {testResult.simulated_output || testResult.actual_output}
      </pre>
    </div>
  </div>
)}
```

## Data Flow

### Create Agent Skill Flow

```
User → Upload ZIP → Frontend
                      ↓
                   Validate file
                      ↓
                   POST /api/v1/skills
                      ↓
Backend → Extract package → Parse SKILL.md → Validate
            ↓                    ↓              ↓
         Check size         Parse YAML      Check required fields
            ↓                    ↓              ↓
         Upload to MinIO    Extract metadata   Check gating
            ↓                    ↓              ↓
         Store in PostgreSQL ← Combine ← Return result
            ↓
         Return skill info → Frontend → Show success
```

### Test Agent Skill Flow

```
User → Enter natural language → Frontend
                                   ↓
                              POST /api/v1/skills/{id}/test
                                   ↓
Backend → Get skill → Parse SKILL.md → Extract commands
            ↓              ↓               ↓
         Check type    Parse markdown   Find code blocks
            ↓              ↓               ↓
         Natural lang  Extract instructions  Parse bash/API calls
            ↓              ↓               ↓
         Simulate execution ← Match input ← Replace placeholders
            ↓
         Generate output → Return result → Frontend → Show results
```

## Migration Strategy

### Phase 1: Add New Components (No Breaking Changes)

1. Add new database columns (nullable)
2. Add SKILL.md parser
3. Add gating engine
4. Add package handler
5. Add natural language tester
6. Update API to support both modes

### Phase 2: Update Frontend

1. Remove single-file mode from UI
2. Add package upload for agent_skill
3. Fix agent_skill card display
4. Add natural language testing UI

### Phase 3: Migrate Existing Skills

1. Identify existing agent_skill with inline storage
2. Convert to langchain_tool (they're the same)
3. Update skill_type in database
4. Notify users of migration

### Phase 4: Enforce Constraints

1. Add database constraints
2. Reject agent_skill with inline storage
3. Require SKILL.md for agent_skill
4. Remove deprecated code

## Testing Strategy

### Unit Tests

1. **SkillMdParser:**
   - Valid SKILL.md parsing
   - Invalid frontmatter handling
   - Missing required fields
   - Metadata JSON parsing
   - Instructions extraction

2. **GatingEngine:**
   - Binary existence check
   - Environment variable check
   - Config value check
   - OS compatibility check
   - Combined gating logic

3. **PackageHandler:**
   - ZIP extraction
   - tar.gz extraction
   - Package validation
   - Size limit enforcement
   - MinIO upload

4. **NaturalLanguageTester:**
   - Command parsing
   - Bash command extraction
   - API call extraction
   - Simulation logic
   - Placeholder replacement

### Integration Tests

1. **Create Agent Skill:**
   - Upload valid package
   - Upload invalid package
   - Upload oversized package
   - Duplicate skill name

2. **Test Agent Skill:**
   - Natural language input
   - Dry run mode
   - Actual execution
   - Error handling

3. **Gating:**
   - Skill with missing binary
   - Skill with missing env var
   - Skill with wrong OS
   - Skill with all requirements met

### End-to-End Tests

1. **Full Workflow:**
   - Create agent skill from package
   - View skill in UI
   - Test skill with natural language
   - Activate/deactivate skill
   - Delete skill

## Performance Considerations

1. **Package Upload:**
   - Stream upload to MinIO (don't load entire file in memory)
   - Async processing
   - Progress feedback

2. **SKILL.md Parsing:**
   - Cache parsed results
   - Lazy load instructions
   - Index metadata for search

3. **Gating Checks:**
   - Cache binary existence checks
   - Batch environment variable checks
   - Periodic refresh (not on every request)

## Security Considerations

1. **Package Validation:**
   - Check file extensions
   - Scan for malicious content
   - Limit package size
   - Validate file paths (no traversal)

2. **Command Execution:**
   - Sandbox all executions
   - Timeout limits
   - Resource limits (CPU, memory)
   - No arbitrary code execution

3. **MinIO Access:**
   - Presigned URLs with expiration
   - User-scoped access
   - Audit logging

## Correctness Properties

### Property 1: SKILL.md Format Validity

**Property:** All agent_skill entries must have valid SKILL.md format

**Test:**
```python
@given(skill_md_content=text())
def test_skill_md_validity(skill_md_content):
    parser = SkillMdParser()
    try:
        parsed = parser.parse(skill_md_content)
        # If parsing succeeds, validation must pass or fail consistently
        errors = parser.validate(parsed)
        assert isinstance(errors, list)
    except ValueError as e:
        # If parsing fails, error message must be clear
        assert len(str(e)) > 0
```

### Property 2: Gating Consistency

**Property:** Gating results must be consistent for same requirements

**Test:**
```python
@given(metadata=skill_metadata())
def test_gating_consistency(metadata):
    engine = GatingEngine()
    result1 = engine.check_eligibility(metadata)
    result2 = engine.check_eligibility(metadata)
    assert result1.eligible == result2.eligible
    assert result1.missing_bins == result2.missing_bins
```

### Property 3: Package Integrity

**Property:** Uploaded packages must be retrievable and identical

**Test:**
```python
@given(package_data=binary())
def test_package_integrity(package_data):
    handler = PackageHandler(minio_client)
    storage_path = await handler.upload_package(package_data, "test", "1.0.0")
    retrieved = await handler.download_package(storage_path)
    assert retrieved == package_data
```

### Property 4: Type Separation

**Property:** agent_skill and langchain_tool must have distinct storage and interface

**Test:**
```python
@given(skill_type=sampled_from(['agent_skill', 'langchain_tool']))
def test_type_separation(skill_type):
    if skill_type == 'agent_skill':
        # Must have skill_md_content and minio storage
        assert skill.skill_md_content is not None
        assert skill.storage_type == 'minio'
        assert skill.code is None
    elif skill_type == 'langchain_tool':
        # Must have code and interface_definition
        assert skill.code is not None
        assert skill.interface_definition is not None
        assert skill.skill_md_content is None
```

## Open Issues

1. **SKILL.md Template:** Should we provide a template generator?
2. **Skill Discovery:** How to discover skills from ClawdHub?
3. **Versioning:** How to handle skill updates and version conflicts?
4. **Dependencies:** How to handle skill dependencies (one skill requires another)?
5. **Testing Sandbox:** What sandbox technology to use for actual execution?

## References

- AgentSkills.io specification: https://agentskills.io
- Moltbot skills implementation: `examples-of-reference/moltbot/`
- LangChain tools documentation: https://python.langchain.com/docs/modules/tools/
- MinIO Python SDK: https://min.io/docs/minio/linux/developers/python/API.html
