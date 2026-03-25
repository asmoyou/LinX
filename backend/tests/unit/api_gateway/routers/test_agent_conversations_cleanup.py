from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from api_gateway.routers.agent_conversations import (
    _cleanup_incomplete_turn_state,
    _delete_message_and_cleanup_storage,
)
from database.models import AgentConversation, AgentConversationMessage


class _FakeQuery:
    def __init__(
        self,
        *,
        session: "_FakeSession",
        model,
    ) -> None:
        self._session = session
        self._model = model
        self._ordered = False

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        self._ordered = True
        return self

    def first(self):
        if self._model is AgentConversation:
            return self._session.conversation
        if self._model is AgentConversationMessage:
            if not self._session.messages:
                return None
            if self._ordered:
                return max(self._session.messages, key=lambda item: item.created_at)
            return self._session.messages[0]
        return None


class _FakeSession:
    def __init__(
        self,
        *,
        conversation: AgentConversation,
        messages: list[AgentConversationMessage],
    ) -> None:
        self.conversation = conversation
        self.messages = messages
        self.committed = False
        self.flushed = False

    def query(self, model):
        return _FakeQuery(session=self, model=model)

    def delete(self, message: AgentConversationMessage) -> None:
        self.messages = [item for item in self.messages if item.message_id != message.message_id]

    def flush(self) -> None:
        self.flushed = True

    def commit(self) -> None:
        self.committed = True


def test_delete_message_and_cleanup_storage_updates_conversation_and_deletes_attachments(
    monkeypatch,
) -> None:
    conversation_id = uuid4()
    deleted_message_id = uuid4()
    older_message_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    deleted_message_time = older_message_time + timedelta(minutes=3)

    conversation = AgentConversation(conversation_id=conversation_id)
    conversation.last_message_at = deleted_message_time
    conversation.updated_at = older_message_time

    older_message = AgentConversationMessage(
        message_id=uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content_text="older reply",
        created_at=older_message_time,
    )
    deleted_message = AgentConversationMessage(
        message_id=deleted_message_id,
        conversation_id=conversation_id,
        role="user",
        content_text="cancelled turn",
        attachments_json=[
            {"storage_ref": "artifacts/conversations/input-1"},
        ],
        created_at=deleted_message_time,
    )
    fake_session = _FakeSession(
        conversation=conversation,
        messages=[deleted_message, older_message],
    )

    @contextmanager
    def _fake_db_session():
        yield fake_session

    deleted_refs: list[set[str]] = []
    monkeypatch.setattr(
        "api_gateway.routers.agent_conversations.get_db_session",
        _fake_db_session,
    )
    monkeypatch.setattr(
        "api_gateway.routers.agent_conversations.delete_object_references",
        lambda refs: deleted_refs.append(set(refs)),
    )

    deleted = _delete_message_and_cleanup_storage(deleted_message_id)

    assert deleted is True
    assert fake_session.flushed is True
    assert fake_session.committed is True
    assert [message.message_id for message in fake_session.messages] == [older_message.message_id]
    assert conversation.last_message_at == older_message_time
    assert conversation.updated_at is not None
    assert conversation.updated_at >= deleted_message_time
    assert deleted_refs == [{"artifacts/conversations/input-1"}]


def test_cleanup_incomplete_turn_state_keeps_persisted_input_message_on_execution_failure(
    monkeypatch,
) -> None:
    input_message = AgentConversationMessage(
        message_id=uuid4(),
        conversation_id=uuid4(),
        role="user",
        content_text="failed turn input",
        attachments_json=[{"storage_ref": "artifacts/conversations/input-2"}],
    )

    deleted_message_ids: list = []
    deleted_refs: list[set[str]] = []
    monkeypatch.setattr(
        "api_gateway.routers.agent_conversations._delete_message_and_cleanup_storage",
        lambda message_id: deleted_message_ids.append(message_id),
    )
    monkeypatch.setattr(
        "api_gateway.routers.agent_conversations.delete_object_references",
        lambda refs: deleted_refs.append(set(refs)),
    )

    _cleanup_incomplete_turn_state(
        input_message_row=input_message,
        assistant_message_row=None,
        uploaded_attachment_refs={"artifacts/conversations/input-2"},
        remove_input_message=False,
    )

    assert deleted_message_ids == []
    assert deleted_refs == []
