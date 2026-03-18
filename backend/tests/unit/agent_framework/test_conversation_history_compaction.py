from datetime import datetime, timedelta, timezone
from uuid import uuid4

from agent_framework.conversation_history_compaction import (
    _build_fallback_summary_text,
    _split_messages_by_turn_window,
)
from database.models import AgentConversationMessage


def _message(role: str, text: str, minutes_offset: int) -> AgentConversationMessage:
    return AgentConversationMessage(
        message_id=uuid4(),
        conversation_id=uuid4(),
        role=role,
        content_text=text,
        created_at=datetime.now(timezone.utc) + timedelta(minutes=minutes_offset),
    )


def test_split_messages_by_turn_window_keeps_recent_turns() -> None:
    messages = [
        _message("user", "request 1", 0),
        _message("assistant", "reply 1", 1),
        _message("user", "request 2", 2),
        _message("assistant", "reply 2", 3),
        _message("user", "request 3", 4),
        _message("assistant", "reply 3", 5),
    ]

    older, recent = _split_messages_by_turn_window(messages, 2)

    assert [message.content_text for message in older] == ["request 1", "reply 1"]
    assert [message.content_text for message in recent] == [
        "request 2",
        "reply 2",
        "request 3",
        "reply 3",
    ]


def test_build_fallback_summary_text_contains_highlights() -> None:
    messages = [
        _message("user", "Need a launch plan for project Apollo", 0),
        _message("assistant", "Created the plan and noted milestones", 1),
        _message("assistant", "Saved file to output/launch-plan.md", 2),
    ]
    messages[-1].content_json = {"artifacts": [{"path": "output/launch-plan.md"}]}

    summary_text = _build_fallback_summary_text(messages)

    assert summary_text is not None
    assert "Goals:" in summary_text
    assert "Important files:" in summary_text
    assert "output/launch-plan.md" in summary_text
