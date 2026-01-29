# Agent Skills API Documentation

Developer documentation for the Agent Skills backend components.

## Overview

The Agent Skills system consists of four main components:
1. **SKILL.md Parser** - Parses SKILL.md files
2. **Gating Engine** - Checks skill requirements
3. **Package Handler** - Manages skill packages
4. **Natural Language Tester** - Tests skills with natural language

## SKILL.md Parser

### Module

`backend/skill_library/skill_md_parser.py`

### Classes

#### `SkillMetadata`

Dataclass representing parsed skill metadata.

```python
@dataclass
class SkillMetadata:
    """Parsed skill metadata from frontmatter."""
    name: str                           # Required: Skill name
    description: str                    # Required: Brief description
    homepage: Optional[str] = None      # Optional: Homepage URL
    emoji: Optional[str] = None         # Optional: Display emoji
    requires_bins: List[str] = None     # Optional: Required binaries
    requires_env: List[str] = None      # Optional: Required env vars
    requires_config: List[str] = None   # Optional: Required config
    os_filter: Optional[List[str]] = None  # Optional: Compatible OS
```

#### `ParsedSkill`

Dataclass representing a fully parsed skill.

```python
@dataclass
class ParsedSkill:
    """Parsed SKILL.md content."""
    metadata: SkillMetadata  # Parsed metadata
    instructions: str        # Markdown instructions
    raw_content: str        # Full SKILL.md content
```

#### `SkillMdParser`

Main parser class.

```python
class SkillMdParser:
    """Parser for SKILL.md files."""
    
    def parse(self, content: str) -> ParsedSkill:
        """Parse SKILL.md content.
        
        Args:
            content: Raw SKILL.md file content
            
        Returns:
            ParsedSkill with metadata and instructions
            
        Raises:
            ValueError: If SKILL.md format is invalid
        """
        
    def validate(self, parsed: ParsedSkill) -> List[str]:
        """Validate parsed skill.
        
        Args:
            parsed: Parsed skill
            
        Returns:
            List of validation errors (empty if valid)
        """
```

### Usage Example

```python
from skill_library.skill_md_parser import SkillMdParser

# Read SKILL.md file
with open('SKILL.md', 'r') as f:
    content = f.read()

# Parse
parser = SkillMdParser()
parsed = parser.parse(content)

# Validate
errors = parser.validate(parsed)
if errors:
    print(f"Validation errors: {errors}")
else:
    print(f"Skill: {parsed.metadata.name}")
    print(f"Description: {parsed.metadata.description}")
    print(f"Instructions length: {len(parsed.instructions)}")
```

### Error Handling

```python
try:
    parsed = parser.parse(content)
except ValueError as e:
    # Handle parsing errors
    print(f"Parse error: {e}")
    # Common errors:
    # - "Invalid YAML frontmatter"
    # - "Missing required field: name"
    # - "Invalid metadata JSON"
```

## Gating Engine

### Module

`backend/skill_library/gating_engine.py`

### Classes

#### `GatingResult`

Dataclass representing gating check results.

```python
@dataclass
class GatingResult:
    """Result of gating check."""
    eligible: bool                      # Overall eligibility
    missing_bins: List[str]             # Missing binaries
    missing_env: List[str]              # Missing env vars
    missing_config: List[str]           # Missing config values
    os_compatible: bool                 # OS compatibility
    reason: Optional[str] = None        # Reason if not eligible
```

#### `GatingEngine`

Main gating engine class.

```python
class GatingEngine:
    """Check skill eligibility based on requirements."""
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize gating engine.
        
        Args:
            config: Optional config dict (uses get_config() if None)
        """
        
    def check_eligibility(self, metadata: SkillMetadata) -> GatingResult:
        """Check if skill requirements are met.
        
        Args:
            metadata: Skill metadata with requirements
            
        Returns:
            GatingResult with eligibility status
        """
        
    def check_binary(self, binary_name: str) -> bool:
        """Check if binary exists on PATH.
        
        Args:
            binary_name: Name of binary to check
            
        Returns:
            True if binary found
        """
        
    def check_env_var(self, var_name: str) -> bool:
        """Check if environment variable is set.
        
        Args:
            var_name: Name of environment variable
            
        Returns:
            True if variable is set and non-empty
        """
        
    def check_config(self, config_path: str) -> bool:
        """Check if config value is truthy.
        
        Args:
            config_path: Dot-notation path (e.g., "api.enabled")
            
        Returns:
            True if config value is truthy
        """
```

