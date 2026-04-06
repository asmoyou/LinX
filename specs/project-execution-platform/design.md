# Project Execution Platform - Design

## Overview

The project-execution platform reframes execution around three separate layers:

1. **Project** — durable business intent and reusable context
2. **Plan Version** — the structured execution approach for that project
3. **Run** — a concrete attempt to execute a plan and produce artifacts

This replaces the older legacy execution model, where a single record carried both durable
intent and transient runtime state.

## Design Principles

- Separate long-lived intent from short-lived execution attempts
- Make plans explicit, reviewable, and versioned
- Treat events, artifacts, and operator actions as first-class records
- Keep migration understandable by preserving the historical execution model as context
- Publish implementation-facing docs before code-level commitments

## Target Architecture

```text
┌────────────────────── Experience Layer ──────────────────────┐
│ Project UI · Run timeline · Review surfaces · Operator tools │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌─────────────────────── Control Plane ────────────────────────┐
│ Project service · Plan service · Run orchestration · Events  │
└───────────────┬───────────────────────────────┬──────────────┘
                │                               │
┌───────────────▼──────────────┐   ┌────────────▼──────────────┐
│ Execution Plane              │   │ Data Plane                │
│ Workers · Sandboxes · Review │   │ Projects · Plans · Runs   │
│ Retry handlers · Artifact IO │   │ Events · Artifacts        │
└──────────────────────────────┘   └───────────────────────────┘
```

### Layer Responsibilities

- **Experience layer** exposes project setup, run monitoring, review decisions,
  and operator controls.
- **Control plane** owns durable project metadata, plan publication, run lifecycle,
  and system-visible events.
- **Execution plane** performs work, coordinates retries, and produces artifacts.
- **Data plane** stores durable records needed for audit, history, and comparison.

## Core Domain Model

| Entity | Purpose | Notes |
| --- | --- | --- |
| `Project` | Durable objective and reusable context | Created once, reused across runs |
| `PlanVersion` | Snapshot of execution structure | Supports revision without rewriting history |
| `ExecutionRun` | One attempt to execute a plan | Holds runtime status, checkpoints, and outcome |
| `WorkItem` | Executable unit inside a run | May map to task graph nodes or review steps |
| `Artifact` | Output from a run | Includes deliverables, logs, reports, and evidence |
| `TimelineEvent` | Ordered audit record | Includes system events and operator interventions |
| `OperatorDecision` | Explicit human control action | Approval, clarification, pause, resume, cancel |

## Key Flows

### 1. Project Setup
- Create or update a `Project`
- Attach reusable context, goals, and success criteria
- Keep this record stable across future attempts

### 2. Plan Publication
- Generate or author a `PlanVersion`
- Capture milestones, work items, and review gates
- Publish the plan version that future runs may execute

### 3. Run Execution
- Start an `ExecutionRun` against a chosen plan version
- Emit timeline events for state transitions and exceptions
- Persist artifacts as work progresses

### 4. Review and Iteration
- Attach review outcomes to the run that produced them
- Allow follow-up runs without duplicating the whole project
- Preserve prior runs for comparison and audit

## Documentation Deliverables

Phase 0 produces the following companion documents:

- `docs/architecture/project-execution-platform.md`
- `docs/backend/project-execution-platform.md`
- `docs/developer/project-execution-platform.md`

These docs are intentionally concise. They establish shared vocabulary and delivery
boundaries so later phases can add APIs, schema design, and runtime details without
restarting the naming discussion.

## Migration Direction from `mission-system`

The previous mission design remains useful as historical context, but it is no longer
the active planning target.

| Historical Concept | New Direction |
| --- | --- |
| `Mission` | Split into `Project` + `ExecutionRun` |
| Mission planning phase | Becomes explicit `PlanVersion` data |
| Mission events | Become run-scoped `TimelineEvent` records |
| Mission deliverables | Become run-scoped `Artifact` records |
| Mission clarification loop | Becomes an `OperatorDecision` / checkpoint pattern |

## Phase Sequencing

### Phase 0: Documentation and Alignment
- Publish the spec package and companion docs
- Freeze `mission-system` as a superseded reference

### Phase 1: Contracts
- Define canonical resource shapes and lifecycle vocabulary
- Define state transitions, operator checkpoints, and migration assumptions

### Phase 2: Backend Planning
- Draft schema candidates, API families, event contracts, and storage boundaries

### Phase 3: Runtime and UX Delivery
- Implement orchestration, subscriptions, operator controls, and artifact views

## Open Questions

- Should plan versions be editable drafts or append-only snapshots?
- Which operator controls are required for the first runnable release?
- How much of the historical execution data should be mapped forward versus left archival?
- What is the smallest run model that still supports retries, reviews, and audits?
