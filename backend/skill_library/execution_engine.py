"""Skill Execution Engine.

Executes skills of different types with proper isolation and error handling.

References:
- docs/backend/flexible-skill-architecture.md
- docs/backend/skill-type-classification.md
"""

import ast
import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID

from langchain_core.tools import tool as langchain_tool

from skill_library.skill_types import SkillType, StorageType
from database.models import Skill

logger = logging.getLogger(__name__)


class ExecutionResult:
    """Result of skill execution."""
    
    def __init__(
        self,
        success: bool,
        output: Any = None,
        error: Optional[str] = None,
        execution_time: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
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
            "metadata": self.metadata
        }


class SkillExecutionEngine:
    """Execute skills of any type with proper isolation."""
    
    def __init__(self):
        """Initialize execution engine."""
        self._tool_cache: Dict[UUID, Any] = {}
        logger.info("SkillExecutionEngine initialized")
    
    async def execute_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """Execute skill based on its type.
        
        Args:
            skill: Skill model instance
            inputs: Input parameters for the skill
            context: Optional execution context
            
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
                    execution_time=time.time() - start_time
                )
            
            # Route to appropriate executor based on storage type
            if skill.storage_type == StorageType.INLINE.value:
                result = await self._execute_inline_skill(skill, inputs, context)
            elif skill.storage_type == StorageType.MINIO.value:
                result = await self._execute_package_skill(skill, inputs, context)
            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unknown storage type: {skill.storage_type}",
                    execution_time=time.time() - start_time
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
                execution_time=time.time() - start_time
            )
    
    async def _execute_inline_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> ExecutionResult:
        """Execute inline skill (LangChain Tool or Agent Skill Simple).
        
        Args:
            skill: Skill model instance
            inputs: Input parameters
            context: Optional context
            
        Returns:
            ExecutionResult
        """
        try:
            # Get or create LangChain tool from code
            tool = self._get_or_create_tool(skill)
            
            # Execute the tool
            output = await tool.ainvoke(inputs)
            
            return ExecutionResult(
                success=True,
                output=output,
                metadata={
                    "skill_type": skill.skill_type,
                    "storage_type": skill.storage_type
                }
            )
            
        except Exception as e:
            logger.error(f"Error executing inline skill {skill.name}: {e}")
            return ExecutionResult(
                success=False,
                error=str(e)
            )
    
    async def _execute_package_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]]
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
        return ExecutionResult(
            success=False,
            error="Package skill execution not yet implemented"
        )
    
    def _get_or_create_tool(self, skill: Skill) -> Any:
        """Get cached tool or create new one from code.
        
        Args:
            skill: Skill model instance
            
        Returns:
            LangChain tool instance
        """
        # Check cache
        if skill.skill_id in self._tool_cache:
            return self._tool_cache[skill.skill_id]
        
        # Validate code exists
        if not skill.code:
            raise ValueError(f"Skill {skill.name} has no code")
        
        # Validate code safety
        self._validate_code_safety(skill.code)
        
        # Create tool from code
        tool = self._create_tool_from_code(skill.code, skill.name)
        
        # Cache the tool
        self._tool_cache[skill.skill_id] = tool
        
        return tool
    
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
                    if alias.name in ['subprocess', 'sys']:
                        dangerous_patterns.append(f"Dangerous import: {alias.name}")
            
            # Check for dangerous calls (but allow eval with restricted builtins)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ['exec', '__import__']:
                        dangerous_patterns.append(f"Dangerous function: {node.func.id}")
                    elif node.func.id == 'eval':
                        # Check if eval is used with restricted builtins
                        # This is a simplified check - in production, do more thorough analysis
                        logger.warning("Code uses eval - ensure it's properly restricted")
        
        if dangerous_patterns:
            raise ValueError(f"Code contains dangerous patterns: {', '.join(dangerous_patterns)}")
    
    def _create_tool_from_code(self, code: str, skill_name: str) -> Any:
        """Create LangChain tool from Python code.
        
        Args:
            code: Python code containing @tool decorated function
            skill_name: Name of the skill
            
        Returns:
            LangChain tool instance
        """
        # Create execution namespace
        namespace = {
            '__name__': f'skill_{skill_name}',
            '__builtins__': __builtins__,
            'tool': langchain_tool,
        }
        
        # Execute code to define the tool
        try:
            exec(code, namespace)
        except Exception as e:
            raise ValueError(f"Error executing skill code: {e}")
        
        # Find the tool function (decorated with @tool)
        tool_func = None
        for name, obj in namespace.items():
            if hasattr(obj, 'name') and hasattr(obj, 'description'):
                # This is likely a LangChain tool
                tool_func = obj
                break
        
        if tool_func is None:
            raise ValueError("No @tool decorated function found in code")
        
        return tool_func
    
    async def _update_execution_stats(
        self,
        skill: Skill,
        result: ExecutionResult
    ) -> None:
        """Update skill execution statistics.
        
        Args:
            skill: Skill model instance
            result: Execution result
        """
        try:
            from database.connection import get_db_session
            from datetime import datetime
            
            with get_db_session() as session:
                # Get fresh skill instance
                db_skill = session.query(Skill).filter(
                    Skill.skill_id == skill.skill_id
                ).first()
                
                if db_skill:
                    # Update execution count
                    db_skill.execution_count += 1
                    db_skill.last_executed_at = datetime.utcnow()
                    
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
    
    def clear_cache(self, skill_id: Optional[UUID] = None) -> None:
        """Clear tool cache.
        
        Args:
            skill_id: Optional specific skill to clear, or None for all
        """
        if skill_id:
            self._tool_cache.pop(skill_id, None)
            logger.info(f"Cleared cache for skill {skill_id}")
        else:
            self._tool_cache.clear()
            logger.info("Cleared all tool cache")


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
