from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from access_control.permissions import CurrentUser
from api_gateway.routers import agent_conversations
from database.models import AgentConversation, AgentConversationMessage, AgentConversationSnapshot


class _FakeConversationQuery:
    def __init__(self, rows: list[AgentConversation], total_count: int) -> None:
        self._rows = rows
        self._total_count = total_count
        self._limit: int | None = None

    def filter(self, *_args, **_kwargs):
        return self

    def count(self) -> int:
        return self._total_count

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, value: int):
        self._limit = value
        return self

    def all(self) -> list[AgentConversation]:
        if self._limit is None:
            return list(self._rows)
        return list(self._rows[: self._limit])


class _FakeSingleResultQuery:
    def __init__(self, result=None) -> None:
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, query_map: dict[object, object]) -> None:
        self._query_map = query_map

    def query(self, model):
        return self._query_map[model]


@contextmanager
def _fake_db_session(session: _FakeSession):
    yield session


def _current_user() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid4()),
        username="tester",
        role="user",
    )


def _conversation_row(*, updated_at: datetime, title: str) -> AgentConversation:
    row = AgentConversation(
        conversation_id=uuid4(),
        agent_id=uuid4(),
        owner_user_id=uuid4(),
        title=title,
        status="active",
        source="web",
        created_at=updated_at - timedelta(hours=1),
        updated_at=updated_at,
    )
    row.last_message_at = updated_at
    return row


def _message_row(*, created_at: datetime, role: str, text: str) -> AgentConversationMessage:
    return AgentConversationMessage(
        message_id=uuid4(),
        conversation_id=uuid4(),
        role=role,
        content_text=text,
        source="web",
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_list_agent_conversations_returns_cursor_page(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _conversation_row(updated_at=now, title="Newest"),
        _conversation_row(updated_at=now - timedelta(minutes=1), title="Older"),
        _conversation_row(updated_at=now - timedelta(minutes=2), title="Oldest"),
    ]
    fake_session = _FakeSession(
        {
            AgentConversation: _FakeConversationQuery(rows=rows, total_count=5),
            AgentConversationMessage: _FakeSingleResultQuery(),
            AgentConversationSnapshot: _FakeSingleResultQuery(),
        }
    )
    monkeypatch.setattr(
        agent_conversations,
        "get_db_session",
        lambda: _fake_db_session(fake_session),
    )
    monkeypatch.setattr(
        agent_conversations.agents_router,
        "_get_accessible_agent_or_raise",
        lambda *_args, **_kwargs: None,
    )

    response = await agent_conversations.list_agent_conversations(
        agent_id=str(uuid4()),
        limit=2,
        cursor=None,
        current_user=_current_user(),
    )

    assert response.total == 5
    assert response.hasMore is True
    assert [item.title for item in response.items] == ["Newest", "Older"]
    assert isinstance(response.nextCursor, str)
    decoded = agent_conversations._decode_conversation_cursor(response.nextCursor)
    assert decoded is not None
    assert decoded[0] == rows[1].updated_at
    assert decoded[1] == rows[1].conversation_id


@pytest.mark.asyncio
async def test_list_agent_conversation_messages_returns_older_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    owned_conversation = SimpleNamespace(conversation_id=uuid4())
    messages = [
        _message_row(created_at=now - timedelta(minutes=2), role="user", text="First"),
        _message_row(created_at=now - timedelta(minutes=1), role="assistant", text="Second"),
    ]
    history_page = {
        "messages": messages,
        "summary_row": None,
        "summary_text": None,
        "compacted_message_count": 12,
        "archived_segment_count": 1,
        "recent_window_size": 40,
        "has_older_live_messages": True,
    }

    @contextmanager
    def _session_ctx():
        yield SimpleNamespace()

    monkeypatch.setattr(agent_conversations, "get_db_session", _session_ctx)
    monkeypatch.setattr(
        agent_conversations,
        "_load_owned_conversation",
        lambda *_args, **_kwargs: owned_conversation,
    )
    monkeypatch.setattr(
        agent_conversations,
        "get_conversation_history_compaction_service",
        lambda: SimpleNamespace(
            list_live_message_page=lambda *_args, **_kwargs: history_page,
        ),
    )

    response = await agent_conversations.list_agent_conversation_messages(
        agent_id=str(uuid4()),
        conversation_id=str(owned_conversation.conversation_id),
        limit=50,
        before=None,
        current_user=_current_user(),
    )

    assert [item.contentText for item in response.items] == ["First", "Second"]
    assert response.hasOlderLiveMessages is True
    decoded = agent_conversations._decode_message_cursor(response.olderCursor)
    assert decoded is not None
    assert decoded[0] == messages[0].created_at
    assert decoded[1] == messages[0].message_id
    assert response.compactedMessageCount == 12
    assert response.archivedSegmentCount == 1


@pytest.mark.asyncio
async def test_build_conversation_history_uses_runtime_window(monkeypatch: pytest.MonkeyPatch) -> None:
    conversation_id = uuid4()
    recent_messages = [
        _message_row(
            created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            role="user",
            text="Need a summary",
        ),
        _message_row(
            created_at=datetime.now(timezone.utc),
            role="assistant",
            text="Here is the result",
        ),
    ]
    history_window = {
        "summary_text": "Goals:\n- Keep durable context only",
        "summary_row": None,
        "recent_messages": recent_messages,
    }

    monkeypatch.setattr(
        agent_conversations,
        "get_conversation_history_compaction_service",
        lambda: SimpleNamespace(load_runtime_window=lambda _conversation_id: history_window),
    )

    async def _fake_build_history_content_from_row(message: AgentConversationMessage):
        return message.content_text

    monkeypatch.setattr(
        agent_conversations,
        "_build_history_content_from_row",
        _fake_build_history_content_from_row,
    )

    history, returned_window = await agent_conversations._build_conversation_history(conversation_id)

    assert returned_window is history_window
    assert history[0]["role"] == "system"
    assert "Earlier persistent conversation summary." in history[0]["content"]
    assert history[1:] == [
        {"role": "user", "content": "Need a summary"},
        {"role": "assistant", "content": "Here is the result"},
    ]


def test_cursor_helpers_reject_invalid_payload() -> None:
    with pytest.raises(Exception):
        agent_conversations._decode_conversation_cursor("not-a-valid-cursor")
