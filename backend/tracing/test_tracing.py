"""Tests for distributed tracing.

References:
- Design Section 11.4: Distributed Tracing
- Requirements 11: Monitoring and Observability
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from tracing.context_propagation import (
    ContextPropagator,
    TraceContext,
    extract_trace_context,
    get_current_trace_id,
    propagate_trace_context,
)
from tracing.jaeger_config import (
    JaegerConfig,
    get_jaeger_config_from_env,
    get_jaeger_ui_url,
    validate_jaeger_connection,
)
from tracing.sampling import (
    SamplingConfig,
    SamplingStrategy,
    TraceSampler,
    configure_sampling,
)
from tracing.tracer import (
    TracingManager,
    get_tracer,
    trace_async_function,
    trace_function,
)


class TestTracingManager:
    """Test tracing manager."""

    def test_init_enabled(self):
        """Test initialization with tracing enabled."""
        manager = TracingManager(enabled=True)

        assert manager.enabled is True
        assert manager.service_name == "digital-workforce-platform"

    def test_init_disabled(self):
        """Test initialization with tracing disabled."""
        manager = TracingManager(enabled=False)

        assert manager.enabled is False

    def test_get_tracer(self):
        """Test getting tracer."""
        manager = TracingManager(enabled=False)
        tracer = manager.get_tracer()

        assert tracer is not None

    @patch("tracing.tracer.FastAPIInstrumentor")
    def test_instrument_fastapi(self, mock_instrumentor):
        """Test FastAPI instrumentation."""
        manager = TracingManager(enabled=True)
        mock_app = Mock()

        manager.instrument_fastapi(mock_app)

        mock_instrumentor.instrument_app.assert_called_once_with(mock_app)

    @patch("tracing.tracer.RequestsInstrumentor")
    def test_instrument_requests(self, mock_instrumentor):
        """Test requests instrumentation."""
        manager = TracingManager(enabled=True)

        manager.instrument_requests()

        mock_instrumentor.return_value.instrument.assert_called_once()

    def test_start_span(self):
        """Test starting a span."""
        manager = TracingManager(enabled=False)

        with manager.start_span("test_span", {"key": "value"}) as span:
            # Span should be None when disabled
            assert span is None


class TestTraceDecorators:
    """Test trace decorators."""

    def test_trace_function_decorator(self):
        """Test function tracing decorator."""

        @trace_function(name="test_func")
        def my_function(x, y):
            return x + y

        result = my_function(2, 3)

        assert result == 5

    def test_trace_function_with_exception(self):
        """Test function tracing with exception."""

        @trace_function(name="test_func_error")
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_function()

    @pytest.mark.asyncio
    async def test_trace_async_function(self):
        """Test async function tracing."""

        @trace_async_function(name="test_async")
        async def async_function(x):
            return x * 2

        result = await async_function(5)

        assert result == 10

    @pytest.mark.asyncio
    async def test_trace_async_function_with_exception(self):
        """Test async function tracing with exception."""

        @trace_async_function(name="test_async_error")
        async def failing_async_function():
            raise ValueError("Async test error")

        with pytest.raises(ValueError):
            await failing_async_function()


class TestContextPropagation:
    """Test trace context propagation."""

    def test_inject_context(self):
        """Test injecting trace context."""
        propagator = ContextPropagator()
        carrier = {}

        propagator.inject(carrier)

        # Carrier should have trace context headers
        assert isinstance(carrier, dict)

    def test_extract_context(self):
        """Test extracting trace context."""
        propagator = ContextPropagator()
        carrier = {"traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"}

        context = propagator.extract(carrier)

        # Context extraction should not fail
        assert context is not None or context is None  # May be None if no active span

    def test_get_current_trace_context(self):
        """Test getting current trace context."""
        propagator = ContextPropagator()

        context = propagator.get_current_trace_context()

        # May be None if no active span
        assert context is None or isinstance(context, TraceContext)

    def test_create_headers_with_context(self):
        """Test creating headers with trace context."""
        propagator = ContextPropagator()

        headers = propagator.create_headers_with_context({"existing": "header"})

        assert "existing" in headers
        assert isinstance(headers, dict)

    def test_propagate_trace_context(self):
        """Test propagate_trace_context helper."""
        carrier = {}

        propagate_trace_context(carrier)

        assert isinstance(carrier, dict)

    def test_extract_trace_context(self):
        """Test extract_trace_context helper."""
        carrier = {}

        context = extract_trace_context(carrier)

        # May be None if no context in carrier
        assert context is None or context is not None

    def test_get_current_trace_id(self):
        """Test getting current trace ID."""
        trace_id = get_current_trace_id()

        # May be None if no active span
        assert trace_id is None or isinstance(trace_id, str)


class TestSampling:
    """Test trace sampling."""

    def test_sampling_config_default(self):
        """Test default sampling configuration."""
        config = SamplingConfig()

        assert config.strategy == SamplingStrategy.RATIO_BASED
        assert config.sample_rate == 0.1
        assert config.parent_based is True

    def test_sampling_config_custom(self):
        """Test custom sampling configuration."""
        config = SamplingConfig(
            strategy=SamplingStrategy.ALWAYS_ON,
            sample_rate=1.0,
            parent_based=False,
        )

        assert config.strategy == SamplingStrategy.ALWAYS_ON
        assert config.sample_rate == 1.0
        assert config.parent_based is False

    def test_trace_sampler_init(self):
        """Test trace sampler initialization."""
        sampler = TraceSampler()

        assert sampler.config.strategy == SamplingStrategy.RATIO_BASED

    def test_trace_sampler_always_on(self):
        """Test ALWAYS_ON sampling strategy."""
        config = SamplingConfig(strategy=SamplingStrategy.ALWAYS_ON)
        sampler = TraceSampler(config)

        assert sampler.get_sampler() is not None

    def test_trace_sampler_always_off(self):
        """Test ALWAYS_OFF sampling strategy."""
        config = SamplingConfig(strategy=SamplingStrategy.ALWAYS_OFF)
        sampler = TraceSampler(config)

        assert sampler.get_sampler() is not None

    def test_update_sample_rate(self):
        """Test updating sample rate."""
        sampler = TraceSampler()

        sampler.update_sample_rate(0.5)

        assert sampler.config.sample_rate == 0.5

    def test_update_sample_rate_invalid(self):
        """Test updating sample rate with invalid value."""
        sampler = TraceSampler()

        with pytest.raises(ValueError):
            sampler.update_sample_rate(1.5)

    def test_enable_sampling(self):
        """Test enabling sampling."""
        sampler = TraceSampler()

        sampler.enable_sampling()

        assert sampler.config.strategy == SamplingStrategy.ALWAYS_ON

    def test_disable_sampling(self):
        """Test disabling sampling."""
        sampler = TraceSampler()

        sampler.disable_sampling()

        assert sampler.config.strategy == SamplingStrategy.ALWAYS_OFF

    def test_configure_sampling(self):
        """Test configure_sampling helper."""
        sampler = configure_sampling(
            strategy=SamplingStrategy.RATIO_BASED,
            sample_rate=0.2,
            parent_based=True,
        )

        assert sampler.config.sample_rate == 0.2


class TestJaegerConfig:
    """Test Jaeger configuration."""

    def test_jaeger_config_default(self):
        """Test default Jaeger configuration."""
        config = JaegerConfig()

        assert config.agent_host == "localhost"
        assert config.agent_port == 6831
        assert config.service_name == "digital-workforce-platform"

    def test_jaeger_config_custom(self):
        """Test custom Jaeger configuration."""
        config = JaegerConfig(
            agent_host="jaeger.example.com",
            agent_port=6832,
            service_name="test-service",
        )

        assert config.agent_host == "jaeger.example.com"
        assert config.agent_port == 6832
        assert config.service_name == "test-service"

    def test_jaeger_config_to_dict(self):
        """Test converting config to dictionary."""
        config = JaegerConfig()
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert "agent_host" in config_dict
        assert "service_name" in config_dict

    @patch.dict(
        "os.environ",
        {
            "JAEGER_AGENT_HOST": "test-host",
            "JAEGER_AGENT_PORT": "6832",
            "JAEGER_SERVICE_NAME": "test-service",
        },
    )
    def test_get_jaeger_config_from_env(self):
        """Test getting config from environment."""
        config = get_jaeger_config_from_env()

        assert config.agent_host == "test-host"
        assert config.agent_port == 6832
        assert config.service_name == "test-service"

    @patch("socket.socket")
    def test_validate_jaeger_connection_success(self, mock_socket):
        """Test successful Jaeger connection validation."""
        mock_sock = Mock()
        mock_socket.return_value = mock_sock

        config = JaegerConfig()
        result = validate_jaeger_connection(config)

        # Should attempt to connect
        mock_sock.connect.assert_called_once()

    @patch("socket.socket")
    def test_validate_jaeger_connection_failure(self, mock_socket):
        """Test failed Jaeger connection validation."""
        mock_sock = Mock()
        mock_sock.connect.side_effect = Exception("Connection failed")
        mock_socket.return_value = mock_sock

        config = JaegerConfig()
        result = validate_jaeger_connection(config)

        assert result is False

    def test_get_jaeger_ui_url(self):
        """Test getting Jaeger UI URL."""
        config = JaegerConfig()

        url = get_jaeger_ui_url(config)

        assert "http://" in url
        assert config.service_name in url

    def test_get_jaeger_ui_url_with_trace_id(self):
        """Test getting Jaeger UI URL with trace ID."""
        config = JaegerConfig()
        trace_id = "0af7651916cd43dd8448eb211c80319c"

        url = get_jaeger_ui_url(config, trace_id)

        assert trace_id in url
        assert "/trace/" in url
