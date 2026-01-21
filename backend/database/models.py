"""SQLAlchemy models for Digital Workforce Platform.

This module defines all database tables according to the design document
section 3.1 (PostgreSQL Schema).
"""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    Numeric,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    """User accounts table.
    
    Stores user authentication and profile information.
    """
    __tablename__ = 'users'
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default='user', index=True)  # for RBAC
    attributes = Column(JSONB, nullable=True)  # for ABAC
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    agents = relationship('Agent', back_populates='owner', cascade='all, delete-orphan')
    tasks = relationship('Task', back_populates='creator', cascade='all, delete-orphan')
    permissions = relationship('Permission', back_populates='user', cascade='all, delete-orphan')
    knowledge_items = relationship('KnowledgeItem', back_populates='owner', cascade='all, delete-orphan')
    resource_quota = relationship('ResourceQuota', back_populates='user', uselist=False, cascade='all, delete-orphan')
    audit_logs = relationship('AuditLog', back_populates='user', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<User(user_id={self.user_id}, username={self.username}, role={self.role})>"


class Agent(Base):
    """Agents table.
    
    Stores agent metadata and configuration.
    """
    __tablename__ = 'agents'
    
    agent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    agent_type = Column(String(100), nullable=False, index=True)  # template type
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    capabilities = Column(JSONB, nullable=False)  # list of skills
    status = Column(String(50), nullable=False, default='idle', index=True)  # active, idle, terminated
    container_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    owner = relationship('User', back_populates='agents')
    tasks = relationship('Task', back_populates='assigned_agent')
    audit_logs = relationship('AuditLog', back_populates='agent')
    
    # Indexes
    __table_args__ = (
        Index('idx_agent_owner_status', 'owner_user_id', 'status'),
        Index('idx_agent_type_status', 'agent_type', 'status'),
    )
    
    def __repr__(self):
        return f"<Agent(agent_id={self.agent_id}, name={self.name}, type={self.agent_type}, status={self.status})>"


class Task(Base):
    """Tasks table.
    
    Stores task information with hierarchical structure support.
    """
    __tablename__ = 'tasks'
    
    task_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_text = Column(Text, nullable=False)
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.task_id', ondelete='CASCADE'), nullable=True, index=True)
    assigned_agent_id = Column(UUID(as_uuid=True), ForeignKey('agents.agent_id', ondelete='SET NULL'), nullable=True, index=True)
    status = Column(String(50), nullable=False, default='pending', index=True)  # pending, in_progress, completed, failed
    priority = Column(Integer, nullable=False, default=0, index=True)
    dependencies = Column(JSONB, nullable=True)  # array of task_ids
    result = Column(JSONB, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    creator = relationship('User', back_populates='tasks')
    assigned_agent = relationship('Agent', back_populates='tasks')
    parent_task = relationship('Task', remote_side=[task_id], backref='subtasks')
    
    # Indexes
    __table_args__ = (
        Index('idx_task_user_status', 'created_by_user_id', 'status'),
        Index('idx_task_agent_status', 'assigned_agent_id', 'status'),
        Index('idx_task_created_at', 'created_at'),
        Index('idx_task_parent', 'parent_task_id'),
    )
    
    def __repr__(self):
        return f"<Task(task_id={self.task_id}, status={self.status}, priority={self.priority})>"


class Skill(Base):
    """Skills table.
    
    Stores skill library definitions and metadata.
    """
    __tablename__ = 'skills'
    
    skill_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    interface_definition = Column(JSONB, nullable=False)
    dependencies = Column(JSONB, nullable=True)
    version = Column(String(50), nullable=False, default='1.0.0')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<Skill(skill_id={self.skill_id}, name={self.name}, version={self.version})>"


class Permission(Base):
    """Permissions table.
    
    Stores access control permissions for users.
    """
    __tablename__ = 'permissions'
    
    permission_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False, index=True)  # knowledge, memory, agent
    resource_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    access_level = Column(String(50), nullable=False)  # read, write, admin
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship('User', back_populates='permissions')
    
    # Indexes
    __table_args__ = (
        Index('idx_permission_user_resource', 'user_id', 'resource_type', 'resource_id'),
    )
    
    def __repr__(self):
        return f"<Permission(permission_id={self.permission_id}, user_id={self.user_id}, resource_type={self.resource_type}, access_level={self.access_level})>"


class KnowledgeItem(Base):
    """Knowledge items table.
    
    Stores metadata for knowledge base documents.
    """
    __tablename__ = 'knowledge_items'
    
    knowledge_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False, index=True)
    content_type = Column(String(100), nullable=False, index=True)  # document, policy, domain_knowledge
    file_reference = Column(String(500), nullable=True)  # MinIO object key
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    access_level = Column(String(50), nullable=False, default='private', index=True)  # private, team, public
    item_metadata = Column(JSONB, nullable=True)  # Renamed from 'metadata' to avoid SQLAlchemy conflict
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    owner = relationship('User', back_populates='knowledge_items')
    
    # Indexes
    __table_args__ = (
        Index('idx_knowledge_owner_access', 'owner_user_id', 'access_level'),
        Index('idx_knowledge_type_access', 'content_type', 'access_level'),
    )
    
    def __repr__(self):
        return f"<KnowledgeItem(knowledge_id={self.knowledge_id}, title={self.title}, content_type={self.content_type})>"


