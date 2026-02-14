# Mission Execution System - Tasks

## Phase 1: Database Schema & Models
- [x] 1.1 Create `Mission` SQLAlchemy model with all columns and relationships
- [x] 1.2 Create `MissionAttachment` model with file reference storage
- [x] 1.3 Create `MissionAgent` model with role and status tracking
- [x] 1.4 Create `MissionEvent` model with JSONB event_data
- [x] 1.5 Create `MissionSettings` model with per-role JSONB config
- [x] 1.6 Add `mission_id`, `acceptance_criteria`, `task_metadata` columns to `Task` model
- [x] 1.7 Add `mission` relationship to Task model
- [x] 1.8 Create Alembic migration `m1a2b3c4d5e6` for mission tables + task extensions
- [x] 1.9 Create Alembic migration `n2b3c4d5e6f7` for mission_settings table
- [x] 1.10 Register mission models in `database/__init__.py`

## Phase 2: Mission Repository (CRUD)
- [x] 2.1 Implement `create_mission()` with expunge pattern
- [x] 2.2 Implement `get_mission()` with eager-loading (attachments, agents)
- [x] 2.3 Implement `update_mission_status()` with timestamp management
- [x] 2.4 Implement `update_mission_fields()` for arbitrary column updates
- [x] 2.5 Implement `list_missions()` with user/status filters and pagination
- [x] 2.6 Implement `count_missions()` for pagination metadata
- [x] 2.7 Implement `add_attachment()`, `list_attachments()` helpers
- [x] 2.8 Implement `assign_agent()`, `update_agent_status()`, `list_mission_agents()` helpers
- [x] 2.9 Implement `list_events()` with event_type filter
- [x] 2.10 Implement `get_mission_settings()` with defaults fallback
- [x] 2.11 Implement `upsert_mission_settings()` with partial update support

## Phase 3: Mission Orchestrator
- [x] 3.1 Implement singleton `MissionOrchestrator` with `_active_missions` tracking
- [x] 3.2 Implement `start_mission()` — launch as background asyncio.Task
- [x] 3.3 Implement `cancel_mission()` — cancel task, update status, cleanup
- [x] 3.4 Implement `_run_mission()` — sequential phase execution with error handling
- [x] 3.5 Implement `_phase_requirements()` — leader analysis + clarification loop
- [x] 3.6 Implement `_phase_planning()` — task decomposition + JSON parsing + DB persistence
- [x] 3.7 Implement `_phase_execution()` — topological sort + concurrent execution with semaphore
- [x] 3.8 Implement `_execute_task_with_retry()` — exponential backoff retry
- [x] 3.9 Implement `_phase_review()` — supervisor review with PASS/FAIL + retry cycle
- [x] 3.10 Implement `_phase_qa()` — QA audit with verdict + retry cycle
- [x] 3.11 Implement `_phase_complete()` — collect deliverables + finalize
- [x] 3.12 Implement `_transition()` — validate status transitions
- [x] 3.13 Implement `_topological_sort()` — Kahn's algorithm with cycle-breaking fallback
- [x] 3.14 Implement `_extract_json_array()` — extract JSON from LLM output
- [x] 3.15 Implement `_get_llm_config()` — extract per-role LLM config from mission_config
- [x] 3.16 Implement `provide_clarification()` — user clarification input

## Phase 4: Supporting Services
- [x] 4.1 Implement `MissionEventEmitter` — persist events + WebSocket broadcast
- [x] 4.2 Implement `MissionWorkspaceManager` — Docker container lifecycle
- [x] 4.3 Implement `create_workspace()` — create container + init directories
- [x] 4.4 Implement `setup_attachments()` — download from MinIO + copy into container
- [x] 4.5 Implement `exec_as_agent()` — execute commands in shared container
- [x] 4.6 Implement `write_file()` / `read_file()` — workspace file I/O
- [x] 4.7 Implement `list_files()` — directory listing
- [x] 4.8 Implement `collect_deliverables()` — gather output + upload to MinIO
- [x] 4.9 Implement `cleanup_workspace()` — stop and remove container
- [x] 4.10 Implement `AgentFactory.create_mission_agent()` — create BaseAgent with LLM
- [x] 4.11 Implement agent role configs (Leader, Supervisor, QA system prompts)
- [x] 4.12 Implement mission exceptions (MissionError, MissionCancelledException, WorkspaceError, AgentExecutionError, MissionTimeoutError)

## Phase 5: REST API
- [x] 5.1 Create `missions.py` router with Pydantic schemas
- [x] 5.2 Implement POST `/missions` — create mission with settings merge
- [x] 5.3 Implement GET `/missions` — list with filters and pagination
- [x] 5.4 Implement GET/PUT `/missions/settings` — user settings CRUD
- [x] 5.5 Implement GET `/missions/{id}` — get mission details
- [x] 5.6 Implement PUT `/missions/{id}` — update draft mission
- [x] 5.7 Implement DELETE `/missions/{id}` — delete/cancel mission
- [x] 5.8 Implement POST `/missions/{id}/start` — start execution
- [x] 5.9 Implement POST `/missions/{id}/cancel` — cancel execution
- [x] 5.10 Implement POST `/missions/{id}/clarify` — clarification response
- [x] 5.11 Implement attachment CRUD endpoints (POST, GET, DELETE)
- [x] 5.12 Implement query endpoints (agents, tasks, events, deliverables, workspace files)
- [x] 5.13 Register router in `main.py` and `routers/__init__.py`

