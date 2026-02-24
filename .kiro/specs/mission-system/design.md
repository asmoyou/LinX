# Mission Execution System - Design

## Related Specs

- Runtime unification and profile strategy: `../agent-test-chat-runtime-strategy/`

## Architecture Overview

The Mission Execution System follows a layered architecture:

```
┌──────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│  Missions Page → MissionCreateWizard → MissionFlowCanvas         │
│  MissionSettingsPanel → ClarificationPanel → DeliverablesPanel   │
│  missionStore (Zustand) ← WebSocket ← missionsApi (Axios)       │
├──────────────────────────────────────────────────────────────────┤
│                     API Gateway (FastAPI)                         │
│  /api/v1/missions/* → missions.py router (CRUD + Actions)        │
│  /ws/missions/{id} → websocket.py (real-time event streaming)    │
├──────────────────────────────────────────────────────────────────┤
│                    Mission System (Backend)                       │
│  MissionOrchestrator ── async state machine lifecycle             │
│  MissionRepository ──── CRUD for all mission models              │
│  MissionEventEmitter ── persist events + WebSocket broadcast     │
│  MissionWorkspaceManager ─ Docker container management           │
│  AgentFactory ────────── create BaseAgent with LLM config        │
│  AgentRoles ─────────── system prompts for Leader/Supervisor/QA  │
├──────────────────────────────────────────────────────────────────┤
│                       Database Layer                             │
│  missions │ mission_attachments │ mission_agents │ mission_events │
│  mission_settings │ tasks (+ mission_id FK)                      │
└──────────────────────────────────────────────────────────────────┘
```

## Database Schema

### missions
| Column | Type | Description |
|--------|------|-------------|
| mission_id | UUID PK | Primary key |
| title | VARCHAR(500) | Mission title |
| instructions | TEXT | User-provided goal description |
| requirements_doc | TEXT | Generated requirements document |
| status | VARCHAR(50) | Lifecycle status (draft/requirements/planning/executing/reviewing/qa/completed/failed/cancelled) |
| created_by_user_id | UUID FK→users | Owner |
| department_id | UUID FK→departments | Optional department scope |
| container_id | VARCHAR(255) | Docker container ID |
| workspace_bucket | VARCHAR(255) | MinIO bucket reference |
| mission_config | JSONB | Merged role + execution config |
| result | JSONB | Final deliverables metadata |
| error_message | TEXT | Error details on failure |
| total_tasks / completed_tasks / failed_tasks | INTEGER | Progress counters |
| created_at / started_at / completed_at / updated_at | TIMESTAMPTZ | Timestamps |

**Indexes:** title, status, created_by_user_id, department_id, (user_id, status), created_at

### mission_attachments
| Column | Type | Description |
|--------|------|-------------|
| attachment_id | UUID PK | Primary key |
| mission_id | UUID FK→missions (CASCADE) | Parent mission |
| filename | VARCHAR(500) | Original filename |
| file_reference | VARCHAR(500) | MinIO bucket/key path |
| content_type | VARCHAR(100) | MIME type |
| file_size | BIGINT | File size in bytes |
| uploaded_at | TIMESTAMPTZ | Upload timestamp |

### mission_agents
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Primary key |
| mission_id | UUID FK→missions (CASCADE) | Parent mission |
| agent_id | UUID FK→agents (CASCADE) | Assigned agent |
| role | VARCHAR(50) | leader / worker / reviewer |
| status | VARCHAR(50) | assigned / active / completed |
| is_temporary | BOOLEAN | Whether agent was created for this mission |
| assigned_at | TIMESTAMPTZ | Assignment timestamp |

**Unique constraint:** (mission_id, agent_id)

### mission_events
| Column | Type | Description |
|--------|------|-------------|
| event_id | UUID PK | Primary key |
| mission_id | UUID FK→missions (CASCADE) | Parent mission |
| event_type | VARCHAR(100) | Structured event name |
| agent_id | UUID FK→agents (SET NULL) | Related agent |
| task_id | UUID FK→tasks (SET NULL) | Related task |
| event_data | JSONB | Arbitrary payload |
| message | TEXT | Human-readable description |
| created_at | TIMESTAMPTZ | Event timestamp |

**Indexes:** mission_id, event_type, agent_id, task_id, created_at, (mission_id, event_type), (mission_id, created_at)

### mission_settings
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Primary key |
| user_id | UUID FK→users (CASCADE, UNIQUE) | One per user |
| leader_config | JSONB | LLM config for leader role |
| supervisor_config | JSONB | LLM config for supervisor role |
| qa_config | JSONB | LLM config for QA role |
| execution_config | JSONB | Execution parameters |
| updated_at | TIMESTAMPTZ | Last update |

### tasks (extended columns)
| Column | Type | Description |
|--------|------|-------------|
| mission_id | UUID FK→missions (SET NULL) | Optional parent mission |
| acceptance_criteria | TEXT | Testable completion criteria |
| task_metadata | JSONB | Title, dependencies, review feedback |

## Mission Lifecycle State Machine

```
                ┌─────────┐
                │  DRAFT  │
                └────┬────┘
                     │ start_mission()
                ┌────▼────┐
           ┌────│REQUIREM.│────┐
           │    └────┬────┘    │ CLARIFICATION loop
           │         │         │
           │    ┌────▼────┐    │
           │    │PLANNING │    │
           │    └────┬────┘    │
           │         │         │
           │    ┌────▼────┐    │
           ├────│EXECUTING│◄───┤ Review retry
           │    └────┬────┘    │
           │         │         │
           │    ┌────▼────┐    │
           ├────│REVIEWING│────┤
           │    └────┬────┘    │
           │         │         │
           │    ┌────▼────┐    │
           ├────│   QA    │────┘ QA retry → back to REVIEWING
           │    └────┬────┘
           │         │
           │    ┌────▼────┐
           │    │COMPLETED│
           │    └─────────┘
           │
      ┌────▼────┐  ┌──────────┐
      │ FAILED  │  │CANCELLED │ (from any active state)
      └─────────┘  └──────────┘
```

