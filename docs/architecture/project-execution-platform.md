# Project Execution Platform Architecture

This page describes the target architecture for evolving LinX from the historical mission flow into the project-execution platform.

## Why This Exists

The historical execution model proved that multi-step execution, review loops, and
deliverable collection are valuable. Its main limitation was that one legacy record
had to represent both durable user intent and a single runtime attempt.

The new platform separates those concerns so the system can support retries,
comparisons, and operator interventions without rewriting the project itself.

## Core Model

| Concept | Meaning |
| --- | --- |
| `Project` | Durable objective, context, and success criteria |
| `PlanVersion` | Reviewable execution structure for a project |
| `ExecutionRun` | One attempt to execute a chosen plan |
| `Artifact` | Output, evidence, or deliverable produced by a run |
| `TimelineEvent` | Ordered history of system and operator actions |

## Architectural Layers

### Experience Layer
- Project setup and editing
- Run timeline and status views
- Review, approval, and retry controls

### Control Plane
- Project lifecycle management
- Plan publication and selection
- Run orchestration and checkpoint handling
- Event publication for UI and audit consumers

### Execution Plane
- Worker coordination
- Sandbox or workspace management
- Retry and recovery loops
- Artifact collection and upload

### Data Plane
- Durable project metadata
- Versioned plans
- Run history and event streams
- Artifact metadata and provenance

## Expected Runtime Flow

1. A user defines a `Project`.
2. A planner or system publishes a `PlanVersion`.
3. An `ExecutionRun` starts against that plan.
4. Work items emit `TimelineEvent` records as execution progresses.
5. Review outputs and deliverables are stored as `Artifact` records.
6. A future run can reuse the same project with a new or existing plan version.

## Relationship to `mission-system`

`specs/mission-system/` remains a frozen historical design record only and should not
be treated as an active architecture target. The project-execution platform
keeps the valuable orchestration ideas while introducing a cleaner separation between
project intent, planning, runtime state, and review output.

## Related Documents

- `specs/project-execution-platform/requirements.md`
- `specs/project-execution-platform/design.md`
- `docs/backend/project-execution-platform.md`
- `docs/developer/project-execution-platform.md`