### Usage Example

```python
from skill_library.gating_engine import GatingEngine
from skill_library.skill_md_parser import SkillMdParser

# Parse skill
parser = SkillMdParser()
parsed = parser.parse(skill_content)

# Check gating
engine = GatingEngine()
result = engine.check_eligibility(parsed.metadata)

if result.eligible:
    print("✓ All requirements met")
else:
    print(f"✗ Requirements not met: {result.reason}")
    if result.missing_bins:
        print(f"  Missing binaries: {', '.join(result.missing_bins)}")
    if result.missing_env:
        print(f"  Missing env vars: {', '.join(result.missing_env)}")
    if result.missing_config:
        print(f"  Missing config: {', '.join(result.missing_config)}")
    if not result.os_compatible:
        print(f"  OS not compatible")
```

### Caching

The gating engine caches binary checks for performance:

```python
# First check (queries system)
result1 = engine.check_binary("curl")  # ~10ms

# Subsequent checks (cached)
result2 = engine.check_binary("curl")  # <1ms
```

Cache is cleared when engine is recreated.

## Package Handler

### Module

`backend/skill_library/package_handler.py`

### Classes

#### `PackageInfo`

Dataclass representing package information.

```python
@dataclass
class PackageInfo:
    """Information about uploaded package."""
    skill_md_path: Path              # Path to SKILL.md
    additional_files: List[Path]     # Other files in package
    total_size: int                  # Total size in bytes
    format: str                      # 'zip' or 'tar.gz'
```

#### `PackageHandler`

Main package handler class.

```python
class PackageHandler:
    """Handle skill package upload and extraction."""
    
    def __init__(self, minio_client):
        """Initialize package handler.
        
        Args:
            minio_client: MinIO client instance
        """
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
        
    def extract_package(self, file_data: bytes) -> PackageInfo:
        """Extract and validate package.
        
        Args:
            file_data: Package file bytes
            
        Returns:
            PackageInfo with package details
            
        Raises:
            ValueError: If package format is invalid
        """
        
    def validate_package(self, package_info: PackageInfo) -> List[str]:
        """Validate package contents.
        
        Args:
            package_info: Package information
            
        Returns:
            List of validation errors (empty if valid)
        """
```

### Usage Example

```python
from skill_library.package_handler import PackageHandler
from object_storage.minio_client import get_minio_client

# Initialize
minio_client = get_minio_client()
handler = PackageHandler(minio_client)

# Read uploaded file
with open('skill-package.zip', 'rb') as f:
    file_data = f.read()

# Extract and validate
try:
    package_info = handler.extract_package(file_data)
    errors = handler.validate_package(package_info)
    
    if errors:
        print(f"Validation errors: {errors}")
    else:
        print(f"Package valid: {package_info.format}")
        print(f"SKILL.md found at: {package_info.skill_md_path}")
        print(f"Additional files: {len(package_info.additional_files)}")
        
        # Upload to MinIO
        storage_path = await handler.upload_package(
            file_data,
            skill_name="my-skill",
            version="1.0.0"
        )
        print(f"Uploaded to: {storage_path}")
        
except ValueError as e:
    print(f"Package error: {e}")
```

### Validation Rules

The package handler validates:
- Package size (max 50MB)
- SKILL.md exists at root
- No malicious files (executables, hidden files)
- No path traversal attempts
- Valid ZIP or tar.gz format

## Natural Language Tester

### Module

`backend/skill_library/nl_tester.py`

### Classes

#### `TestCommand`

Dataclass representing a parsed command.

```python
@dataclass
class TestCommand:
    """Parsed command from skill instructions."""
    command_type: str  # 'bash', 'api', 'python', etc.
    command: str       # Actual command
    description: str   # Command description
```

