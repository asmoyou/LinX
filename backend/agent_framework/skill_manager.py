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

from database.connection import get_db_session
from database.models import Skill as SkillModel
from skill_library.skill_registry import get_skill_registry

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Information about a skill available to an agent."""
    
    skill_id: UUID
    name: str
    description: str
    skill_type: str  # "langchain_tool" or "agent_skill"
    storage_type: str  # "inline", "minio", etc.
    storage_path: Optional[str] = None
    skill_md_content: Optional[str] = None
    code: Optional[str] = None
    interface_definition: Optional[dict] = None
    manifest: Optional[dict] = None


@dataclass
class AgentSkillReference:
    """Reference to an Agent Skill for prompt inclusion.
    
    Agent Skills are NOT wrapped as tools. Instead, they are included in the
    system prompt as documentation. The agent reads the SKILL.md content and
    decides how to use it (write code, follow workflow, use provided scripts, etc.)
    """
    
    name: str
    description: str
    skill_md_content: str  # Full SKILL.md content
    has_scripts: bool  # Whether package contains Python scripts
    package_path: Optional[Path] = None  # Path to extracted package (if needed)
    package_files: Dict[str, str] = None  # filename -> content mapping for example code
    
    def __post_init__(self):
        if self.package_files is None:
            self.package_files = {}
    
    def format_for_prompt(self) -> str:
        """Format skill for inclusion in agent prompt.
        
        Returns:
            Formatted string for system prompt
        """
        script_info = (
            "This skill includes executable Python scripts in the package."
            if self.has_scripts
            else "This is a workflow/documentation skill. Follow the instructions to accomplish the task."
        )
        
        prompt = f"""
## Skill: {self.name}

{self.skill_md_content}

