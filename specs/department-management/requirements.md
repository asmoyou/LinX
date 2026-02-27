# Department Management - Requirements

## 1. Overview

LinX 平台需要完整的部门（Department）管理功能，用于组织架构的数字化映射。部门是用户、Agent、知识库等资源的组织归属单元，也是数据权限隔离的核心维度。

### Current State

- User 模型通过 `attributes` JSONB 字段存储 `department` 字符串（无外键关系）
- ABAC 系统支持 `user.department == resource.department` 策略评估
- `knowledge_filter.py` 基于 `attributes.department` 字符串匹配实现 team 级别访问控制
- Agent 模型有 `access_level` (private/team/public) 但无部门关联
- 系统没有独立的 Department 数据模型、管理 API 和前端管理页面

### Target State

- 独立的 Department 数据模型（支持树形层级）
- User、Agent、KnowledgeItem 通过外键关联到 Department
- 完整的部门 CRUD API
- 前端部门管理页面
- 基于部门的数据权限过滤

## 2. User Stories

### US-1: Department CRUD Management

**As a** system administrator
**I want** to create, edit, view, and delete departments
**So that** I can establish the company's organizational structure

**Acceptance Criteria**:
- AC-1.1: Admin can create a department with name, code, description, and manager
- AC-1.2: Admin can edit department information (name, description, manager, status)
- AC-1.3: Admin can view all departments as a list with search and pagination
- AC-1.4: Admin can delete an empty department (no associated users/agents/knowledge items)
- AC-1.5: Department code is globally unique and immutable after creation
- AC-1.6: Department supports tree hierarchy via `parent_id` (initially used flat)
- AC-1.7: Department has `status` field (active/archived); archived departments are hidden from selectors

### US-2: User Department Assignment

**As a** system administrator
**I want** to assign a department when creating or editing a user
**So that** data access can be controlled based on department

**Acceptance Criteria**:
- AC-2.1: Department can be selected when creating a user
- AC-2.2: Department can be changed when editing a user
- AC-2.3: User list shows department information
- AC-2.4: Each user belongs to exactly one department (nullable - can be unassigned)
- AC-2.5: Migration from `User.attributes.department` (string) to `User.department_id` (foreign key)

### US-3: Agent Department Assignment

**As a** manager or administrator
**I want** to assign a department when creating an agent
**So that** I can control agent visibility and access permissions

**Acceptance Criteria**:
- AC-3.1: Department can be selected when creating an agent
- AC-3.2: Agent list supports department filter
- AC-3.3: Agents with `access_level=team` are only visible to users in the same department
- AC-3.4: Department managers can manage all agents in their department

### US-4: Knowledge Base Department Assignment

**As a** manager or administrator
**I want** knowledge documents to have department ownership
**So that** department-level knowledge isolation is achieved

**Acceptance Criteria**:
- AC-4.1: Department can be specified when uploading knowledge documents
- AC-4.2: Documents with `access_level=team` are only accessible to users in the same department
- AC-4.3: Department managers can manage all knowledge documents in their department
- AC-4.4: Vector search results respect department permission filtering

### US-5: Department Dashboard

**As a** department manager
**I want** to view my department's resource overview
**So that** I can understand department resource utilization

**Acceptance Criteria**:
- AC-5.1: Department detail page shows member count, agent count, knowledge document count
- AC-5.2: Department managers can only see statistics for their own department
- AC-5.3: System administrators can see statistics for all departments

## 3. Non-Functional Requirements

### NFR-1: Performance
- Department list query < 200ms
- Permission refresh after department change < 500ms

### NFR-2: Data Migration
- Migration from existing `User.attributes.department` string to foreign key relationship
- System remains available during migration

### NFR-3: Backward Compatibility
- ABAC system continues to support `user.department` attribute (derived from foreign key relationship)
- Existing `knowledge_filter.py` department matching logic adapts to new model
- Existing ABAC policies using `user.department` continue to work

### NFR-4: Security
- Only admin users can create/edit/delete departments
- Department managers can view department members and resources
- Regular users can only see departments in selectors (for reference)