#### `TestResult`

Dataclass representing test results.

```python
@dataclass
class TestResult:
    """Result of skill test."""
    success: bool                           # Test success
    input: str                              # Natural language input
    parsed_commands: List[TestCommand]      # Parsed commands
    simulated_output: str                   # Simulated output
    actual_output: Optional[str] = None     # Actual output (if executed)
    execution_time: float = 0.0             # Execution time in seconds
```

#### `NaturalLanguageTester`

Main tester class.

```python
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
            dry_run: If True, simulate without executing
            
        Returns:
            TestResult with parsed commands and output
        """
        
    def parse_commands(self, instructions: str) -> List[TestCommand]:
        """Parse commands from skill instructions.
        
        Args:
            instructions: Skill instructions markdown
            
        Returns:
            List of parsed commands
        """
        
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
```

### Usage Example

```python
from skill_library.nl_tester import NaturalLanguageTester
from skill_library.skill_md_parser import SkillMdParser

# Parse skill
parser = SkillMdParser()
parsed = parser.parse(skill_content)

# Test with natural language
tester = NaturalLanguageTester()
result = tester.test_skill(
    skill=parsed,
    natural_input="Get weather for London",
    dry_run=True
)

print(f"Success: {result.success}")
print(f"Input: {result.input}")
print(f"\nParsed Commands:")
for i, cmd in enumerate(result.parsed_commands, 1):
    print(f"  {i}. [{cmd.command_type}] {cmd.command}")
    print(f"     {cmd.description}")

print(f"\nSimulated Output:")
print(result.simulated_output)

if result.actual_output:
    print(f"\nActual Output:")
    print(result.actual_output)

print(f"\nExecution Time: {result.execution_time:.3f}s")
```

### Dry Run vs Actual Execution

```python
# Dry run (safe, no execution)
result_dry = tester.test_skill(
    skill=parsed,
    natural_input="Deploy to production",
    dry_run=True  # Only simulates
)

# Actual execution (runs commands)
result_actual = tester.test_skill(
    skill=parsed,
    natural_input="Deploy to production",
    dry_run=False  # Actually executes
)
```

## Integration Example

Complete workflow using all components:

```python
from skill_library.skill_md_parser import SkillMdParser
from skill_library.gating_engine import GatingEngine
from skill_library.package_handler import PackageHandler
from skill_library.nl_tester import NaturalLanguageTester
from object_storage.minio_client import get_minio_client

async def process_skill_upload(package_file: bytes, skill_name: str):
    """Process uploaded skill package."""
    
    # 1. Extract package
    minio_client = get_minio_client()
    handler = PackageHandler(minio_client)
    
    package_info = handler.extract_package(package_file)
    errors = handler.validate_package(package_info)
    if errors:
        raise ValueError(f"Invalid package: {errors}")
    
    # 2. Parse SKILL.md
    with open(package_info.skill_md_path) as f:
        skill_content = f.read()
    
    parser = SkillMdParser()
    parsed = parser.parse(skill_content)
    
    errors = parser.validate(parsed)
    if errors:
        raise ValueError(f"Invalid SKILL.md: {errors}")
    
    # 3. Check gating
    engine = GatingEngine()
    gating_result = engine.check_eligibility(parsed.metadata)
    
    # 4. Upload to MinIO
    storage_path = await handler.upload_package(
        package_file,
        skill_name,
        version="1.0.0"
    )
    
    # 5. Store in database
    skill_data = {
        'name': skill_name,
        'description': parsed.metadata.description,
        'skill_type': 'agent_skill',
        'storage_type': 'minio',
        'storage_path': storage_path,
        'skill_md_content': parsed.raw_content,
        'homepage': parsed.metadata.homepage,
        'metadata': {
            'emoji': parsed.metadata.emoji,
            'requires': {
                'bins': parsed.metadata.requires_bins or [],
                'env': parsed.metadata.requires_env or [],
                'config': parsed.metadata.requires_config or [],
            },
            'os': parsed.metadata.os_filter or [],
        },
        'gating_status': {
            'eligible': gating_result.eligible,
            'missing_bins': gating_result.missing_bins,
            'missing_env': gating_result.missing_env,
            'missing_config': gating_result.missing_config,
            'os_compatible': gating_result.os_compatible,
            'reason': gating_result.reason,
        }
    }
    
    return skill_data

async def test_skill(skill_id: str, natural_input: str, dry_run: bool = True):
    """Test a skill with natural language."""
    
    # 1. Get skill from database
    skill = get_skill_by_id(skill_id)
    
    # 2. Parse SKILL.md
    parser = SkillMdParser()
    parsed = parser.parse(skill.skill_md_content)
    
    # 3. Test with natural language
    tester = NaturalLanguageTester()
    result = tester.test_skill(
        skill=parsed,
        natural_input=natural_input,
        dry_run=dry_run
    )
    
    return {
        'success': result.success,
        'input': result.input,
        'parsed_commands': [
            {
                'type': cmd.command_type,
                'command': cmd.command,
                'description': cmd.description
            }
            for cmd in result.parsed_commands
        ],
        'simulated_output': result.simulated_output,
        'actual_output': result.actual_output,
        'execution_time': result.execution_time,
    }
```

