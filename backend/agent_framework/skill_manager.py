"""Skill Manager for Agent Framework.

This module manages skill discovery, loading, and integration for agents.
It handles two types of skills:
1. LangChain Tools: Direct tool execution (wrapped as LangChain tools)
2. Agent Skills: Documentation-based (included in prompt, agent decides how to use)

References:
- Design: docs/backend/agent-skill-integration-design.md
- Requirements 4: Skill Library
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.tools import BaseTool

from skill_library.runtime_registry import get_skill_runtime_registry

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Information about a skill available to an agent."""

    skill_id: UUID
    skill_slug: str
    display_name: str
    description: str
    skill_type: str  # "langchain_tool" or "agent_skill"
    storage_type: str  # "inline", "minio", etc.
    storage_path: Optional[str] = None
    skill_md_content: Optional[str] = None
    code: Optional[str] = None
    interface_definition: Optional[dict] = None
    manifest: Optional[dict] = None

    @property
    def name(self) -> str:
        return self.skill_slug


@dataclass
class AgentSkillReference:
    """Reference to an Agent Skill for prompt inclusion.

    Agent Skills are NOT wrapped as tools. Instead, only their name and description
    are included in the system prompt. The agent can use the read_skill tool to
    read the full SKILL.md content when needed.

    This follows the moltbot pattern:
    1. List skills with name + description in prompt
    2. Agent decides which skill to use
    3. Agent calls read_skill to get full documentation
    4. Agent follows the documentation to execute the skill
    """

    skill_id: UUID  # Skill UUID for code loading
    skill_slug: str
    display_name: str
    description: str
    skill_md_content: str  # Full SKILL.md content (loaded but not in prompt)
    has_scripts: bool  # Whether package contains Python scripts
    storage_path: Optional[str] = None  # MinIO storage path for package skills
    manifest: Optional[dict] = None  # Parsed manifest for package skills
    package_path: Optional[Path] = None  # Path to extracted package (if needed)
    package_files: Dict[str, str] = None  # filename -> content mapping for example code

    def __post_init__(self):
        if self.package_files is None:
            self.package_files = {}

    @property
    def name(self) -> str:
        return self.skill_slug

    def format_for_prompt(self) -> str:
        """Format skill for inclusion in agent prompt.
        
        Only includes name and description - NOT the full SKILL.md content.
        Agent must use read_skill tool to get full documentation.
        
        Returns:
            Formatted string for system prompt (name + description only)
        """
        return f"- {self.display_name} ({self.skill_slug}): {self.description}"


