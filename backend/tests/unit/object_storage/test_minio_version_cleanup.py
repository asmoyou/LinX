from types import SimpleNamespace
from unittest.mock import Mock, call

from object_storage.minio_client import MinIOClient


def _build_client() -> MinIOClient:
    client = MinIOClient.__new__(MinIOClient)
    client.client = Mock()
    return client


def test_list_objects_includes_version_and_user_metadata_when_requested():
    client = _build_client()
    client.client.list_objects.return_value = [
        SimpleNamespace(
            object_name="user-1/doc.txt",
            size=123,
            etag="etag-1",
            last_modified=None,
            is_dir=False,
            version_id="version-1",
            is_delete_marker=False,
            metadata={"storage_scope": "knowledge_base", "knowledge_id": "kid-1"},
        )
    ]

    result = client.list_objects(
        "documents",
        recursive=True,
        include_user_meta=True,
        include_version=True,
    )

    assert result == [
        {
            "object_key": "user-1/doc.txt",
            "size": 123,
            "etag": "etag-1",
            "last_modified": None,
            "is_dir": False,
            "version_id": "version-1",
            "is_delete_marker": False,
            "metadata": {
                "storage_scope": "knowledge_base",
                "knowledge_id": "kid-1",
            },
        }
    ]


def test_delete_file_versions_removes_all_matching_versions():
    client = _build_client()
    client.client.list_objects.return_value = [
        SimpleNamespace(object_name="user-1/doc.txt", version_id="v1"),
        SimpleNamespace(object_name="user-1/other.txt", version_id="skip-me"),
        SimpleNamespace(object_name="user-1/doc.txt", version_id="v2"),
    ]

    deleted = client.delete_file_versions("documents", "user-1/doc.txt")

    assert deleted == 2
    assert client.client.remove_object.call_args_list == [
        call(bucket_name="documents", object_name="user-1/doc.txt", version_id="v1"),
        call(bucket_name="documents", object_name="user-1/doc.txt", version_id="v2"),
    ]
