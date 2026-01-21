"""Trace sampling configuration.

References:
- Design Section 11.4: Distributed Tracing
- Requirements 11: Monitoring and Observability
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from opentelemetry.sdk.trace.sampling import (
    ALWAYS_OFF,
    ALWAYS_ON,
    Decision,
    ParentBased,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)

logger = logging.getLogger(__name__)


class SamplingStrategy(Enum):
    """Sampling strategy types."""

    ALWAYS_ON = "always_on"
    ALWAYS_OFF = "always_off"
    RATIO_BASED = "ratio_based"
    PARENT_BASED = "parent_based"


@dataclass
class SamplingConfig:
    """Sampling configuration."""

    strategy: SamplingStrategy = SamplingStrategy.RATIO_BASED
    sample_rate: float = 0.1  # 10% sampling by default
    parent_based: bool = True  # Respect parent sampling decision


class TraceSampler:
    """Configure trace sampling strategies."""

    def __init__(self, config: Optional[SamplingConfig] = None):
        """Initialize trace sampler.

        Args:
            config: Sampling configuration
        """
        self.config = config or SamplingConfig()
        self._sampler = self._create_sampler()
        logger.info(f"TraceSampler initialized: strategy={self.config.strategy.value}")

    def _create_sampler(self) -> Sampler:
        """Create sampler based on configuration.

        Returns:
            OpenTelemetry Sampler
        """
        if self.config.strategy == SamplingStrategy.ALWAYS_ON:
            return ALWAYS_ON

        elif self.config.strategy == SamplingStrategy.ALWAYS_OFF:
            return ALWAYS_OFF

        elif self.config.strategy == SamplingStrategy.RATIO_BASED:
            base_sampler = TraceIdRatioBased(self.config.sample_rate)

            if self.config.parent_based:
                return ParentBased(root=base_sampler)
            else:
                return base_sampler

        elif self.config.strategy == SamplingStrategy.PARENT_BASED:
            # Use ratio-based as root sampler for parent-based
            root_sampler = TraceIdRatioBased(self.config.sample_rate)
            return ParentBased(root=root_sampler)

        else:
            logger.warning(f"Unknown sampling strategy: {self.config.strategy}")
            return TraceIdRatioBased(0.1)  # Default to 10%

    def get_sampler(self) -> Sampler:
        """Get the configured sampler.

        Returns:
            OpenTelemetry Sampler
        """
        return self._sampler

    def update_sample_rate(self, rate: float) -> None:
        """Update sampling rate.

        Args:
            rate: New sample rate (0.0 to 1.0)
        """
        if not 0.0 <= rate <= 1.0:
            raise ValueError("Sample rate must be between 0.0 and 1.0")

        self.config.sample_rate = rate
        self._sampler = self._create_sampler()
        logger.info(f"Sample rate updated to: {rate}")

    def enable_sampling(self) -> None:
        """Enable sampling (set to ALWAYS_ON)."""
        self.config.strategy = SamplingStrategy.ALWAYS_ON
        self._sampler = self._create_sampler()
        logger.info("Sampling enabled (ALWAYS_ON)")

    def disable_sampling(self) -> None:
        """Disable sampling (set to ALWAYS_OFF)."""
        self.config.strategy = SamplingStrategy.ALWAYS_OFF
        self._sampler = self._create_sampler()
        logger.info("Sampling disabled (ALWAYS_OFF)")


# Global sampler instance
_sampler: Optional[TraceSampler] = None


def get_sampler() -> TraceSampler:
    """Get the global trace sampler.

    Returns:
        TraceSampler instance
    """
    global _sampler

    if _sampler is None:
        _sampler = TraceSampler()

    return _sampler


def configure_sampling(
    strategy: SamplingStrategy = SamplingStrategy.RATIO_BASED,
    sample_rate: float = 0.1,
    parent_based: bool = True,
) -> TraceSampler:
    """Configure trace sampling.

    Args:
        strategy: Sampling strategy
        sample_rate: Sample rate (0.0 to 1.0)
        parent_based: Whether to respect parent sampling decision

    Returns:
        Configured TraceSampler
    """
    global _sampler

    config = SamplingConfig(
        strategy=strategy,
        sample_rate=sample_rate,
        parent_based=parent_based,
    )

    _sampler = TraceSampler(config)
    return _sampler
