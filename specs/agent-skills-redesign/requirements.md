# Agent Skills Redesign - Requirements

## Overview

Redesign the Agent Skills system to be fundamentally different from LangChain Tools. Agent Skills should use natural language instructions (SKILL.md format) to teach agents HOW to use tools, rather than being executable code themselves.

## Problem Statement

Current implementation has two critical issues:

1. **Agent skill type cards don't display properly**: No icon, no type label shown in the UI
2. **Agent skill single-file mode is redundant**: It's essentially the same as `langchain_tool` (both use `@tool` decorator), making it confusing and unnecessary

The fundamental issue is that Agent Skills are currently implemented as executable code (like LangChain tools), when they should be **instructions** that teach agents how to use tools.

## Reference Implementations

### Moltbot (AgentSkills.io format)
- Skills are markdown files (SKILL.md) with YAML frontmatter + natural language instructions
- Skills describe HOW to use tools (bash commands, APIs, CLIs, scripts)
- **Skills include executable code** (scripts/, src/) that agents call
- Skills can gate on binaries, env vars, config
- Skills use `{baseDir}` placeholders for paths
- Testing is natural language input/output, not structured parameters

**Examples:**
- `openai-image-gen`: SKILL.md + scripts/gen.py (300+ lines Python)
- `local-places`: SKILL.md + src/ (complete FastAPI MCP server)
- `bitwarden`: SKILL.md + scripts/bw-session.sh + references/

### Claude Code
- Skills are markdown files with instructions
- **Plugins include executable code** (hooks/, core/, utils/)
- Skills can be pure instructions or reference plugin code
- Clear separation between instructions and implementation

