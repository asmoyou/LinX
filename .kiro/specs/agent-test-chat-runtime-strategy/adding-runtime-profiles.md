# Adding Runtime Profiles

## 1. Add Profile Enum

1. Update `backend/agent_framework/runtime_policy.py`:
   - add enum value in `ExecutionProfile`.

## 2. Add Default Policy

1. Extend `RuntimePolicyRegistry._defaults` with the new profile.
2. Define loop mode, retry budget, timeout, and stream policy.

## 3. Wire Adapter Mapping

1. Update entry-point adapter (agent test chat, mission orchestrator, or future adapter) to pass the new profile.
2. Keep transport concerns in adapter layer; do not encode strategy in callback presence.

## 4. Add Tests

1. Add unit tests for profile parsing and policy resolution.
2. Add adapter-level tests to assert profile is forwarded to runtime invocation.
