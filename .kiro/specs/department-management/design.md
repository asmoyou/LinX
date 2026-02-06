# Department Management - Technical Design

## 1. Overview

This document details the technical design for implementing department management in the LinX platform. The design introduces a first-class `Department` entity, foreign key relationships from User/Agent/KnowledgeItem, and adapts the existing ABAC and knowledge filtering systems.

## 2. Architecture

### 2.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Department Management                      │
│                                                               │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────┐   │
│  │  Department  │   │   User       │   │  Agent         │   │
│  │  Model       │◀──│  .dept_id    │   │  .dept_id      │   │
│  │  (CRUD)      │◀──│              │   │                │   │
│  └─────────────┘   └──────────────┘   └────────────────┘   │
│        ▲                                                     │
│        │           ┌──────────────┐   ┌────────────────┐   │
│        └───────────│ Knowledge    │   │  ABAC          │   │
│                    │ .dept_id     │   │  (adapted)     │   │
│                    └──────────────┘   └────────────────┘   │
│                                              │               │
│                                       ┌──────────────┐      │
│                                       │  Knowledge   │      │
│                                       │  Filter      │      │
│                                       │  (adapted)   │      │
│                                       └──────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Component Responsibilities

**Department Model**: Core data model with tree hierarchy support via self-referencing `parent_id`.

**Department Router**: REST API for CRUD operations, member/agent/stats queries.

**ABAC Adapter**: Derives `user.department` attribute from the new foreign key relationship instead of `User.attributes` JSONB.

**Knowledge Filter Adapter**: Uses `department_id` foreign key for team-level access matching instead of string comparison.

**Frontend Department Module**: Management page, reusable selector component, store and API client.

## 3. Data Model

### 3.1 Department Model (New)

Location: `backend/database/models.py`

```python
class Department(Base):
    """Departments table.

    Stores organizational department structure with tree hierarchy support.
    """

    __tablename__ = "departments"

    department_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.department_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    manager_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(20), nullable=False, default="active", index=True)  # active, archived
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    parent = relationship("Department", remote_side=[department_id], backref="children")
    manager = relationship("User", foreign_keys=[manager_id])
    members = relationship("User", back_populates="department", foreign_keys="User.department_id")
    agents = relationship("Agent", back_populates="department")
    knowledge_items = relationship("KnowledgeItem", back_populates="department")

    # Indexes
    __table_args__ = (
        Index("idx_department_parent_status", "parent_id", "status"),
    )

    def __repr__(self):
        return f"<Department(department_id={self.department_id}, name={self.name}, code={self.code})>"
```

### 3.2 User Model Changes

Add to `User` model in `backend/database/models.py`:

```python
# New field
department_id = Column(
    UUID(as_uuid=True),
    ForeignKey("departments.department_id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)

# New relationship
department = relationship("Department", back_populates="members", foreign_keys=[department_id])
```

### 3.3 Agent Model Changes

Add to `Agent` model in `backend/database/models.py`:

```python
# New field
department_id = Column(
    UUID(as_uuid=True),
    ForeignKey("departments.department_id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)

# New relationship
department = relationship("Department", back_populates="agents")
```

### 3.4 KnowledgeItem Model Changes

Add to `KnowledgeItem` model in `backend/database/models.py`:

```python
# New field
department_id = Column(
    UUID(as_uuid=True),
    ForeignKey("departments.department_id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)

# New relationship
department = relationship("Department", back_populates="knowledge_items")
```

## 4. API Design

### 4.1 Department CRUD API

New router: `backend/api_gateway/routers/departments.py`

| Method | Path | Description | Permission |
|--------|------|-------------|------------|
| POST | /api/departments | Create department | admin |
| GET | /api/departments | List departments (tree/flat) | authenticated |
| GET | /api/departments/{id} | Department detail with stats | authenticated |
| PUT | /api/departments/{id} | Update department | admin |
| DELETE | /api/departments/{id} | Delete department (must be empty) | admin |
| GET | /api/departments/{id}/members | Department member list | manager/admin |
| GET | /api/departments/{id}/agents | Department agent list | manager/admin |
| GET | /api/departments/{id}/stats | Department statistics | manager/admin |

### 4.2 Pydantic Schemas

Location: `backend/api_gateway/routers/departments.py`

```python
class DepartmentCreate(BaseModel):
    """Create department request."""
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    sort_order: int = 0

class DepartmentUpdate(BaseModel):
    """Update department request."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    status: Optional[str] = Field(None, pattern=r"^(active|archived)$")
    sort_order: Optional[int] = None

class DepartmentResponse(BaseModel):
    """Department response model."""
    department_id: UUID
    name: str
    code: str
    description: Optional[str]
    parent_id: Optional[UUID]
    manager_id: Optional[UUID]
    manager_name: Optional[str] = None
    status: str
    sort_order: int
    member_count: int = 0
    agent_count: int = 0
    knowledge_count: int = 0
    children: List["DepartmentResponse"] = []
    created_at: datetime
    updated_at: datetime

class DepartmentStats(BaseModel):
    """Department statistics."""
    member_count: int
    agent_count: int
    knowledge_count: int
    active_task_count: int
```

