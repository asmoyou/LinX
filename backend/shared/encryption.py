"""Encryption Configuration and Utilities.

Provides encryption configuration helpers and utilities for the platform.

References:
- Requirements 7: Data Security and Privacy
- Design Section 8.4: Data Protection
- Task 5.1: Data Encryption
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TLSConfig:
    """TLS configuration for secure connections."""
    
    enabled: bool = False
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    ca_file: Optional[str] = None
    verify_mode: str = "CERT_REQUIRED"
    
    def validate(self) -> bool:
        """Validate TLS configuration.
        
        Returns:
            True if configuration is valid
        """
        if not self.enabled:
            return True
        
        if not self.cert_file or not self.key_file:
            logger.error("TLS enabled but cert_file or key_file not provided")
            return False
        
        cert_path = Path(self.cert_file)
        key_path = Path(self.key_file)
        
        if not cert_path.exists():
            logger.error(f"Certificate file not found: {self.cert_file}")
            return False
        
        if not key_path.exists():
            logger.error(f"Key file not found: {self.key_file}")
            return False
        
        # Check key file permissions (should be 600)
        key_stat = key_path.stat()
        if key_stat.st_mode & 0o077:
            logger.warning(
                f"Key file {self.key_file} has insecure permissions. "
                "Should be 600 (owner read/write only)"
            )
        
        if self.ca_file:
            ca_path = Path(self.ca_file)
            if not ca_path.exists():
                logger.error(f"CA file not found: {self.ca_file}")
                return False
        
        return True


@dataclass
class EncryptionConfig:
    """Encryption configuration for the platform."""
    
    # Encryption at rest
    postgres_encryption_enabled: bool = False
    milvus_encryption_enabled: bool = False
    minio_encryption_enabled: bool = False
    
    # Encryption in transit (TLS)
    api_tls: TLSConfig = None
    postgres_tls: TLSConfig = None
    milvus_tls: TLSConfig = None
    minio_tls: TLSConfig = None
    redis_tls: TLSConfig = None
    
    # Key management
    key_management_service: Optional[str] = None  # "vault", "aws-kms", "local"
    key_rotation_days: int = 90
    
    def __post_init__(self):
        """Initialize TLS configs if not provided."""
        if self.api_tls is None:
            self.api_tls = TLSConfig()
        if self.postgres_tls is None:
            self.postgres_tls = TLSConfig()
        if self.milvus_tls is None:
            self.milvus_tls = TLSConfig()
        if self.minio_tls is None:
            self.minio_tls = TLSConfig()
        if self.redis_tls is None:
            self.redis_tls = TLSConfig()
    
    def validate(self) -> bool:
        """Validate encryption configuration.
        
        Returns:
            True if configuration is valid
        """
        valid = True
        
        # Validate TLS configs
        for name, tls_config in [
            ("API", self.api_tls),
            ("PostgreSQL", self.postgres_tls),
            ("Milvus", self.milvus_tls),
            ("MinIO", self.minio_tls),
            ("Redis", self.redis_tls),
        ]:
            if not tls_config.validate():
                logger.error(f"{name} TLS configuration is invalid")
                valid = False
        
        return valid
    
    def get_security_summary(self) -> Dict[str, bool]:
        """Get summary of security features enabled.
        
        Returns:
            Dictionary of security features and their status
        """
        return {
            "encryption_at_rest": {
                "postgres": self.postgres_encryption_enabled,
                "milvus": self.milvus_encryption_enabled,
                "minio": self.minio_encryption_enabled,
            },
            "encryption_in_transit": {
                "api": self.api_tls.enabled,
                "postgres": self.postgres_tls.enabled,
                "milvus": self.milvus_tls.enabled,
                "minio": self.minio_tls.enabled,
                "redis": self.redis_tls.enabled,
            },
            "key_management": {
                "service": self.key_management_service or "local",
                "rotation_enabled": self.key_rotation_days > 0,
            },
        }


def load_encryption_config_from_env() -> EncryptionConfig:
    """Load encryption configuration from environment variables.
    
    Returns:
        EncryptionConfig instance
    """
    certs_dir = os.getenv("CERTS_DIR", "infrastructure/certs")
    
    # API TLS
    api_tls = TLSConfig(
        enabled=os.getenv("API_TLS_ENABLED", "false").lower() == "true",
        cert_file=os.getenv("API_TLS_CERT", f"{certs_dir}/server-cert.pem"),
        key_file=os.getenv("API_TLS_KEY", f"{certs_dir}/server-key.pem"),
        ca_file=os.getenv("API_TLS_CA", f"{certs_dir}/ca-cert.pem"),
    )
    
    # PostgreSQL TLS
    postgres_tls = TLSConfig(
        enabled=os.getenv("POSTGRES_TLS_ENABLED", "false").lower() == "true",
        cert_file=os.getenv("POSTGRES_TLS_CERT", f"{certs_dir}/client-cert.pem"),
        key_file=os.getenv("POSTGRES_TLS_KEY", f"{certs_dir}/client-key.pem"),
        ca_file=os.getenv("POSTGRES_TLS_CA", f"{certs_dir}/ca-cert.pem"),
    )
    
    # Milvus TLS
    milvus_tls = TLSConfig(
        enabled=os.getenv("MILVUS_TLS_ENABLED", "false").lower() == "true",
        cert_file=os.getenv("MILVUS_TLS_CERT", f"{certs_dir}/client-cert.pem"),
        key_file=os.getenv("MILVUS_TLS_KEY", f"{certs_dir}/client-key.pem"),
        ca_file=os.getenv("MILVUS_TLS_CA", f"{certs_dir}/ca-cert.pem"),
    )
    
    # MinIO TLS
    minio_tls = TLSConfig(
        enabled=os.getenv("MINIO_TLS_ENABLED", "false").lower() == "true",
        cert_file=os.getenv("MINIO_TLS_CERT", f"{certs_dir}/client-cert.pem"),
        key_file=os.getenv("MINIO_TLS_KEY", f"{certs_dir}/client-key.pem"),
        ca_file=os.getenv("MINIO_TLS_CA", f"{certs_dir}/ca-cert.pem"),
    )
    
    # Redis TLS
    redis_tls = TLSConfig(
        enabled=os.getenv("REDIS_TLS_ENABLED", "false").lower() == "true",
        cert_file=os.getenv("REDIS_TLS_CERT", f"{certs_dir}/client-cert.pem"),
        key_file=os.getenv("REDIS_TLS_KEY", f"{certs_dir}/client-key.pem"),
        ca_file=os.getenv("REDIS_TLS_CA", f"{certs_dir}/ca-cert.pem"),
    )
    
    config = EncryptionConfig(
        postgres_encryption_enabled=os.getenv("POSTGRES_ENCRYPTION_ENABLED", "false").lower() == "true",
        milvus_encryption_enabled=os.getenv("MILVUS_ENCRYPTION_ENABLED", "false").lower() == "true",
        minio_encryption_enabled=os.getenv("MINIO_ENCRYPTION_ENABLED", "false").lower() == "true",
        api_tls=api_tls,
        postgres_tls=postgres_tls,
        milvus_tls=milvus_tls,
        minio_tls=minio_tls,
        redis_tls=redis_tls,
        key_management_service=os.getenv("KEY_MANAGEMENT_SERVICE"),
        key_rotation_days=int(os.getenv("KEY_ROTATION_DAYS", "90")),
    )
    
    return config


def get_postgres_connection_params(tls_config: TLSConfig) -> Dict[str, str]:
    """Get PostgreSQL connection parameters with TLS.
    
    Args:
        tls_config: TLS configuration
    
    Returns:
        Dictionary of connection parameters
    """
    params = {}
    
    if tls_config.enabled:
        params["sslmode"] = "require"
        if tls_config.cert_file:
            params["sslcert"] = tls_config.cert_file
        if tls_config.key_file:
            params["sslkey"] = tls_config.key_file
        if tls_config.ca_file:
            params["sslrootcert"] = tls_config.ca_file
    
    return params


def get_redis_connection_params(tls_config: TLSConfig) -> Dict[str, any]:
    """Get Redis connection parameters with TLS.
    
    Args:
        tls_config: TLS configuration
    
    Returns:
        Dictionary of connection parameters
    """
    params = {}
    
    if tls_config.enabled:
        params["ssl"] = True
        if tls_config.cert_file:
            params["ssl_certfile"] = tls_config.cert_file
        if tls_config.key_file:
            params["ssl_keyfile"] = tls_config.key_file
        if tls_config.ca_file:
            params["ssl_ca_certs"] = tls_config.ca_file
    
    return params


# Global encryption configuration
_encryption_config: Optional[EncryptionConfig] = None


def get_encryption_config() -> EncryptionConfig:
    """Get global encryption configuration.
    
    Returns:
        EncryptionConfig instance
    """
    global _encryption_config
    
    if _encryption_config is None:
        _encryption_config = load_encryption_config_from_env()
        
        if not _encryption_config.validate():
            logger.warning("Encryption configuration validation failed")
        
        # Log security summary
        summary = _encryption_config.get_security_summary()
        logger.info(
            "Encryption configuration loaded",
            extra={"security_summary": summary},
        )
    
    return _encryption_config
