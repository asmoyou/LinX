"""Read Skill Tool - Allows agent to read full SKILL.md content on demand.

This tool enables agents to:
1. Read the complete SKILL.md documentation for a specific skill
2. Access example code and configuration files from the skill package
3. Load skills only when needed (lazy loading)
4. Extract executable code blocks for direct use

References:
- Design: docs/backend/agent-skill-integration-design.md
- Design: .kiro/specs/code-execution-improvement/design.md
- Moltbot reference: examples-of-reference/moltbot/src/agents/system-prompt.ts
"""

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from skill_library.skill_loader import SkillLoader, get_skill_loader

logger = logging.getLogger(__name__)


class ReadSkillInput(BaseModel):
    """Input for read_skill tool."""
    
    skill_name: str = Field(description="Name of the skill to read (e.g., 'my_cal', 'weather-forcast')")


class ReadSkillTool(BaseTool):
    """Tool for reading complete skill documentation.
    
    This tool allows the agent to read the full SKILL.md content and
    extract executable code for a specific skill when needed.
    """
    
    name: str = "read_skill"
    description: str = """Read the complete documentation (SKILL.md) for a specific skill and extract executable code.

Use this tool when:
- You've decided to use a specific skill
- You need to understand how to use the skill
- You need to see example code or get executable code
- You want to import and run skill code directly

Input: skill_name (e.g., "my_cal", "weather-forcast")
Output: Complete SKILL.md content with extracted code blocks ready for execution"""
    
    args_schema: type[BaseModel] = ReadSkillInput
    
    agent_id: UUID
    user_id: UUID
    skill_manager: Any  # SkillManager instance with loaded skills
    skill_loader: SkillLoader  # SkillLoader for extracting code
    
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
            
            # Load skill package with code extraction
            skill_package = self.skill_loader.load_skill(
                skill_id=skill_ref.skill_id,
                skill_name=skill_ref.name,
                skill_md_content=skill_ref.skill_md_content,
                storage_path=skill_ref.storage_path,
                manifest=skill_ref.manifest,
            )

            # Replace {baseDir} placeholders with relative path hint
            # Since skill files are copied to workdir, {baseDir} should be "."
            skill_md_cleaned = skill_ref.skill_md_content.replace('{baseDir}/', '')
            skill_md_cleaned = skill_md_cleaned.replace('{baseDir}', '.')

            # Format the skill documentation
            output = f"""# Skill: {skill_ref.name}

## Description
{skill_ref.description}

## Documentation (SKILL.md)

{skill_md_cleaned}

"""
            
            # Add extracted executable code blocks
            if skill_package.code_blocks:
                output += "\n## Extracted Executable Code\n\n"
                output += "The following code blocks have been extracted and are ready for execution:\n\n"
                
                for idx, code_block in enumerate(skill_package.code_blocks, 1):
                    if code_block.is_executable:
                        output += f"### Code Block {idx}: {code_block.language.upper()}"
                        if code_block.filename:
                            output += f" ({code_block.filename})"
                        if code_block.description:
                            output += f"\n**Description:** {code_block.description}"
                        output += f"\n\n```{code_block.language}\n{code_block.code}\n```\n\n"
                
                # Provide execution instructions
                output += "\n## How to Execute This Code\n\n"
                output += "**CRITICAL: All skill files are pre-loaded in the working directory!**\n\n"
                output += "To execute code, simply output it as a markdown code block:\n\n"

                python_code = skill_package.get_executable_code('python')
                if python_code:
                    output += """**For Python scripts in the skill package**, use RELATIVE paths:
```bash
python3 scripts/weather_helper.py current --location "Fuzhou"
```

**For inline Python code**:
```python
import requests
# ... your code here ...
print(result)
```

"""

                bash_code = skill_package.get_executable_code('bash')
                if bash_code:
                    output += """**For Bash code**:
```bash
curl "https://api.example.com/..."
```

"""
                output += "**IMPORTANT RULES:**\n"
                output += "- Use RELATIVE paths like `scripts/xxx.py`, NOT absolute paths\n"
                output += "- DO NOT use placeholders like `{baseDir}` or `/path/to/...`\n"
                output += "- All skill files are ALREADY in the current working directory\n"
                output += "- API keys and credentials are pre-configured in the environment\n"
                output += "- Just output the code block - it will be executed automatically\n\n"
            
            # Add package files if available
            if skill_ref.package_files:
                output += "\n## Available Files in Skill Package\n\n"
                for filename, content in skill_ref.package_files.items():
                    # Only include relevant files (Python, YAML, JSON, TXT)
                    if filename.endswith(('.py', '.yaml', '.yml', '.json', '.txt')):
                        output += f"### File: {filename}\n\n```python\n{content}\n```\n\n"
            
            # Add execution note
            if skill_ref.has_scripts or skill_package.code_blocks:
                output += "\n## Execution Rules\n\n"
                output += "1. All skill files are PRE-LOADED in the working directory\n"
                output += "2. Use RELATIVE paths: `python3 scripts/xxx.py` (NOT `/path/to/...`)\n"
                output += "3. Output code as ```bash or ```python code blocks\n"
                output += "4. The code will be executed automatically\n"
                output += "5. DO NOT use {baseDir} placeholders - just use relative paths\n"
                output += "6. API keys are pre-configured - just run the code\n"
            else:
                output += "\n## Execution Note\n\nThis is a workflow/documentation skill. Follow the instructions to accomplish the task.\n"
            
            logger.info(
                f"Agent read skill documentation: {skill_name}",
                extra={
                    "agent_id": str(self.agent_id),
                    "skill_name": skill_name,
                    "doc_length": len(output),
                    "code_blocks": len(skill_package.code_blocks),
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
        skill_manager=skill_manager,
        skill_loader=get_skill_loader(),
    )
