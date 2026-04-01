"""Sync curated repository-backed skills into the canonical skill library."""

from __future__ import annotations

import io
import hashlib
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import frontmatter
from sqlalchemy.orm import joinedload

from database.connection import get_db_session
from database.models import Skill
from object_storage.minio_client import get_minio_client
from shared.config import get_config
from skill_library.canonical_service import (
    compute_revision_checksum,
    get_canonical_skill_service,
)
from skill_library.package_handler import PackageHandler
from skill_library.skill_md_parser import SkillMdParser

logger = logging.getLogger(__name__)

DEFAULT_CURATED_SKILL_ROOT = "backend/skill_library/curated_skills"


@dataclass(frozen=True)
class CuratedSkillDefinition:
    slug: str
    display_name: str
    description: str
    version: str
    homepage: Optional[str]
    skill_md_content: str
    manifest: Dict[str, Any]
    config: Dict[str, Any]
    interface_definition: Dict[str, Any]
    package_bytes: bytes
    package_checksum: str
    source_path: str


@dataclass(frozen=True)
class CuratedSyncSummary:
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0


def _resolve_curated_root(curated_root: Optional[str] = None) -> Path:
    raw_root = str(curated_root or DEFAULT_CURATED_SKILL_ROOT).strip() or DEFAULT_CURATED_SKILL_ROOT
    root_path = Path(raw_root).expanduser()
    if root_path.is_absolute():
        return root_path

    repo_root = Path(__file__).resolve().parents[2]
    backend_root = Path(__file__).resolve().parents[1]
    candidates = [repo_root / root_path, backend_root / root_path, Path.cwd() / root_path]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (repo_root / root_path).resolve()


def _iter_curated_skill_dirs(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "SKILL.md").exists())


