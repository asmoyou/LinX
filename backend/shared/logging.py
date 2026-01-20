"""
Structured JSON Logging Module

This module provides structured JSON logging capabilities for the platform including:
- JSON format for machine parsing
- Correlation IDs for request tracking across components
- Different log levels per component
- Integration with configuration system
- Timestamp, level, caller information
- Support for stdout and file output

References:
- Requirements 11: Monitoring and Observability
- Design Section 11.2: Logging Strategy
"""

import logging
import logging.handlers
import sys
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import structlog
from pythonjsonlogger import jsonlogger


# Global correlation ID storage (thread-local)
import threading
_correlation_context = threading.local()


def set_correlation_id(correlation_id: str) -> None:
    """
    Set correlation ID for the current thread/request.
    
    Args:
        correlation_id: Unique identifier for tracking requests across components
        
    Example:
        >>> from shared.logging import set_correlation_id
        >>> set_correlation_id("req-12345")
    """
    _correlation_context.correlation_id = correlation_id


def get_correlation_id() -> Optional[str]:
    """
    Get correlation ID for the current thread/request.
    
    Returns:
        Correlation ID if set, None otherwise
    """
    return getattr(_correlation_context, 'correlation_id', None)


def clear_correlation_id() -> None:
    """Clear correlation ID for the current thread/request."""
    if hasattr(_correlation_context, 'correlation_id'):
        delattr(_correlation_context, 'correlation_id')


