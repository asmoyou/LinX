from types import SimpleNamespace

from api_gateway.routers.agent_conversations import _build_runtime_chunk


def test_build_runtime_chunk_marks_restore_only_for_new_runtime() -> None:
    runtime = SimpleNamespace(
        runtime_session_id="runtime-1",
        restored_from_snapshot=True,
        snapshot_generation=4,
        use_sandbox=True,
    )

    restored_chunk = _build_runtime_chunk(runtime, is_new_runtime=True)
    reused_chunk = _build_runtime_chunk(runtime, is_new_runtime=False)

    assert restored_chunk == {
        "type": "runtime",
        "runtime_session_id": "runtime-1",
        "is_new_runtime": True,
        "restored_from_snapshot": True,
        "snapshot_generation": 4,
        "use_sandbox": True,
    }
    assert reused_chunk == {
        "type": "runtime",
        "runtime_session_id": "runtime-1",
        "is_new_runtime": False,
        "restored_from_snapshot": False,
        "snapshot_generation": 4,
        "use_sandbox": True,
    }
