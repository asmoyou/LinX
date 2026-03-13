from unittest.mock import patch

from user_memory.builder import UserMemoryBuilder, get_user_memory_builder


def test_user_memory_builder_aliases_session_observation_builder() -> None:
    assert UserMemoryBuilder.__name__ == "SessionObservationBuilder"


def test_get_user_memory_builder_delegates_to_session_observation_builder() -> None:
    sentinel = object()

    with patch("user_memory.builder.get_session_observation_builder", return_value=sentinel):
        assert get_user_memory_builder() is sentinel