### 4.3 Existing API Adaptations

**User API** (`backend/api_gateway/routers/users.py`):
- `RegisterRequest` / user creation: add optional `department_id` field
- `GET /users/me` response: include `department_id` and `department_name`

**Agent API** (`backend/api_gateway/routers/agents.py`):
- `CreateAgentRequest`: add optional `department_id` field
- `GET /agents` list: add `department_id` query parameter for filtering
- Agent response: include `department_id` and `department_name`

**Knowledge API** (`backend/api_gateway/routers/knowledge.py`):
- Upload knowledge: add optional `department_id` field
- `GET /knowledge` list: add `department_id` query parameter
- Knowledge response: include `department_id` and `department_name`

## 5. Access Control Integration

### 5.1 ABAC Adaptation

In `backend/access_control/abac.py`, the ABAC context builder must derive `user.department` from the new relationship:

```python
# Before (from JSONB attributes):
# user_attributes = user.attributes  # {"department": "engineering", ...}

# After (from foreign key + attributes merge):
def build_user_attributes(user: User) -> Dict[str, Any]:
    """Build user attributes for ABAC evaluation."""
    attrs = dict(user.attributes or {})
    # Override department from FK relationship
    if user.department:
        attrs["department"] = user.department.code
    return attrs
```

This ensures existing ABAC policies like `Condition("user.department", ConditionOperator.EQUALS, "engineering")` continue to work.

### 5.2 Knowledge Filter Adaptation

In `backend/access_control/knowledge_filter.py`:

**`can_access_knowledge_item()`**: Change team matching from string comparison to `department_id` comparison:

```python
elif access_level == KnowledgeAccessLevel.TEAM:
    # Before: string match on attributes.department
    # After: foreign key match on department_id
    user_dept_id = getattr(current_user, 'department_id', None)
    resource_dept_id = resource_attributes.get("department_id")

    if user_dept_id and resource_dept_id and str(user_dept_id) == str(resource_dept_id):
        if check_permission(role, ResourceType.KNOWLEDGE, action, "permitted"):
            return True
```

**`filter_knowledge_query()`**: Add `department_id` condition for team filtering:

```python
if user_dept_id:
    conditions.append(
        and_(
            KnowledgeItem.access_level == KnowledgeAccessLevel.TEAM,
            KnowledgeItem.department_id == user_dept_id,
        )
    )
```

**`build_milvus_filter_expr()`**: Add `department_id` filter for vector search:

```python
if user_dept_id:
    conditions.append(
        f'(access_level == "{KnowledgeAccessLevel.TEAM}" and department_id == "{user_dept_id}")'
    )
```

### 5.3 Permission Matrix

| Operation | admin | manager (own dept) | user (own dept) | user (other dept) |
|-----------|-------|--------------------|-----------------|-------------------|
| View department list | All | All | All | All |
| Create/Edit/Delete department | YES | NO | NO | NO |
| View department members | All | Own dept | Own dept | NO |
| View department agents | All | Own dept | Own dept (team+public) | public only |
| Manage department agents | All | Own dept | Own only | NO |
| View department knowledge | All | Own dept | Own dept (team+public) | public only |

## 6. Frontend Design

### 6.1 New Files

```
frontend/src/
├── types/department.ts              # TypeScript type definitions
├── api/departments.ts               # Department API client
├── stores/departmentStore.ts        # Zustand state management
├── pages/Departments.tsx            # Department management page
└── components/departments/          # Department components
    ├── DepartmentList.tsx           # Table + tree view
    ├── DepartmentForm.tsx           # Create/edit dialog
    ├── DepartmentDetail.tsx         # Detail panel with stats
    └── DepartmentSelect.tsx         # Reusable selector (dropdown)
```

### 6.2 TypeScript Types

Location: `frontend/src/types/department.ts`

```typescript
export interface Department {
  id: string;
  name: string;
  code: string;
  description?: string;
  parentId?: string;
  managerId?: string;
  managerName?: string;
  status: 'active' | 'archived';
  sortOrder: number;
  memberCount: number;
  agentCount: number;
  knowledgeCount: number;
  children: Department[];
  createdAt: string;
  updatedAt: string;
}

export interface DepartmentStats {
  memberCount: number;
  agentCount: number;
  knowledgeCount: number;
  activeTaskCount: number;
}

export interface CreateDepartmentRequest {
  name: string;
  code: string;
  description?: string;
  parentId?: string;
  managerId?: string;
}

export interface UpdateDepartmentRequest {
  name?: string;
  description?: string;
  parentId?: string;
  managerId?: string;
  status?: 'active' | 'archived';
  sortOrder?: number;
}
```

