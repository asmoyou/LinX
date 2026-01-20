"""
Logging System Demo

This script demonstrates the usage of the structured JSON logging system.

Run this script to see examples of:
- Basic logging with JSON format
- Correlation ID tracking
- Component-specific log levels
- Context-aware logging
- Convenience logging functions

Usage:
    python examples/logging_demo.py
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import Config
from shared.logging import (
    setup_logging,
    get_logger,
    LogContext,
    log_api_request,
    log_task_event,
    log_agent_event,
    log_security_event,
    log_error,
)


def demo_basic_logging():
    """Demonstrate basic logging."""
    print("\n=== Demo 1: Basic Logging ===\n")
    
    logger = get_logger(__name__)
    
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    
    time.sleep(0.5)


def demo_correlation_id():
    """Demonstrate correlation ID tracking."""
    print("\n=== Demo 2: Correlation ID Tracking ===\n")
    
    logger = get_logger(__name__)
    
    # Simulate processing multiple requests
    for i in range(3):
        correlation_id = f"req-{i+1:04d}"
        
        with LogContext(correlation_id=correlation_id):
            logger.info(f"Processing request {i+1}")
            logger.info(f"Request {i+1} completed successfully")
    
    time.sleep(0.5)


def demo_context_logging():
    """Demonstrate context-aware logging."""
    print("\n=== Demo 3: Context-Aware Logging ===\n")
    
    # Create logger with context
    logger = get_logger(__name__, user_id="user-123", agent_id="agent-456")
    
    logger.info("Agent started processing task")
    logger.info("Task completed successfully")
    
    time.sleep(0.5)


def demo_convenience_functions():
    """Demonstrate convenience logging functions."""
    print("\n=== Demo 4: Convenience Logging Functions ===\n")
    
    logger = get_logger(__name__)
    
    # Log API request
    log_api_request(
        logger,
        method="POST",
        path="/api/v1/tasks",
        user_id="user-123",
        status_code=201
    )
    
    # Log task event
    log_task_event(
        logger,
        event="started",
        task_id="task-789",
        agent_id="agent-456"
    )
    
    # Log agent event
    log_agent_event(
        logger,
        event="created",
        agent_id="agent-456",
        agent_type="data_analyst"
    )
    
    # Log security event
    log_security_event(
        logger,
        event="failed_login_attempt",
        user_id="user-999",
        severity="high",
        ip_address="192.168.1.100"
    )
    
    # Log error
    try:
        raise ValueError("Something went wrong")
    except Exception as e:
        log_error(
            logger,
            error=e,
            context="Processing user request",
            user_id="user-123"
        )
    
    time.sleep(0.5)


def demo_component_specific_levels():
    """Demonstrate component-specific log levels."""
    print("\n=== Demo 5: Component-Specific Log Levels ===\n")
    
    # Create loggers for different components
    api_logger = get_logger("api_gateway")
    task_logger = get_logger("task_manager")
    llm_logger = get_logger("llm_providers")
    
    # These will be logged at different levels based on config
    api_logger.debug("API Gateway debug message")
    api_logger.info("API Gateway info message")
    
    task_logger.debug("Task Manager debug message")
    task_logger.info("Task Manager info message")
    
    llm_logger.debug("LLM Provider debug message")
    llm_logger.warning("LLM Provider warning message")
    
    time.sleep(0.5)


def demo_structured_data():
    """Demonstrate logging with structured data."""
    print("\n=== Demo 6: Structured Data Logging ===\n")
    
    logger = get_logger(__name__)
    
    # Log with additional structured data
    logger.info(
        "Task execution completed",
        extra={
            'task_id': 'task-123',
            'duration_ms': 1500,
            'status': 'success',
            'result_size_bytes': 2048,
            'agent_id': 'agent-456'
        }
    )
    
    logger.info(
        "Agent performance metrics",
        extra={
            'agent_id': 'agent-456',
            'tasks_completed': 42,
            'avg_duration_ms': 1200,
            'success_rate': 0.95,
            'cpu_usage_percent': 45.2,
            'memory_usage_mb': 512
        }
    )
    
    time.sleep(0.5)


def main():
    """Run all demos."""
    print("\n" + "="*70)
    print("Structured JSON Logging System Demo")
    print("="*70)
    
    # Load configuration
    config_path = Path(__file__).parent.parent / "config.yaml"
    config = Config.load(str(config_path))
    
    # Set up logging
    setup_logging(config)
    
    print("\nLogging system initialized with JSON format")
    print("All log output will be in structured JSON format\n")
    
    # Run demos
    demo_basic_logging()
    demo_correlation_id()
    demo_context_logging()
    demo_convenience_functions()
    demo_component_specific_levels()
    demo_structured_data()
    
    print("\n" + "="*70)
    print("Demo completed!")
    print("="*70)
    print("\nNote: In production, logs would be written to files and/or")
    print("sent to a centralized logging system (ELK, Loki, etc.)")
    print("\nCheck the log output above to see the structured JSON format.")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
