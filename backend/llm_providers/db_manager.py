"""
LLM Provider Database Manager

Handles CRUD operations for LLM providers in the database.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 18.8: Settings Page
"""

import logging
import os
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from database.models import LLMProvider
from llm_providers.models import ProviderConfig, ProviderProtocol

logger = logging.getLogger(__name__)

# Load .env file from backend directory
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    logger.info(f"Loaded .env file from {env_path}")
else:
    logger.warning(f".env file not found at {env_path}")


def _get_encryption_key() -> bytes:
    """Get or generate encryption key for API keys."""
    key = os.getenv('LLM_ENCRYPTION_KEY')
    if not key:
        # Generate a key for development (should use env var in production)
        logger.warning("LLM_ENCRYPTION_KEY not set, using generated key (not secure for production)")
        key = Fernet.generate_key().decode()
    
    # Ensure key is bytes
    if isinstance(key, str):
        key = key.encode()
    
    return key


# Initialize cipher suite
_cipher_suite = Fernet(_get_encryption_key())


class ProviderDBManager:
    """Manages LLM provider configurations in the database."""
    
    def __init__(self, db_session: Session):
        """
        Initialize database manager.
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
    
    def _encrypt_api_key(self, api_key: str) -> str:
        """Encrypt API key for storage."""
        if not api_key:
            return ""
        return _cipher_suite.encrypt(api_key.encode()).decode()
    
    def _decrypt_api_key(self, encrypted_key: str) -> Optional[str]:
        """Decrypt API key from storage."""
        if not encrypted_key:
            return None
        try:
            return _cipher_suite.decrypt(encrypted_key.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")
            return None
    
    def create_provider(
        self,
        name: str,
        protocol: ProviderProtocol,
        base_url: str,
        models: List[str],
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        created_by: Optional[UUID] = None,
    ) -> LLMProvider:
        """
        Create a new LLM provider.
        
        Args:
            name: Provider name (unique)
            protocol: Protocol type (ollama, openai_compatible)
            base_url: Base URL for the provider
            models: List of model names
            api_key: Optional API key (will be encrypted)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            created_by: User ID who created the provider
            
        Returns:
            Created LLMProvider instance
            
        Raises:
            ValueError: If provider with same name already exists
        """
        # Check if provider already exists
        existing = self.db.query(LLMProvider).filter(LLMProvider.name == name).first()
        if existing:
            raise ValueError(f"Provider with name '{name}' already exists")
        
        # Encrypt API key if provided
        encrypted_key = self._encrypt_api_key(api_key) if api_key else None
        
        # Create provider
        provider = LLMProvider(
            name=name,
            protocol=protocol.value,
            base_url=base_url,
            api_key_encrypted=encrypted_key,
            timeout=timeout,
            max_retries=max_retries,
            models=models,
            enabled=True,
            created_by=created_by,
        )
        
        self.db.add(provider)
        self.db.commit()
        self.db.refresh(provider)
        
        logger.info(f"Created LLM provider: {name}")
        return provider
    
    def get_provider(self, name: str) -> Optional[LLMProvider]:
        """Get provider by name."""
        return self.db.query(LLMProvider).filter(LLMProvider.name == name).first()
    
    def get_provider_by_id(self, provider_id: UUID) -> Optional[LLMProvider]:
        """Get provider by ID."""
        return self.db.query(LLMProvider).filter(LLMProvider.provider_id == provider_id).first()
    
    def list_providers(self, enabled_only: bool = False) -> List[LLMProvider]:
        """
        List all providers.
        
        Args:
            enabled_only: If True, only return enabled providers
            
        Returns:
            List of LLMProvider instances
        """
        query = self.db.query(LLMProvider)
        if enabled_only:
            query = query.filter(LLMProvider.enabled == True)
        return query.order_by(LLMProvider.created_at.desc()).all()
    
    def update_provider(
        self,
        name: str,
        base_url: Optional[str] = None,
        models: Optional[List[str]] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> LLMProvider:
        """
        Update an existing provider.
        
        Args:
            name: Provider name
            base_url: New base URL (optional)
            models: New model list (optional)
            api_key: New API key (optional, will be encrypted)
            timeout: New timeout (optional)
            max_retries: New max retries (optional)
            enabled: New enabled status (optional)
            
        Returns:
            Updated LLMProvider instance
            
        Raises:
            ValueError: If provider not found
        """
        provider = self.get_provider(name)
        if not provider:
            raise ValueError(f"Provider '{name}' not found")
        
        # Update fields if provided
        if base_url is not None:
            provider.base_url = base_url
        if models is not None:
            provider.models = models
        if api_key is not None:
            provider.api_key_encrypted = self._encrypt_api_key(api_key)
        if timeout is not None:
            provider.timeout = timeout
        if max_retries is not None:
            provider.max_retries = max_retries
        if enabled is not None:
            provider.enabled = enabled
        
        self.db.commit()
        self.db.refresh(provider)
        
        logger.info(f"Updated LLM provider: {name}")
        return provider
    
    def delete_provider(self, name: str) -> bool:
        """
        Delete a provider.
        
        Args:
            name: Provider name
            
        Returns:
            True if deleted, False if not found
        """
        provider = self.get_provider(name)
        if not provider:
            return False
        
        self.db.delete(provider)
        self.db.commit()
        
        logger.info(f"Deleted LLM provider: {name}")
        return True
    
    def update_test_status(
        self,
        provider_name: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update provider's last test status.
        
        Args:
            provider_name: Provider name
            status: Test status ('success', 'failed', 'untested')
            error_message: Error message if test failed
            
        Returns:
            True if updated, False if provider not found
        """
        from datetime import datetime, timezone
        
        provider = self.get_provider(provider_name)
        if not provider:
            return False
        
        provider.last_test_status = status
        provider.last_test_time = datetime.now(timezone.utc)
        provider.last_test_error = error_message
        
        self.db.commit()
        
        logger.info(f"Updated test status for {provider_name}: {status}")
        return True
    
    def to_provider_config(self, provider: LLMProvider) -> ProviderConfig:
        """
        Convert database model to ProviderConfig.
        
        Args:
            provider: LLMProvider database model
            
        Returns:
            ProviderConfig instance
        """
        return ProviderConfig(
            name=provider.name,
            protocol=ProviderProtocol(provider.protocol),
            base_url=provider.base_url,
            api_key=self._decrypt_api_key(provider.api_key_encrypted),
            timeout=provider.timeout,
            max_retries=provider.max_retries,
            selected_models=provider.models,
        )
    
    def get_model_metadata(self, provider_name: str, model_name: str):
        """
        Get metadata for a specific model.
        
        Args:
            provider_name: Provider name
            model_name: Model name
            
        Returns:
            ModelMetadata object or None if not found
        """
        from llm_providers.model_metadata import ModelMetadata
        
        provider = self.get_provider(provider_name)
        if not provider:
            logger.warning(f"Provider '{provider_name}' not found")
            return None
        
        # Check if model metadata exists
        if not provider.model_metadata or model_name not in provider.model_metadata:
            logger.warning(f"Metadata for model '{model_name}' not found in provider '{provider_name}'")
            return None
        
        # Convert dict to ModelMetadata object
        metadata_dict = provider.model_metadata[model_name]
        try:
            return ModelMetadata(**metadata_dict)
        except Exception as e:
            logger.error(f"Failed to parse model metadata: {e}")
            return None
