from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from user_memory.conversation_memory_repository import ConversationMemoryRepository


def test_build_complete_turns_groups_consecutive_user_messages_and_skips_incomplete_tail() -> None:
    base_time = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
    messages = [
        SimpleNamespace(
            role="user",
            content_text="第一段需求",
            created_at=base_time,
            message_id=uuid4(),
        ),
        SimpleNamespace(
            role="user",
            content_text="补充说明",
            created_at=base_time,
            message_id=uuid4(),
        ),
        SimpleNamespace(
            role="assistant",
            content_text="收到，这里是完整回复。",
            created_at=base_time,
            message_id=uuid4(),
        ),
        SimpleNamespace(
            role="user",
            content_text="下一轮还没回复",
            created_at=base_time,
            message_id=uuid4(),
        ),
    ]

    turns = ConversationMemoryRepository._build_complete_turns(messages, agent_name="Planner")

    assert len(turns) == 1
    assert turns[0].user_message == "第一段需求\n\n补充说明"
    assert turns[0].agent_response == "收到，这里是完整回复。"
    assert turns[0].agent_name == "Planner"
    assert len(turns[0].user_message_ids) == 2
