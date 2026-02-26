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
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
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

    @staticmethod
    def _sanitize_skill_dir(skill_name: str) -> str:
        """Normalize skill name to a safe directory name."""
        candidate = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(skill_name or "")).strip("._")
        return candidate or "skill"

    @classmethod
    def _infer_skill_base_dir(
        cls, skill_name: str, package_files: Optional[Dict[str, str]]
    ) -> str:
        """Infer workspace base directory for package files."""
        if not package_files:
            return "."

        # Preferred: directory containing SKILL.md in package structure.
        for rel_path in package_files:
            path_obj = Path(rel_path)
            if path_obj.name != "SKILL.md":
                continue
            if len(path_obj.parts) > 1:
                return path_obj.parts[0]

        top_level_dirs = {
            Path(rel_path).parts[0]
            for rel_path in package_files
            if len(Path(rel_path).parts) > 1
        }
        if len(top_level_dirs) == 1:
            only_dir = next(iter(top_level_dirs))
            if only_dir.lower() not in {"scripts", "src", "lib", "docs"}:
                return only_dir

        # Legacy layout stores files directly in workspace root.
        return "."
    
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
                storage_path=None,
                manifest=skill_ref.manifest,
                package_files=skill_ref.package_files or {},
            )

            package_files = skill_ref.package_files or {}
            skill_base_dir = self._infer_skill_base_dir(skill_ref.name, package_files)

            skill_md_source = skill_ref.skill_md_content or ""
            if skill_base_dir == ".":
                skill_md_cleaned = skill_md_source.replace("{baseDir}/", "")
                skill_md_cleaned = skill_md_cleaned.replace("{baseDir}", ".")
            else:
                skill_md_cleaned = skill_md_source.replace(
                    "{baseDir}/", f"{skill_base_dir}/"
                )
                skill_md_cleaned = skill_md_cleaned.replace("{baseDir}", skill_base_dir)

            python_scripts: List[str] = sorted(
                path for path in package_files if path.endswith(".py")
            )
            requirements_files: List[str] = sorted(
                path for path in package_files if Path(path).name.startswith("requirements")
            )
            preferred_script = next(
                (path for path in python_scripts if path.endswith("weather_helper.py")),
                python_scripts[0] if python_scripts else None,
            )

            # Format the skill documentation
            output = f"""# Skill: {skill_ref.name}

## Description
{skill_ref.description}

## Package Workspace Layout

- Skill base directory: `{skill_base_dir}`
- Use relative paths from workspace root, e.g. `{skill_base_dir}/scripts/...` (or `scripts/...` when base is `.`)

"""

            if preferred_script or requirements_files:
                output += "## Execution Strategy (MANDATORY)\n\n"
                output += "1. Run existing packaged scripts first; do NOT rewrite API logic first.\n"
                if requirements_files:
                    output += (
                        f"2. If dependency is missing, install from `{requirements_files[0]}`.\n"
                    )
                else:
                    output += "2. If dependency is missing, install required package(s) before rerun.\n"
                output += "3. Only write custom code when packaged scripts are unusable.\n\n"
                if requirements_files:
                    output += f"```bash\npython3 -m pip install -r {requirements_files[0]}\n```\n\n"
                if preferred_script:
                    output += f"```bash\npython3 {preferred_script} --help\n```\n\n"
                    output += (
                        "Never hardcode placeholder API keys such as `your_api_key`; "
                        "use environment variables expected by the script.\n\n"
                    )

            output += f"""## Documentation (SKILL.md)

{skill_md_cleaned}

"""

            # Add package files first so model can prioritize scripts/config over ad-hoc code.
            if package_files:
                output += "## Available Files in Skill Package\n\n"
                for filename, content in sorted(package_files.items()):
                    if Path(filename).name == "SKILL.md":
                        continue
                    if filename.endswith((".py", ".yaml", ".yml", ".json", ".txt", ".md")):
                        output += f"### File: {filename}\n\n```text\n{content}\n```\n\n"

            # Add extracted executable code blocks (reference/fallback).
            if skill_package.code_blocks:
                output += "\n## Extracted Code Blocks (Reference)\n\n"
                output += "Use packaged scripts first; these blocks are fallback/reference.\n\n"
                
                for idx, code_block in enumerate(skill_package.code_blocks, 1):
                    if code_block.is_executable:
                        output += f"### Code Block {idx}: {code_block.language.upper()}"
                        if code_block.filename:
                            output += f" ({code_block.filename})"
                        if code_block.description:
                            output += f"\n**Description:** {code_block.description}"
                        output += f"\n\n```{code_block.language}\n{code_block.code}\n```\n\n"
            
            # Add execution note
            if skill_ref.has_scripts or skill_package.code_blocks:
                output += "\n## Execution Rules\n\n"
                output += "1. All skill files are PRE-LOADED in the working directory\n"
                output += "2. Use packaged script paths first (from file list above)\n"
                output += "3. Install dependencies from requirements file when needed\n"
                output += "4. Avoid placeholder API keys; rely on environment variables\n"
                output += "5. Only fallback to ad-hoc code when packaged scripts fail\n"
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