### Valid Transitions
| Source | Targets |
|--------|---------|
| draft | requirements, cancelled |
| requirements | planning, failed, cancelled |
| planning | executing, failed, cancelled |
| executing | reviewing, failed, cancelled |
| reviewing | executing (retry), qa, failed, cancelled |
| qa | reviewing (retry), completed, failed, cancelled |
| completed | (terminal) |
| failed | (terminal) |
| cancelled | (terminal) |

## Key Components

### MissionOrchestrator (Singleton)
- Manages running missions as `asyncio.Task` instances in `_active_missions` dict
- Sequential phase execution: requirements → planning → execution → review → QA → complete
- Clarification loop: blocks on `asyncio.Event`, resumes when user responds
- Error handling: CancelledError → cancelled, MissionCancelledException → cancelled, Exception → failed

### MissionWorkspaceManager (Singleton)
- Creates Docker containers via `ContainerManager` with structured workspace layout
- Downloads attachments from MinIO into container `/workspace/input/`
- Provides `exec_as_agent()` for running commands inside the shared container
- Collects deliverables from `/workspace/output/` and uploads to MinIO
- Cleanup: stops and removes container on mission completion/cancellation

### AgentFactory
- Creates `BaseAgent` instances with LLM from database provider config
- Supports `openai_compatible` and `ollama` protocols
- Resolves model context window from provider metadata or capability detector

### Agent Roles
- **Leader**: Analyses instructions, gathers requirements, decomposes into tasks, coordinates execution
- **Supervisor**: Reviews completed task outputs against acceptance criteria (PASS/FAIL)
- **QA Auditor**: Final quality and security audit of all deliverables (PASS/FAIL verdict)

### MissionEventEmitter (Singleton)
- Persists events to `mission_events` table
- Broadcasts events via WebSocket (`broadcast_mission_event()`)
- Fire-and-forget WebSocket broadcast (errors logged, not propagated)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /missions | Create mission (draft) |
| GET | /missions | List user's missions (filterable) |
| GET | /missions/settings | Get user's mission settings |
| PUT | /missions/settings | Update user's mission settings |
| GET | /missions/{id} | Get mission details |
| PUT | /missions/{id} | Update draft mission |
| DELETE | /missions/{id} | Delete/cancel mission |
| POST | /missions/{id}/start | Start mission execution |
| POST | /missions/{id}/cancel | Cancel running mission |
| POST | /missions/{id}/clarify | Answer clarification question |
| POST | /missions/{id}/attachments | Upload attachment |
| GET | /missions/{id}/attachments | List attachments |
| DELETE | /missions/{id}/attachments/{aid} | Delete attachment |
| GET | /missions/{id}/agents | List assigned agents |
| GET | /missions/{id}/tasks | List mission tasks |
| GET | /missions/{id}/events | List mission events |
| GET | /missions/{id}/deliverables | List deliverables |
| GET | /missions/{id}/workspace/files | Browse workspace files |

**WebSocket:** `/ws/missions/{mission_id}` — real-time event streaming with heartbeat

## Frontend Architecture

### Pages
- **Missions.tsx** — List view with search/filter + detail view with flow canvas
  - Status filter (all/draft/executing/completed/etc.)
  - Mission cards with status dots, progress bars, and timestamps
  - Detail view: header, controls toolbar, MissionFlowCanvas, side panels

### Components
- **MissionCreateWizard** — 4-step wizard: instructions → attachments → configuration → review
  - Drag-and-drop file upload
  - Execution config (retries, timeout, rework cycles, network)
  - Advanced section: shows per-role LLM config from saved settings
- **MissionSettingsPanel** — Per-role LLM configuration (provider, model, temperature, max_tokens) + execution defaults
  - Loads available providers from `llmApi.getAvailableProviders()`
  - Expandable sections for each role
- **MissionFlowCanvas** — React Flow visualization of mission lifecycle nodes
  - Node types: MissionNode, AgentNode, TaskNode, RequirementsNode, SupervisorNode, QANode, ClarificationNode
- **MissionControls** — Toolbar for start/cancel/deliverables actions
- **ClarificationPanel** — Side panel for answering leader's clarifying questions
- **DeliverablesPanel** — Side panel listing completed deliverables with download

### State Management
- **missionStore (Zustand)** — Centralized state for missions, events, tasks, agents, attachments, settings
  - WebSocket handlers: `handleMissionEvent`, `handleMissionStatusUpdate`, `handleTaskStatusUpdate`
  - Filters: statusFilter, searchQuery with `getFilteredMissions()` derived state

### API Client
- **missionsApi** — Typed Axios wrapper for all mission endpoints
  - Uses `apiClient` with auth interceptors (follows project convention)

## Alembic Migrations

1. **m1a2b3c4d5e6** — Create `missions`, `mission_attachments`, `mission_agents`, `mission_events` tables; add `mission_id`, `acceptance_criteria`, `task_metadata` columns to `tasks`
2. **n2b3c4d5e6f7** — Create `mission_settings` table (depends on m1a2b3c4d5e6)

**Migration chain:** `91c4e2b8a5d1` → `m1a2b3c4d5e6` → `n2b3c4d5e6f7`
