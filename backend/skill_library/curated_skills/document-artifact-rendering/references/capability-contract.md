# Capability Snapshot Contract

The preferred input is `/workspace/.linx_runtime/capabilities.json`.

Expected keys:

- `python_runtime`
- `commands`
- `python_modules`
- `fonts`
- `renderers`
- `verifiers`

If the file is missing, scripts may probe the current sandbox environment directly and proceed with the best available renderer.
