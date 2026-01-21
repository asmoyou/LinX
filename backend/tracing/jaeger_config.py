"""Jaeger configuration and setup.

References:
- Design Section 11.4: Distributed Tracing
- Requirements 11: Monitoring and Observability
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class JaegerConfig:
    """Jaeger configuration."""
    
    # Agent configuration
    agent_host: str = "localhost"
    agent_port: int = 6831
    
    # Collector configuration (alternative to agent)
    collector_endpoint: Optional[str] = None
    
    # Service configuration
    service_name: str = "digital-workforce-platform"
    service_version: str = "1.0.0"
    
    # Sampling configuration
    sampler_type: str = "probabilistic"  # const, probabilistic, ratelimiting, remote
    sampler_param: float = 0.1  # 10% sampling
    
    # Reporter configuration
    log_spans: bool = False
    max_queue_size: int = 100
    flush_interval_ms: int = 1000
    
    # Tags
    tags: Optional[dict] = None
    
    def __post_init__(self):
        """Validate configuration."""
        if self.tags is None:
            self.tags = {}
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary.
        
        Returns:
            Configuration as dictionary
        """
        return {
            "agent_host": self.agent_host,
            "agent_port": self.agent_port,
            "collector_endpoint": self.collector_endpoint,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "sampler_type": self.sampler_type,
            "sampler_param": self.sampler_param,
            "log_spans": self.log_spans,
            "max_queue_size": self.max_queue_size,
            "flush_interval_ms": self.flush_interval_ms,
            "tags": self.tags,
        }


def get_jaeger_config_from_env() -> JaegerConfig:
    """Get Jaeger configuration from environment variables.
    
    Returns:
        JaegerConfig instance
    """
    import os
    
    return JaegerConfig(
        agent_host=os.getenv("JAEGER_AGENT_HOST", "localhost"),
        agent_port=int(os.getenv("JAEGER_AGENT_PORT", "6831")),
        collector_endpoint=os.getenv("JAEGER_COLLECTOR_ENDPOINT"),
        service_name=os.getenv("JAEGER_SERVICE_NAME", "digital-workforce-platform"),
        service_version=os.getenv("SERVICE_VERSION", "1.0.0"),
        sampler_type=os.getenv("JAEGER_SAMPLER_TYPE", "probabilistic"),
        sampler_param=float(os.getenv("JAEGER_SAMPLER_PARAM", "0.1")),
        log_spans=os.getenv("JAEGER_LOG_SPANS", "false").lower() == "true",
    )


def validate_jaeger_connection(config: JaegerConfig) -> bool:
    """Validate connection to Jaeger.
    
    Args:
        config: Jaeger configuration
        
    Returns:
        True if connection is valid, False otherwise
    """
    import socket
    
    try:
        # Try to connect to Jaeger agent
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        sock.connect((config.agent_host, config.agent_port))
        sock.close()
        
        logger.info(f"Jaeger connection validated: {config.agent_host}:{config.agent_port}")
        return True
        
    except Exception as e:
        logger.warning(f"Failed to validate Jaeger connection: {e}")
        return False


def get_jaeger_ui_url(config: JaegerConfig, trace_id: Optional[str] = None) -> str:
    """Get Jaeger UI URL for viewing traces.
    
    Args:
        config: Jaeger configuration
        trace_id: Optional trace ID to link directly to trace
        
    Returns:
        Jaeger UI URL
    """
    # Default Jaeger UI port
    ui_port = 16686
    base_url = f"http://{config.agent_host}:{ui_port}"
    
    if trace_id:
        return f"{base_url}/trace/{trace_id}"
    else:
        return f"{base_url}/search?service={config.service_name}"
