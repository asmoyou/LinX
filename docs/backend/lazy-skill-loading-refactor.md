# Lazy Skill Loading Refactor

## Overview

Refactored the agent skill system to implement lazy loading following the moltbot pattern. This significantly reduces token usage and improves agent performance by only loading full skill documentation when needed.

## Problem

Previously, the entire SKILL.md content for all configured skills was included in the agent's system prompt. This:
- Wasted tokens on skills the agent might not use
- Reduced context window available for actual conversation
- Decreased agent performance due to prompt bloat

## Solution

Implemented lazy loading pattern inspired by moltbot:

1. **System prompt**: Only includes skill names + short descriptions
2. **Agent decision**: Agent chooses which skill to use based on descriptions
3. **On-demand loading**: Agent calls `read_skill` tool to get full SKILL.md
4. **Execution**: Agent follows SKILL.md instructions (may be multi-turn)
5. **Summary**: Agent returns final result to user

## Changes Made

### 1. Modified `AgentSkillReference.format_for_prompt()`

**File**: `backend/agent_framework/skill_manager.py`

Changed from returning full SKILL.md content to only name + description:

```python
def format_for_prompt(self) -> str:
    """Format skill for inclusion in agent prompt.
    
    Only includes name and description - NOT the full SKILL.md content.
    Agent must use read_skill tool to get full documentation.
    """
    return f"- {self.name}: {self.description}"
```

### 2. Updated `SkillManager.format_skills_for_prompt()`

**File**: `backend/agent_framework/skill_manager.py`

Updated to follow moltbot pattern with clear instructions:

```python
def format_skills_for_prompt(self) -> str:
    """Format Agent Skills for inclusion in agent prompt.
    
    Following moltbot pattern: Only include skill names and descriptions.
    Agent must use read_skill tool to get full SKILL.md content.
    """
    # ... code ...
    
    prompt = f"""

## Skills (mandatory)

Before replying: scan available skills below.
- If exactly one skill clearly applies: read its SKILL.md with `read_skill`, then follow it.
- If multiple could apply: choose the most specific one, then read/follow it.
- If none clearly apply: do not read any SKILL.md.

Constraints: never read more than one skill up front; only read after selecting.

Available skills:
{skills_list}

"""
```

### 3. Added `read_skill` Tool

**File**: `backend/agent_framework/tools/read_skill_tool.py`

Created new tool that allows agents to read full SKILL.md content on demand:

```python
class ReadSkillTool(BaseTool):
    """Tool for reading complete skill documentation.
    
    This tool allows the agent to read the full SKILL.md content and
    example code for a specific skill when needed.
    """
    
    name: str = "read_skill"
    description: str = """Read the complete documentation (SKILL.md) for a specific skill.

Use this tool when:
- You've decided to use a specific skill
- You need to understand how to use the skill
- You need to see example code or configuration

Input: skill_name (e.g., "my_cal", "weather-forcast")
Output: Complete SKILL.md content with usage instructions and examples"""
```

### 4. Integrated `read_skill` Tool in Agent Initialization

**File**: `backend/agent_framework/base_agent.py`

Added read_skill tool to agent's toolset:

```python
# Add read_skill tool (for lazy loading of Agent Skills)
from agent_framework.tools.read_skill_tool import create_read_skill_tool
read_skill_tool = create_read_skill_tool(
    agent_id=self.config.agent_id,
    user_id=self.config.owner_user_id
)
self.tools.append(read_skill_tool)
```

### 5. Simplified System Prompt

**File**: `backend/agent_framework/base_agent.py`

Removed over-emphasis on code_execution tool:

```python
def _create_system_prompt(self) -> str:
    # ... code ...
    
    # Simplified tool listing - no special treatment for code_execution
    if self.tools and not self.llm_supports_tools:
        tools_prompt = "\n\n## Available Tools\n\n"
        tools_prompt += "You have access to the following tools. Use them when appropriate:\n\n"
        
        for tool in self.tools:
            tools_prompt += f"- {tool.name}: {tool.description}\n"
```

### 6. Added Multi-Turn Execution with Recursion Limits

**File**: `backend/agent_framework/base_agent.py`

Added support for multi-turn tool execution with configurable limits:

```python
# Compile the agent graph with recursion limit
self.agent = builder.compile(
    checkpointer=None,
    interrupt_before=None,
    interrupt_after=None,
    debug=False
)

# Set recursion limit based on max_iterations
# Each iteration can have: LLM call -> Tool call -> LLM call
# So we need at least 2x max_iterations for the recursion limit
self.recursion_limit = self.config.max_iterations * 2

# Use recursion limit when invoking
result = self.agent.invoke(
    {"messages": [HumanMessage(content=user_message)]},
    config={"recursion_limit": self.recursion_limit}
)
```

