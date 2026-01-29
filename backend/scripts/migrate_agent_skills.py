#!/usr/bin/env python3
"""
Migration script for agent skills redesign.

This script migrates existing agent_skill entries that use inline storage
to langchain_tool type, since agent_skill now requires SKILL.md package format.

Usage:
    python scripts/migrate_agent_skills.py [--dry-run] [--backup]
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database.connection import get_db_session
from database.models import Skill
from shared.config import get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentSkillMigration:
    """Handle migration of agent_skill entries."""
    
    def __init__(self, dry_run: bool = False, backup: bool = True):
        """Initialize migration.
        
        Args:
            dry_run: If True, only show what would be migrated
            backup: If True, create backup before migration
        """
        self.dry_run = dry_run
        self.backup = backup
        self.migration_report = {
            'timestamp': datetime.utcnow().isoformat(),
            'dry_run': dry_run,
            'skills_found': 0,
            'skills_migrated': 0,
            'skills_skipped': 0,
            'errors': [],
            'migrated_skills': []
        }
    
    def find_inline_agent_skills(self) -> List[Skill]:
        """Find agent_skill entries with inline storage.
        
        Returns:
            List of skills that need migration
        """
        logger.info("Searching for agent_skill entries with inline storage...")
        
        with get_db_session() as session:
            # Find agent_skill with inline storage (not minio)
            skills = session.query(Skill).filter(
                Skill.skill_type == 'agent_skill',
                Skill.storage_type != 'minio'
            ).all()
            
            # Also find agent_skill without skill_md_content (if column exists)
            try:
                skills_without_md = session.query(Skill).filter(
                    Skill.skill_type == 'agent_skill',
                    Skill.skill_md_content.is_(None)
                ).all()
            except AttributeError:
                # Column doesn't exist yet, skip this check
                logger.warning("skill_md_content column not found, skipping check")
                skills_without_md = []
            
            # Combine and deduplicate
            all_skills = {skill.skill_id: skill for skill in skills + skills_without_md}
            
            logger.info(f"Found {len(all_skills)} agent_skill entries that need migration")
            return list(all_skills.values())
    
    def create_backup(self, skills: List[Skill]) -> str:
        """Create backup of skills before migration.
        
        Args:
            skills: Skills to backup
            
        Returns:
            Path to backup file
        """
        backup_dir = Path('backups')
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f'agent_skills_backup_{timestamp}.json'
        
        backup_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'count': len(skills),
            'skills': [
                {
                    'skill_id': skill.skill_id,
                    'name': skill.name,
                    'skill_type': skill.skill_type,
                    'storage_type': skill.storage_type,
                    'storage_path': skill.storage_path,
                    'code': skill.code,
                    'config': skill.config,
                    'manifest': skill.manifest,
                }
                for skill in skills
            ]
        }
        
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        logger.info(f"Backup created: {backup_file}")
        return str(backup_file)
    
    def migrate_skill(self, skill: Skill, session) -> bool:
        """Migrate a single skill from agent_skill to langchain_tool.
        
        Args:
            skill: Skill to migrate
            session: Database session
            
        Returns:
            True if migration successful
        """
        try:
            old_type = skill.skill_type
            old_storage = skill.storage_type
            
            # Log migration
            migration_info = {
                'skill_id': skill.skill_id,
                'name': skill.name,
                'old_type': old_type,
                'new_type': 'langchain_tool',
                'old_storage': old_storage,
                'storage_path': skill.storage_path,
                'has_code': skill.code is not None,
            }
            
            self.migration_report['migrated_skills'].append(migration_info)
            
            if not self.dry_run:
                # Update skill type to langchain_tool
                skill.skill_type = 'langchain_tool'
                session.commit()
                logger.info(f"✓ Migrated: {skill.name} (ID: {skill.skill_id})")
            else:
                logger.info(f"[DRY RUN] Would migrate: {skill.name} (ID: {skill.skill_id})")
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to migrate {skill.name}: {str(e)}"
            logger.error(error_msg)
            self.migration_report['errors'].append(error_msg)
            if not self.dry_run:
                session.rollback()
            return False
    
    def run(self) -> Dict[str, Any]:
        """Run the migration.
        
        Returns:
            Migration report
        """
        logger.info("=" * 60)
        logger.info("Agent Skills Migration")
        logger.info("=" * 60)
        
        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        
        # Find skills to migrate
        skills = self.find_inline_agent_skills()
        self.migration_report['skills_found'] = len(skills)
        
        if not skills:
            logger.info("No skills need migration")
            return self.migration_report
        
        # Create backup if requested
        if self.backup and not self.dry_run:
            backup_file = self.create_backup(skills)
            self.migration_report['backup_file'] = backup_file
        
        # Migrate each skill
        logger.info(f"\nMigrating {len(skills)} skills...")
        
        with get_db_session() as session:
            for skill in skills:
                if self.migrate_skill(skill, session):
                    self.migration_report['skills_migrated'] += 1
                else:
                    self.migration_report['skills_skipped'] += 1
        
        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("Migration Summary")
        logger.info("=" * 60)
        logger.info(f"Skills found:    {self.migration_report['skills_found']}")
        logger.info(f"Skills migrated: {self.migration_report['skills_migrated']}")
        logger.info(f"Skills skipped:  {self.migration_report['skills_skipped']}")
        logger.info(f"Errors:          {len(self.migration_report['errors'])}")
        
        if self.migration_report['errors']:
            logger.error("\nErrors encountered:")
            for error in self.migration_report['errors']:
                logger.error(f"  - {error}")
        
        # Save report
        report_dir = Path('migration_reports')
        report_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        report_file = report_dir / f'agent_skills_migration_{timestamp}.json'
        
        with open(report_file, 'w') as f:
            json.dump(self.migration_report, f, indent=2)
        
        logger.info(f"\nMigration report saved: {report_file}")
        
        return self.migration_report


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate agent_skill entries to langchain_tool'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without making changes'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup before migration'
    )
    
    args = parser.parse_args()
    
    migration = AgentSkillMigration(
        dry_run=args.dry_run,
        backup=not args.no_backup
    )
    
    try:
        report = migration.run()
        
        # Exit with error code if there were errors
        if report['errors']:
            return 1
        
        return 0
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
