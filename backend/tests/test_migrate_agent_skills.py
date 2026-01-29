"""
Tests for agent skills migration script.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from scripts.migrate_agent_skills import AgentSkillMigration
from database.models import Skill


@pytest.fixture
def mock_skills():
    """Create mock skills for testing."""
    # Agent skill with inline storage (needs migration)
    skill1 = Mock(spec=Skill)
    skill1.skill_id = "skill-1"
    skill1.name = "Old Agent Skill 1"
    skill1.skill_type = "agent_skill"
    skill1.storage_type = "inline"
    skill1.storage_path = None
    skill1.code = "def test(): pass"
    skill1.skill_md_content = None
    skill1.config = {}
    skill1.manifest = {}
    
    # Agent skill without skill_md_content (needs migration)
    skill2 = Mock(spec=Skill)
    skill2.skill_id = "skill-2"
    skill2.name = "Old Agent Skill 2"
    skill2.skill_type = "agent_skill"
    skill2.storage_type = "database"
    skill2.storage_path = None
    skill2.code = "def test2(): pass"
    skill2.skill_md_content = None
    skill2.config = {}
    skill2.manifest = {}
    
    # Agent skill with minio storage (should not migrate)
    skill3 = Mock(spec=Skill)
    skill3.skill_id = "skill-3"
    skill3.name = "New Agent Skill"
    skill3.skill_type = "agent_skill"
    skill3.storage_type = "minio"
    skill3.storage_path = "skills/test/1.0.0/package.zip"
    skill3.code = None
    skill3.skill_md_content = "# Test Skill"
    skill3.config = {}
    skill3.manifest = {}
    
    return [skill1, skill2, skill3]


class TestAgentSkillMigration:
    """Test agent skill migration."""
    
    def test_init(self):
        """Test migration initialization."""
        migration = AgentSkillMigration(dry_run=True, backup=False)
        
        assert migration.dry_run is True
        assert migration.backup is False
        assert migration.migration_report['dry_run'] is True
        assert migration.migration_report['skills_found'] == 0
        assert migration.migration_report['skills_migrated'] == 0
    
    @patch('scripts.migrate_agent_skills.get_db_session')
    def test_find_inline_agent_skills(self, mock_session, mock_skills):
        """Test finding agent skills with inline storage."""
        # Setup mock session
        mock_query = MagicMock()
        mock_session.return_value.__enter__.return_value.query.return_value = mock_query
        mock_query.filter.return_value.all.return_value = [mock_skills[0], mock_skills[1]]
        
        migration = AgentSkillMigration(dry_run=True)
        skills = migration.find_inline_agent_skills()
        
        assert len(skills) >= 2
    
    def test_create_backup(self, mock_skills, tmp_path):
        """Test backup creation."""
        migration = AgentSkillMigration(dry_run=False, backup=True)
        
        with patch('scripts.migrate_agent_skills.Path') as mock_path:
            mock_path.return_value = tmp_path
            backup_file = migration.create_backup([mock_skills[0]])
            
            assert backup_file is not None
    
    def test_migrate_skill_dry_run(self, mock_skills):
        """Test skill migration in dry run mode."""
        migration = AgentSkillMigration(dry_run=True)
        mock_session = Mock()
        
        skill = mock_skills[0]
        original_type = skill.skill_type
        result = migration.migrate_skill(skill, mock_session)
        
        assert result is True
        assert skill.skill_type == original_type  # Should not change in dry run
        assert len(migration.migration_report['migrated_skills']) == 1
        mock_session.commit.assert_not_called()
    
    def test_migrate_skill_actual(self, mock_skills):
        """Test actual skill migration."""
        migration = AgentSkillMigration(dry_run=False)
        mock_session = Mock()
        
        skill = mock_skills[0]
        result = migration.migrate_skill(skill, mock_session)
        
        assert result is True
        assert skill.skill_type == "langchain_tool"  # Should change
        assert len(migration.migration_report['migrated_skills']) == 1
        mock_session.commit.assert_called_once()
    
    def test_migrate_skill_error(self, mock_skills):
        """Test skill migration error handling."""
        migration = AgentSkillMigration(dry_run=False)
        mock_session = Mock()
        mock_session.commit.side_effect = Exception("Database error")
        
        skill = mock_skills[0]
        result = migration.migrate_skill(skill, mock_session)
        
        assert result is False
        assert len(migration.migration_report['errors']) == 1
        mock_session.rollback.assert_called_once()
    
    @patch('scripts.migrate_agent_skills.get_db_session')
    def test_run_no_skills(self, mock_session):
        """Test migration run with no skills to migrate."""
        # Setup mock to return empty list
        mock_query = MagicMock()
        mock_session.return_value.__enter__.return_value.query.return_value = mock_query
        mock_query.filter.return_value.all.return_value = []
        
        migration = AgentSkillMigration(dry_run=True)
        report = migration.run()
        
        assert report['skills_found'] == 0
        assert report['skills_migrated'] == 0
    
    @patch('scripts.migrate_agent_skills.get_db_session')
    @patch('scripts.migrate_agent_skills.Path')
    def test_run_with_skills(self, mock_path, mock_session, mock_skills, tmp_path):
        """Test migration run with skills."""
        # Setup mock session
        mock_query = MagicMock()
        mock_session.return_value.__enter__.return_value.query.return_value = mock_query
        mock_query.filter.return_value.all.return_value = [mock_skills[0]]
        
        # Setup mock path
        mock_path.return_value = tmp_path
        
        migration = AgentSkillMigration(dry_run=True, backup=False)
        report = migration.run()
        
        assert report['skills_found'] >= 1
        assert report['skills_migrated'] >= 1
    
    def test_migration_report_structure(self):
        """Test migration report has correct structure."""
        migration = AgentSkillMigration(dry_run=True)
        report = migration.migration_report
        
        assert 'timestamp' in report
        assert 'dry_run' in report
        assert 'skills_found' in report
        assert 'skills_migrated' in report
        assert 'skills_skipped' in report
        assert 'errors' in report
        assert 'migrated_skills' in report
        
        assert isinstance(report['errors'], list)
        assert isinstance(report['migrated_skills'], list)


class TestMigrationCLI:
    """Test migration CLI."""
    
    @patch('scripts.migrate_agent_skills.AgentSkillMigration')
    def test_main_dry_run(self, mock_migration_class):
        """Test main function with dry run."""
        from scripts.migrate_agent_skills import main
        
        mock_migration = Mock()
        mock_migration.run.return_value = {'errors': []}
        mock_migration_class.return_value = mock_migration
        
        with patch('sys.argv', ['migrate_agent_skills.py', '--dry-run']):
            result = main()
        
        assert result == 0
        mock_migration_class.assert_called_once_with(dry_run=True, backup=True)
    
    @patch('scripts.migrate_agent_skills.AgentSkillMigration')
    def test_main_no_backup(self, mock_migration_class):
        """Test main function without backup."""
        from scripts.migrate_agent_skills import main
        
        mock_migration = Mock()
        mock_migration.run.return_value = {'errors': []}
        mock_migration_class.return_value = mock_migration
        
        with patch('sys.argv', ['migrate_agent_skills.py', '--no-backup']):
            result = main()
        
        assert result == 0
        mock_migration_class.assert_called_once_with(dry_run=False, backup=False)
    
    @patch('scripts.migrate_agent_skills.AgentSkillMigration')
    def test_main_with_errors(self, mock_migration_class):
        """Test main function with errors."""
        from scripts.migrate_agent_skills import main
        
        mock_migration = Mock()
        mock_migration.run.return_value = {'errors': ['Error 1', 'Error 2']}
        mock_migration_class.return_value = mock_migration
        
        with patch('sys.argv', ['migrate_agent_skills.py']):
            result = main()
        
        assert result == 1
    
    @patch('scripts.migrate_agent_skills.AgentSkillMigration')
    def test_main_exception(self, mock_migration_class):
        """Test main function with exception."""
        from scripts.migrate_agent_skills import main
        
        mock_migration_class.side_effect = Exception("Fatal error")
        
        with patch('sys.argv', ['migrate_agent_skills.py']):
            result = main()
        
        assert result == 1
