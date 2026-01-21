"""Runbooks for common operations.

References:
- All requirements
- Design Section 10: Scalability and Performance
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class RunbookCategory(Enum):
    """Runbook categories."""
    
    DEPLOYMENT = "deployment"
    MAINTENANCE = "maintenance"
    TROUBLESHOOTING = "troubleshooting"
    SCALING = "scaling"
    BACKUP_RESTORE = "backup_restore"
    SECURITY = "security"


@dataclass
class RunbookStep:
    """Runbook step."""
    
    step_number: int
    title: str
    description: str
    command: Optional[str] = None
    expected_output: Optional[str] = None
    troubleshooting: Optional[str] = None


@dataclass
class Runbook:
    """Runbook definition."""
    
    runbook_id: str
    title: str
    category: RunbookCategory
    description: str
    prerequisites: List[str]
    steps: List[RunbookStep]
    estimated_time_minutes: int
    required_permissions: List[str]


class RunbookManager:
    """Runbook manager.
    
    Manages operational runbooks:
    - Deployment procedures
    - Maintenance tasks
    - Troubleshooting guides
    - Scaling operations
    """
    
    def __init__(self):
        """Initialize runbook manager."""
        self.runbooks: Dict[str, Runbook] = {}
        
        # Initialize default runbooks
        self._initialize_runbooks()
        
        logger.info("RunbookManager initialized")
    
    def _initialize_runbooks(self):
        """Initialize default runbooks."""
        # Deployment runbook
        self.runbooks["deploy-production"] = Runbook(
            runbook_id="deploy-production",
            title="Deploy to Production",
            category=RunbookCategory.DEPLOYMENT,
            description="Deploy application to production environment",
            prerequisites=[
                "All tests passing",
                "Code review approved",
                "Staging deployment successful",
                "Backup completed",
            ],
            steps=[
                RunbookStep(
                    step_number=1,
                    title="Create backup",
                    description="Create full database backup before deployment",
                    command="python -m production.backup_restore create --type full",
                    expected_output="Backup completed successfully",
                ),
                RunbookStep(
                    step_number=2,
                    title="Enable maintenance mode",
                    description="Put application in maintenance mode",
                    command="python -m production.maintenance_mode enable",
                    expected_output="Maintenance mode enabled",
                ),
                RunbookStep(
                    step_number=3,
                    title="Pull latest code",
                    description="Pull latest code from main branch",
                    command="git pull origin main",
                    expected_output="Already up to date",
                ),
                RunbookStep(
                    step_number=4,
                    title="Run database migrations",
                    description="Apply database schema changes",
                    command="cd backend && alembic upgrade head",
                    expected_output="Running upgrade",
                ),
                RunbookStep(
                    step_number=5,
                    title="Restart services",
                    description="Restart all application services",
                    command="docker-compose restart api task-manager",
                    expected_output="Services restarted",
                ),
                RunbookStep(
                    step_number=6,
                    title="Verify health",
                    description="Check service health endpoints",
                    command="curl http://localhost:8000/health",
                    expected_output='{"status": "healthy"}',
                ),
                RunbookStep(
                    step_number=7,
                    title="Disable maintenance mode",
                    description="Resume normal operations",
                    command="python -m production.maintenance_mode disable",
                    expected_output="Maintenance mode disabled",
                ),
                RunbookStep(
                    step_number=8,
                    title="Monitor logs",
                    description="Monitor application logs for errors",
                    command="docker-compose logs -f --tail=100",
                    expected_output="No errors",
                ),
            ],
            estimated_time_minutes=30,
            required_permissions=["admin", "deploy"],
        )
        
        # Database maintenance runbook
        self.runbooks["db-maintenance"] = Runbook(
            runbook_id="db-maintenance",
            title="Database Maintenance",
            category=RunbookCategory.MAINTENANCE,
            description="Perform routine database maintenance",
            prerequisites=["Low traffic period", "Backup completed"],
            steps=[
                RunbookStep(
                    step_number=1,
                    title="Analyze tables",
                    description="Update table statistics",
                    command="psql -c 'ANALYZE;'",
                    expected_output="ANALYZE",
                ),
                RunbookStep(
                    step_number=2,
                    title="Vacuum database",
                    description="Reclaim storage and update statistics",
                    command="psql -c 'VACUUM ANALYZE;'",
                    expected_output="VACUUM",
                ),
                RunbookStep(
                    step_number=3,
                    title="Reindex tables",
                    description="Rebuild indexes for performance",
                    command="psql -c 'REINDEX DATABASE linx;'",
                    expected_output="REINDEX",
                ),
                RunbookStep(
                    step_number=4,
                    title="Check for bloat",
                    description="Identify bloated tables",
                    command="psql -f scripts/check_bloat.sql",
                    expected_output="Bloat report",
                ),
            ],
            estimated_time_minutes=60,
            required_permissions=["admin", "dba"],
        )
        
        # Troubleshooting runbook
        self.runbooks["troubleshoot-high-cpu"] = Runbook(
            runbook_id="troubleshoot-high-cpu",
            title="Troubleshoot High CPU Usage",
            category=RunbookCategory.TROUBLESHOOTING,
            description="Diagnose and resolve high CPU usage",
            prerequisites=["Monitoring access", "SSH access"],
            steps=[
                RunbookStep(
                    step_number=1,
                    title="Check CPU usage",
                    description="Identify processes using high CPU",
                    command="top -b -n 1 | head -20",
                    expected_output="Process list",
                ),
                RunbookStep(
                    step_number=2,
                    title="Check container stats",
                    description="Check Docker container resource usage",
                    command="docker stats --no-stream",
                    expected_output="Container stats",
                ),
                RunbookStep(
                    step_number=3,
                    title="Check application logs",
                    description="Look for errors or warnings",
                    command="docker-compose logs --tail=100 | grep -i error",
                    expected_output="Error logs",
                ),
                RunbookStep(
                    step_number=4,
                    title="Check slow queries",
                    description="Identify slow database queries",
                    command="psql -c 'SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;'",
                    expected_output="Slow queries",
                    troubleshooting="If slow queries found, optimize or add indexes",
                ),
                RunbookStep(
                    step_number=5,
                    title="Scale resources",
                    description="Add more resources if needed",
                    command="docker-compose up -d --scale api=3",
                    expected_output="Scaled to 3 instances",
                ),
            ],
            estimated_time_minutes=20,
            required_permissions=["admin", "devops"],
        )
        
        # Scaling runbook
        self.runbooks["scale-up"] = Runbook(
            runbook_id="scale-up",
            title="Scale Up Application",
            category=RunbookCategory.SCALING,
            description="Increase application capacity",
            prerequisites=["Monitoring shows high load", "Resources available"],
            steps=[
                RunbookStep(
                    step_number=1,
                    title="Check current capacity",
                    description="Review current resource usage",
                    command="docker stats --no-stream",
                    expected_output="Current stats",
                ),
                RunbookStep(
                    step_number=2,
                    title="Scale API Gateway",
                    description="Increase API Gateway instances",
                    command="docker-compose up -d --scale api=5",
                    expected_output="Scaled to 5 instances",
                ),
                RunbookStep(
                    step_number=3,
                    title="Scale Task Manager",
                    description="Increase Task Manager instances",
                    command="docker-compose up -d --scale task-manager=3",
                    expected_output="Scaled to 3 instances",
                ),
                RunbookStep(
                    step_number=4,
                    title="Verify load balancing",
                    description="Check that load is distributed",
                    command="curl http://localhost:8000/health",
                    expected_output="All instances healthy",
                ),
                RunbookStep(
                    step_number=5,
                    title="Monitor performance",
                    description="Monitor metrics after scaling",
                    command="open http://localhost:3000/d/system-metrics",
                    expected_output="Metrics dashboard",
                ),
            ],
            estimated_time_minutes=15,
            required_permissions=["admin", "devops"],
        )
        
        # Backup and restore runbook
        self.runbooks["restore-backup"] = Runbook(
            runbook_id="restore-backup",
            title="Restore from Backup",
            category=RunbookCategory.BACKUP_RESTORE,
            description="Restore database from backup",
            prerequisites=["Backup file available", "Maintenance mode enabled"],
            steps=[
                RunbookStep(
                    step_number=1,
                    title="List available backups",
                    description="Find the backup to restore",
                    command="python -m production.backup_restore list",
                    expected_output="Backup list",
                ),
                RunbookStep(
                    step_number=2,
                    title="Verify backup",
                    description="Verify backup integrity",
                    command="python -m production.backup_restore verify --backup-id <backup_id>",
                    expected_output="Backup verified",
                ),
                RunbookStep(
                    step_number=3,
                    title="Stop services",
                    description="Stop all services accessing database",
                    command="docker-compose stop api task-manager",
                    expected_output="Services stopped",
                ),
                RunbookStep(
                    step_number=4,
                    title="Restore database",
                    description="Restore from backup file",
                    command="python -m production.backup_restore restore --backup-id <backup_id>",
                    expected_output="Restore completed",
                ),
                RunbookStep(
                    step_number=5,
                    title="Verify data",
                    description="Check that data is restored correctly",
                    command="psql -c 'SELECT COUNT(*) FROM users;'",
                    expected_output="Row count",
                ),
                RunbookStep(
                    step_number=6,
                    title="Start services",
                    description="Restart all services",
                    command="docker-compose start api task-manager",
                    expected_output="Services started",
                ),
            ],
            estimated_time_minutes=45,
            required_permissions=["admin", "dba"],
        )
    
    def get_runbook(self, runbook_id: str) -> Optional[Runbook]:
        """Get runbook by ID.
        
        Args:
            runbook_id: Runbook ID
            
        Returns:
            Runbook or None
        """
        return self.runbooks.get(runbook_id)
    
    def list_runbooks(
        self,
        category: Optional[RunbookCategory] = None,
    ) -> List[Runbook]:
        """List available runbooks.
        
        Args:
            category: Filter by category
            
        Returns:
            List of runbooks
        """
        runbooks = list(self.runbooks.values())
        
        if category:
            runbooks = [r for r in runbooks if r.category == category]
        
        return runbooks
    
    def add_runbook(self, runbook: Runbook):
        """Add custom runbook.
        
        Args:
            runbook: Runbook to add
        """
        self.runbooks[runbook.runbook_id] = runbook
        logger.info(f"Added runbook: {runbook.runbook_id}")
    
    def execute_runbook(self, runbook_id: str) -> Dict[str, Any]:
        """Execute runbook (returns execution plan).
        
        Args:
            runbook_id: Runbook ID
            
        Returns:
            Execution plan
        """
        runbook = self.get_runbook(runbook_id)
        if not runbook:
            raise ValueError(f"Runbook not found: {runbook_id}")
        
        logger.info(f"Executing runbook: {runbook_id}")
        
        return {
            "runbook_id": runbook_id,
            "title": runbook.title,
            "steps": [
                {
                    "step_number": step.step_number,
                    "title": step.title,
                    "command": step.command,
                }
                for step in runbook.steps
            ],
            "estimated_time_minutes": runbook.estimated_time_minutes,
        }