**Examples:**
- `hookify`: skills/writing-rules/SKILL.md + hooks/*.py + core/*.py
- `frontend-design`: Pure instruction skill (agent generates code directly)

### LangChain Demo
- Shows clear separation: LangChain tools are executable functions
- Agent uses tools to accomplish tasks
- Tools have structured input/output

## User Stories

### 1. As a developer, I want to create Agent Skills that teach agents HOW to use tools

**Acceptance Criteria:**
- Agent Skills use SKILL.md format with YAML frontmatter
- Skills contain natural language instructions on how to use tools
- **Skills can include executable code** (scripts/, src/) that agents call
- Skills can reference external tools (bash commands, APIs, CLIs)
- Skills can include examples and usage patterns
- Skills can gate on required binaries, environment variables, or config

**Example 1: Simple Script Mode**
```
weather-skill/
├── SKILL.md              # Instructions on how to use the weather tool
├── requirements.txt
└── scripts/
    └── weather_helper.py # Executable Python script
```

SKILL.md content:
```markdown
---
name: weather
description: Get current weather and forecasts (no API key required)
homepage: https://wttr.in/:help
metadata:
  emoji: "🌤️"
  requires:
    bins: ["curl", "python3"]
    env: []
---

# Weather

Use the weather helper script to get weather information.

## Quick Start

```bash
python3 {baseDir}/scripts/weather_helper.py --city London
```

## Usage Examples

Get current weather:
```bash
python3 {baseDir}/scripts/weather_helper.py --city "New York" --format json
```

Get forecast:
```bash
python3 {baseDir}/scripts/weather_helper.py --city "Tokyo" --forecast 5
```
```

**Example 2: Complete Package Mode**
```
places-skill/
├── SKILL.md              # Instructions on how to use the places API
├── pyproject.toml
└── src/
    └── places_api/
        ├── __init__.py
        ├── main.py       # FastAPI server
        └── client.py
```

### 2. As a developer, I want Agent Skills to be distinct from LangChain Tools

**Acceptance Criteria:**
- Remove agent_skill single-file mode (it's redundant with langchain_tool)
- Keep only agent_skill_package mode
- Agent Skills use SKILL.md format, not Python code with @tool decorator
- Clear visual distinction in UI (different icon, different card style)
- Different testing interface (natural language, not structured parameters)

### 3. As a user, I want to test Agent Skills with natural language

**Acceptance Criteria:**
- Test interface accepts natural language input (not structured parameters)
- Test shows how the agent would interpret and use the skill
- Test can simulate tool execution (bash commands, API calls)
- Test results show natural language output

### 4. As a developer, I want to upload Agent Skill packages

**Acceptance Criteria:**
- Upload ZIP/tar.gz containing SKILL.md and optional files
- System validates SKILL.md format (YAML frontmatter + instructions)
- System extracts metadata (name, description, requirements)
- System stores package in MinIO
- System checks gating requirements (bins, env vars, config)

### 5. As a user, I want to see Agent Skills displayed correctly in the UI

**Acceptance Criteria:**
- Agent skill cards show proper icon (different from langchain_tool)
- Agent skill cards show "Agent Skill" type label
- Agent skill cards show gating requirements (required binaries, env vars)
- Agent skill cards show homepage link if provided
- Agent skill cards have distinct visual style

## Functional Requirements

### FR1: SKILL.md Format Support

**Priority:** High

**Description:** Support AgentSkills.io-compatible SKILL.md format

**Requirements:**
- Parse YAML frontmatter (name, description, homepage, metadata)
- Extract natural language instructions
- Support metadata.requires (bins, env, config)
- Support {baseDir} placeholder in instructions
- Validate SKILL.md structure

### FR2: Remove Single-File Mode

**Priority:** High

**Description:** Remove redundant agent_skill single-file mode

**Requirements:**
- Remove single-file option from AddSkillModalV2
- Update SkillTypeSelector to show only package mode for agent_skill
- Update backend to reject agent_skill with inline storage_type
- Migrate any existing single-file agent skills to langchain_tool

### FR3: Package Upload and Storage

**Priority:** High

**Description:** Support uploading and storing Agent Skill packages

**Requirements:**
- Accept ZIP/tar.gz uploads
- Extract and validate SKILL.md
- Store package in MinIO
- Store metadata in PostgreSQL
- Support package versioning

### FR4: Gating Requirements

**Priority:** Medium

**Description:** Support skill gating based on requirements

**Requirements:**
- Check for required binaries on PATH
- Check for required environment variables
- Check for required config values
- Mark skills as eligible/ineligible based on gates
- Show gating status in UI

### FR5: Natural Language Testing

**Priority:** Medium

**Description:** Test Agent Skills with natural language

**Requirements:**
- Accept natural language test input
- Parse skill instructions
- Simulate tool execution (dry run)
- Return natural language output
- Show what commands/APIs would be called

### FR6: UI Improvements

**Priority:** High

**Description:** Fix Agent Skill display in UI

**Requirements:**
- Show proper icon for agent_skill type
- Show "Agent Skill" type label
- Show gating requirements
- Show homepage link
- Distinct card styling

## Non-Functional Requirements

### NFR1: Backward Compatibility

**Priority:** High

**Description:** Maintain compatibility with existing LangChain Tools

**Requirements:**
- Existing langchain_tool skills continue to work
- No breaking changes to langchain_tool API
- Clear migration path for single-file agent skills

### NFR2: Performance

**Priority:** Medium

**Description:** Efficient package handling

**Requirements:**
- Package upload < 5 seconds for 10MB files
- SKILL.md parsing < 100ms
- MinIO storage with CDN support

### NFR3: Security

**Priority:** High

**Description:** Secure package handling

**Requirements:**
- Validate package contents (no malicious files)
- Sandbox skill testing
- Validate SKILL.md structure
- Limit package size (max 50MB)

## Data Model Changes

### Skill Table Updates

```python
class Skill:
    # Existing fields
    skill_id: UUID
    name: str
    description: str
    version: str
    skill_type: str  # 'langchain_tool' or 'agent_skill'
    storage_type: str  # 'inline' or 'minio'
    
    # New/Updated fields for agent_skill
    skill_md_content: Optional[str]  # Parsed SKILL.md content
    homepage: Optional[str]  # From frontmatter
    metadata: Optional[dict]  # From frontmatter (requires, emoji, etc.)
    gating_status: Optional[dict]  # Eligibility check results
    
    # Existing fields (unchanged)
    code: Optional[str]  # Only for langchain_tool
    interface_definition: dict  # Only for langchain_tool
    storage_path: Optional[str]  # MinIO path for packages
    manifest: Optional[dict]  # Package manifest
```

## API Changes

### Create Skill Endpoint

**Before:**
```json
POST /api/v1/skills
{
  "name": "my_skill",
  "description": "...",
  "skill_type": "agent_skill",
  "code": "...",  // Single-file mode
  "interface_definition": {...}
}
```

**After:**
```json
POST /api/v1/skills
Content-Type: multipart/form-data

name: "my_skill"
description: "..."
skill_type: "agent_skill"
package_file: <ZIP/tar.gz>  // Package mode only
```

### Test Skill Endpoint

**Before:**
```json
POST /api/v1/skills/{skill_id}/test
{
  "inputs": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

**After (for agent_skill):**
```json
POST /api/v1/skills/{skill_id}/test
{
  "natural_language_input": "Get the weather for London",
  "dry_run": true  // Don't actually execute commands
}
```

## Success Metrics

1. **Clarity:** Users can distinguish between LangChain Tools and Agent Skills
2. **Usability:** Agent Skills are easier to create (markdown vs code)
3. **Flexibility:** Agent Skills can teach any tool usage (bash, APIs, CLIs)
4. **Correctness:** Agent skill cards display properly with icon and label
5. **Adoption:** Users create more Agent Skills than before

## Out of Scope

- Automatic skill discovery from ClawdHub
- Skill marketplace/sharing
- Skill versioning and updates
- Multi-language support (Python only for now)
- Skill dependencies and composition

## Open Questions

1. Should we support inline SKILL.md (paste markdown) or only package upload?
2. How to handle skill testing without actual tool execution?
3. Should we migrate existing single-file agent skills automatically?
4. What's the maximum package size limit?
5. Should we support skill templates for SKILL.md format?

## References

- Moltbot skills documentation: `examples-of-reference/moltbot/docs/tools/skills.md`
- Moltbot weather skill example: `examples-of-reference/moltbot/skills/weather/SKILL.md`
- LangChain demo: `examples-of-reference/langchain-demo/app.py`
- AgentSkills.io specification: https://agentskills.io
