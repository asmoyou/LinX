"""User-memory extraction builder."""

from user_memory.session_observation_builder import (
    _SESSION_MEMORY_EXTRACTION_FAIL_UNTIL,
    SessionObservationBuilder as UserMemoryBuilder,
    get_session_observation_builder,
)


def get_user_memory_builder() -> UserMemoryBuilder:
    """Return the shared user-memory builder."""

    return get_session_observation_builder()


__all__ = [
    "_SESSION_MEMORY_EXTRACTION_FAIL_UNTIL",
    "UserMemoryBuilder",
    "get_user_memory_builder",
]
