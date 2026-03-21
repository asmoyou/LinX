from types import SimpleNamespace

from api_gateway.routers.agent_conversations import (
    _build_runtime_chunk,
    _sanitize_unverified_workspace_save_claims,
)


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


def test_sanitize_unverified_workspace_save_claims_drops_hallucinated_file_sections() -> None:
    text = """
## 📝 赞美福州的古诗创作完成！

---

我为你创作了一首七言律诗，并保存到文档中：

**文件路径**：`/workspace/output/fuzhou-poem.md`

---

## 🏮 原创作品

闽水悠悠绕郭流，榕城风物韵千秋。

---

## 📁 文件信息

| 项目 | 信息 |
|------|------|
| **文件路径** | `/workspace/output/fuzhou-poem.md` |
| **格式** | Markdown 文档 |
""".strip()

    sanitized = _sanitize_unverified_workspace_save_claims(
        text,
        artifact_delta_entries=[],
    )

    assert "保存到文档中" not in sanitized
    assert "fuzhou-poem.md" not in sanitized
    assert "文件信息" not in sanitized
    assert "原创作品" in sanitized
    assert "闽水悠悠绕郭流" in sanitized


def test_sanitize_unverified_workspace_save_claims_keeps_verified_output_paths() -> None:
    text = """
已将结果保存到 `/workspace/output/fuzhou-poem.md`

## 🏮 原创作品

闽水悠悠绕郭流，榕城风物韵千秋。
""".strip()

    sanitized = _sanitize_unverified_workspace_save_claims(
        text,
        artifact_delta_entries=[{"path": "output/fuzhou-poem.md"}],
    )

    assert "保存到 `/workspace/output/fuzhou-poem.md`" in sanitized
    assert "原创作品" in sanitized