class SkillManager:
    """Manages skills for an agent.
    
    Responsibilities:
    - Discover available skills for an agent
    - Load LangChain tools
    - Load Agent Skill documentation
    - Provide skills to agent for initialization
    """
    
    def __init__(self, agent_id: UUID, user_id: UUID):
        """Initialize skill manager.
        
        Args:
            agent_id: Agent UUID
            user_id: User UUID (for permissions)
        """
        self.agent_id = agent_id
        self.user_id = user_id
        self.loaded_langchain_tools: Dict[UUID, BaseTool] = {}
        self.loaded_agent_skills: Dict[UUID, AgentSkillReference] = {}
        
        logger.info(
            f"SkillManager initialized for agent {agent_id}",
            extra={"agent_id": str(agent_id), "user_id": str(user_id)}
        )
    
    async def discover_skills(
        self,
        agent_capabilities: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[SkillInfo]:
        """Discover available skills for this agent.
        
        Skills are discovered based on:
        1. Agent's configured capabilities (skill IDs)
        2. User permissions
        3. Skill active status
        
        Args:
            agent_capabilities: List of skill IDs the agent can use
            context: Optional context for filtering
        
        Returns:
            List of SkillInfo objects
        """
        logger.info(
            "Discovering bound skills for agent %s",
            self.agent_id,
            extra={"agent_id": str(self.agent_id)},
        )

        runtime_registry = get_skill_runtime_registry()
        discovered_skills: List[SkillInfo] = []
        seen: set[tuple[UUID, str]] = set()

        for descriptor in runtime_registry.list_tool_skills(
            agent_id=self.agent_id,
            user_id=self.user_id,
        ):
            key = (descriptor.skill_id, "langchain_tool")
            if key in seen:
                continue
            seen.add(key)
            discovered_skills.append(
                SkillInfo(
                    skill_id=descriptor.skill_id,
                    skill_slug=descriptor.slug,
                    display_name=descriptor.display_name,
                    description=descriptor.description,
                    skill_type="langchain_tool",
                    storage_type=descriptor.artifact_storage_kind,
                    storage_path=descriptor.artifact_ref,
                    skill_md_content=descriptor.instruction_md,
                    code=descriptor.tool_code,
                    interface_definition=descriptor.interface_definition,
                    manifest=descriptor.manifest,
                )
            )

        for descriptor in runtime_registry.list_doc_skills(
            agent_id=self.agent_id,
            user_id=self.user_id,
        ):
            key = (descriptor.skill_id, "agent_skill")
            if key in seen:
                continue
            seen.add(key)
            discovered_skills.append(
                SkillInfo(
                    skill_id=descriptor.skill_id,
                    skill_slug=descriptor.slug,
                    display_name=descriptor.display_name,
                    description=descriptor.description,
                    skill_type="agent_skill",
                    storage_type=descriptor.artifact_storage_kind,
                    storage_path=descriptor.artifact_ref,
                    skill_md_content=descriptor.instruction_md,
                    code=descriptor.tool_code,
                    interface_definition=descriptor.interface_definition,
                    manifest=descriptor.manifest,
                )
            )

        logger.info(
            f"Discovered {len(discovered_skills)} skills for agent {self.agent_id}",
            extra={
                "agent_id": str(self.agent_id),
                "skill_count": len(discovered_skills)
            }
        )
        
        return discovered_skills
    
    async def load_langchain_tool(self, skill_info: SkillInfo) -> Optional[BaseTool]:
        """Load a LangChain tool from skill.
        
        Args:
            skill_info: Skill information
        
        Returns:
            LangChain BaseTool instance or None if loading fails
        """
        if skill_info.skill_type != "langchain_tool":
            logger.warning(
                f"Skill {skill_info.skill_slug} is not a langchain_tool",
                extra={"skill_id": str(skill_info.skill_id)}
            )
            return None
        
        # Check if already loaded
        if skill_info.skill_id in self.loaded_langchain_tools:
            logger.debug(f"LangChain tool {skill_info.skill_slug} already loaded")
            return self.loaded_langchain_tools[skill_info.skill_id]
        
        try:
            # Import the loader
            from agent_framework.loaders.langchain_tool_loader import LangChainToolLoader
            
            loader = LangChainToolLoader(
                agent_id=self.agent_id,
                user_id=self.user_id
            )
            
            tool = await loader.load(skill_info)
            
            if tool:
                self.loaded_langchain_tools[skill_info.skill_id] = tool
                logger.info(
                    f"Loaded LangChain tool: {skill_info.skill_slug}",
                    extra={"skill_id": str(skill_info.skill_id)}
                )
            
            return tool
            
        except Exception as e:
            logger.error(
                f"Failed to load LangChain tool {skill_info.skill_slug}: {e}",
                extra={"skill_id": str(skill_info.skill_id)},
                exc_info=True
            )
            return None
    
    async def _load_skill_package_files(self, skill_info: SkillInfo) -> Dict[str, str]:
        """Load files from skill package stored in MinIO.
        
        Extracts and reads example code, config files, and other relevant files
        from the skill package to include in the agent's prompt.
        
        Args:
            skill_info: Skill information
        
        Returns:
            Dictionary mapping filename to file content
        """
        import tempfile
        import zipfile
        import tarfile
        
        package_files = {}
        
        try:
            from object_storage.minio_client import get_minio_client
            
            minio_client = get_minio_client()
            bucket_name = minio_client.buckets.get("artifacts", "agent-artifacts")
            object_key = skill_info.storage_path
            
            # Remove bucket prefix if present
            if object_key.startswith(f"{bucket_name}/"):
                object_key = object_key[len(bucket_name) + 1:]
            
            logger.debug(
                f"Downloading skill package from MinIO",
                extra={
                    "bucket": bucket_name,
                    "object_key": object_key,
                    "skill_id": str(skill_info.skill_id)
                }
            )
            
            file_stream, metadata = minio_client.download_file(bucket_name, object_key)
            
            # Create temporary file for package
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                tmp_file.write(file_stream.read())
                tmp_file.flush()
                tmp_path = Path(tmp_file.name)
            
            try:
                # Extract package to temporary directory
                with tempfile.TemporaryDirectory() as extract_dir:
                    extract_path = Path(extract_dir)
                    
                    # Try ZIP first
                    try:
                        with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                            zip_ref.extractall(extract_path)
                    except zipfile.BadZipFile:
                        # Try tar.gz
                        with tarfile.open(tmp_path, 'r:gz') as tar_ref:
                            tar_ref.extractall(extract_path)
                    
                    # Read relevant files while preserving original package structure.
                    # Example: weather-forcast/scripts/weather_helper.py
                    relevant_extensions = {'.py', '.yaml', '.yml', '.json', '.txt', '.md'}

                    for file_path in extract_path.rglob('*'):
                        if file_path.is_file() and file_path.suffix in relevant_extensions:
                            # Skip __pycache__ and other system files
                            relative_path = file_path.relative_to(extract_path)
                            if (
                                '__pycache__' in relative_path.parts
                                or any(part.startswith('__') for part in relative_path.parts)
                                or any(part.startswith('.') for part in relative_path.parts)
                                or file_path.name.startswith('.')
                            ):
                                continue
                            
                            try:
                                # Read file content
                                content = file_path.read_text(encoding='utf-8')
                                
                                # Use full relative path (including package root dir) as key.
                                package_files[str(relative_path)] = content
                                
                                logger.debug(
                                    f"Loaded file from skill package: {relative_path}",
                                    extra={"skill_id": str(skill_info.skill_id)}
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to read file {file_path}: {e}",
                                    extra={"skill_id": str(skill_info.skill_id)}
                                )
            
            finally:
                # Clean up temporary file
                try:
                    tmp_path.unlink()
                except:
                    pass
        
        except Exception as e:
            logger.error(
                f"Failed to load package files for {skill_info.skill_slug}: {e}",
                extra={"skill_id": str(skill_info.skill_id)},
                exc_info=True
            )
        
        return package_files
    
    async def load_agent_skill_doc(
        self,
        skill_info: SkillInfo
    ) -> Optional[AgentSkillReference]:
        """Load Agent Skill documentation and package files for prompt inclusion.
        
        Agent Skills are NOT loaded as tools. Instead, we load their documentation
        (SKILL.md content) AND any example code/scripts from the package, which will
        be included in the agent's system prompt.
        
        Args:
            skill_info: Skill information
        
        Returns:
            AgentSkillReference or None if loading fails
        """
        if skill_info.skill_type != "agent_skill":
            logger.warning(
                f"Skill {skill_info.skill_slug} is not an agent_skill",
                extra={"skill_id": str(skill_info.skill_id)}
            )
            return None
        
        # Check if already loaded
        if skill_info.skill_id in self.loaded_agent_skills:
            logger.debug(f"Agent skill {skill_info.skill_slug} already loaded")
            return self.loaded_agent_skills[skill_info.skill_id]
        
        try:
            # Check if SKILL.md content exists
            if not skill_info.skill_md_content:
                logger.warning(
                    f"Agent skill {skill_info.skill_slug} has no SKILL.md content",
                    extra={"skill_id": str(skill_info.skill_id)}
                )
                return None
            
            # Load package files if stored in MinIO
            package_files = {}
            if skill_info.storage_type == "minio" and skill_info.storage_path:
                package_files = await self._load_skill_package_files(skill_info)
            
            # Check if skill has Python scripts
            has_scripts = bool(package_files) or (
                skill_info.manifest and (
                    skill_info.manifest.get("entry_points") or
                    skill_info.manifest.get("scripts")
                )
            )
            
            # Create reference
            skill_ref = AgentSkillReference(
                skill_id=skill_info.skill_id,
                skill_slug=skill_info.skill_slug,
                display_name=skill_info.display_name,
                description=skill_info.description,
                skill_md_content=skill_info.skill_md_content,
                has_scripts=has_scripts,
                storage_path=skill_info.storage_path,
                manifest=skill_info.manifest,
                package_path=None,  # Not needed - we include files directly
                package_files=package_files  # Include all package files
            )
            
            self.loaded_agent_skills[skill_info.skill_id] = skill_ref
            
            logger.info(
                f"Loaded Agent Skill documentation: {skill_info.skill_slug}",
                extra={
                    "skill_id": str(skill_info.skill_id),
                    "has_scripts": has_scripts,
                    "file_count": len(package_files)
                }
            )
            
            return skill_ref
            
        except Exception as e:
            logger.error(
                f"Failed to load Agent Skill {skill_info.skill_slug}: {e}",
                extra={"skill_id": str(skill_info.skill_id)},
                exc_info=True
            )
            return None
    
    def get_langchain_tools(self) -> List[BaseTool]:
        """Get all loaded LangChain tools.
        
        Returns:
            List of LangChain BaseTool instances
        """
        return list(self.loaded_langchain_tools.values())
    
    def get_agent_skill_docs(self) -> List[AgentSkillReference]:
        """Get all loaded Agent Skill documentation.
        
        Returns:
            List of AgentSkillReference objects
        """
        return list(self.loaded_agent_skills.values())
    
    def format_skills_for_prompt(self) -> str:
        """Format Agent Skills for inclusion in agent prompt.
        
        Following moltbot pattern: Only include skill names and descriptions.
        Agent must use read_skill tool to get full SKILL.md content.
        
        Returns:
            Formatted string for system prompt
        """
        agent_skills = self.get_agent_skill_docs()
        
        logger.info(
            f"Formatting {len(agent_skills)} agent skills for prompt",
            extra={
                "agent_id": str(self.agent_id),
                "skill_count": len(agent_skills),
                "skill_slugs": [skill.skill_slug for skill in agent_skills],
            }
        )
        
        if not agent_skills:
            logger.warning(
                f"No agent skills loaded for agent {self.agent_id}",
                extra={"agent_id": str(self.agent_id)}
            )
            return ""
        
        # Format: only name + description (NOT full SKILL.md content)
        skills_list = "\n".join([
            skill.format_for_prompt() for skill in agent_skills
        ])
        
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
        
        logger.debug(
            f"Generated skills prompt section (length: {len(prompt)}, skills: {len(agent_skills)})",
            extra={"agent_id": str(self.agent_id)}
        )
        
        return prompt
    
    async def reload_skills(self, agent_capabilities: List[str]) -> None:
        """Reload all skills for the agent.
        
        This can be called to refresh skills without restarting the agent.
        
        Args:
            agent_capabilities: Updated list of skill IDs
        """
        logger.info(
            f"Reloading skills for agent {self.agent_id}",
            extra={"agent_id": str(self.agent_id)}
        )
        
        # Clear loaded skills
        self.loaded_langchain_tools.clear()
        self.loaded_agent_skills.clear()
        
        # Discover and load skills again
        skills = await self.discover_skills(agent_capabilities)
        
        for skill_info in skills:
            if skill_info.skill_type == "langchain_tool":
                await self.load_langchain_tool(skill_info)
            elif skill_info.skill_type == "agent_skill":
                await self.load_agent_skill_doc(skill_info)
        
        logger.info(
            f"Reloaded {len(self.loaded_langchain_tools)} LangChain tools and "
            f"{len(self.loaded_agent_skills)} Agent Skills",
            extra={"agent_id": str(self.agent_id)}
        )


def get_skill_manager(agent_id: UUID, user_id: UUID) -> SkillManager:
    """Get a SkillManager instance for an agent.
    
    Args:
        agent_id: Agent UUID
        user_id: User UUID
    
    Returns:
        SkillManager instance
    """
    return SkillManager(agent_id=agent_id, user_id=user_id)
