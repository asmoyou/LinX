# Department Management - Tasks

## Phase 1: Database Model & Migration (Backend)

### Task 1.1: Department Model
- [x] 1.1.1: Create `Department` model class in `backend/database/models.py` with all fields (department_id, name, code, description, parent_id, manager_id, status, sort_order, timestamps)
- [x] 1.1.2: Add `department_id` foreign key and `department` relationship to `User` model
- [x] 1.1.3: Add `department_id` foreign key and `department` relationship to `Agent` model
- [x] 1.1.4: Add `department_id` foreign key and `department` relationship to `KnowledgeItem` model
- [x] 1.1.5: Add database indexes (idx_department_parent_status, idx_user_department, idx_agent_department, idx_knowledge_department)

### Task 1.2: Alembic Migrations
- [x] 1.2.1: Create migration - `departments` table with all columns, indexes, and constraints
- [x] 1.2.2: Create migration - Add `department_id` column to `users`, `agents`, `knowledge_items` tables
- [x] 1.2.3: Create data migration script - Extract unique department strings from `User.attributes`, create Department records, and update foreign keys

## Phase 2: Department CRUD API (Backend)

### Task 2.1: Department Router
- [x] 2.1.1: Create Pydantic schemas (DepartmentCreate, DepartmentUpdate, DepartmentResponse, DepartmentStats)
- [x] 2.1.2: Implement `POST /api/departments` - Create department (admin only, validate unique code)
- [x] 2.1.3: Implement `GET /api/departments` - List departments (support flat and tree mode via `?view=tree|flat`, search, pagination)
- [x] 2.1.4: Implement `GET /api/departments/{id}` - Department detail with member/agent/knowledge counts
- [x] 2.1.5: Implement `PUT /api/departments/{id}` - Update department (admin only, code is immutable)
- [x] 2.1.6: Implement `DELETE /api/departments/{id}` - Delete department (admin only, must be empty)
- [x] 2.1.7: Register departments router in `backend/api_gateway/main.py`

### Task 2.2: Department Resource APIs
- [x] 2.2.1: Implement `GET /api/departments/{id}/members` - List department members (manager/admin)
- [x] 2.2.2: Implement `GET /api/departments/{id}/agents` - List department agents (manager/admin)
- [x] 2.2.3: Implement `GET /api/departments/{id}/stats` - Department statistics (manager/admin)

### Task 2.3: Existing API Adaptations
- [x] 2.3.1: Add `department_id` to user registration/creation API request and response
- [ ] 2.3.2: Add `department_id` to agent creation/update API request and response
- [x] 2.3.3: Add `department_id` to knowledge upload API request and response
- [ ] 2.3.4: Add `department_id` query parameter to `GET /api/agents` for filtering
- [x] 2.3.5: Add `department_id` query parameter to `GET /api/knowledge` for filtering

## Phase 3: Access Control Adaptation (Backend)

### Task 3.1: ABAC Adaptation
- [x] 3.1.1: Create `build_user_attributes()` helper that merges `User.attributes` with `user.department.code` from FK relationship
- [x] 3.1.2: Update ABAC context builder in `abac.py` to use the new helper
- [x] 3.1.3: Verify existing ABAC policies continue to work with derived `user.department` attribute

### Task 3.2: Knowledge Filter Adaptation
- [x] 3.2.1: Update `can_access_knowledge_item()` in `knowledge_filter.py` to use `department_id` FK comparison instead of `attributes.department` string comparison
- [x] 3.2.2: Update `build_milvus_filter_expr()` to include `department_id` in filter expressions for team-level knowledge
- [x] 3.2.3: Add `filter_knowledge_query()` helper for SQLAlchemy department-based filtering

### Task 3.3: Permission Middleware
- [x] 3.3.1: Implement department-level permission check decorator/dependency (admin for CRUD, manager for own dept resources)
- [ ] 3.3.2: Implement agent list filtering by department + access_level
- [x] 3.3.3: Implement knowledge list filtering by department + access_level

## Phase 4: Frontend Infrastructure