def _zip_skill_directory(skill_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(path for path in skill_dir.rglob("*") if path.is_file()):
            relative_path = file_path.relative_to(skill_dir)
            archive.writestr(f"{skill_dir.name}/{relative_path.as_posix()}", file_path.read_bytes())
    buffer.seek(0)
    return buffer.read()


def _load_curated_definition(skill_dir: Path) -> CuratedSkillDefinition:
    skill_md_path = skill_dir / "SKILL.md"
    raw_skill_md = skill_md_path.read_text(encoding="utf-8")

    parser = SkillMdParser()
    parsed = parser.parse(raw_skill_md)
    errors = parser.validate(parsed)
    if errors:
        raise ValueError(f"Invalid curated SKILL.md for {skill_dir.name}: {errors}")

    frontmatter_doc = frontmatter.loads(raw_skill_md)
    version = str(frontmatter_doc.get("version") or "1.0.0")
    metadata_payload = frontmatter_doc.get("metadata") or {}
    if not isinstance(metadata_payload, dict):
        metadata_payload = {"raw": metadata_payload}
    metadata_payload.setdefault("curated", True)
    metadata_payload.setdefault("repository_path", str(skill_dir))
    gating_payload = frontmatter_doc.get("gating") or {}
    if not isinstance(gating_payload, dict):
        gating_payload = {"raw": gating_payload}

    package_bytes = _zip_skill_directory(skill_dir)
    package_content_checksum = hashlib.sha256(package_bytes).hexdigest()
    config = {
        "package_content_checksum": package_content_checksum,
        "source_path": str(skill_dir),
        "capability_snapshot_path": "/workspace/.linx_runtime/capabilities.json",
        "supported_outputs": ["pdf"],
        "supported_inputs": [
            ".doc",
            ".docx",
            ".ppt",
            ".pptx",
            ".odt",
            ".html",
            ".htm",
            ".md",
            ".markdown",
            ".txt",
            ".json",
            ".csv",
        ],
    }
    package_checksum = compute_revision_checksum(
        version=version,
        instruction_md=raw_skill_md,
        tool_code=None,
        interface_definition={},
        config=config,
    )
    manifest = {
        "homepage": parsed.metadata.homepage,
        "skill_metadata": metadata_payload,
        "gating_status": gating_payload,
    }

    return CuratedSkillDefinition(
        slug=parsed.metadata.skill_slug,
        display_name=parsed.metadata.display_name,
        description=parsed.metadata.description,
        version=version,
        homepage=parsed.metadata.homepage,
        skill_md_content=raw_skill_md,
        manifest=manifest,
        config=config,
        interface_definition={},
        package_bytes=package_bytes,
        package_checksum=package_checksum,
        source_path=str(skill_dir),
    )


def _build_revision_payload(definition: CuratedSkillDefinition, storage_path: str) -> Dict[str, Any]:
    return {
        "version": definition.version,
        "instruction_md": definition.skill_md_content,
        "tool_code": None,
        "interface_definition": definition.interface_definition,
        "artifact_storage_kind": "minio",
        "artifact_ref": storage_path,
        "manifest": definition.manifest,
        "config": definition.config,
        "review_state": "approved",
        "change_note": "Curated repository sync",
    }


def _needs_revision(skill: Skill, definition: CuratedSkillDefinition) -> bool:
    active_revision = getattr(skill, "active_revision", None)
    if active_revision is None:
        return True
    return str(getattr(active_revision, "checksum", "") or "") != definition.package_checksum


def _sync_top_level_skill_fields(skill: Skill, definition: CuratedSkillDefinition) -> bool:
    changed = False
    desired_values = {
        "display_name": definition.display_name,
        "description": definition.description,
        "source_kind": "curated",
        "artifact_kind": "instruction",
        "runtime_mode": "doc",
        "visibility": "public",
        "lifecycle_state": "active",
        "skill_type": "agent_skill",
        "is_active": True,
        "interface_definition": definition.interface_definition,
        "manifest": definition.manifest,
        "homepage": definition.homepage,
        "skill_metadata": definition.manifest.get("skill_metadata"),
        "gating_status": definition.manifest.get("gating_status"),
        "config": definition.config,
    }
    for field_name, desired_value in desired_values.items():
        current_value = getattr(skill, field_name)
        if current_value != desired_value:
            setattr(skill, field_name, desired_value)
            changed = True
    return changed


async def sync_curated_skills(
    *,
    run_on_startup: Optional[bool] = None,
    fail_soft: Optional[bool] = None,
    curated_root: Optional[str] = None,
) -> CuratedSyncSummary:
    config = get_config()
    configured_run_on_startup = config.get("skill_library.curated_sync.run_on_startup", True)
    configured_fail_soft = config.get("skill_library.curated_sync.fail_soft", True)
    configured_root = config.get("skill_library.curated_sync.curated_root", DEFAULT_CURATED_SKILL_ROOT)

    should_run = configured_run_on_startup if run_on_startup is None else bool(run_on_startup)
    if not should_run:
        logger.info("Curated skill sync skipped by configuration")
        return CuratedSyncSummary()

    effective_fail_soft = configured_fail_soft if fail_soft is None else bool(fail_soft)
    root = _resolve_curated_root(curated_root or configured_root)
    if not root.exists():
        logger.warning("Curated skill root does not exist", extra={"curated_root": str(root)})
        return CuratedSyncSummary()

    canonical_service = get_canonical_skill_service()
    package_handler = PackageHandler(get_minio_client())
    created_count = 0
    updated_count = 0
    skipped_count = 0
    failed_count = 0

    for skill_dir in _iter_curated_skill_dirs(root):
        try:
            definition = _load_curated_definition(skill_dir)

            with get_db_session() as session:
                existing_skill = (
                    session.query(Skill)
                    .options(joinedload(Skill.active_revision))
                    .filter(Skill.skill_slug == definition.slug)
                    .one_or_none()
                )

            if existing_skill is None:
                storage_path = await package_handler.upload_package(
                    definition.package_bytes,
                    definition.slug,
                    definition.version,
                )
                canonical_service.create_skill(
                    slug=definition.slug,
                    display_name=definition.display_name,
                    description=definition.description,
                    source_kind="curated",
                    artifact_kind="instruction",
                    runtime_mode="doc",
                    visibility="public",
                    owner_user_id=None,
                    department_id=None,
                    dependencies=[],
                    revision_payload=_build_revision_payload(definition, storage_path),
                    lifecycle_state="active",
                )
                created_count += 1
                logger.info("Created curated skill", extra={"skill_slug": definition.slug})
                continue

            skill_changed = False
            with get_db_session() as session:
                persisted_skill = (
                    session.query(Skill)
                    .options(joinedload(Skill.active_revision))
                    .filter(Skill.skill_id == existing_skill.skill_id)
                    .one()
                )
                skill_changed = _sync_top_level_skill_fields(persisted_skill, definition)

            if _needs_revision(existing_skill, definition):
                storage_path = await package_handler.upload_package(
                    definition.package_bytes,
                    definition.slug,
                    definition.version,
                )
                revision = canonical_service.create_revision(
                    skill_id=existing_skill.skill_id,
                    owner_user_id=None,
                    revision_payload=_build_revision_payload(definition, storage_path),
                )
                canonical_service.activate_revision(
                    skill_id=existing_skill.skill_id,
                    revision_id=revision.revision_id,
                    actor_user_id=None,
                )
                updated_count += 1
                logger.info("Updated curated skill revision", extra={"skill_slug": definition.slug})
            elif skill_changed:
                updated_count += 1
                logger.info("Updated curated skill metadata", extra={"skill_slug": definition.slug})
            else:
                skipped_count += 1
        except Exception as sync_error:
            failed_count += 1
            logger.error(
                "Failed to sync curated skill",
                extra={
                    "skill_dir": str(skill_dir),
                    "error": str(sync_error),
                },
                exc_info=True,
            )
            if not effective_fail_soft:
                raise

    summary = CuratedSyncSummary(
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
    )
    logger.info(
        "Curated skill sync completed",
        extra={
            "created_count": created_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "curated_root": str(root),
        },
    )
    return summary