# AgentTemplate model is defined in agent_framework/agent_template.py
# to avoid circular imports and keep agent-specific models with agent code


class ResourceQuota(Base):
    """Resource quotas table.
    
    Stores resource limits and usage for users.
    """
    __tablename__ = 'resource_quotas'
    
    quota_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.user_id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    max_agents = Column(Integer, nullable=False, default=10)
    max_storage_gb = Column(Integer, nullable=False, default=100)
    max_cpu_cores = Column(Integer, nullable=False, default=10)
    max_memory_gb = Column(Integer, nullable=False, default=20)
    current_agents = Column(Integer, nullable=False, default=0)
    current_storage_gb = Column(Numeric(10, 2), nullable=False, default=0.0)
    
    # Relationships
    user = relationship('User', back_populates='resource_quota')
    
    def __repr__(self):
        return f"<ResourceQuota(quota_id={self.quota_id}, user_id={self.user_id}, current_agents={self.current_agents}/{self.max_agents})>"


class AuditLog(Base):
    """Audit logs table.
    
    Stores audit trail of all actions in the system.
    """
    __tablename__ = 'audit_logs'
    
    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey('agents.agent_id', ondelete='SET NULL'), nullable=True, index=True)
    action = Column(String(255), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False, index=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    details = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Relationships
    user = relationship('User', back_populates='audit_logs')
    agent = relationship('Agent', back_populates='audit_logs')
    
    # Indexes
    __table_args__ = (
        Index('idx_audit_user_timestamp', 'user_id', 'timestamp'),
        Index('idx_audit_action_timestamp', 'action', 'timestamp'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
    )
    
    def __repr__(self):
        return f"<AuditLog(log_id={self.log_id}, action={self.action}, resource_type={self.resource_type}, timestamp={self.timestamp})>"


class ABACPolicyModel(Base):
    """ABAC policies table.
    
    Stores ABAC (Attribute-Based Access Control) policies for fine-grained
    permission evaluation.
    """
    __tablename__ = 'abac_policies'
    
    policy_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    effect = Column(String(50), nullable=False, index=True)  # allow, deny
    resource_type = Column(String(100), nullable=False, index=True)
    actions = Column(JSONB, nullable=False)  # array of action strings
    conditions = Column(JSONB, nullable=False)  # condition group structure
    priority = Column(Integer, nullable=False, default=0, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_policy_resource_enabled', 'resource_type', 'enabled'),
        Index('idx_policy_priority', 'priority'),
    )
    
    def __repr__(self):
        return f"<ABACPolicyModel(policy_id={self.policy_id}, name={self.name}, effect={self.effect}, enabled={self.enabled})>"