## Phase 6: WebSocket Integration
- [x] 6.1 Add `mission_subscriptions` dict to websocket.py
- [x] 6.2 Implement `/ws/missions/{mission_id}` WebSocket endpoint with heartbeat
- [x] 6.3 Implement `broadcast_mission_event()` for real-time event push
- [x] 6.4 Handle subscription lifecycle (connect, disconnect, cleanup)

## Phase 7: Frontend - Types & API
- [x] 7.1 Define TypeScript types: Mission, MissionAgent, MissionAttachment, MissionEvent, MissionDeliverable, MissionTask, MissionRoleConfig, MissionExecutionConfig, MissionSettings
- [x] 7.2 Define MissionStatus and MissionAgentRole union types
- [x] 7.3 Implement `missionsApi` with all endpoint methods (getAll, getById, create, update, delete, start, cancel, clarify, attachments, agents, tasks, events, deliverables, workspace, settings)
- [x] 7.4 Add request/response interfaces (CreateMissionRequest, UpdateMissionRequest, ClarifyRequest, WorkspaceFile, MissionListResponse)

## Phase 8: Frontend - State Management
- [x] 8.1 Create `missionStore` (Zustand) with full state interface
- [x] 8.2 Implement CRUD actions (fetchMissions, fetchMission, createMission, deleteMission)
- [x] 8.3 Implement lifecycle actions (startMission, cancelMission, clarify)
- [x] 8.4 Implement sub-resource loading (fetchMissionTasks, fetchMissionAgents, fetchMissionEvents, fetchMissionAttachments)
- [x] 8.5 Implement attachment actions (uploadAttachment, removeAttachment)
- [x] 8.6 Implement settings actions (fetchMissionSettings, updateMissionSettings)
- [x] 8.7 Implement WebSocket handlers (handleMissionEvent, handleMissionStatusUpdate, handleTaskStatusUpdate)
- [x] 8.8 Implement filters (setStatusFilter, setSearchQuery, getFilteredMissions)
- [x] 8.9 Export store in `stores/index.ts`

## Phase 9: Frontend - Pages & Components
- [x] 9.1 Create `Missions.tsx` page with list view and detail view
- [x] 9.2 Implement MissionCard component with status colors, dots, and progress bar
- [x] 9.3 Implement search and status filter controls
- [x] 9.4 Create `MissionCreateWizard` — 4-step modal wizard
- [x] 9.5 Implement instructions step with title + instructions inputs
- [x] 9.6 Implement attachments step with drag-and-drop file upload
- [x] 9.7 Implement configuration step with execution params + advanced role config
- [x] 9.8 Implement review step with summary of all inputs
- [x] 9.9 Create `MissionSettingsPanel` — per-role LLM config + execution defaults
- [x] 9.10 Implement provider/model dropdown loading from `llmApi.getAvailableProviders()`
- [x] 9.11 Create `MissionFlowCanvas` — React Flow lifecycle visualization
- [x] 9.12 Create flow node components (MissionNode, AgentNode, TaskNode, RequirementsNode, SupervisorNode, QANode, ClarificationNode)
- [x] 9.13 Create `MissionControls` — toolbar for mission actions
- [x] 9.14 Create `ClarificationPanel` — side panel for user clarification
- [x] 9.15 Create `DeliverablesPanel` — side panel for deliverable listing

## Phase 10: App Integration
- [x] 10.1 Update `App.tsx` — replace Tasks page with Missions page
- [x] 10.2 Update `Sidebar.tsx` — add Missions navigation item
- [x] 10.3 Add i18n translations for missions (en.json, zh.json)
- [x] 10.4 Add `reactflow` and `@reactflow/core` to package.json dependencies

## Phase 11: Testing
- [ ] 11.1 Unit tests for MissionRepository (CRUD, settings, counts)
- [ ] 11.2 Unit tests for MissionOrchestrator (transitions, lifecycle, clarification)
- [ ] 11.3 Unit tests for MissionWorkspaceManager (container lifecycle)
- [ ] 11.4 Unit tests for AgentFactory (LLM creation, provider protocols)
- [ ] 11.5 Integration tests for missions API endpoints
- [ ] 11.6 Frontend component tests for MissionCreateWizard
- [ ] 11.7 Frontend store tests for missionStore

## Phase 12: Documentation
- [ ] 12.1 API documentation for all mission endpoints
- [ ] 12.2 Architecture documentation for mission lifecycle
