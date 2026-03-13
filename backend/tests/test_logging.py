"""
Tests for the structured JSON logging module.

Tests cover:
- Logging setup and configuration
- JSON formatting
- Correlation ID tracking
- Component-specific log levels
- File and stdout output
- Log context management
- Convenience logging functions
"""

import json
import logging
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from shared.config import Config
from shared.logging import (
    CorrelationIdFilter,
    CustomJsonFormatter,
    LogContext,
    clear_correlation_id,
    get_correlation_id,
    get_logger,
    log_agent_event,
    log_api_request,
    log_error,
    log_security_event,
    log_task_event,
    log_with_context,
    set_correlation_id,
    setup_logging,
)


def _close_root_logger_handlers() -> None:
    """Close and detach root handlers to avoid leaking open file handles in tests."""
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        handler.close()
        root_logger.removeHandler(handler)


class TestCorrelationId:
    """Test correlation ID management."""

    def test_set_and_get_correlation_id(self):
        """Test setting and getting correlation ID."""
        test_id = "test-correlation-123"
        set_correlation_id(test_id)
        assert get_correlation_id() == test_id
        clear_correlation_id()

    def test_get_correlation_id_when_not_set(self):
        """Test getting correlation ID when not set returns None."""
        clear_correlation_id()
        assert get_correlation_id() is None

    def test_clear_correlation_id(self):
        """Test clearing correlation ID."""
        set_correlation_id("test-123")
        clear_correlation_id()
        assert get_correlation_id() is None

    def test_correlation_id_thread_local(self):
        """Test that correlation IDs are thread-local."""
        import threading

        results = {}

        def set_and_get(thread_id, correlation_id):
            set_correlation_id(correlation_id)
            results[thread_id] = get_correlation_id()

        # Create two threads with different correlation IDs
        thread1 = threading.Thread(target=set_and_get, args=(1, "corr-1"))
        thread2 = threading.Thread(target=set_and_get, args=(2, "corr-2"))

        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()

        # Each thread should have its own correlation ID
        assert results[1] == "corr-1"
        assert results[2] == "corr-2"


class TestCorrelationIdFilter:
    """Test correlation ID filter."""

    def test_filter_adds_correlation_id(self):
        """Test that filter adds correlation ID to log record."""
        set_correlation_id("test-123")

        filter_obj = CorrelationIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert hasattr(record, "correlation_id")
        assert record.correlation_id == "test-123"

        clear_correlation_id()

    def test_filter_adds_none_when_no_correlation_id(self):
        """Test that filter adds 'none' when correlation ID not set."""
        clear_correlation_id()

        filter_obj = CorrelationIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert record.correlation_id == "none"


class TestCustomJsonFormatter:
    """Test custom JSON formatter."""

    def test_formatter_creates_json_output(self):
        """Test that formatter creates valid JSON output."""
        formatter = CustomJsonFormatter()

        record = logging.LogRecord(
            name="test.component",
            level=logging.INFO,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function",
        )
        record.correlation_id = "test-123"

        output = formatter.format(record)

        # Should be valid JSON
        log_data = json.loads(output)

        # Check required fields
        assert "timestamp" in log_data
        assert "level" in log_data
        assert log_data["level"] == "INFO"
        assert "component" in log_data
        assert log_data["component"] == "test.component"
        assert "message" in log_data
        assert log_data["message"] == "Test message"
        assert "correlation_id" in log_data
        assert log_data["correlation_id"] == "test-123"
        assert "caller" in log_data
        assert log_data["caller"]["file"] == "/path/to/test.py"
        assert log_data["caller"]["function"] == "test_function"
        assert log_data["caller"]["line"] == 42

    def test_formatter_includes_context_fields(self):
        """Test that formatter includes context fields like user_id, agent_id."""
        formatter = CustomJsonFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_func",
        )
        record.correlation_id = "test-123"
        record.user_id = "user-456"
        record.agent_id = "agent-789"
        record.task_id = "task-101"

        output = formatter.format(record)
        log_data = json.loads(output)

        assert log_data["user_id"] == "user-456"
        assert log_data["agent_id"] == "agent-789"
        assert log_data["task_id"] == "task-101"