### Task 4.1: Types and API Client
- [x] 4.1.1: Create `frontend/src/types/department.ts` with Department, DepartmentStats, CreateDepartmentRequest, UpdateDepartmentRequest interfaces
- [x] 4.1.2: Create `frontend/src/api/departments.ts` with API functions (list, getById, create, update, delete, getMembers, getAgents, getStats)
- [x] 4.1.3: Create `frontend/src/stores/departmentStore.ts` with Zustand store (departments list, selected department, loading states, CRUD actions)

### Task 4.2: Reusable Components
- [x] 4.2.1: Create `frontend/src/components/departments/DepartmentSelect.tsx` - Reusable dropdown selector for departments (used in user/agent/knowledge forms)
- [x] 4.2.2: Add i18n translations for department-related strings (zh-CN and en)

## Phase 5: Frontend - Department Management Page

### Task 5.1: Page and Routing
- [x] 5.1.1: Create `frontend/src/pages/Departments.tsx` - Department management page with list and detail views
- [x] 5.1.2: Add `/departments` route to router configuration
- [x] 5.1.3: Add "Department Management" (部门管理) menu item to `Sidebar.tsx` with Building2 icon (visible to admin/manager)

### Task 5.2: Department Components
- [x] 5.2.1: Implement `DepartmentList.tsx` - Table view with columns: name, code, manager, members, agents, status, actions (integrated in Departments.tsx)
- [x] 5.2.2: Implement `DepartmentForm.tsx` - Create/edit dialog with fields: name, code (create only), description, parent department selector, manager selector, sort order (integrated in Departments.tsx)
- [x] 5.2.3: Implement `DepartmentDetail.tsx` - Side panel showing department info, member list, agent list, stats (integrated in Departments.tsx)
- [x] 5.2.4: Implement `DepartmentStats.tsx` - Statistics cards (member count, agent count, knowledge count) (integrated in DepartmentDetail)

## Phase 6: Frontend - Existing Page Integration

### Task 6.1: User Management Integration
- [x] 6.1.1: Add department display to user profile section (ProfileSection.tsx, read-only)
- [x] 6.1.2: Show department column/badge in user list

### Task 6.2: Agent Management Integration
- [x] 6.2.1: Add DepartmentSelect to AddAgentModal.tsx and AgentConfigModal.tsx
- [x] 6.2.2: Add department filter to agent list page (Workforce.tsx)
- [ ] 6.2.3: Show department info in AgentDetailsModal.tsx

### Task 6.3: Knowledge Base Integration
- [x] 6.3.1: Add DepartmentSelect to knowledge upload flow (UploadDocumentForm.tsx)
- [x] 6.3.2: Add department filter to knowledge list page (SearchBar.tsx)

## Phase 7: Testing

### Task 7.1: Backend Unit Tests
- [x] 7.1.1: Test Department schema validation (DepartmentCreate, DepartmentUpdate)
- [x] 7.1.2: Test _department_to_response helper function
- [x] 7.1.3: Test _build_tree helper for hierarchical department views
- [x] 7.1.4: Test DepartmentResponse model construction
- [x] 7.1.5: Test knowledge_filter team-level access with department_id matching
- [ ] 7.1.6: Test data migration script (attributes.department -> department_id FK)
- [ ] 7.1.7: Test department-level permission checks (admin CRUD, manager own dept)

### Task 7.2: Frontend Tests
- [x] 7.2.1: Test departmentStore initial state
- [x] 7.2.2: Test departmentStore fetchDepartments (success and error)
- [x] 7.2.3: Test departmentStore CRUD actions (create, update, delete)
- [x] 7.2.4: Test departmentStore reset
- [ ] 7.2.5: Test DepartmentSelect component rendering

## Phase 8: Documentation & Cleanup

### Task 8.1: Documentation
- [ ] 8.1.1: Create API documentation in `docs/api/departments.md`
- [x] 8.1.2: Update CLAUDE.md architecture section to include Department model and relationships

### Task 8.2: Cleanup
- [x] 8.2.1: Verify TypeScript compilation passes for all department-related files
- [x] 8.2.2: Run frontend tests and backend tests
- [x] 8.2.3: Update this tasks.md to mark all completed tasks
