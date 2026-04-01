import io
import zipfile
from uuid import uuid4

import pytest

from agent_framework.skill_manager import AgentSkillReference, SkillInfo, SkillManager


@pytest.mark.asyncio
async def test_load_skill_package_files_includes_shell_scripts(monkeypatch):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_ref:
        zip_ref.writestr("document-artifact-rendering/SKILL.md", "# Skill\n")
        zip_ref.writestr(
            "document-artifact-rendering/scripts/render_document.sh",
            "#!/bin/sh\necho render\n",
        )
        zip_ref.writestr(
            "document-artifact-rendering/scripts/verify_artifact.py",
            "print('verify')\n",
        )

    payload = zip_buffer.getvalue()

    class _FakeMinioClient:
        buckets = {"artifacts": "agent-artifacts"}

        def download_file(self, bucket_name: str, object_key: str):
            return io.BytesIO(payload), {}

    import object_storage.minio_client as minio_client_module

    monkeypatch.setattr(minio_client_module, "get_minio_client", lambda: _FakeMinioClient())

    manager = SkillManager(agent_id=uuid4(), user_id=uuid4())
    skill_info = SkillInfo(
        skill_id=uuid4(),
        skill_slug="document-artifact-rendering-installed-d4d838b4",
        display_name="Document Artifact Rendering",
        description="Render documents to PDF",
        skill_type="agent_skill",
        storage_type="minio",
        storage_path="system/document-artifact-rendering-1.0.0.zip",
    )

    package_files = await manager._load_skill_package_files(skill_info)

    assert "document-artifact-rendering/SKILL.md" in package_files
    assert "document-artifact-rendering/scripts/render_document.sh" in package_files
    assert "document-artifact-rendering/scripts/verify_artifact.py" in package_files


def test_agent_skill_reference_formats_prompt_with_input_output_hints() -> None:
    skill_ref = AgentSkillReference(
        skill_id=uuid4(),
        skill_slug="document-artifact-rendering-installed-d4d838b4",
        display_name="Document Artifact Rendering",
        description="Render and verify document artifacts.",
        skill_md_content="# Skill",
        has_scripts=True,
        config={
            "supported_inputs": [".md", ".markdown", ".html", ".docx"],
            "supported_outputs": ["pdf"],
            "when_to_use": "converting workspace markdown or office docs into PDFs",
        },
    )

    prompt_line = skill_ref.format_for_prompt()

    assert "document-artifact-rendering-installed-d4d838b4" in prompt_line
    assert "inputs: .md, .markdown, .html, .docx" in prompt_line
    assert "outputs: pdf" in prompt_line
    assert "converting workspace markdown or office docs into PDFs" in prompt_line
