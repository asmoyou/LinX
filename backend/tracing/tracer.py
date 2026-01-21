"""OpenTelemetry tracer setup and management.

References:
- Design Section 11.4: Distributed Tracing
- Requirements 11: Monitoring and Observability
"""

import logging
import functools
from typing import Optional, Callable, Any
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

logger = logging.getLogger(__name__)


class TracingManager:
    """Manage OpenTelemetry tracing configuration."""
    
    def __init__(
        self,
        service_name: str = "digital-workforce-platform",
        jaeger_host: str = "localhost",
        jaeger_port: int = 6831,
        enabled: bool = True,
    ):
        """Initialize tracing manager.
        
        Args:
            service_name: Name of the service
            jaeger_host: Jaeger agent host
            jaeger_port: Jaeger agent port
            enabled: Whether tracing is enabled
        """
        self.service_name = service_name
        self.jaeger_host = jaeger_host
        self.jaeger_port = jaeger_port
        self.enabled = enabled
        self._tracer_provider: Optional[TracerProvider] = None
        self._tracer: Optional[trace.Tracer] = None
        
        if self.enabled:
            self._setup_tracing()
    
    def _setup_tracing(self) -> None:
        """Set up OpenTelemetry tracing."""
        try:
            # Create resource with service name
            resource = Resource(attributes={
                SERVICE_NAME: self.service_name
            })
            
            # Create tracer provider
            self._tracer_provider = TracerProvider(resource=resource)
            
            # Create Jaeger exporter
            jaeger_exporter = JaegerExporter(
                agent_host_name=self.jaeger_host,
                agent_port=self.jaeger_port,
            )
            
            # Add span processor
            span_processor = BatchSpanProcessor(jaeger_exporter)
            self._tracer_provider.add_span_processor(span_processor)
            
            # Set global tracer provider
            trace.set_tracer_provider(self._tracer_provider)
            
            # Get tracer
            self._tracer = trace.get_tracer(__name__)
            
            logger.info(
                f"Tracing initialized: service={self.service_name}, "
                f"jaeger={self.jaeger_host}:{self.jaeger_port}"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize tracing: {e}")
            self.enabled = False
    
    def get_tracer(self) -> trace.Tracer:
        """Get the tracer instance.
        
        Returns:
            OpenTelemetry Tracer
        """
        if not self.enabled or not self._tracer:
            # Return no-op tracer if disabled
            return trace.get_tracer(__name__)
        
        return self._tracer
    
    def instrument_fastapi(self, app) -> None:
        """Instrument FastAPI application.
        
        Args:
            app: FastAPI application instance
        """
        if not self.enabled:
            return
        
        try:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI instrumented for tracing")
        except Exception as e:
            logger.error(f"Failed to instrument FastAPI: {e}")
    
    def instrument_requests(self) -> None:
        """Instrument requests library."""
        if not self.enabled:
            return
        
        try:
            RequestsInstrumentor().instrument()
            logger.info("Requests library instrumented for tracing")
        except Exception as e:
            logger.error(f"Failed to instrument requests: {e}")
    
    def instrument_sqlalchemy(self, engine) -> None:
        """Instrument SQLAlchemy engine.
        
        Args:
            engine: SQLAlchemy engine instance
        """
        if not self.enabled:
            return
        
        try:
            SQLAlchemyInstrumentor().instrument(engine=engine)
            logger.info("SQLAlchemy instrumented for tracing")
        except Exception as e:
            logger.error(f"Failed to instrument SQLAlchemy: {e}")
    
    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: Optional[dict] = None,
    ):
        """Start a new span.
        
        Args:
            name: Span name
            attributes: Optional span attributes
            
        Yields:
            Span instance
        """
        if not self.enabled or not self._tracer:
            yield None
            return
        
        with self._tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            yield span
    
    def shutdown(self) -> None:
        """Shutdown tracing and flush remaining spans."""
        if self._tracer_provider:
            self._tracer_provider.shutdown()
            logger.info("Tracing shutdown complete")


# Global tracing manager instance
_tracing_manager: Optional[TracingManager] = None


def get_tracer() -> trace.Tracer:
    """Get the global tracer instance.
    
    Returns:
        OpenTelemetry Tracer
    """
    global _tracing_manager
    
    if _tracing_manager is None:
        _tracing_manager = TracingManager()
    
    return _tracing_manager.get_tracer()


def trace_function(
    name: Optional[str] = None,
    attributes: Optional[dict] = None,
) -> Callable:
    """Decorator to trace a function.
    
    Args:
        name: Optional span name (defaults to function name)
        attributes: Optional span attributes
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            tracer = get_tracer()
            
            with tracer.start_as_current_span(span_name) as span:
                # Add attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                
                # Add function info
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)
                
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("function.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("function.status", "error")
                    span.set_attribute("function.error", str(e))
                    span.record_exception(e)
                    raise
        
        return wrapper
    return decorator


def trace_async_function(
    name: Optional[str] = None,
    attributes: Optional[dict] = None,
) -> Callable:
    """Decorator to trace an async function.
    
    Args:
        name: Optional span name (defaults to function name)
        attributes: Optional span attributes
        
    Returns:
        Decorated async function
    """
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            tracer = get_tracer()
            
            with tracer.start_as_current_span(span_name) as span:
                # Add attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                
                # Add function info
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)
                
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("function.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("function.status", "error")
                    span.set_attribute("function.error", str(e))
                    span.record_exception(e)
                    raise
        
        return wrapper
    return decorator