## Error Handling

### Common Errors

```python
# Parse errors
try:
    parsed = parser.parse(content)
except ValueError as e:
    # Handle: Invalid YAML, missing fields, invalid JSON
    pass

# Validation errors
errors = parser.validate(parsed)
if errors:
    # Handle: Empty instructions, invalid metadata
    pass

# Package errors
try:
    package_info = handler.extract_package(file_data)
except ValueError as e:
    # Handle: Invalid format, too large, no SKILL.md
    pass

# Gating errors
result = engine.check_eligibility(metadata)
if not result.eligible:
    # Handle: Missing requirements, OS incompatible
    pass

# Test errors
result = tester.test_skill(parsed, input, dry_run=False)
if not result.success:
    # Handle: Command failed, timeout, error
    pass
```

## Performance Considerations

### Caching

```python
# Gating engine caches binary checks
engine = GatingEngine()
engine.check_binary("curl")  # Cached after first call

# Create new engine to clear cache
engine = GatingEngine()
```

### Async Operations

```python
# Package upload is async
storage_path = await handler.upload_package(...)

# Use in async context
async def upload_skill():
    storage_path = await handler.upload_package(...)
    return storage_path
```

### Resource Limits

```python
# Package size limit
handler.max_size = 50 * 1024 * 1024  # 50MB

# Test timeout (in sandbox)
result = tester.test_skill(
    skill=parsed,
    natural_input=input,
    dry_run=False,
    timeout=30  # 30 seconds
)
```

## Testing

### Unit Tests

```python
# Test parser
def test_parse_valid_skill():
    parser = SkillMdParser()
    parsed = parser.parse(valid_content)
    assert parsed.metadata.name == "test-skill"

# Test gating
def test_check_binary():
    engine = GatingEngine()
    assert engine.check_binary("python3") == True
    assert engine.check_binary("nonexistent") == False

# Test package handler
def test_extract_zip():
    handler = PackageHandler(mock_minio)
    info = handler.extract_package(zip_data)
    assert info.format == "zip"

# Test natural language tester
def test_parse_commands():
    tester = NaturalLanguageTester()
    commands = tester.parse_commands(instructions)
    assert len(commands) > 0
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_workflow():
    # Upload package
    skill_data = await process_skill_upload(package_file, "test-skill")
    
    # Test skill
    result = await test_skill(
        skill_data['skill_id'],
        "Test input",
        dry_run=True
    )
    
    assert result['success'] == True
```

## References

- [Creating Agent Skills](../user-guide/creating-agent-skills.md)
- [SKILL.md Format Reference](../user-guide/skill-md-format.md)
- [Gating Requirements Guide](../user-guide/gating-requirements.md)
- [Testing Agent Skills](../user-guide/testing-agent-skills.md)
- [AgentSkills.io Specification](https://agentskills.io)
