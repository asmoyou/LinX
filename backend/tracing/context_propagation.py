"""Trace context propagation across services.

References:
- Design Section 11.4: Distributed Tracing
- Requirements 11: Monitoring and Observability
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)


@dataclass
class TraceContext:
    """Trace context information."""

    trace_id: str
    span_id: str
    trace_flags: str
    trace_state: Optional[str] = None


class ContextPropagator:
    """Propagate trace context across service boundaries."""

    def __init__(self):
        """Initialize context propagator."""
        self.propagator = TraceContextTextMapPropagator()
        logger.info("ContextPropagator initialized")

    def inject(self, carrier: Dict[str, str]) -> None:
        """Inject trace context into carrier (e.g., HTTP headers).

        Args:
            carrier: Dictionary to inject context into
        """
        try:
            self.propagator.inject(carrier)
            logger.debug(f"Trace context injected: {carrier}")
        except Exception as e:
            logger.error(f"Failed to inject trace context: {e}")

    def extract(self, carrier: Dict[str, str]) -> Optional[Context]:
        """Extract trace context from carrier.

        Args:
            carrier: Dictionary containing trace context

        Returns:
            Extracted context or None
        """
        try:
            context = self.propagator.extract(carrier)
            logger.debug(f"Trace context extracted from: {carrier}")
            return context
        except Exception as e:
            logger.error(f"Failed to extract trace context: {e}")
            return None

    def get_current_trace_context(self) -> Optional[TraceContext]:
        """Get current trace context.

        Returns:
            TraceContext or None if no active span
        """
        try:
            span = trace.get_current_span()

            if not span or not span.get_span_context().is_valid:
                return None

            span_context = span.get_span_context()

            return TraceContext(
                trace_id=format(span_context.trace_id, "032x"),
                span_id=format(span_context.span_id, "016x"),
                trace_flags=format(span_context.trace_flags, "02x"),
                trace_state=str(span_context.trace_state) if span_context.trace_state else None,
            )

        except Exception as e:
            logger.error(f"Failed to get current trace context: {e}")
            return None

    def create_headers_with_context(
        self,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Create HTTP headers with trace context.

        Args:
            headers: Existing headers to add context to

        Returns:
            Headers with trace context
        """
        if headers is None:
            headers = {}

        self.inject(headers)
        return headers

    def extract_from_headers(
        self,
        headers: Dict[str, str],
    ) -> Optional[Context]:
        """Extract trace context from HTTP headers.

        Args:
            headers: HTTP headers

        Returns:
            Extracted context or None
        """
        return self.extract(headers)


# Global propagator instance
_propagator: Optional[ContextPropagator] = None


def get_propagator() -> ContextPropagator:
    """Get the global context propagator.

    Returns:
        ContextPropagator instance
    """
    global _propagator

    if _propagator is None:
        _propagator = ContextPropagator()

    return _propagator


def propagate_trace_context(carrier: Dict[str, str]) -> None:
    """Inject trace context into carrier.

    Args:
        carrier: Dictionary to inject context into
    """
    propagator = get_propagator()
    propagator.inject(carrier)


def extract_trace_context(carrier: Dict[str, str]) -> Optional[Context]:
    """Extract trace context from carrier.

    Args:
        carrier: Dictionary containing trace context

    Returns:
        Extracted context or None
    """
    propagator = get_propagator()
    return propagator.extract(carrier)


def get_current_trace_id() -> Optional[str]:
    """Get current trace ID.

    Returns:
        Trace ID as hex string or None
    """
    propagator = get_propagator()
    context = propagator.get_current_trace_context()

    return context.trace_id if context else None


def get_current_span_id() -> Optional[str]:
    """Get current span ID.

    Returns:
        Span ID as hex string or None
    """
    propagator = get_propagator()
    context = propagator.get_current_trace_context()

    return context.span_id if context else None
