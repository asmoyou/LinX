"""LangChain Tool Loader.

Loads LangChain tools from skill packages stored in MinIO.

References:
- Design: docs/backend/agent-skill-integration-design.md
"""

import importlib.util
import logging
import sys
import tempfile
import zipfile
import tarfile
from pathlib import Path
from typing import Optional
from uuid import UUID

from langchain_core.tools import BaseTool

from object_storage.minio_client import get_minio_client

logger = logging.getLogger(__name__)


class LangChainToolLoader:
    """Loader for LangChain tools from skill packages."""
    
    def __init__(self, agent_id: UUID, user_id: UUID):
        """Initialize loader.
        
        Args:
            agent_id: Agent UUID (for context)
            user_id: User UUID (for permissions)
        """
        self.agent_id = agent_id
        self.user_id = user_id
        self.minio_client = get_minio_client()
        
        logger.debug(
            f"LangChainToolLoader initialized",
            extra={"agent_id": str(agent_id), "user_id": str(user_id)}
        )
    
    async def load(self, skill_info) -> Optional[BaseTool]:
        """Load a LangChain tool from skill package.
        
        Args:
            skill_info: SkillInfo object with skill details
        
        Returns:
            LangChain BaseTool instance or None if loading fails
        """
        logger.info(
            f"Loading LangChain tool: {skill_info.name}",
            extra={"skill_id": str(skill_info.skill_id)}
        )
        
        # Handle inline code (code stored directly in database)
        if skill_info.storage_type == "inline" and skill_info.code:
            return await self._load_from_inline_code(skill_info)
        
        # Handle package stored in MinIO
        elif skill_info.storage_type == "minio" and skill_info.storage_path:
            return await self._load_from_minio_package(skill_info)
        
        else:
            logger.error(
                f"Unsupported storage type or missing data for skill {skill_info.name}",
                extra={
                    "skill_id": str(skill_info.skill_id),
                    "storage_type": skill_info.storage_type
                }
            )
            return None
    
    async def _load_from_inline_code(self, skill_info) -> Optional[BaseTool]:
        """Load tool from inline Python code.
        
        For LangChain tools stored inline, we should use the skill_library's
        execution engine which already handles tool creation properly.
        
        Args:
            skill_info: SkillInfo object
        
        Returns:
            BaseTool instance or None
        """
        try:
            # Use skill_library's execution engine to create the tool
            # This is the same mechanism used for skill testing
            from skill_library.execution_engine import get_execution_engine
            from database.connection import get_db_session
            from database.models import Skill
            
            execution_engine = get_execution_engine()
            
            # Get Skill object from database
            with get_db_session() as session:
                skill = session.query(Skill).filter(
                    Skill.skill_id == skill_info.skill_id
                ).first()
                
                if not skill:
                    logger.error(
                        f"Skill not found in database: {skill_info.name}",
                        extra={"skill_id": str(skill_info.skill_id)}
                    )
                    return None
                
                # Get or create tool using the execution engine
                tool = execution_engine._get_or_create_tool(
                    skill=skill,
                    user_id=self.user_id
                )
            
            if tool and isinstance(tool, BaseTool):
                logger.info(
                    f"Loaded inline LangChain tool via execution engine: {skill_info.name}",
                    extra={"skill_id": str(skill_info.skill_id)}
                )
                return tool
            else:
                logger.error(
                    f"Execution engine returned invalid tool for {skill_info.name}",
                    extra={"skill_id": str(skill_info.skill_id)}
                )
                return None
                
        except Exception as e:
            logger.error(
                f"Failed to load inline tool {skill_info.name}: {e}",
                extra={"skill_id": str(skill_info.skill_id)},
                exc_info=True
            )
            return None
    
    async def _load_from_minio_package(self, skill_info) -> Optional[BaseTool]:
        """Load tool from package stored in MinIO.
        
        Args:
            skill_info: SkillInfo object
        
        Returns:
            BaseTool instance or None
        """
        try:
            # Download package from MinIO
            bucket_name = self.minio_client.buckets.get("artifacts", "agent-artifacts")
            object_key = skill_info.storage_path
            
            # Remove bucket prefix if present
            if object_key.startswith(f"{bucket_name}/"):
                object_key = object_key[len(bucket_name) + 1:]
            
            logger.debug(
                f"Downloading package from MinIO",
                extra={
                    "bucket": bucket_name,
                    "object_key": object_key
                }
            )
            
            file_stream, metadata = self.minio_client.download_file(bucket_name, object_key)
            
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
                        logger.error(
                            f"No skill directory found in package for {skill_info.name}",
                            extra={"skill_id": str(skill_info.skill_id)}
                        )
                        return None
                    
                    skill_dir = skill_dirs[0]
                    
                    # Add skill directory to Python path
                    sys.path.insert(0, str(skill_dir))
                    
                    try:
                        # Look for tool module
                        # Common patterns: tool.py, main.py, __init__.py
                        tool_files = ['tool.py', 'main.py', '__init__.py']
                        tool_module = None
                        
                        for tool_file in tool_files:
                            tool_path = skill_dir / tool_file
                            if tool_path.exists():
                                # Import the module
                                module_name = f"skill_{skill_info.skill_id.hex}"
                                spec = importlib.util.spec_from_file_location(
                                    module_name,
                                    tool_path
                                )
                                tool_module = importlib.util.module_from_spec(spec)
                                sys.modules[module_name] = tool_module
                                spec.loader.exec_module(tool_module)
                                break
                        
                        if not tool_module:
                            logger.error(
                                f"No tool module found in package for {skill_info.name}",
                                extra={"skill_id": str(skill_info.skill_id)}
                            )
                            return None
                        
                        # Look for tool instance or class
                        tool = None
                        
                        if hasattr(tool_module, 'tool'):
                            tool = tool_module.tool
                        elif hasattr(tool_module, 'Tool'):
                            Tool = tool_module.Tool
                            tool = Tool()
                        else:
                            # Look for any BaseTool subclass
                            for attr_name in dir(tool_module):
                                attr = getattr(tool_module, attr_name)
                                if isinstance(attr, type) and issubclass(attr, BaseTool) and attr != BaseTool:
                                    tool = attr()
                                    break
                        
                        if tool and isinstance(tool, BaseTool):
                            logger.info(
                                f"Loaded packaged LangChain tool: {skill_info.name}",
                                extra={"skill_id": str(skill_info.skill_id)}
                            )
                            return tool
                        else:
                            logger.error(
                                f"No valid LangChain tool found in package for {skill_info.name}",
                                extra={"skill_id": str(skill_info.skill_id)}
                            )
                            return None
                    
                    finally:
                        # Remove from Python path
                        if str(skill_dir) in sys.path:
                            sys.path.remove(str(skill_dir))
            
            finally:
                # Clean up temporary file
                try:
                    tmp_path.unlink()
                except:
                    pass
        
        except Exception as e:
            logger.error(
                f"Failed to load packaged tool {skill_info.name}: {e}",
                extra={"skill_id": str(skill_info.skill_id)},
                exc_info=True
            )
            return None
