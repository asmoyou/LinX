"""Skill Execution Engine.

Executes skills of different types with proper isolation and error handling.

References:
- docs/backend/flexible-skill-architecture.md
- docs/backend/skill-type-classification.md
"""

import ast
import logging
import re
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from langchain_core.tools import tool as langchain_tool

from agent_framework.sandbox_policy import allow_host_execution_fallback
from database.models import Skill
from shared.datetime_utils import utcnow
from skill_library.skill_types import SkillType, StorageType

logger = logging.getLogger(__name__)


DEPENDENCY_IMPORT_NAME_OVERRIDES = {
    "tavily-python": "tavily",
    "python-dotenv": "dotenv",
    "psycopg2-binary": "psycopg2",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "python-magic": "magic",
    "pillow": "PIL",
    "pyjwt": "jwt",
    "beautifulsoup4": "bs4",
    "opencv-python": "cv2",
    "scikit-learn": "sklearn",
    "python-dateutil": "dateutil",
}


class CacheEntry:
    """Cache entry with timestamp for LRU eviction."""

    def __init__(self, tool: Any):
        self.tool = tool
        self.last_accessed = utcnow()
        self.access_count = 0

    def access(self) -> Any:
        """Access the tool and update stats."""
        self.last_accessed = utcnow()
        self.access_count += 1
        return self.tool


class ExecutionResult:
    """Result of skill execution."""

    def __init__(
        self,
        success: bool,
        output: Any = None,
        error: Optional[str] = None,
        execution_time: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.execution_time = execution_time
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time": self.execution_time,
            "metadata": self.metadata,
        }