class TestSetupLogging:
    """Test logging setup."""

    def teardown_method(self):
        """Clean up logging handlers after each test."""
        _close_root_logger_handlers()

    def test_setup_logging_with_defaults(self):
        """Test setting up logging with default configuration."""
        setup_logging(None)

        root_logger = logging.getLogger()

        # Should have at least one handler
        assert len(root_logger.handlers) > 0

        # Should be set to INFO level by default
        assert root_logger.level == logging.INFO

    def test_setup_logging_with_config(self):
        """Test setting up logging with configuration."""
        # Create a mock config
        config = Mock()
        config.get = Mock(
            side_effect=lambda key, default=None: {
                "monitoring.logging.level": "DEBUG",
                "monitoring.logging.format": "json",
                "monitoring.logging.output": "stdout",
                "monitoring.logging.include_timestamp": True,
                "monitoring.logging.include_level": True,
                "monitoring.logging.include_caller": True,
                "monitoring.logging.include_correlation_id": True,
                "monitoring.logging.components": {},
            }.get(key, default)
        )

        setup_logging(config)

        root_logger = logging.getLogger()

        # Should be set to DEBUG level
        assert root_logger.level == logging.DEBUG

        # Should have handlers
        assert len(root_logger.handlers) > 0

    def test_setup_logging_with_file_output(self):
        """Test setting up logging with file output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Mock()
            config.get = Mock(
                side_effect=lambda key, default=None: {
                    "monitoring.logging.level": "INFO",
                    "monitoring.logging.format": "json",
                    "monitoring.logging.output": "file",
                    "monitoring.logging.file.path": tmpdir,
                    "monitoring.logging.file.filename": "test.log",
                    "monitoring.logging.file.max_size_mb": 10,
                    "monitoring.logging.file.max_files": 5,
                    "monitoring.logging.file.rotation": "size",
                    "monitoring.logging.include_timestamp": True,
                    "monitoring.logging.include_level": True,
                    "monitoring.logging.include_caller": True,
                    "monitoring.logging.include_correlation_id": True,
                    "monitoring.logging.components": {},
                }.get(key, default)
            )

            setup_logging(config)

            # Log a message
            logger = logging.getLogger("test")
            logger.info("Test message")

            # Check that log file was created
            log_file = Path(tmpdir) / "test.log"
            assert log_file.exists()

            # Check that log file contains JSON
            with open(log_file, "r") as f:
                content = f.read()
                # Should contain JSON log entry
                assert "Test message" in content

    def test_setup_logging_with_component_levels(self):
        """Test setting up logging with component-specific levels."""
        config = Mock()
        config.get = Mock(
            side_effect=lambda key, default=None: {
                "monitoring.logging.level": "INFO",
                "monitoring.logging.format": "json",
                "monitoring.logging.output": "stdout",
                "monitoring.logging.include_timestamp": True,
                "monitoring.logging.include_level": True,
                "monitoring.logging.include_caller": True,
                "monitoring.logging.include_correlation_id": True,
                "monitoring.logging.components": {
                    "api_gateway": "DEBUG",
                    "task_manager": "WARNING",
                },
            }.get(key, default)
        )

        setup_logging(config)

        # Check component-specific levels
        api_logger = logging.getLogger("api_gateway")
        task_logger = logging.getLogger("task_manager")

        assert api_logger.level == logging.DEBUG
        assert task_logger.level == logging.WARNING


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_without_context(self):
        """Test getting logger without context."""
        logger = get_logger("test.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_with_context(self):
        """Test getting logger with context."""
        logger = get_logger("test.module", user_id="user-123", agent_id="agent-456")

        assert isinstance(logger, logging.LoggerAdapter)
        assert logger.extra["user_id"] == "user-123"
        assert logger.extra["agent_id"] == "agent-456"


class TestLogContext:
    """Test LogContext context manager."""

    def test_log_context_sets_correlation_id(self):
        """Test that LogContext sets correlation ID."""
        clear_correlation_id()

        with LogContext(correlation_id="test-123"):
            assert get_correlation_id() == "test-123"

        # Should be cleared after context
        assert get_correlation_id() is None

    def test_log_context_restores_old_correlation_id(self):
        """Test that LogContext restores old correlation ID."""
        set_correlation_id("old-123")

        with LogContext(correlation_id="new-456"):
            assert get_correlation_id() == "new-456"

        # Should restore old ID
        assert get_correlation_id() == "old-123"

        clear_correlation_id()

    def test_log_context_without_correlation_id(self):
        """Test LogContext without correlation ID."""
        set_correlation_id("test-123")

        with LogContext():
            # Should not change correlation ID
            assert get_correlation_id() == "test-123"

        clear_correlation_id()


class TestConvenienceFunctions:
    """Test convenience logging functions."""

    def setup_method(self):
        """Set up test logger."""
        setup_logging(None)
        self.logger = get_logger("test")

    def teardown_method(self):
        """Clean up."""
        _close_root_logger_handlers()

    def test_log_api_request(self):
        """Test log_api_request function."""
        with patch.object(self.logger, "info") as mock_info:
            log_api_request(self.logger, method="GET", path="/api/v1/agents", user_id="user-123")

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "GET /api/v1/agents" in call_args[0][0]
            assert call_args[1]["extra"]["event_type"] == "api_request"
            assert call_args[1]["extra"]["http_method"] == "GET"
            assert call_args[1]["extra"]["user_id"] == "user-123"

    def test_log_task_event(self):
        """Test log_task_event function."""
        with patch.object(self.logger, "info") as mock_info:
            log_task_event(self.logger, event="started", task_id="task-123", agent_id="agent-456")

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "task-123" in call_args[0][0]
            assert call_args[1]["extra"]["event_type"] == "task_event"
            assert call_args[1]["extra"]["task_event"] == "started"
            assert call_args[1]["extra"]["task_id"] == "task-123"
            assert call_args[1]["extra"]["agent_id"] == "agent-456"

    def test_log_agent_event(self):
        """Test log_agent_event function."""
        with patch.object(self.logger, "info") as mock_info:
            log_agent_event(self.logger, event="created", agent_id="agent-789")

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "agent-789" in call_args[0][0]
            assert call_args[1]["extra"]["event_type"] == "agent_event"
            assert call_args[1]["extra"]["agent_event"] == "created"
            assert call_args[1]["extra"]["agent_id"] == "agent-789"

    def test_log_security_event(self):
        """Test log_security_event function."""
        with patch.object(self.logger, "warning") as mock_warning:
            log_security_event(
                self.logger, event="unauthorized_access", user_id="user-123", severity="high"
            )

            mock_warning.assert_called_once()
            call_args = mock_warning.call_args
            assert "unauthorized_access" in call_args[0][0]
            assert call_args[1]["extra"]["event_type"] == "security_event"
            assert call_args[1]["extra"]["security_event"] == "unauthorized_access"
            assert call_args[1]["extra"]["user_id"] == "user-123"
            assert call_args[1]["extra"]["severity"] == "high"

    def test_log_error(self):
        """Test log_error function."""
        with patch.object(self.logger, "error") as mock_error:
            test_exception = ValueError("Test error")

            log_error(self.logger, error=test_exception, context="Testing error logging")

            mock_error.assert_called_once()
            call_args = mock_error.call_args
            assert "Test error" in call_args[0][0]
            assert call_args[1]["extra"]["event_type"] == "error"
            assert call_args[1]["extra"]["error_type"] == "ValueError"
            assert call_args[1]["extra"]["error_message"] == "Test error"
            assert call_args[1]["extra"]["context"] == "Testing error logging"
            assert call_args[1]["exc_info"] is True


class TestIntegration:
    """Integration tests for logging system."""

    def teardown_method(self):
        """Clean up."""
        _close_root_logger_handlers()
        clear_correlation_id()

    def test_end_to_end_json_logging(self):
        """Test end-to-end JSON logging with correlation ID."""
        # Set up logging to capture output
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Mock()
            config.get = Mock(
                side_effect=lambda key, default=None: {
                    "monitoring.logging.level": "INFO",
                    "monitoring.logging.format": "json",
                    "monitoring.logging.output": "file",
                    "monitoring.logging.file.path": tmpdir,
                    "monitoring.logging.file.filename": "test.log",
                    "monitoring.logging.file.max_size_mb": 10,
                    "monitoring.logging.file.max_files": 5,
                    "monitoring.logging.file.rotation": "size",
                    "monitoring.logging.include_timestamp": True,
                    "monitoring.logging.include_level": True,
                    "monitoring.logging.include_caller": True,
                    "monitoring.logging.include_correlation_id": True,
                    "monitoring.logging.components": {},
                }.get(key, default)
            )

            setup_logging(config)

            # Use LogContext to set correlation ID
            with LogContext(correlation_id="req-12345"):
                logger = get_logger("test.module", user_id="user-123")
                logger.info("Test message with context")

            # Read log file
            log_file = Path(tmpdir) / "test.log"
            with open(log_file, "r") as f:
                lines = f.readlines()

            # Parse JSON logs
            logs = [json.loads(line) for line in lines if line.strip()]

            # Find our test log
            test_log = None
            for log in logs:
                if "Test message with context" in log.get("message", ""):
                    test_log = log
                    break

            assert test_log is not None
            assert test_log["correlation_id"] == "req-12345"
            assert test_log["user_id"] == "user-123"
            assert test_log["level"] == "INFO"
            assert test_log["component"] == "test.module"
            assert "timestamp" in test_log
            assert "caller" in test_log

    def test_component_specific_logging(self):
        """Test that component-specific log levels work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Mock()
            config.get = Mock(
                side_effect=lambda key, default=None: {
                    "monitoring.logging.level": "WARNING",
                    "monitoring.logging.format": "json",
                    "monitoring.logging.output": "file",
                    "monitoring.logging.file.path": tmpdir,
                    "monitoring.logging.file.filename": "test.log",
                    "monitoring.logging.file.max_size_mb": 10,
                    "monitoring.logging.file.max_files": 5,
                    "monitoring.logging.file.rotation": "size",
                    "monitoring.logging.include_timestamp": True,
                    "monitoring.logging.include_level": True,
                    "monitoring.logging.include_caller": True,
                    "monitoring.logging.include_correlation_id": True,
                    "monitoring.logging.components": {
                        "test.debug_component": "DEBUG",
                    },
                }.get(key, default)
            )

            setup_logging(config)

            # Regular logger should only log WARNING and above
            regular_logger = get_logger("test.regular")
            regular_logger.info("This should not appear")
            regular_logger.warning("This should appear")

            # Debug component should log DEBUG and above
            debug_logger = get_logger("test.debug_component")
            debug_logger.debug("Debug message should appear")

            # Read log file
            log_file = Path(tmpdir) / "test.log"
            with open(log_file, "r") as f:
                content = f.read()

            # Check that only appropriate messages appear
            assert "This should not appear" not in content
            assert "This should appear" in content
            assert "Debug message should appear" in content
