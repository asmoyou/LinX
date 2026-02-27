# Mission Execution System - Requirements

## Overview

The Mission Execution System enables users to define high-level goals and have an AI agent team autonomously execute them through a structured lifecycle: requirements gathering, task planning, parallel execution, supervisor review, and QA audit.

## User Stories

### US-1: Create a Mission
**As a** user, **I want to** create a mission with a title, instructions, and optional file attachments, **so that** the AI team has all the context needed to execute my goal.

**Acceptance Criteria:**
- [x] User can provide a title (max 500 chars) and free-form instructions
- [x] User can attach files (PDF, DOCX, images, etc.) that are stored in MinIO
- [x] Mission is created in `draft` status
- [x] User's saved mission settings are merged as defaults into mission_config
- [x] A multi-step creation wizard guides the user through instructions, attachments, configuration, and review

### US-2: Start and Monitor a Mission
**As a** user, **I want to** start a draft mission and watch it progress through phases in real-time, **so that** I can track the AI team's work.

**Acceptance Criteria:**
- [x] Clicking "Start" transitions the mission from `draft` → `requirements` → `planning` → `executing` → `reviewing` → `qa` → `completed`
- [x] Each phase emits lifecycle events persisted to `mission_events` and broadcast via WebSocket
- [x] Frontend receives real-time status and event updates via WebSocket subscription
- [x] Progress bar shows completed_tasks / total_tasks
- [x] Mission flow canvas visualizes the lifecycle as a node graph (React Flow)

### US-3: Clarification Loop
**As a** user, **I want to** answer clarifying questions from the leader agent during requirements gathering, **so that** ambiguous instructions can be resolved without restarting.

**Acceptance Criteria:**
- [x] If the leader outputs text containing "CLARIFICATION:", the orchestrator pauses and emits a `USER_CLARIFICATION_REQUESTED` event
- [x] User can submit a response via the Clarification panel (POST `/missions/{id}/clarify`)
- [x] The leader re-invokes with the user's answer and produces the final requirements document

### US-4: Cancel a Mission
**As a** user, **I want to** cancel a running mission at any point, **so that** I can stop wasted compute.

**Acceptance Criteria:**
- [x] Cancel request stops the asyncio task, updates status to `cancelled`, cleans up the workspace container
- [x] Cancel is idempotent and works from any active status

### US-5: Configure Mission Defaults
**As a** user, **I want to** configure default LLM providers, models, and execution parameters for each agent role, **so that** I don't have to reconfigure every mission.

**Acceptance Criteria:**
- [x] Settings panel allows configuring leader, supervisor, and QA agent LLM provider/model/temperature/max_tokens
- [x] Execution defaults: max_retries, task_timeout_s, max_rework_cycles, network_access, max_concurrent_tasks
- [x] Settings are per-user and persisted in `mission_settings` table
- [x] New missions automatically inherit saved settings

### US-6: Review Deliverables
**As a** user, **I want to** view and download the deliverables produced by a completed mission, **so that** I can use the outputs.

**Acceptance Criteria:**
- [x] Deliverables are collected from the container's `/workspace/output/` directory
- [x] Files are uploaded to MinIO with download metadata
- [x] Deliverables panel lists files with size and download option

### US-7: Browse Workspace Files
**As a** user, **I want to** browse the workspace filesystem of a running mission, **so that** I can inspect intermediate artifacts.

**Acceptance Criteria:**
- [x] GET endpoint returns file listing for any path within the workspace container
- [x] Files include name, path, size, and directory flag

## Non-Functional Requirements

### NFR-1: Concurrency
- Missions run as independent `asyncio.Task` instances
- Task execution within a mission respects `max_concurrent_tasks` via semaphore
- Multiple missions can run simultaneously

### NFR-2: Fault Tolerance
- Failed tasks retry with exponential backoff (up to `max_retries`)
- Review failures trigger re-execution (up to `MAX_REVIEW_CYCLES = 2`)
- QA failures route back to review (up to `MAX_QA_CYCLES = 1`)
- Mission-level exceptions transition to `failed` status with error_message preserved

### NFR-3: Isolation
- Each mission gets a dedicated Docker container (via ContainerManager)
- Workspace has structured directories: input, output, tasks, shared, logs
- Network access is configurable per mission

### NFR-4: Real-time Updates
- All lifecycle events are persisted to `mission_events` and broadcast via WebSocket
- Frontend subscribes to `/ws/missions/{mission_id}` for live updates
