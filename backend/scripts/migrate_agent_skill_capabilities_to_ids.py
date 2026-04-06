#!/usr/bin/env python3
"""Migrate persisted agent platform skill capabilities from skill slugs to skill IDs."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database.connection import get_db_session
from database.models import Agent, Skill
from shared.datetime_utils import utcnow

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _normalize_capability(value: Any) -> str:
    return str(value or "").strip()


def _build_skill_maps(session) -> tuple[Dict[str, str], Dict[str, str]]:
    skills = session.query(Skill).all()
    slug_to_id = {str(skill.skill_slug): str(skill.skill_id) for skill in skills if skill.skill_slug}
    id_to_slug = {str(skill.skill_id): str(skill.skill_slug) for skill in skills}
    return slug_to_id, id_to_slug


def migrate_agent_capabilities(*, dry_run: bool) -> int:
    report: Dict[str, Any] = {
        "timestamp": utcnow().isoformat(),
        "dry_run": dry_run,
        "agents_scanned": 0,
        "agents_updated": 0,
        "mapped_capabilities": 0,
        "already_migrated_capabilities": 0,
        "preserved_internal_capabilities": 0,
        "failed_agents": [],
        "failed_capabilities": [],
    }

    report_dir = Path("migration_reports")
    report_dir.mkdir(exist_ok=True)

    with get_db_session() as session:
        slug_to_id, id_to_slug = _build_skill_maps(session)
        agents = session.query(Agent).all()
        report["agents_scanned"] = len(agents)

        for agent in agents:
            capabilities = agent.capabilities if isinstance(agent.capabilities, list) else []
            if not capabilities:
                continue

            updated_capabilities: List[str] = []
            changed = False
            agent_failures: List[str] = []

            for raw_capability in capabilities:
                capability = _normalize_capability(raw_capability)
                if not capability:
                    continue

                try:
                    normalized_uuid = str(UUID(capability))
                except ValueError:
                    normalized_uuid = ""

                if normalized_uuid:
                    if normalized_uuid in id_to_slug:
                        updated_capabilities.append(normalized_uuid)
                        report["already_migrated_capabilities"] += 1
                        continue

                    agent_failures.append(capability)
                    continue

                mapped_skill_id = slug_to_id.get(capability)
                if mapped_skill_id:
                    updated_capabilities.append(mapped_skill_id)
                    report["mapped_capabilities"] += 1
                    changed = True
                    continue

                if str(agent.agent_type or "") == "execution_temp_worker":
                    updated_capabilities.append(capability)
                    report["preserved_internal_capabilities"] += 1
                    continue

                agent_failures.append(capability)

            if agent_failures:
                report["failed_agents"].append(
                    {
                        "agent_id": str(agent.agent_id),
                        "agent_name": agent.name,
                        "agent_type": agent.agent_type,
                        "unmapped_capabilities": agent_failures,
                    }
                )
                report["failed_capabilities"].extend(
                    {
                        "agent_id": str(agent.agent_id),
                        "agent_name": agent.name,
                        "capability": capability,
                    }
                    for capability in agent_failures
                )
                continue

            if changed and updated_capabilities != capabilities:
                agent.capabilities = updated_capabilities
                report["agents_updated"] += 1

        if report["failed_capabilities"]:
            session.rollback()
        elif dry_run:
            session.rollback()
        else:
            session.commit()

    timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"agent_skill_capabilities_to_ids_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    logger.info("Agents scanned: %s", report["agents_scanned"])
    logger.info("Agents updated: %s", report["agents_updated"])
    logger.info("Mapped capabilities: %s", report["mapped_capabilities"])
    logger.info(
        "Already migrated capabilities: %s", report["already_migrated_capabilities"]
    )
    logger.info(
        "Preserved temp-worker internal capabilities: %s",
        report["preserved_internal_capabilities"],
    )
    logger.info("Report written to %s", report_path)

    if report["failed_capabilities"]:
        logger.error("Migration blocked by unmapped capabilities:")
        for item in report["failed_agents"]:
            logger.error(
                "agent_id=%s agent_name=%s agent_type=%s unmapped=%s",
                item["agent_id"],
                item["agent_name"],
                item["agent_type"],
                ", ".join(item["unmapped_capabilities"]),
            )
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate persisted agent skill capabilities from slug strings to skill IDs."
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without committing")
    args = parser.parse_args()
    return migrate_agent_capabilities(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
