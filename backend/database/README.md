# Database Module

This module provides database management for the Digital Workforce Platform, including:
- PostgreSQL schema definitions using SQLAlchemy ORM
- Database connection pooling
- Alembic migrations
- Migration runner for application startup

## Components

### Models (`models.py`)

Defines all database tables according to the design document:

- **users**: User accounts with authentication and RBAC/ABAC support
- **agents**: Agent metadata and configuration
- **tasks**: Hierarchical task structure with dependencies
- **skills**: Skill library definitions
- **permissions**: Access control permissions
- **knowledge_items**: Knowledge base document metadata
- **agent_templates**: Pre-configured agent templates
- **resource_quotas**: User resource limits and usage tracking
- **audit_logs**: Comprehensive audit trail

### Connection Pool (`connection.py`)

Provides database connection pooling with:
- Configurable pool size and overflow
- Automatic connection recycling
- Health checks
- Session management
- Graceful shutdown

**Usage:**

```python
from database import get_db_session, User

# Using context manager (recommended)
with get_db_session() as session:
    users = session.query(User).all()
    # Session automatically commits and closes

# Or get the connection pool directly
from database import get_connection_pool

pool = get_connection_pool()
with pool.get_session() as session:
    user = session.query(User).filter_by(username='admin').first()
```

### Migrations (`migrations.py`)

Provides database migration management using Alembic:
- Check current schema version
- Run migrations to upgrade/downgrade
- Migration history
- Automatic migration on startup

**Usage:**

```python
from database import run_migrations_on_startup

# Run migrations on application startup
if run_migrations_on_startup(auto_upgrade=True):
    print("Database is ready")
else:
    print("Migration failed")

# Or use the migration runner directly
from database import get_migration_runner

runner = get_migration_runner()
current = runner.get_current_version()
head = runner.get_head_version()

if not runner.is_up_to_date():
    runner.upgrade()
```

## Database Schema

The database schema follows the design document (Section 3.1) with the following tables:

### users
- `user_id` (UUID, PK)
- `username` (VARCHAR, UNIQUE)
- `email` (VARCHAR, UNIQUE)
- `password_hash` (VARCHAR)
- `role` (VARCHAR) - for RBAC
- `attributes` (JSONB) - for ABAC
- `created_at`, `updated_at` (TIMESTAMP)

### agents
- `agent_id` (UUID, PK)
- `name` (VARCHAR)
- `agent_type` (VARCHAR)
- `owner_user_id` (UUID, FK → users)
- `capabilities` (JSONB)
- `status` (VARCHAR) - active, idle, terminated
- `container_id` (VARCHAR)
- `created_at`, `updated_at` (TIMESTAMP)

### tasks
- `task_id` (UUID, PK)
- `goal_text` (TEXT)
- `parent_task_id` (UUID, FK → tasks)
- `assigned_agent_id` (UUID, FK → agents)
- `status` (VARCHAR) - pending, in_progress, completed, failed
- `priority` (INTEGER)
- `dependencies` (JSONB)
- `result` (JSONB)
- `created_by_user_id` (UUID, FK → users)
- `created_at`, `completed_at` (TIMESTAMP)

### skills
- `skill_id` (UUID, PK)
- `name` (VARCHAR, UNIQUE)
- `description` (TEXT)
- `interface_definition` (JSONB)
- `dependencies` (JSONB)
- `version` (VARCHAR)
- `created_at` (TIMESTAMP)

### permissions
- `permission_id` (UUID, PK)
- `user_id` (UUID, FK → users)
- `resource_type` (VARCHAR)
- `resource_id` (UUID)
- `access_level` (VARCHAR) - read, write, admin
- `created_at` (TIMESTAMP)

### knowledge_items
- `knowledge_id` (UUID, PK)
- `title` (VARCHAR)
- `content_type` (VARCHAR)
- `file_reference` (VARCHAR) - MinIO object key
- `owner_user_id` (UUID, FK → users)
- `access_level` (VARCHAR) - private, team, public
- `item_metadata` (JSONB)
- `created_at`, `updated_at` (TIMESTAMP)

### agent_templates
- `template_id` (UUID, PK)
- `name` (VARCHAR, UNIQUE)
- `description` (TEXT)
- `default_skills` (JSONB)
- `default_config` (JSONB)
- `version` (INTEGER)
- `created_at` (TIMESTAMP)

### resource_quotas
- `quota_id` (UUID, PK)
- `user_id` (UUID, FK → users, UNIQUE)
- `max_agents`, `max_storage_gb`, `max_cpu_cores`, `max_memory_gb` (INTEGER)
- `current_agents` (INTEGER)
- `current_storage_gb` (NUMERIC)

### audit_logs
- `log_id` (UUID, PK)
- `user_id` (UUID, FK → users)
- `agent_id` (UUID, FK → agents)
- `action` (VARCHAR)
- `resource_type` (VARCHAR)
- `resource_id` (UUID)
- `details` (JSONB)
- `timestamp` (TIMESTAMP)

## Indexes

The schema includes comprehensive indexes for optimal query performance:

- **users**: username, email, role
- **agents**: owner_user_id, agent_type, status, (owner_user_id, status), (agent_type, status)
- **tasks**: created_by_user_id, assigned_agent_id, status, priority, parent_task_id, created_at, (user, status), (agent, status)
- **skills**: name
- **permissions**: user_id, resource_type, resource_id, (user_id, resource_type, resource_id)
- **knowledge_items**: title, content_type, owner_user_id, access_level, (owner, access), (type, access)
- **agent_templates**: name
- **resource_quotas**: user_id
- **audit_logs**: user_id, agent_id, action, resource_type, resource_id, timestamp, (user, timestamp), (action, timestamp), (resource_type, resource_id)

## Migrations

### Creating a New Migration

```bash
# Auto-generate migration from model changes
cd backend
python -m alembic revision --autogenerate -m "Description of changes"

# Create empty migration for manual changes
python -m alembic revision -m "Description of changes"
```

### Running Migrations

```bash
# Upgrade to latest version
python -m alembic upgrade head

# Upgrade to specific version
python -m alembic upgrade <revision>

# Downgrade one version
python -m alembic downgrade -1

# Downgrade to specific version
python -m alembic downgrade <revision>

# Show current version
python -m alembic current

# Show migration history
python -m alembic history
```

### Migration Files

Migration files are stored in `backend/alembic/versions/`. Each migration has:
- `upgrade()`: Function to apply the migration
- `downgrade()`: Function to revert the migration

## Configuration

Database configuration is loaded from `config.yaml`:

```yaml
database:
  postgres:
    host: "localhost"
    port: 5432
    database: "digital_workforce"
    username: "dwp_user"
    password: "dwp_password_change_me"
    pool_size: 20
    max_overflow: 10
    pool_timeout: 30
    pool_recycle: 3600
    echo: false
    echo_pool: false
```

## Testing

Run the test script to verify database connectivity and migrations:

```bash
cd backend
python database/test_connection.py
```

This will test:
1. Database connection and connection pool
2. Migration status and history
3. Session creation and queries

## References

- **Requirements 3.3**: Primary Database for Operational Data
- **Design Section 3.1**: Database Design (PostgreSQL Schema)
- **Design Section 10.3**: Resource Management (Connection Pooling)
- **Tasks 1.2**: Database Setup - PostgreSQL