class CorrelationIdFilter(logging.Filter):
    """
    Logging filter that adds correlation ID to log records.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add correlation_id to the log record.
        
        Args:
            record: Log record to modify
            
        Returns:
            True (always allow the record through)
        """
        record.correlation_id = get_correlation_id() or "none"
        return True


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter that includes standard fields:
    - timestamp
    - level
    - component (logger name)
    - message
    - correlation_id
    - caller information (file, function, line)
    - user_id, agent_id, task_id (if available)
    """
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, 
                   message_dict: Dict[str, Any]) -> None:
        """
        Add custom fields to the log record.
        
        Args:
            log_record: Dictionary to add fields to
            record: Original log record
            message_dict: Additional message fields
        """
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp in ISO format
        log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        
        # Add log level
        log_record['level'] = record.levelname
        
        # Add component (logger name)
        log_record['component'] = record.name
        
        # Add correlation ID
        log_record['correlation_id'] = getattr(record, 'correlation_id', 'none')
        
        # Add caller information
        log_record['caller'] = {
            'file': record.pathname,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add context fields if available
        for field in ['user_id', 'agent_id', 'task_id']:
            if hasattr(record, field):
                log_record[field] = getattr(record, field)
        
        # Ensure message is present
        if 'message' not in log_record:
            log_record['message'] = record.getMessage()


def setup_logging(config: Optional[Any] = None) -> None:
    """
    Set up structured JSON logging based on configuration.
    
    This function configures the logging system with:
    - JSON formatting for structured logs
    - Correlation ID tracking
    - Component-specific log levels
    - File and stdout output
    - Log rotation
    
    Args:
        config: Configuration object (if None, uses defaults)
        
    Example:
        >>> from shared.config import Config
        >>> from shared.logging import setup_logging
        >>> 
        >>> config = Config.load("config.yaml")
        >>> setup_logging(config)
    """
    # Get configuration values with defaults
    if config is None:
        log_level = "INFO"
        log_format = "json"
        log_output = "stdout"
        log_file_path = "/var/log/workforce-platform"
        log_file_name = "platform.log"
        log_max_size_mb = 100
        log_max_files = 10
        log_rotation = "daily"
        include_timestamp = True
        include_level = True
        include_caller = True
        include_correlation_id = True
        component_levels = {}
    else:
        log_level = config.get("monitoring.logging.level", "INFO")
        log_format = config.get("monitoring.logging.format", "json")
        log_output = config.get("monitoring.logging.output", "stdout")
        log_file_path = config.get("monitoring.logging.file.path", "/var/log/workforce-platform")
        log_file_name = config.get("monitoring.logging.file.filename", "platform.log")
        log_max_size_mb = config.get("monitoring.logging.file.max_size_mb", 100)
        log_max_files = config.get("monitoring.logging.file.max_files", 10)
        log_rotation = config.get("monitoring.logging.file.rotation", "daily")
        include_timestamp = config.get("monitoring.logging.include_timestamp", True)
        include_level = config.get("monitoring.logging.include_level", True)
        include_caller = config.get("monitoring.logging.include_caller", True)
        include_correlation_id = config.get("monitoring.logging.include_correlation_id", True)
        component_levels = config.get("monitoring.logging.components", {})
    
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    if log_format == "json":
        formatter = CustomJsonFormatter(
            '%(timestamp)s %(level)s %(component)s %(message)s'
        )
    else:
        # Plain text format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Add correlation ID filter
    correlation_filter = CorrelationIdFilter()
    
    # Set up stdout handler
    if log_output in ["stdout", "both"]:
        stdout_handler = logging.StreamHandler(sys.stdout)
        # Set handler to DEBUG so component-specific levels can control output
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.setFormatter(formatter)
        stdout_handler.addFilter(correlation_filter)
        root_logger.addHandler(stdout_handler)
    
    # Set up file handler
    if log_output in ["file", "both"]:
        # Create log directory if it doesn't exist
        log_dir = Path(log_file_path)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / log_file_name
        
        # Choose handler based on rotation strategy
        if log_rotation == "daily":
            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_file,
                when='midnight',
                interval=1,
                backupCount=log_max_files,
                encoding='utf-8'
            )
        else:
            # Size-based rotation
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=log_max_size_mb * 1024 * 1024,
                backupCount=log_max_files,
                encoding='utf-8'
            )
        
        # Set handler to DEBUG so component-specific levels can control output
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(correlation_filter)
        root_logger.addHandler(file_handler)
    
    # Set component-specific log levels
    for component, level in component_levels.items():
        component_logger = logging.getLogger(component)
        component_numeric_level = getattr(logging, level.upper(), logging.INFO)
        component_logger.setLevel(component_numeric_level)
    
    # Log that logging has been initialized
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging system initialized",
        extra={
            'log_level': log_level,
            'log_format': log_format,
            'log_output': log_output
        }
    )


def get_logger(name: str, **context: Any) -> logging.Logger:
    """
    Get a logger with optional context fields.
    
    Args:
        name: Logger name (typically __name__)
        **context: Additional context fields (user_id, agent_id, task_id, etc.)
        
    Returns:
        Logger instance
        
    Example:
        >>> from shared.logging import get_logger
        >>> 
        >>> logger = get_logger(__name__, user_id="user-123", agent_id="agent-456")
        >>> logger.info("Agent started processing task")
    """
    logger = logging.getLogger(name)
    
    # If context is provided, create an adapter
    if context:
        return logging.LoggerAdapter(logger, context)
    
    return logger


class LogContext:
    """
    Context manager for setting correlation ID and other context fields.
    
    Example:
        >>> from shared.logging import LogContext, get_logger
        >>> 
        >>> logger = get_logger(__name__)
        >>> 
        >>> with LogContext(correlation_id="req-12345", user_id="user-123"):
        >>>     logger.info("Processing request")
        >>>     # correlation_id will be included in all logs within this context
    """
    
    def __init__(self, correlation_id: Optional[str] = None, **context: Any):
        """
        Initialize log context.
        
        Args:
            correlation_id: Correlation ID for request tracking
            **context: Additional context fields
        """
        self.correlation_id = correlation_id
        self.context = context
        self.old_correlation_id = None
    
    def __enter__(self):
        """Enter context - set correlation ID."""
        if self.correlation_id:
            self.old_correlation_id = get_correlation_id()
            set_correlation_id(self.correlation_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - restore old correlation ID."""
        if self.correlation_id:
            if self.old_correlation_id:
                set_correlation_id(self.old_correlation_id)
            else:
                clear_correlation_id()


