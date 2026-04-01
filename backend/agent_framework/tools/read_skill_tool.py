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

    skill_name: str = Field(
        description="Skill slug to read (e.g., 'my_cal', 'weather-forcast')"
    )


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

Input: skill_name / skill slug (e.g., "my_cal", "weather-forcast")
Output: Complete SKILL.md content with extracted code blocks ready for execution"""
    
    args_schema: type[BaseModel] = ReadSkillInput
    
    agent_id: UUID
    user_id: UUID
    skill_manager: Any  # SkillManager instance with loaded skills
    skill_loader: SkillLoader  # SkillLoader for extracting code
    
    # Use model_config instead of Config class
    model_config = {"arbitrary_types_allowed": True}

    @staticmethod
    def _skill_slug(skill_ref: Any) -> str:
        return str(
            getattr(skill_ref, "skill_slug", None)
            or getattr(skill_ref, "name", None)
            or ""
        ).strip()

    @staticmethod
    def _skill_display_name(skill_ref: Any) -> str:
        return str(
            getattr(skill_ref, "display_name", None)
            or getattr(skill_ref, "name", None)
            or getattr(skill_ref, "skill_slug", None)
            or "Skill"
        ).strip()

    @classmethod
    def _skill_identifier_candidates(cls, skill_ref: Any) -> List[str]:
        candidates: List[str] = []
        for value in (
            cls._skill_slug(skill_ref),
            cls._skill_display_name(skill_ref),
            str(getattr(skill_ref, "name", None) or "").strip(),
        ):
            if value and value not in candidates:
                candidates.append(value)

        slug = cls._skill_slug(skill_ref)
        if "-installed-" in slug:
            base_slug = slug.split("-installed-", 1)[0].strip()
            if base_slug and base_slug not in candidates:
                candidates.append(base_slug)

        return candidates

    @classmethod
    def _matches_skill_request(cls, skill_ref: Any, requested_skill_name: str) -> bool:
        requested = str(requested_skill_name or "").strip()
        if not requested:
            return False

        requested_lower = requested.casefold()
        return any(candidate.casefold() == requested_lower for candidate in cls._skill_identifier_candidates(skill_ref))

    @staticmethod
    def _sanitize_skill_dir(skill_slug: str) -> str:
        """Normalize skill slug to a safe directory name."""
        candidate = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(skill_slug or "")).strip("._")
        return candidate or "skill"

    @classmethod
    def _workspace_skill_root(cls, skill_slug: str) -> str:
        """Return workspace-relative root directory for one skill package."""
        return f".skills/{cls._sanitize_skill_dir(skill_slug)}"

    @staticmethod
    def _sanitize_relative_path(raw_path: str) -> Optional[Path]:
        """Normalize package-relative path and drop traversal segments."""
        parts: List[str] = []
        for part in Path(str(raw_path or "").replace("\\", "/")).parts:
            if part in {"", ".", ".."}:
                continue
            parts.append(part)
        if not parts:
            return None
        return Path(*parts)

    @classmethod
    def _infer_package_root_dir(cls, package_files: Optional[Dict[str, str]]) -> Optional[str]:
        """Infer package archive root directory to flatten under .skills/<skill-name>/."""
        if not package_files:
            return None

        normalized_paths: List[Path] = []
        for rel_path in package_files:
            safe_path = cls._sanitize_relative_path(rel_path)
            if safe_path is not None:
                normalized_paths.append(safe_path)

        if not normalized_paths:
            return None

        for path_obj in normalized_paths:
            if path_obj.name == "SKILL.md" and len(path_obj.parts) > 1:
                return path_obj.parts[0]

        top_level_dirs = {p.parts[0] for p in normalized_paths if len(p.parts) > 1}
        has_root_files = any(len(p.parts) == 1 for p in normalized_paths)
        if len(top_level_dirs) == 1 and not has_root_files:
            only_dir = next(iter(top_level_dirs))
            if only_dir.lower() not in {"scripts", "src", "lib", "docs"}:
                return only_dir

        return None

    @classmethod
    def _normalize_package_relative_path(
        cls, raw_path: str, package_root_dir: Optional[str]
    ) -> Optional[Path]:
        """Normalize package path and strip archive root directory when detected."""
        safe_relative = cls._sanitize_relative_path(raw_path)
        if safe_relative is None:
            return None

        parts = safe_relative.parts
        if package_root_dir and parts and parts[0] == package_root_dir:
            stripped_parts = parts[1:]
            if stripped_parts:
                return Path(*stripped_parts)

        return safe_relative

    def _materialize_skill_files_to_workspace(self, skill_ref: Any) -> int:
        """Copy selected skill package files to current workspace root on demand."""
        try:
            from agent_framework.tools.file_tools import get_workspace_root
        except Exception:
            return 0

        workspace_root = get_workspace_root()
        if workspace_root is None:
            return 0

        package_files = skill_ref.package_files or {}
        skill_root = Path(workspace_root) / self._workspace_skill_root(self._skill_slug(skill_ref))
        package_root_dir = self._infer_package_root_dir(package_files)
        copied = 0

        for filename, content in package_files.items():
            safe_relative = self._normalize_package_relative_path(filename, package_root_dir)
            if safe_relative is None:
                continue
            destination = skill_root / safe_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
            if destination.suffix in {".py", ".sh"}:
                destination.chmod(0o755)
            copied += 1

        has_skill_doc = bool(
            package_files and any(Path(path).name == "SKILL.md" for path in package_files)
        )
        if skill_ref.skill_md_content and not has_skill_doc:
            skill_doc_path = skill_root / "SKILL.md"
            skill_doc_path.parent.mkdir(parents=True, exist_ok=True)
            skill_doc_path.write_text(skill_ref.skill_md_content, encoding="utf-8")
            copied += 1

        return copied

    def _run(self, skill_name: str) -> str:
        """Read skill documentation synchronously."""
        try:
            # Use the skill_manager instance passed during initialization
            # This instance already has the agent's skills loaded
            skill_manager = self.skill_manager
            
            # Get the skill reference from loaded agent skills
            agent_skills = skill_manager.get_agent_skill_docs()
            
            requested_skill_name = str(skill_name or "").strip()

            # Find the skill by slug
            skill_ref = None
            for skill in agent_skills:
                if self._matches_skill_request(skill, requested_skill_name):
                    skill_ref = skill
                    break
            
            if not skill_ref:
                available_skills = ", ".join(
                    f"{self._skill_display_name(skill)} ({self._skill_slug(skill)})"
                    for skill in agent_skills
                )
                return (
                    f"Error: Skill '{requested_skill_name}' not found or not configured for "
                    f"this agent.\n\nAvailable skills: {available_skills}"
                )

            materialized_count = self._materialize_skill_files_to_workspace(skill_ref)
            if materialized_count:
                logger.info(
                    "Materialized skill files into workspace for read_skill",
                    extra={
                        "agent_id": str(self.agent_id),
                        "skill_slug": self._skill_slug(skill_ref),
                        "file_count": materialized_count,
                    },
                )

            # Load skill package with code extraction
            skill_package = self.skill_loader.load_skill(
                skill_id=skill_ref.skill_id,
                skill_name=self._skill_slug(skill_ref),
                skill_md_content=skill_ref.skill_md_content,
                storage_path=None,
                manifest=skill_ref.manifest,
                package_files=skill_ref.package_files or {},
            )

            package_files = skill_ref.package_files or {}
            workspace_skill_root = self._workspace_skill_root(self._skill_slug(skill_ref))
            package_root_dir = self._infer_package_root_dir(package_files)
            skill_base_dir = workspace_skill_root

            def _workspace_package_path(rel_path: str) -> str:
                safe_relative = self._normalize_package_relative_path(rel_path, package_root_dir)
                if safe_relative is None:
                    return workspace_skill_root
                normalized = str(safe_relative).replace("\\", "/").lstrip("./")
                if not normalized:
                    return workspace_skill_root
                return f"{workspace_skill_root}/{normalized}"

            skill_md_source = skill_ref.skill_md_content or ""
            skill_md_cleaned = skill_md_source.replace("{baseDir}/", f"{skill_base_dir}/")
            skill_md_cleaned = skill_md_cleaned.replace("{baseDir}", skill_base_dir)

            normalized_workspace_files = {
                path: _workspace_package_path(path) for path in package_files
            }
            shell_scripts: List[str] = sorted(
                normalized_workspace_files[path]
                for path in package_files
                if path.endswith(".sh")
            )
            python_scripts: List[str] = sorted(
                normalized_workspace_files[path]
                for path in package_files
                if path.endswith(".py")
            )
            requirements_files: List[str] = sorted(
                normalized_workspace_files[path]
                for path in package_files
                if Path(path).name.startswith("requirements")
            )
            preferred_shell_script = next(
                (path for path in shell_scripts if path.endswith("render_document.sh")),
                shell_scripts[0] if shell_scripts else None,
            )
            preferred_script = next(
                (path for path in python_scripts if path.endswith("weather_helper.py")),
                python_scripts[0] if python_scripts else None,
            )

            # Format the skill documentation
            output = f"""# Skill: {self._skill_display_name(skill_ref)} ({self._skill_slug(skill_ref)})

