# Agent Skill Integration Design

## Overview

This document outlines the design for integrating two types of skills into the LinX agent framework:
1. **LangChain Tools**: Standard LangChain tools that can be directly used by agents
2. **Agent Skills**: Packaged Python projects (similar to moltbot's skills) that agents can dynamically load and execute

## Current State Analysis

### What We Have
- **Skill Library Module** (`backend/skill_library/`):
  - Skill registry and validation
  - Two skill types: `langchain_tool` and `agent_skill`
  - Package handler for ZIP/tar.gz uploads
  - Storage in MinIO (artifacts bucket)
  - SKILL.md parser for metadata

- **Agent Framework** (`backend/agent_framework/`):
  - BaseAgent with LangChain integration
  - AgentExecutor for task execution
  - AgentRegistry for managing agent instances
  - Memory interface integration

### What's Missing
- **Dynamic skill loading**: Agents don't currently load skills dynamically
- **Skill discovery**: No mechanism for agents to discover available skills
- **Skill invocation**: No standardized way for agents to call skills
- **Tool registration**: LangChain tools aren't registered with agents
- **Skill context**: Skills don't have access to agent context (user_id, session, etc.)

## Reference Implementation Analysis

### Moltbot Approach

**Key Insights from moltbot**:

1. **Skill Loading** (`src/agents/skills/workspace.ts`):
   - Skills are loaded from multiple directories with precedence
   - Precedence: extra < bundled < managed < workspace
   - Skills are Markdown files with frontmatter metadata
   - Skills contain bash commands/scripts

2. **Skill Structure**:
   ```markdown
   ---
   name: weather
   description: Get current weather
   metadata: {"moltbot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
   ---
   
   # Weather
   
   Quick one-liner:
   ```bash
   curl -s "wttr.in/London?format=3"
   ```
   ```

3. **Skill Integration**:
   - Skills are formatted into a prompt for the LLM
   - Agent decides which skill to use based on user request
   - Skills are executed as bash commands
   - Results are returned to the agent

4. **Skill Filtering**:
   - Skills can be filtered by name
   - Skills have eligibility context (remote, environment, etc.)
   - Skills can be disabled via configuration

### Claude-Code Approach

**Key Insights from claude-code**:

1. **Plugin System**:
   - Plugins extend agent capabilities
   - Each plugin has commands and hooks
   - Plugins are loaded from directories

2. **Command Structure**:
   - Commands are user-invocable actions
   - Commands can dispatch to tools
   - Commands have descriptions for discovery

## Proposed Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Agent Instance                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              BaseAgent (LangChain)                     │ │
│  │  - LLM Configuration                                   │ │
│  │  - System Prompt                                       │ │
│  │  - Tools (LangChain Tools + Agent Skills)             │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Skill Manager                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Skill Discovery                                       │ │
│  │  - Load skills from database                          │ │
│  │  - Filter by agent capabilities                       │ │
│  │  - Build skill catalog                                │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Skill Loader                                          │ │
│  │  - LangChain Tool Loader                              │ │
│  │  - Agent Skill Package Loader                         │ │
│  │  - Skill Context Injection                            │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Skill Executor                                        │ │
│  │  - Execute LangChain tools                            │ │
│  │  - Execute Agent Skill packages                       │ │
│  │  - Handle errors and timeouts                         │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Skill Registry                            │
│  - Database: skills table                                   │
│  - Storage: MinIO (artifacts bucket)                        │
│  - Metadata: SKILL.md parsing                               │
└─────────────────────────────────────────────────────────────┘
```

### Component Design

#### 1. Skill Manager (`backend/agent_framework/skill_manager.py`)

**Purpose**: Manage skill discovery, loading, and execution for agents

**Key Classes**:

```python
class SkillManager:
    """Manages skills for an agent."""
    
    def __init__(self, agent_id: UUID, user_id: UUID):
        self.agent_id = agent_id
        self.user_id = user_id
        self.skill_registry = get_skill_registry()
        self.loaded_skills: Dict[str, LoadedSkill] = {}
    
    async def discover_skills(
        self,
        capabilities: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List[SkillInfo]:
        """Discover available skills for this agent."""
        # Query database for skills matching agent capabilities
        # Filter by user permissions
        # Return skill metadata
        pass
    
    async def load_skill(self, skill_id: UUID) -> LoadedSkill:
        """Load a skill and make it available to the agent."""
        # Check if already loaded
        # Load from database
        # Download package from MinIO if needed
        # Parse SKILL.md
        # Create appropriate wrapper (LangChain tool or Agent skill)
        pass
    
    def get_langchain_tools(self) -> List[BaseTool]:
        """Get all loaded skills as LangChain tools."""
        # Convert loaded skills to LangChain tools
        # Return list of tools for agent
        pass
    
    def format_skills_for_prompt(self) -> str:
        """Format skills for inclusion in agent prompt."""
        # Similar to moltbot's formatSkillsForPrompt
        # Include skill names, descriptions, usage examples
        pass
```

#### 2. Skill Loaders

**LangChain Tool Loader** (`backend/agent_framework/loaders/langchain_tool_loader.py`):

```python
class LangChainToolLoader:
    """Load LangChain tools from skill packages."""
    
    async def load(self, skill: Skill) -> BaseTool:
        """Load a LangChain tool from a skill."""
        # Download package from MinIO
        # Extract and import Python module
        # Instantiate LangChain tool
        # Inject context (user_id, agent_id, etc.)
        # Return tool instance
        pass
```

**Agent Skill Loader** (`backend/agent_framework/loaders/agent_skill_loader.py`):

```python
class AgentSkillLoader:
    """Load Agent Skills (packaged Python projects)."""
    
    async def load(self, skill: Skill) -> AgentSkillWrapper:
        """Load an agent skill package."""
        # Download package from MinIO
        # Extract to temporary directory
        # Parse SKILL.md for entry points
        # Create wrapper that can execute scripts
        # Return wrapper
        pass
```

#### 3. Skill Wrappers

**Agent Skill Wrapper** (`backend/agent_framework/wrappers/agent_skill_wrapper.py`):

**IMPORTANT**: Agent Skills are NOT directly wrapped as tools. Instead:
1. Agent Skills are included in the system prompt as documentation
2. Agent reads the SKILL.md content and decides how to use it
3. Agent may write code to execute the skill, or follow the workflow
4. Agent uses the code execution sandbox to run any generated code

```python
class AgentSkillReference:
    """Reference to an Agent Skill for prompt inclusion."""
    
    name: str
    description: str
    skill_md_content: str  # Full SKILL.md content
    has_scripts: bool  # Whether package contains Python scripts
    package_path: Optional[Path]  # Path to extracted package (if needed)
    
    def format_for_prompt(self) -> str:
        """Format skill for inclusion in agent prompt."""
        return f"""
## Skill: {self.name}

{self.skill_md_content}

{"This skill includes executable Python scripts in the package." if self.has_scripts else "This is a workflow/documentation skill. Follow the instructions to accomplish the task."}
"""
```

#### 4. Skill Context

**Skill Execution Context** (`backend/agent_framework/skill_context.py`):

```python
@dataclass
class SkillExecutionContext:
    """Context provided to skills during execution."""
    
    agent_id: UUID
    user_id: UUID
    session_id: Optional[UUID]
    workspace_dir: Path
    env_vars: Dict[str, str]  # User-specific environment variables
    permissions: List[str]
    
    def to_env(self) -> Dict[str, str]:
        """Convert context to environment variables."""
        return {
            "LINX_AGENT_ID": str(self.agent_id),
            "LINX_USER_ID": str(self.user_id),
            "LINX_SESSION_ID": str(self.session_id) if self.session_id else "",
            **self.env_vars
        }
```

### Integration with BaseAgent

**Modified BaseAgent** (`backend/agent_framework/base_agent.py`):

```python
class BaseAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.skill_manager = SkillManager(
            agent_id=config.agent_id,
            user_id=config.owner_user_id
        )
        # ... existing initialization
    
    async def initialize(self):
        """Initialize agent with skills."""
        # Discover available skills based on agent's configured skill list
        skills = await self.skill_manager.discover_skills(
            agent_id=self.config.agent_id,
            user_id=self.config.owner_user_id
        )
        
        # Load skills
        langchain_tools = []
        agent_skill_docs = []
        
        for skill_info in skills:
            if skill_info.skill_type == "langchain_tool":
                tool = await self.skill_manager.load_langchain_tool(skill_info.skill_id)
                langchain_tools.append(tool)
            elif skill_info.skill_type == "agent_skill":
                # Agent skills are NOT loaded as tools
                # They are included in the prompt as documentation
                skill_doc = await self.skill_manager.load_agent_skill_doc(skill_info.skill_id)
                agent_skill_docs.append(skill_doc)
        
        # Add code execution tool (for agent to run generated code)
        from virtualization.code_execution_sandbox import CodeExecutionTool
        code_exec_tool = CodeExecutionTool(
            agent_id=self.config.agent_id,
            user_id=self.config.owner_user_id
        )
        langchain_tools.append(code_exec_tool)
        
        # Create agent with tools
        self.agent = create_react_agent(
            llm=self.llm,
            tools=langchain_tools,
            prompt=self._create_system_prompt(agent_skill_docs)
        )
    
    def _create_system_prompt(self, agent_skill_docs: List[AgentSkillReference]) -> str:
        """Create system prompt with skill information."""
        base_prompt = self.config.system_prompt or DEFAULT_SYSTEM_PROMPT
        
        # Add LangChain tools section (handled by LangChain automatically)
        
        # Add Agent Skills section (as documentation)
        if agent_skill_docs:
            skills_section = "\n\n".join([
                skill.format_for_prompt() for skill in agent_skill_docs
            ])
            
            agent_skills_prompt = f"""

## Available Agent Skills (Documentation)

The following skills are available as documentation and workflows. You can:
1. Follow the instructions in the skill documentation
2. Write Python code to execute the workflow
3. Use the code_execution tool to run any code you write

{skills_section}

When a user asks you to use one of these skills, read the documentation carefully and decide the best approach to accomplish the task.
"""
        else:
            agent_skills_prompt = ""
        
        return f"""{base_prompt}{agent_skills_prompt}"""
```

### Skill Discovery and Filtering

**Capability Matching**:

```python
def match_skills_to_agent(
    agent_capabilities: List[str],
    available_skills: List[Skill]
) -> List[Skill]:
    """Match skills to agent based on capabilities."""
    matched = []
    for skill in available_skills:
        # Check if skill's required capabilities are subset of agent's capabilities
        if set(skill.required_capabilities or []).issubset(set(agent_capabilities)):
            matched.append(skill)
    return matched
```

**Permission Filtering**:

```python
def filter_skills_by_permissions(
    skills: List[Skill],
    user_id: UUID,
    agent_id: UUID
) -> List[Skill]:
    """Filter skills based on user permissions."""
    # Check user has access to each skill
    # Check agent is allowed to use each skill
    # Return filtered list
    pass
```

### Skill Execution Flow

**For LangChain Tools**:

1. Agent receives user request
2. LLM decides to use a tool
3. Tool is executed directly (already a LangChain tool)
4. Result is returned to agent
5. Agent continues conversation

**For Agent Skills** (Documentation/Workflow):

1. Agent receives user request
2. Agent sees Agent Skills in system prompt as documentation
3. LLM reads the SKILL.md content and understands the workflow
4. Agent decides how to accomplish the task:
   - Option A: Follow the workflow instructions (e.g., "use curl to call wttr.in")
   - Option B: Write Python code to execute the workflow
   - Option C: Use existing Python scripts from the skill package (if available)
5. If code execution needed, agent uses the code execution sandbox
6. Agent interprets results and responds to user

**Example - Weather Skill**:
```markdown
# In system prompt:
## Skill: weather_forecast

Get current weather using wttr.in (no API key required).

Quick one-liner:
```bash
curl -s "wttr.in/London?format=3"
# Output: London: ⛅️ +8°C
```

# Agent sees this and decides:
# "I'll write Python code to call wttr.in"
import subprocess
result = subprocess.run(['curl', '-s', 'wttr.in/London?format=3'], capture_output=True, text=True)
print(result.stdout)
```

### Database Schema Updates

**Add to `skills` table**:

```sql
ALTER TABLE skills ADD COLUMN required_capabilities JSONB;
ALTER TABLE skills ADD COLUMN entry_points JSONB;  -- For agent skills
ALTER TABLE skills ADD COLUMN execution_timeout INTEGER DEFAULT 30;
```

**New table `agent_skills`** (many-to-many):

```sql
CREATE TABLE agent_skills (
    agent_id UUID REFERENCES agents(agent_id) ON DELETE CASCADE,
    skill_id UUID REFERENCES skills(skill_id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (agent_id, skill_id)
);
```

### Configuration

**Agent Configuration** (add to `agents` table or config):

```python
{
    "skills": {
        "auto_discover": true,  # Automatically discover skills based on capabilities
        "allowed_skills": ["*"],  # Or specific skill names
        "denied_skills": [],
        "max_concurrent_executions": 3,
        "execution_timeout": 30
    }
}
```

### Security Considerations

1. **Sandboxing**: Agent skills must run in isolated environments
   - Use subprocess with restricted permissions
   - Set resource limits (CPU, memory, time)
   - Restrict network access if needed

2. **Code Validation**: Validate skill packages before loading
   - Check for malicious code patterns
   - Verify package integrity
   - Scan for vulnerabilities

3. **Permission Checks**: Always verify permissions before execution
   - User must own or have access to skill
   - Agent must be authorized to use skill
   - Skill must be enabled for agent

4. **Environment Isolation**: Each skill execution gets isolated environment
   - Temporary workspace directory
   - Isolated environment variables
   - No access to other skills' data

### Implementation Status

### Phase 1: Foundation - IN PROGRESS ✅

**Completed:**
- [x] Created SkillManager class (`backend/agent_framework/skill_manager.py`)
  - Skill discovery based on agent capabilities
  - Loading LangChain tools
  - Loading Agent Skill documentation (not as tools)
  - Formatting skills for prompt inclusion
- [x] Created LangChainToolLoader (`backend/agent_framework/loaders/langchain_tool_loader.py`)
  - Loads tools from inline code
  - Loads tools from MinIO packages
  - Handles ZIP and tar.gz archives
- [x] Created CodeExecutionTool (`backend/agent_framework/tools/code_execution_tool.py`)
  - Wraps virtualization sandbox as LangChain tool
  - Allows agents to execute Python code safely
- [x] Integrated SkillManager with BaseAgent
  - Updated `initialize()` to be async
  - Discovers and loads skills during initialization
  - Adds code execution tool automatically
  - Includes Agent Skills in system prompt
- [x] Updated AgentLifecycleManager
  - Made `initialize_agent()` async
- [x] Updated API Gateway
  - Fixed agent initialization calls to use async

**Next Steps:**
- [ ] Test the implementation with actual skills
- [ ] Fix any bugs in skill loading
- [ ] Add error handling improvements
- [ ] Create unit tests

## Implementation Phases

**Phase 1: Foundation** (Current Task)
- [ ] Create SkillManager class
- [ ] Implement skill discovery
- [ ] Create LangChainToolLoader
- [ ] Create AgentSkillLoader
- [ ] Create AgentSkillWrapper

**Phase 2: Integration**
- [ ] Integrate SkillManager with BaseAgent
- [ ] Update agent initialization to load skills
- [ ] Modify system prompt generation
- [ ] Add skill execution context

**Phase 3: Testing**
- [ ] Test LangChain tool loading
- [ ] Test Agent skill loading
- [ ] Test skill execution
- [ ] Test error handling

**Phase 4: API Updates**
- [ ] Update agent creation API to handle skills
- [ ] Add skill assignment endpoints
- [ ] Update skill test endpoint to use SkillManager
- [ ] Add skill discovery endpoint for agents

**Phase 5: Frontend**
- [ ] Add skill selection UI for agents
- [ ] Show available skills for each agent
- [ ] Enable/disable skills per agent
- [ ] Test skill execution from UI

## Example Usage

### Creating an Agent with Skills

```python
# 1. Create agent
agent = await agent_registry.create_agent(
    name="Weather Assistant",
    agent_type="assistant",
    capabilities=["weather", "location"],
    llm_provider="ollama",
    llm_model="llama2"
)

# 2. Skills are automatically discovered and loaded based on capabilities

# 3. User asks: "What's the weather in London?"

# 4. Agent's LLM sees available skills in prompt:
#    - weather_forecast: Get weather forecast for a location
#    - location_lookup: Convert city name to coordinates

# 5. Agent decides to use weather_forecast skill

# 6. Skill is executed with context (user_id, agent_id, etc.)

# 7. Result is returned to agent

# 8. Agent formats response for user
```

### Skill Package Structure

**LangChain Tool**:
```
weather-tool/
├── SKILL.md              # Metadata
├── __init__.py
├── weather_tool.py       # LangChain tool implementation
└── requirements.txt
```

**Agent Skill**:
```
weather-skill/
├── SKILL.md              # Metadata with entry points
├── get_weather.py        # Executable script
├── forecast.py           # Another script
├── utils.py              # Helper functions
└── requirements.txt
```

**SKILL.md for Agent Skill**:
```markdown
---
name: weather_forecast
description: Get weather forecast for any location
skill_type: agent_skill
required_capabilities: ["weather"]
entry_points:
  get_current: get_weather.py
  get_forecast: forecast.py
---

# Weather Forecast Skill

This skill provides weather information using multiple APIs.

## Usage

The agent can call this skill with natural language like:
- "Get current weather for London"
- "What's the forecast for New York?"

## Entry Points

- `get_current`: Get current weather
- `get_forecast`: Get 7-day forecast
```

## Open Questions

1. **Skill Versioning**: ✅ **DECIDED: Always use latest version**
   - Skills in database only store latest version
   - Updates overwrite previous version
   - Simpler implementation and maintenance

2. **Skill Dependencies**: ✅ **DECIDED: Skills are independent**
   - Each skill is self-contained
   - If agent needs something not in skill, it can create it
   - No dependency management needed

3. **Skill Marketplace**: ✅ **DECIDED: Skills can be shared**
   - Skills belong to skill library (not agent-specific)
   - Agents configure which skills they can use
   - Sharing is at skill library level, not agent level

4. **Skill Caching**: ⚠️ **NEEDS DECISION**
   - **Option A**: Load skills on every agent initialization
     - Pros: Always fresh, no stale data
     - Cons: Slower initialization, repeated I/O
   
   - **Option B**: Cache in memory with TTL (e.g., 5 minutes)
     - Pros: Fast access, reduced I/O
     - Cons: May serve stale data briefly
   
   - **Option C**: Cache with change detection (database triggers/events)
     - Pros: Fast + always fresh
     - Cons: More complex implementation
   
   - **RECOMMENDATION**: Start with Option B (TTL cache), add Option C later if needed
     - Use 5-minute TTL for skill metadata
     - Invalidate cache on skill updates
     - Simple LRU cache implementation

5. **Skill Execution Environment**: ✅ **DECIDED: Use existing virtualization system**
   - System already has gVisor/Firecracker/Docker isolation
   - Located in `backend/virtualization/`
   - Use code_execution_sandbox for running agent-generated code
   - Fallback chain: gVisor → Firecracker → Docker
   - No need to reinvent isolation

6. **Agent Skill Type**: ✅ **CLARIFIED: Documentation-based, not direct execution**
   - Agent Skills are NOT wrapped as tools
   - They are included in system prompt as documentation
   - Agent reads SKILL.md and decides how to use it
   - Agent may write code or follow workflow instructions
   - Uses existing code execution sandbox if needed

## Next Steps

1. **Review this design document**
2. **Discuss and refine approach**
3. **Create implementation plan**
4. **Begin Phase 1 implementation**

## References

- Moltbot skills: `examples-of-reference/moltbot/src/agents/skills/`
- Claude-code plugins: `examples-of-reference/claude-code/plugins/`
- LangChain tools: https://python.langchain.com/docs/modules/agents/tools/
- Current skill library: `backend/skill_library/`
