"""Distributed tracing module using OpenTelemetry.

This module provides distributed tracing capabilities including:
- OpenTelemetry instrumentation
- Jaeger trace storage
- Trace context propagation
- Trace sampling configuration
- Trace visualization

References:
- Design Section 11.4: Distributed Tracing
- Requirements 11: Monitoring and Observability
"""

from tracing.tracer import (
    TracingManager,
    get_tracer,
    trace_function,
    trace_async_function,
)

from tracing.context_propagation import (
    TraceContext,
    propagate_trace_context,
    extract_trace_context,
)

from tracing.sampling import (
    SamplingConfig,
    TraceSampler,
    get_sampler,
)

__all__ = [
    # Tracer
    'TracingManager',
    'get_tracer',
    'trace_function',
    'trace_async_function',
    
    # Context propagation
    'TraceContext',
    'propagate_trace_context',
    'extract_trace_context',
    
    # Sampling
    'SamplingConfig',
    'TraceSampler',
    'get_sampler',
]
