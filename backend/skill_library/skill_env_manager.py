"""Skill Environment Variable Manager.

Manages environment variables for skill execution, allowing users to configure
API keys and other secrets needed by skills.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
import os
from typing import Dict, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import User

logger = logging.getLogger(__name__)


class SkillEnvManager:
    """Manage environment variables for skill execution."""
    
    def __init__(self):
        """Initialize environment manager."""
        self._env_cache: Dict[UUID, Dict[str, str]] = {}
        logger.info("SkillEnvManager initialized")
    
    def get_env_for_user(self, user_id: UUID) -> Dict[str, str]:
        """Get environment variables for a user.
        
        Args:
            user_id: User UUID
            
        Returns:
            Dictionary of environment variables
        """
        # Check cache
        if user_id in self._env_cache:
            return self._env_cache[user_id].copy()
        
        # Load from database
        env_vars = self._load_user_env(user_id)
        
        # Cache it
        self._env_cache[user_id] = env_vars
        
        return env_vars.copy()
    
    def set_env_for_user(
        self,
        user_id: UUID,
        key: str,
        value: str
    ) -> None:
        """Set an environment variable for a user.
        
        Args:
            user_id: User UUID
            key: Environment variable name
            value: Environment variable value
        """
        # Update database
        self._save_user_env(user_id, key, value)
        
        # Update cache
        if user_id not in self._env_cache:
            self._env_cache[user_id] = {}
        self._env_cache[user_id][key] = value
        
        logger.info(f"Set environment variable {key} for user {user_id}")
    
    def delete_env_for_user(
        self,
        user_id: UUID,
        key: str
    ) -> None:
        """Delete an environment variable for a user.
        
        Args:
            user_id: User UUID
            key: Environment variable name
        """
        # Update database
        self._delete_user_env(user_id, key)
        
        # Update cache
        if user_id in self._env_cache:
            self._env_cache[user_id].pop(key, None)
        
        logger.info(f"Deleted environment variable {key} for user {user_id}")
    
    def list_env_keys_for_user(self, user_id: UUID) -> list:
        """List environment variable keys for a user (not values).
        
        Args:
            user_id: User UUID
            
        Returns:
            List of environment variable keys
        """
        env_vars = self.get_env_for_user(user_id)
        return list(env_vars.keys())
    
    def apply_env_to_namespace(
        self,
        user_id: UUID,
        namespace: Dict
    ) -> None:
        """Apply user environment variables to execution namespace.
        
        Args:
            user_id: User UUID
            namespace: Execution namespace to update
        """
        env_vars = self.get_env_for_user(user_id)
        
        # Create a custom environ dict that merges user env with system env
        class CustomEnviron(dict):
            def __init__(self, user_env: Dict[str, str]):
                super().__init__(os.environ)
                # Override with user environment variables
                self.update(user_env)
            
            def __getitem__(self, key: str) -> str:
                # Check user environment first
                if key in env_vars:
                    return env_vars[key]
                # Fall back to system environment
                return super().__getitem__(key)
            
            def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
                # Check user environment first
                if key in env_vars:
                    return env_vars[key]
                # Fall back to system environment
                return super().get(key, default)
        
        # Create a custom os module with both getenv and environ
        class CustomOS:
            environ = CustomEnviron(env_vars)
            
            @staticmethod
            def getenv(key: str, default: Optional[str] = None) -> Optional[str]:
                # Check user environment first
                if key in env_vars:
                    return env_vars[key]
                # Fall back to system environment
                return os.getenv(key, default)
            
            # Pass through other os attributes
            def __getattr__(self, name: str):
                return getattr(os, name)
        
        # Replace os in namespace
        namespace['os'] = CustomOS()
    
    def _load_user_env(self, user_id: UUID) -> Dict[str, str]:
        """Load environment variables from database.
        
        Args:
            user_id: User UUID
            
        Returns:
            Dictionary of environment variables
        """
        with get_db_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            
            if not user:
                return {}
            
            # Get env vars from user attributes (JSONB field)
            # Use getattr to avoid SQLAlchemy metadata conflict
            # Store them under 'skill_env_vars' key
            attributes_data = getattr(user, 'attributes', None) or {}
            if not isinstance(attributes_data, dict):
                logger.warning(f"User {user_id} attributes is not a dict: {type(attributes_data)}")
                return {}
            return attributes_data.get('skill_env_vars', {})
    
    def _save_user_env(
        self,
        user_id: UUID,
        key: str,
        value: str
    ) -> None:
        """Save environment variable to database.
        
        Args:
            user_id: User UUID
            key: Environment variable name
            value: Environment variable value
        """
        with get_db_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            # Get current attributes using getattr to avoid SQLAlchemy metadata conflict
            attributes_data = getattr(user, 'attributes', None)
            
            # Initialize attributes if needed
            if attributes_data is None or not isinstance(attributes_data, dict):
                attributes_data = {}
            
            # Initialize skill_env_vars if needed
            if 'skill_env_vars' not in attributes_data:
                attributes_data['skill_env_vars'] = {}
            
            # Set the value
            attributes_data['skill_env_vars'][key] = value
            
            # Set back to user object
            setattr(user, 'attributes', attributes_data)
            
            # Mark as modified for SQLAlchemy to detect change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(user, 'attributes')
            
            session.commit()
    
    def _delete_user_env(
        self,
        user_id: UUID,
        key: str
    ) -> None:
        """Delete environment variable from database.
        
        Args:
            user_id: User UUID
            key: Environment variable name
        """
        with get_db_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            
            if not user:
                return
            
            # Get current attributes using getattr
            attributes_data = getattr(user, 'attributes', None)
            if not attributes_data or not isinstance(attributes_data, dict):
                return
            
            # Remove the key
            env_vars = attributes_data.get('skill_env_vars', {})
            env_vars.pop(key, None)
            
            # Set back to user object
            setattr(user, 'attributes', attributes_data)
            
            # Mark as modified
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(user, 'attributes')
            
            session.commit()
    
    def clear_cache(self, user_id: Optional[UUID] = None) -> None:
        """Clear environment cache.
        
        Args:
            user_id: Optional specific user to clear, or None for all
        """
        if user_id:
            self._env_cache.pop(user_id, None)
            logger.info(f"Cleared env cache for user {user_id}")
        else:
            self._env_cache.clear()
            logger.info("Cleared all env cache")


# Singleton instance
_env_manager: Optional[SkillEnvManager] = None


def get_skill_env_manager() -> SkillEnvManager:
    """Get or create the skill environment manager singleton.
    
    Returns:
        SkillEnvManager instance
    """
    global _env_manager
    if _env_manager is None:
        _env_manager = SkillEnvManager()
    return _env_manager