### 7. Updated System Prompt for Multi-Turn Guidance

**File**: `backend/agent_framework/base_agent.py`

Added clear guidelines for when agent should complete tasks:

```python
## Task Execution Guidelines

When solving problems:
1. Analyze the user's request carefully
2. Use available tools when appropriate
3. Execute multiple steps if needed (you can call tools multiple times)
4. Provide clear and helpful responses
5. If you need more information from the user, ask clarifying questions

## When to Complete

You should complete the task when:
- You have successfully accomplished what the user asked for
- You have gathered all necessary information and provided a complete answer
- You need additional input from the user (ask a question and wait)

You can use tools multiple times in sequence to accomplish complex tasks. 
The system allows up to {max_iterations} iterations.
```

## Architecture

### Two Types of Skills

1. **LangChain Tool**: Lightweight, single-turn, fast execution
   - Bound directly to LLM
   - Example: `my_cal` (calculator)
   - No lazy loading needed (already lightweight)

2. **Agent Skill**: Heavyweight, multi-turn, complex workflows
   - Requires reading SKILL.md documentation
   - Example: `weather-forcast` (multi-step workflow)
   - Uses lazy loading pattern

### Workflow

```
User Request
    ↓
Agent analyzes request
    ↓
Agent scans skill descriptions (in prompt)
    ↓
Agent selects appropriate skill (if needed)
    ↓
Agent calls read_skill("skill-name") (if needed)
    ↓
read_skill returns full SKILL.md
    ↓
Agent follows SKILL.md instructions
    ↓
Agent may execute code, call APIs, etc. (multi-turn)
    ↓
Agent may call more tools if needed (up to max_iterations)
    ↓
Agent decides task is complete
    ↓
Agent returns final summary to user
```

### Multi-Turn Execution

The agent can execute multiple tool calls in sequence:

1. **LangGraph handles the loop**: The agent graph automatically loops between LLM and tool nodes
2. **Recursion limit**: Set to `max_iterations * 2` to allow multiple LLM→Tool→LLM cycles
3. **Agent decides when done**: Agent stops when it has no more tool calls to make
4. **Prevents infinite loops**: Recursion limit ensures the agent doesn't loop forever
5. **Configurable**: `max_iterations` can be set per agent (default: 10)

Example multi-turn flow:
```
User: "What's the weather in Beijing?"
    ↓
Agent: Calls read_skill("weather-forcast")
    ↓
Agent: Reads SKILL.md instructions
    ↓
Agent: Calls code_execution to fetch weather data
    ↓
Agent: Analyzes the data
    ↓
Agent: Formats and returns weather summary
```

## Benefits

1. **Reduced Token Usage**: Only load skills that are actually used
2. **Better Performance**: Smaller prompts = faster inference
3. **More Context**: More room for conversation history
4. **Clearer Intent**: Agent explicitly chooses which skill to use
5. **Better Tool Selection**: Agent prefers specialized tools (my_cal) over generic ones (code_execution)
6. **Multi-Turn Execution**: Agent can execute multiple tool calls in sequence to accomplish complex tasks
7. **Controlled Iterations**: Recursion limit prevents infinite loops while allowing flexible execution
8. **Agent-Driven Completion**: Agent decides when task is complete or when to ask for user input

## Testing

To test the lazy loading:

1. **Test LangChain Tool** (should be called directly):
   ```
   User: "What is 2423 * 1312?"
   Expected: Agent calls my_cal tool directly
   ```

2. **Test Agent Skill** (should read SKILL.md first):
   ```
   User: "What's the weather in Beijing?"
   Expected: 
   - Agent calls read_skill("weather-forcast")
   - Agent reads SKILL.md
   - Agent follows instructions
   - Agent returns weather summary
   ```

3. **Test Thinking/Content Separation**:
   ```
   User: "Calculate 21312 * 213"
   Expected:
   - Frontend shows thinking process separately
   - Frontend shows final answer in content section
   - No mixing of thinking and content
   ```

## References

- Moltbot reference: `examples-of-reference/moltbot/src/agents/system-prompt.ts`
- Original design: `docs/backend/agent-skill-integration-design.md`
- CustomOpenAIChat: `backend/llm_providers/custom_openai_provider.py`

## Future Improvements

1. **Caching**: Cache read SKILL.md content within a conversation
2. **Skill Discovery**: Allow agent to search for skills by capability
3. **Skill Composition**: Allow agent to combine multiple skills
4. **Skill Versioning**: Support multiple versions of the same skill