### 6.3 Navigation Integration

Add to `Sidebar.tsx` nav items (after Settings):

```typescript
import { Building2 } from 'lucide-react';

// In navItems array, add before Settings:
{ path: '/departments', icon: Building2, label: t('nav.departments') },
```

Only visible to admin/manager roles.

### 6.4 Route Registration

Add to router configuration:

```typescript
{ path: '/departments', element: <Departments /> }
```

### 6.5 Existing Page Modifications

**AddAgentModal.tsx**: Add `DepartmentSelect` component for department selection
**Knowledge upload**: Add `DepartmentSelect` for department assignment
**User management** (if exists): Add `DepartmentSelect` for department assignment
**Agent list / Knowledge list**: Add department filter dropdown

## 7. Database Migration Strategy

### 7.1 Migration 1: Create departments table

```python
def upgrade():
    op.create_table(
        "departments",
        sa.Column("department_id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.UUID(), sa.ForeignKey("departments.department_id", ondelete="SET NULL"), nullable=True),
        sa.Column("manager_id", sa.UUID(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_department_code", "departments", ["code"])
    op.create_index("idx_department_name", "departments", ["name"])
    op.create_index("idx_department_parent_status", "departments", ["parent_id", "status"])
```

### 7.2 Migration 2: Add department_id to User, Agent, KnowledgeItem

```python
def upgrade():
    op.add_column("users", sa.Column("department_id", sa.UUID(), sa.ForeignKey("departments.department_id", ondelete="SET NULL"), nullable=True))
    op.add_column("agents", sa.Column("department_id", sa.UUID(), sa.ForeignKey("departments.department_id", ondelete="SET NULL"), nullable=True))
    op.add_column("knowledge_items", sa.Column("department_id", sa.UUID(), sa.ForeignKey("departments.department_id", ondelete="SET NULL"), nullable=True))
    op.create_index("idx_user_department", "users", ["department_id"])
    op.create_index("idx_agent_department", "agents", ["department_id"])
    op.create_index("idx_knowledge_department", "knowledge_items", ["department_id"])
```

### 7.3 Migration 3: Data migration from attributes.department

```python
def upgrade():
    """Migrate department strings from User.attributes to Department FK."""
    conn = op.get_bind()

    # 1. Find all unique department values in User.attributes
    result = conn.execute(sa.text(
        "SELECT DISTINCT attributes->>'department' AS dept "
        "FROM users WHERE attributes->>'department' IS NOT NULL"
    ))
    departments = [row.dept for row in result if row.dept]

    # 2. Create Department records for each unique value
    for dept in departments:
        dept_id = str(uuid.uuid4())
        conn.execute(sa.text(
            "INSERT INTO departments (department_id, name, code, status) "
            "VALUES (:id, :name, :code, 'active')"
        ), {"id": dept_id, "name": dept, "code": dept.lower().replace(" ", "_")})

        # 3. Update User.department_id
        conn.execute(sa.text(
            "UPDATE users SET department_id = :dept_id "
            "WHERE attributes->>'department' = :dept_name"
        ), {"dept_id": dept_id, "dept_name": dept})
```

## 8. Internationalization

Add translations for department-related UI strings:

```json
// zh-CN
{
  "nav.departments": "部门管理",
  "departments.title": "部门管理",
  "departments.create": "创建部门",
  "departments.edit": "编辑部门",
  "departments.delete": "删除部门",
  "departments.name": "部门名称",
  "departments.code": "部门编码",
  "departments.description": "部门描述",
  "departments.manager": "部门负责人",
  "departments.status": "状态",
  "departments.members": "成员",
  "departments.agents": "智能体",
  "departments.knowledge": "知识库",
  "departments.active": "活跃",
  "departments.archived": "已归档",
  "departments.empty_delete_only": "只能删除没有关联资源的部门",
  "departments.select": "选择部门"
}
```

```json
// en
{
  "nav.departments": "Departments",
  "departments.title": "Department Management",
  "departments.create": "Create Department",
  "departments.edit": "Edit Department",
  "departments.delete": "Delete Department",
  "departments.name": "Department Name",
  "departments.code": "Department Code",
  "departments.description": "Description",
  "departments.manager": "Manager",
  "departments.status": "Status",
  "departments.members": "Members",
  "departments.agents": "Agents",
  "departments.knowledge": "Knowledge",
  "departments.active": "Active",
  "departments.archived": "Archived",
  "departments.empty_delete_only": "Can only delete departments with no associated resources",
  "departments.select": "Select Department"
}
```
