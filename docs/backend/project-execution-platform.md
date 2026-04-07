# Project Execution Platform Skeleton

This backend slice introduces a minimal DB-backed foundation for a new project execution flow.

## New tables

- `projects`
- `project_tasks`
- `project_plans`
- `project_runs`
- `project_run_steps`
- `project_spaces`
- `external_agent_profiles`
- `external_agent_bindings`
- `external_agent_install_tokens`
- `external_agent_dispatches`
- `project_skill_packages`
- `project_extension_packages`
- `project_audit_events`

## New API surfaces

- `POST|GET|PATCH|DELETE /api/v1/projects`
- `POST|GET|PATCH|DELETE /api/v1/project-tasks`
- `POST|GET|PATCH|DELETE /api/v1/plans`
- `POST|GET|PATCH|DELETE /api/v1/runs`
- `POST|GET|PATCH|DELETE /api/v1/run-steps`
- `PUT|GET|POST /api/v1/project-space/{project_id}`
- `GET|PATCH|POST /api/v1/agents/{agent_id}/external-runtime/*`
- `POST|GET /api/v1/external-runtime/*`
- `POST|GET|PATCH|DELETE /api/v1/extensions`
- `POST /api/v1/skills/import`
- `POST /api/v1/skills/imports/{skill_package_id}/test`

## Notes

- The implementation is intentionally narrow and keeps workflow logic simple.
- Mutating endpoints append rows to `project_audit_events`.
- All new endpoints are database-backed and avoid in-memory state.
- External host execution now routes exclusively through the external runtime binding and dispatch APIs.