{script_info}
"""
        
        # Include example code files if available
        if self.package_files:
            prompt += "\n### Available Example Code:\n\n"
            for filename, content in self.package_files.items():
                # Only include Python files and config files
                if filename.endswith(('.py', '.yaml', '.yml', '.json', '.txt')):
                    prompt += f"**File: {filename}**\n```python\n{content}\n```\n\n"
        
        return prompt


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
        self.skill_registry = get_skill_registry()
        self.loaded_langchain_tools: Dict[UUID, BaseTool] = {}
        self.loaded_agent_skills: Dict[UUID, AgentSkillReference] = {}
        
        logger.info(
            f"SkillManager initialized for agent {agent_id}",
            extra={"agent_id": str(agent_id), "user_id": str(user_id)}
        )
    
    async def discover_skills(
        self,
        agent_capabilities: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List[SkillInfo]:
        """Discover available skills for this agent.
        
        Skills are discovered based on:
        1. Agent's configured capabilities (skill names)
        2. User permissions
        3. Skill active status
        
        Args:
            agent_capabilities: List of skill names the agent can use
            context: Optional context for filtering
        
        Returns:
            List of SkillInfo objects
        """
        logger.info(
            f"Discovering skills for agent {self.agent_id}",
            extra={
                "agent_id": str(self.agent_id),
                "capabilities": agent_capabilities
            }
        )
        
        discovered_skills = []
        
        with get_db_session() as session:
            # Query skills that match agent's capabilities
            for skill_name in agent_capabilities:
                # Get latest version of each skill
                skill = session.query(SkillModel).filter(
                    SkillModel.name == skill_name,
                    SkillModel.is_active == True
                ).order_by(SkillModel.created_at.desc()).first()
                
                if skill:
                    # TODO: Add permission check here
                    # For now, assume user has access to all active skills
                    
                    skill_info = SkillInfo(
                        skill_id=skill.skill_id,
                        name=skill.name,
                        description=skill.description,
                        skill_type=skill.skill_type,
                        storage_type=skill.storage_type,
                        storage_path=skill.storage_path,
                        skill_md_content=skill.skill_md_content,
                        code=skill.code,
                        interface_definition=skill.interface_definition,
                        manifest=skill.manifest
                    )
                    discovered_skills.append(skill_info)
                    
                    logger.debug(
                        f"Discovered skill: {skill.name}",
                        extra={
                            "skill_id": str(skill.skill_id),
                            "skill_type": skill.skill_type
                        }
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
                f"Skill {skill_info.name} is not a langchain_tool",
                extra={"skill_id": str(skill_info.skill_id)}
            )
            return None
        
        # Check if already loaded
        if skill_info.skill_id in self.loaded_langchain_tools:
            logger.debug(f"LangChain tool {skill_info.name} already loaded")
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
                    f"Loaded LangChain tool: {skill_info.name}",
                    extra={"skill_id": str(skill_info.skill_id)}
                )
            
            return tool
            
        except Exception as e:
            logger.error(
                f"Failed to load LangChain tool {skill_info.name}: {e}",
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
                    
                    # Find the skill directory (skip __MACOSX and other system dirs)
                    skill_dirs = [
                        d for d in extract_path.iterdir()
                        if d.is_dir() and not d.name.startswith('__') and not d.name.startswith('.')
                    ]
                    
                    if not skill_dirs:
                        logger.warning(
                            f"No skill directory found in package for {skill_info.name}",
                            extra={"skill_id": str(skill_info.skill_id)}
                        )
                        return package_files
                    
                    skill_dir = skill_dirs[0]
                    
                    # Read relevant files (Python, YAML, JSON, TXT)
                    relevant_extensions = {'.py', '.yaml', '.yml', '.json', '.txt', '.md'}
                    
                    for file_path in skill_dir.rglob('*'):
                        if file_path.is_file() and file_path.suffix in relevant_extensions:
                            # Skip SKILL.md (already loaded separately)
                            if file_path.name == 'SKILL.md':
                                continue
                            
                            # Skip __pycache__ and other system files
                            if '__pycache__' in file_path.parts or file_path.name.startswith('.'):
                                continue
                            
                            try:
                                # Read file content
                                content = file_path.read_text(encoding='utf-8')
                                
                                # Use relative path as key
                                relative_path = file_path.relative_to(skill_dir)
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
                f"Failed to load package files for {skill_info.name}: {e}",
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
                f"Skill {skill_info.name} is not an agent_skill",
                extra={"skill_id": str(skill_info.skill_id)}
            )
            return None
        
        # Check if already loaded
        if skill_info.skill_id in self.loaded_agent_skills:
            logger.debug(f"Agent skill {skill_info.name} already loaded")
            return self.loaded_agent_skills[skill_info.skill_id]
        
        try:
            # Check if SKILL.md content exists
            if not skill_info.skill_md_content:
                logger.warning(
                    f"Agent skill {skill_info.name} has no SKILL.md content",
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
                name=skill_info.name,
                description=skill_info.description,
                skill_md_content=skill_info.skill_md_content,
                has_scripts=has_scripts,
                package_path=None,  # Not needed - we include files directly
                package_files=package_files  # Include all package files
            )
            
            self.loaded_agent_skills[skill_info.skill_id] = skill_ref
            
            logger.info(
                f"Loaded Agent Skill documentation: {skill_info.name}",
                extra={
                    "skill_id": str(skill_info.skill_id),
                    "has_scripts": has_scripts,
                    "file_count": len(package_files)
                }
            )
            
            return skill_ref
            
        except Exception as e:
            logger.error(
                f"Failed to load Agent Skill {skill_info.name}: {e}",
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
        
        Similar to moltbot's formatSkillsForPrompt function.
        
        Returns:
            Formatted string for system prompt
        """
        agent_skills = self.get_agent_skill_docs()
        
        if not agent_skills:
            return ""
        
        skills_section = "\n\n".join([
            skill.format_for_prompt() for skill in agent_skills
        ])
        
        prompt = f"""

## Available Agent Skills (Documentation)

The following skills are available as documentation and workflows. You can:
1. Follow the instructions in the skill documentation
2. Write Python code to execute the workflow
3. Use the code_execution tool to run any code you write

{skills_section}

When a user asks you to use one of these skills, read the documentation carefully and decide the best approach to accomplish the task.
"""
        
        return prompt
    
    async def reload_skills(self, agent_capabilities: List[str]) -> None:
        """Reload all skills for the agent.
        
        This can be called to refresh skills without restarting the agent.
        
        Args:
            agent_capabilities: Updated list of skill names
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
