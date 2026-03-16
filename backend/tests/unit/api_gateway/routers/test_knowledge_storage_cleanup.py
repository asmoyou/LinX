import io
from contextlib import contextmanager

import pytest
from starlette.datastructures import Headers, UploadFile

from access_control.permissions import CurrentUser
from api_gateway.routers.knowledge import upload_knowledge


@pytest.mark.asyncio
async def test_upload_knowledge_cleans_uploaded_objects_when_db_write_fails(monkeypatch):
    deleted_refs = []

    class _FakeMinio:
        def upload_file(self, **kwargs):
            bucket_type = kwargs["bucket_type"]
            filename = kwargs["filename"]
            if bucket_type == "images":
                return "images", f"user-1/{filename}"
            return "documents", f"user-1/{filename}"

        def parse_object_reference(self, reference):
            parts = str(reference).split(":", 2)
            if len(parts) == 3:
                return parts[1], parts[2]
            return None

        def delete_file_versions(self, bucket_name, object_key):
            deleted_refs.append((bucket_name, object_key))
            return 1

    class _FakeSession:
        def add(self, _row):
            return None

        def flush(self):
            raise RuntimeError("flush failed")

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(
        "object_storage.minio_client.get_minio_client",
        lambda: _FakeMinio(),
    )
    monkeypatch.setattr("api_gateway.routers.knowledge.get_db_session", _fake_db_session)
    monkeypatch.setattr(
        "api_gateway.routers.knowledge._upload_thumbnail_if_possible",
        lambda **_kwargs: ("minio:images:user-1/doc_thumb.jpg", "image/jpeg"),
    )

    upload = UploadFile(
        file=io.BytesIO(b"hello world"),
        filename="doc.txt",
        headers=Headers({"content-type": "text/plain"}),
    )
    current_user = CurrentUser(
        user_id="user-1",
        username="tester",
        role="user",
        token_jti="token-1",
    )

    with pytest.raises(Exception) as exc:
        await upload_knowledge(
            file=upload,
            title="",
            description="",
            tags="[]",
            access_level="private",
            department_id="",
            collection_id="",
            current_user=current_user,
        )

    assert exc.value.status_code == 500
    assert set(deleted_refs) == {
        ("documents", "user-1/doc.txt"),
        ("images", "user-1/doc_thumb.jpg"),
    }
