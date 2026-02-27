# Runtime Profile Matrix

## 1. Entry Point to Profile Mapping

| Entry Point | Profile | Loop Mode | Streaming Transport | Primary Purpose |
|---|---|---|---|---|
| `/agents/{id}/test` (chat debug) | `debug_chat` | `recovery_multi_turn` | optional SSE | interactive debugging parity |
| mission task execution | `mission_task` | `recovery_multi_turn` | no (default) | durable task completion + recovery |
| mission control/phase prompts | `mission_control` | `single_turn` | no | planning/review control turns |
| unspecified legacy callers | `legacy` | callback-derived fallback | caller-defined | backward compatibility |

## 2. Adapter Responsibilities

1. Parse request payload/history/context.
2. Resolve profile selection.
3. Pass profile to runtime invocation (`AgentExecutor`/`UnifiedAgentRuntimeService`).
4. Keep transport mapping (stream/no-stream) in adapter layer only.

## 3. Runtime Responsibilities

1. Normalize history and message content.
2. Resolve effective `RuntimePolicy`.
3. Execute loop strategy from policy, independent of transport callback.
4. Emit structured runtime telemetry fields.
