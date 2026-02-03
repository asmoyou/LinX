"""Read Skill Tool - Allows agent to read full SKILL.md content on demand.

This tool enables agents to:
1. Read the complete SKILL.md documentation for a specific skill
2. Access example code and configuration files from the skill package
3. Load skills only when needed (lazy loading)

References:
- Design: docs/backend/agent-skill-integration-design.md
- Moltbot reference: examples-of-reference/moltbot/src/agents/system-prompt.ts
"""

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ReadSkillInput(BaseModel):
    """Input for read_skill tool."""
    
    skill_name: str = Field(description="Name of the skill to read (e.g., 'my_cal', 'weather-forcast')")


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
    
    args_schema: type[BaseModel] = ReadSkillInput
    
    agent_id: UUID
    user_id: UUID
    skill_manager: Any  # SkillManager instance with loaded skills
    
    # Use model_config instead of Config class
    model_config = {"arbitrary_types_allowed": True}
    
    def _run(self, skill_name: str) -> str:
        """Read skill documentation synchronously."""
        try:
            # Use the skill_manager instance passed during initialization
            # This instance already has the agent's skills loaded
            skill_manager = self.skill_manager
            
            # Get the skill reference from loaded agent skills
            agent_skills = skill_manager.get_agent_skill_docs()
            
            # Find the skill by name
            skill_ref = None
            for skill in agent_skills:
                if skill.name == skill_name:
                    skill_ref = skill
                    break
            
            if not skill_ref:
                return f"❌ Error: Skill '{skill_name}' not found or not configured for this agent.\n\nAvailable skills: {', '.join([s.name for s in agent_skills])}"
            
            # Format the skill documentation
            output = f"""# Skill: {skill_ref.name}

## Description
{skill_ref.description}

## Documentation (SKILL.md)

{skill_ref.skill_md_content}

"""
            
            # Add example code if available
            if skill_ref.package_files:
                output += "\n## Available Files in Skill Package\n\n"
                for filename, content in skill_ref.package_files.items():
                    # Only include relevant files (Python, YAML, JSON, TXT)
                    if filename.endswith(('.py', '.yaml', '.yml', '.json', '.txt')):
                        output += f"### File: {filename}\n\n```python\n{content}\n```\n\n"
            
            # Add execution note
            if skill_ref.has_scripts:
                output += "\n## Execution Note\n\nThis skill includes executable Python scripts. You can use the `code_execution` tool to run them.\n"
            else:
                output += "\n## Execution Note\n\nThis is a workflow/documentation skill. Follow the instructions to accomplish the task.\n"
            
            logger.info(
                f"Agent read skill documentation: {skill_name}",
                extra={
                    "agent_id": str(self.agent_id),
                    "skill_name": skill_name,
                    "doc_length": len(output)
                }
            )
            
            return output
            
        except Exception as e:
            logger.error(f"Failed to read skill {skill_name}: {e}", exc_info=True)
            return f"❌ Error reading skill '{skill_name}': {str(e)}"
    
    async def _arun(self, skill_name: str) -> str:
        """Read skill documentation asynchronously."""
        return self._run(skill_name)


def create_read_skill_tool(agent_id: UUID, user_id: UUID, skill_manager: Any) -> ReadSkillTool:
    """Create a read_skill tool instance.
    
    Args:
        agent_id: Agent UUID
        user_id: User UUID
        skill_manager: SkillManager instance with loaded skills
    
    Returns:
        ReadSkillTool instance
    """
    return ReadSkillTool(
        agent_id=agent_id,
        user_id=user_id,
        skill_manager=skill_manager
    )
