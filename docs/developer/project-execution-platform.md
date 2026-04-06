# Project Execution Platform Developer Guide

This guide explains how contributors should work around the new platform during
Phase 0.

## What Phase 0 Means

Phase 0 is a docs-first alignment pass. The source of truth is the spec package in
`specs/project-execution-platform/`, supported by the companion architecture and
backend notes.

## Working Rules

- Treat `Project`, `PlanVersion`, `ExecutionRun`, `Artifact`, and `TimelineEvent`
  as the baseline vocabulary for new planning work
- Keep historical `mission-system` content readable, but do not add new direction there
- When a new doc changes terminology, update the spec and companion docs together
- Keep Phase 0 changes focused on documentation, naming, and planning boundaries

## Suggested Contribution Flow

1. Update requirements if the product shape changes
2. Update design if system boundaries or responsibilities change
3. Update tasks to reflect what is complete versus still pending
4. Update architecture or backend docs if the change affects shared terminology

## Out of Scope for This Phase

- backend routes and persistence work
- runtime orchestration implementation
- frontend views for projects and runs
- migration code for historical legacy execution records

## Handoff Expectations for Later Phases

Before implementation begins, the platform should have:

- agreed resource names
- lifecycle vocabulary and operator checkpoints
- migration assumptions from the frozen historical execution spec
- a task list that makes sequencing obvious for backend and frontend owners

## Related Documents

- `specs/project-execution-platform/requirements.md`
- `specs/project-execution-platform/design.md`
- `specs/project-execution-platform/tasks.md`
- `docs/architecture/project-execution-platform.md`
- `docs/backend/project-execution-platform.md`