def log_with_context(logger: logging.Logger, level: str, message: str, 
                     **context: Any) -> None:
    """
    Log a message with additional context fields.
    
    Args:
        logger: Logger instance
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Log message
        **context: Additional context fields
        
    Example:
        >>> from shared.logging import get_logger, log_with_context
        >>> 
        >>> logger = get_logger(__name__)
        >>> log_with_context(
        >>>     logger, 
        >>>     "INFO", 
        >>>     "Task completed",
        >>>     task_id="task-123",
        >>>     duration_ms=1500
        >>> )
    """
    log_method = getattr(logger, level.lower())
    log_method(message, extra=context)


# Convenience functions for common log patterns
def log_api_request(logger: logging.Logger, method: str, path: str, 
                    user_id: Optional[str] = None, **extra: Any) -> None:
    """
    Log an API request.
    
    Args:
        logger: Logger instance
        method: HTTP method
        path: Request path
        user_id: User ID if authenticated
        **extra: Additional fields
    """
    logger.info(
        f"API request: {method} {path}",
        extra={
            'event_type': 'api_request',
            'http_method': method,
            'http_path': path,
            'user_id': user_id,
            **extra
        }
    )


def log_task_event(logger: logging.Logger, event: str, task_id: str, 
                   agent_id: Optional[str] = None, **extra: Any) -> None:
    """
    Log a task lifecycle event.
    
    Args:
        logger: Logger instance
        event: Event type (started, completed, failed, etc.)
        task_id: Task ID
        agent_id: Agent ID if applicable
        **extra: Additional fields
    """
    logger.info(
        f"Task {event}: {task_id}",
        extra={
            'event_type': 'task_event',
            'task_event': event,
            'task_id': task_id,
            'agent_id': agent_id,
            **extra
        }
    )


def log_agent_event(logger: logging.Logger, event: str, agent_id: str, 
                    **extra: Any) -> None:
    """
    Log an agent lifecycle event.
    
    Args:
        logger: Logger instance
        event: Event type (created, started, stopped, terminated, etc.)
        agent_id: Agent ID
        **extra: Additional fields
    """
    logger.info(
        f"Agent {event}: {agent_id}",
        extra={
            'event_type': 'agent_event',
            'agent_event': event,
            'agent_id': agent_id,
            **extra
        }
    )


def log_security_event(logger: logging.Logger, event: str, user_id: Optional[str] = None,
                       severity: str = "medium", **extra: Any) -> None:
    """
    Log a security event.
    
    Args:
        logger: Logger instance
        event: Event description
        user_id: User ID if applicable
        severity: Severity level (low, medium, high, critical)
        **extra: Additional fields
    """
    logger.warning(
        f"Security event: {event}",
        extra={
            'event_type': 'security_event',
            'security_event': event,
            'user_id': user_id,
            'severity': severity,
            **extra
        }
    )


def log_error(logger: logging.Logger, error: Exception, context: str = "",
              **extra: Any) -> None:
    """
    Log an error with exception details.
    
    Args:
        logger: Logger instance
        error: Exception instance
        context: Context description
        **extra: Additional fields
    """
    logger.error(
        f"Error: {context}: {str(error)}",
        extra={
            'event_type': 'error',
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context,
            **extra
        },
        exc_info=True
    )


# Export public API
__all__ = [
    'setup_logging',
    'get_logger',
    'set_correlation_id',
    'get_correlation_id',
    'clear_correlation_id',
    'LogContext',
    'log_with_context',
    'log_api_request',
    'log_task_event',
    'log_agent_event',
    'log_security_event',
    'log_error',
]