class SkillExecutionEngine:
    """Execute skills of any type with proper isolation."""

    # Cache configuration
    MAX_CACHE_SIZE = 100  # Maximum number of cached tools
    CACHE_TTL_MINUTES = 30  # Time-to-live for cached tools

    def __init__(self):
        """Initialize execution engine."""
        # Use OrderedDict for LRU cache implementation
        self._tool_cache: OrderedDict[
            Tuple[UUID, Optional[UUID], Optional[UUID]], CacheEntry
        ] = OrderedDict()
        logger.info("SkillExecutionEngine initialized with cache management")

    def _dependency_import_name(self, dependency: str) -> str:
        normalized = str(dependency or "").strip()
        if not normalized:
            return ""
        return DEPENDENCY_IMPORT_NAME_OVERRIDES.get(normalized, normalized.replace("-", "_"))

    def _extract_imports_from_code(self, code: str) -> set[str]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return set()

        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_level = str(alias.name or "").split(".", 1)[0].strip()
                    if top_level:
                        imports.add(top_level)
            elif isinstance(node, ast.ImportFrom):
                top_level = str(node.module or "").split(".", 1)[0].strip()
                if top_level:
                    imports.add(top_level)
        return imports

    def _dependency_import_candidates(self, dependency: str, code: Optional[str] = None) -> list[str]:
        normalized = str(dependency or "").strip()
        if not normalized:
            return []

        candidates: list[str] = []
        primary = self._dependency_import_name(normalized)
        if primary:
            candidates.append(primary)

        if code:
            dep_key = re.sub(r"[^a-z0-9]+", "", normalized.casefold())
            imported_modules = self._extract_imports_from_code(code)
            for module_name in imported_modules:
                module_key = re.sub(r"[^a-z0-9]+", "", module_name.casefold())
                if not module_key:
                    continue
                if module_key in dep_key or dep_key in module_key:
                    candidates.append(module_name)

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized_candidate = str(candidate or "").strip()
            if not normalized_candidate or normalized_candidate in seen:
                continue
            deduped.append(normalized_candidate)
            seen.add(normalized_candidate)
        return deduped

    async def execute_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
    ) -> ExecutionResult:
        """Execute skill based on its type.

        Args:
            skill: Skill model instance
            inputs: Input parameters for the skill
            context: Optional execution context
            user_id: Optional user ID for environment variables

        Returns:
            ExecutionResult with output or error
        """
        start_time = time.time()

        try:
            # Validate skill is active
            if not skill.is_active:
                return ExecutionResult(
                    success=False,
                    error=f"Skill {skill.name} is not active",
                    execution_time=time.time() - start_time,
                )

            # Route to appropriate executor based on storage type
            if skill.storage_type == StorageType.INLINE.value:
                result = await self._execute_inline_skill(skill, inputs, context, user_id)
            elif skill.storage_type == StorageType.MINIO.value:
                result = await self._execute_package_skill(skill, inputs, context, user_id)
            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unknown storage type: {skill.storage_type}",
                    execution_time=time.time() - start_time,
                )

            # Update execution stats
            result.execution_time = time.time() - start_time
            await self._update_execution_stats(skill, result)

            return result

        except Exception as e:
            logger.error(f"Error executing skill {skill.name}: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                error=f"Execution error: {str(e)}",
                execution_time=time.time() - start_time,
            )

    async def _execute_inline_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        user_id: Optional[UUID] = None,
    ) -> ExecutionResult:
        """Execute inline skill (LangChain Tool or Agent Skill Simple).

        Args:
            skill: Skill model instance
            inputs: Input parameters
            context: Optional context
            user_id: Optional user ID for environment variables

        Returns:
            ExecutionResult
        """
        try:
            # Get or create LangChain tool from code
            tool = self._get_or_create_tool(skill, user_id)

            # Execute the tool
            output = await tool.ainvoke(inputs)

            return ExecutionResult(
                success=True,
                output=output,
                metadata={"skill_type": skill.skill_type, "storage_type": skill.storage_type},
            )

        except Exception as e:
            logger.error(f"Error executing inline skill {skill.name}: {e}")
            return ExecutionResult(success=False, error=str(e))

    async def _execute_package_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        user_id: Optional[UUID] = None,
    ) -> ExecutionResult:
        """Execute package skill from MinIO.

        Args:
            skill: Skill model instance
            inputs: Input parameters
            context: Optional context

        Returns:
            ExecutionResult
        """
        # TODO: Implement MinIO package execution
        # This will be implemented in a future task
        return ExecutionResult(success=False, error="Package skill execution not yet implemented")

    def _get_or_create_tool(
        self,
        skill: Skill,
        user_id: Optional[UUID] = None,
        fallback_user_id: Optional[UUID] = None,
    ) -> Any:
        """Get cached tool or create new one from code.

        Args:
            skill: Skill model instance
            user_id: Optional user ID for environment variables
            fallback_user_id: Optional fallback user ID for missing environment variables

        Returns:
            LangChain tool instance
        """
        # Create cache key based on skill_id and effective env scope
        cache_key = (skill.skill_id, user_id, fallback_user_id)

        # Clean expired cache entries
        self._cleanup_expired_cache()

        # Check cache
        if cache_key in self._tool_cache:
            entry = self._tool_cache[cache_key]
            # Check if entry is still valid (not expired)
            age = utcnow() - entry.last_accessed
            if age.total_seconds() < self.CACHE_TTL_MINUTES * 60:
                # Move to end (most recently used)
                self._tool_cache.move_to_end(cache_key)
                logger.debug(
                    "Cache hit for skill %s, user %s, fallback_user %s",
                    skill.skill_id,
                    user_id,
                    fallback_user_id,
                )
                return entry.access()
            else:
                # Entry expired, remove it
                del self._tool_cache[cache_key]
                logger.info(
                    "Cache entry expired for skill %s, user %s, fallback_user %s",
                    skill.skill_id,
                    user_id,
                    fallback_user_id,
                )

        # Validate code exists
        if not skill.code:
            raise ValueError(f"Skill {skill.name} has no code")

        # Validate code safety
        self._validate_code_safety(skill.code)

        # Create tool from code with dependencies
        tool = self._create_tool_from_code(
            skill.code,
            skill.name,
            dependencies=skill.dependencies or [],
            user_id=user_id,
            fallback_user_id=fallback_user_id,
        )

        # Evict oldest entry if cache is full
        if len(self._tool_cache) >= self.MAX_CACHE_SIZE:
            # Remove least recently used (first item)
            evicted_key = next(iter(self._tool_cache))
            del self._tool_cache[evicted_key]
            logger.info(f"Cache full, evicted entry: {evicted_key}")

        # Cache the tool
        self._tool_cache[cache_key] = CacheEntry(tool)
        logger.info(
            "Cached new tool for skill %s, user %s, fallback_user %s",
            skill.skill_id,
            user_id,
            fallback_user_id,
        )

        return tool

    def _cleanup_expired_cache(self) -> None:
        """Remove expired cache entries."""
        now = utcnow()
        expired_keys = []

        for key, entry in self._tool_cache.items():
            age = now - entry.last_accessed
            if age.total_seconds() >= self.CACHE_TTL_MINUTES * 60:
                expired_keys.append(key)

        for key in expired_keys:
            del self._tool_cache[key]
            logger.info(f"Removed expired cache entry: {key}")

    def _validate_code_safety(self, code: str) -> None:
        """Validate code for dangerous patterns.

        Args:
            code: Python code to validate

        Raises:
            ValueError: If dangerous patterns detected
        """
        # Parse code to AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise ValueError(f"Syntax error in code: {e}")

        # Check for dangerous patterns
        dangerous_patterns = []

        for node in ast.walk(tree):
            # Check for dangerous imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ["subprocess", "sys"]:
                        dangerous_patterns.append(f"Dangerous import: {alias.name}")

            # Check for dangerous calls (but allow eval with restricted builtins)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ["exec", "__import__"]:
                        dangerous_patterns.append(f"Dangerous function: {node.func.id}")
                    elif node.func.id == "eval":
                        # Check if eval is used with restricted builtins
                        # This is a simplified check - in production, do more thorough analysis
                        logger.warning("Code uses eval - ensure it's properly restricted")

        if dangerous_patterns:
            raise ValueError(f"Code contains dangerous patterns: {', '.join(dangerous_patterns)}")

    def _create_tool_from_code(
        self,
        code: str,
        skill_name: str,
        dependencies: list = None,
        user_id: Optional[UUID] = None,
        fallback_user_id: Optional[UUID] = None,
    ) -> Any:
        """Create LangChain tool from Python code.

        Args:
            code: Python code containing @tool decorated function
            skill_name: Name of the skill
            dependencies: List of required dependencies
            user_id: Optional user ID for environment variables
            fallback_user_id: Optional fallback user ID for missing environment variables

        Returns:
            LangChain tool instance
        """
        # Install dependencies if needed
        if dependencies:
            self._ensure_dependencies_installed(dependencies, code=code)

        # Get user environment variables and temporarily inject into os.environ
        import os

        original_env = {}
        user_env_vars = {}

        if user_id:
            from skill_library.skill_env_manager import get_skill_env_manager

            env_manager = get_skill_env_manager()
            user_env_vars = env_manager.get_env_for_user_with_fallback(
                user_id=user_id,
                fallback_user_id=fallback_user_id,
            )

            # Temporarily inject user env vars into os.environ
            for key, value in user_env_vars.items():
                if key in os.environ:
                    original_env[key] = os.environ[key]
                os.environ[key] = value

        try:
            # Create execution namespace
            namespace = {
                "__name__": f"skill_{skill_name}",
                "__builtins__": __builtins__,
                "tool": langchain_tool,
            }

            # Execute code to define the tool
            try:
                exec(code, namespace)
            except Exception as e:
                raise ValueError(f"Error executing skill code: {e}")

            # Find the tool function (decorated with @tool)
            tool_func = None
            for name, obj in namespace.items():
                if hasattr(obj, "name") and hasattr(obj, "description"):
                    # This is likely a LangChain tool
                    tool_func = obj
                    break

            if tool_func is None:
                raise ValueError("No @tool decorated function found in code")

            return tool_func

        finally:
            # Restore original environment variables
            if user_id:
                for key in user_env_vars.keys():
                    if key in original_env:
                        os.environ[key] = original_env[key]
                    else:
                        os.environ.pop(key, None)

    def _ensure_dependencies_installed(self, dependencies: list, code: Optional[str] = None) -> None:
        """Ensure required dependencies are installed.

        Args:
            dependencies: List of package names to install

        Raises:
            ValueError: If installation fails
        """
        import subprocess
        import sys

        for dep in dependencies:
            import_candidates = self._dependency_import_candidates(dep, code=code)
            dependency_available = False
            last_error: Optional[ImportError] = None
            for import_name in import_candidates:
                try:
                    __import__(import_name)
                    logger.debug("Dependency %s already installed via import %s", dep, import_name)
                    dependency_available = True
                    break
                except ImportError as exc:
                    last_error = exc
            if dependency_available:
                continue
            if last_error is not None:
                logger.debug("Dependency import probe failed for %s: %s", dep, last_error)
            else:
                logger.debug("No dependency import candidates resolved for %s", dep)
            if not allow_host_execution_fallback():
                raise ValueError(
                    "Host dependency installation is disabled by sandbox isolation policy. "
                    f"Missing dependency: {dep}. Install it in sandbox/base image, or set "
                    "LINX_ALLOW_HOST_EXECUTION_FALLBACK=1 for emergency compatibility."
                )
            # Install the package
            logger.info(f"Installing dependency: {dep}")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", dep],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                logger.info(f"Successfully installed {dep}")
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                raise ValueError(f"Failed to install dependency {dep}: {error_msg}")

    async def _update_execution_stats(self, skill: Skill, result: ExecutionResult) -> None:
        """Update skill execution statistics.

        Args:
            skill: Skill model instance
            result: Execution result
        """
        try:
            from datetime import datetime

            from database.connection import get_db_session

            with get_db_session() as session:
                # Get fresh skill instance
                db_skill = session.query(Skill).filter(Skill.skill_id == skill.skill_id).first()

                if db_skill:
                    # Update execution count
                    db_skill.execution_count += 1
                    db_skill.last_executed_at = utcnow()

                    # Update average execution time
                    if db_skill.average_execution_time is None:
                        db_skill.average_execution_time = result.execution_time
                    else:
                        # Running average
                        total_time = (
                            db_skill.average_execution_time * (db_skill.execution_count - 1)
                            + result.execution_time
                        )
                        db_skill.average_execution_time = total_time / db_skill.execution_count

                    session.commit()

        except Exception as e:
            logger.error(f"Error updating execution stats: {e}")

    def clear_cache(self, skill_id: Optional[UUID] = None, user_id: Optional[UUID] = None) -> None:
        """Clear tool cache.

        Args:
            skill_id: Optional specific skill to clear
            user_id: Optional specific user to clear

        If both skill_id and user_id are provided, clears that specific entry.
        If only skill_id is provided, clears all entries for that skill.
        If only user_id is provided, clears all entries for that user.
        If neither is provided, clears all cache.
        """
        if skill_id and user_id:
            # Clear specific entry
            keys_to_remove = [
                key
                for key in self._tool_cache.keys()
                if key[0] == skill_id and (key[1] == user_id or key[2] == user_id)
            ]
            for key in keys_to_remove:
                del self._tool_cache[key]
            logger.info(
                "Cleared %s cache entries for skill %s, user %s",
                len(keys_to_remove),
                skill_id,
                user_id,
            )
        elif skill_id:
            # Clear all entries for this skill
            keys_to_remove = [k for k in self._tool_cache.keys() if k[0] == skill_id]
            for key in keys_to_remove:
                del self._tool_cache[key]
            logger.info(f"Cleared {len(keys_to_remove)} cache entries for skill {skill_id}")
        elif user_id:
            # Clear all entries for this user
            keys_to_remove = [
                k for k in self._tool_cache.keys() if k[1] == user_id or k[2] == user_id
            ]
            for key in keys_to_remove:
                del self._tool_cache[key]
            logger.info(f"Cleared {len(keys_to_remove)} cache entries for user {user_id}")
        else:
            # Clear all cache
            count = len(self._tool_cache)
            self._tool_cache.clear()
            logger.info(f"Cleared all {count} cache entries")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        now = utcnow()
        total_entries = len(self._tool_cache)

        if total_entries == 0:
            return {
                "total_entries": 0,
                "max_size": self.MAX_CACHE_SIZE,
                "ttl_minutes": self.CACHE_TTL_MINUTES,
                "utilization": 0.0,
            }

        # Calculate statistics
        access_counts = [entry.access_count for entry in self._tool_cache.values()]
        ages = [
            (now - entry.last_accessed).total_seconds() / 60 for entry in self._tool_cache.values()
        ]

        return {
            "total_entries": total_entries,
            "max_size": self.MAX_CACHE_SIZE,
            "ttl_minutes": self.CACHE_TTL_MINUTES,
            "utilization": total_entries / self.MAX_CACHE_SIZE,
            "avg_access_count": sum(access_counts) / len(access_counts),
            "avg_age_minutes": sum(ages) / len(ages),
            "oldest_age_minutes": max(ages),
        }


# Singleton instance
_execution_engine: Optional[SkillExecutionEngine] = None


def get_execution_engine() -> SkillExecutionEngine:
    """Get or create the execution engine singleton.

    Returns:
        SkillExecutionEngine instance
    """
    global _execution_engine
    if _execution_engine is None:
        _execution_engine = SkillExecutionEngine()
    return _execution_engine