## Description
{skill_ref.description}

## Package Workspace Layout

- Skill base directory: `{skill_base_dir}`
- Skill package root is flattened under `.skills/<skill_slug>/` to avoid workspace root pollution.
- Use relative paths from workspace root, e.g. `{skill_base_dir}/scripts/...`

"""

            if preferred_shell_script or preferred_script or requirements_files:
                output += "## Execution Strategy (MANDATORY)\n\n"
                output += "1. Run existing packaged scripts first; do NOT rewrite API logic first.\n"
                if preferred_shell_script:
                    output += (
                        "2. If a packaged shell entrypoint exists, run it before any Python "
                        "or ReportLab rewrite.\n"
                    )
                else:
                    output += "2. Prefer packaged command entrypoints over code_execution rewrites.\n"
                if requirements_files:
                    output += (
                        f"3. If dependency is missing, install from `{requirements_files[0]}`.\n"
                    )
                else:
                    output += "3. If dependency is missing, install required package(s) before rerun.\n"
                output += "4. Only write custom code when packaged scripts are unusable.\n\n"
                if requirements_files:
                    output += f"```bash\npython3 -m pip install -r {requirements_files[0]}\n```\n\n"
                if preferred_shell_script:
                    output += f"```bash\nbash {preferred_shell_script} --help\n```\n\n"
                    output += (
                        "If this shell entrypoint matches the task, start there instead of "
                        "writing a fresh ReportLab/Python renderer.\n\n"
                    )
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
                    if filename.endswith((".py", ".sh", ".yaml", ".yml", ".json", ".txt", ".md")):
                        output += (
                            f"### File: {_workspace_package_path(filename)}\n\n"
                            f"```text\n{content}\n```\n\n"
                        )

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
                output += (
                    "1. Selected skill files are materialized under `/workspace/.skills/...` "
                    "after `read_skill`\n"
                )
                output += "2. Use packaged script paths first (from file list above)\n"
                output += "3. Install dependencies from requirements file when needed\n"
                output += "4. Avoid placeholder API keys; rely on environment variables\n"
                output += "5. If a packaged shell script exists, prefer `bash <script>` over `code_execution`\n"
                output += "6. Only fallback to ad-hoc code when packaged scripts fail\n"
            else:
                output += "\n## Execution Note\n\nThis is a workflow/documentation skill. Follow the instructions to accomplish the task.\n"
            
            logger.info(
                f"Agent read skill documentation: {self._skill_slug(skill_ref)}",
                extra={
                    "agent_id": str(self.agent_id),
                    "skill_slug": self._skill_slug(skill_ref),
                    "doc_length": len(output),
                    "code_blocks": len(skill_package.code_blocks),
                }
            )
            
            return output
            
        except Exception as e:
            logger.error(f"Failed to read skill {skill_name}: {e}", exc_info=True)
            return f"Error reading skill '{skill_name}': {str(e)}"
    
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
