# LinX Node Agent

First-pass external runtime host package for the LinX project execution platform.

## What it is
`linx-node-agent` is the program you install on a target host or reachable machine.
That machine becomes a **Runtime Host** in LinX.

It does **not** define business agents by itself. Instead:
- You create `External Agent` in the LinX `Agents` page
- You install `linx-node-agent` on the target host
- You register that host in the LinX `Execution Nodes` page
- LinX can then schedule external agent sessions onto that host

## What it does
- Registers itself as an `external_cli` runtime host
- Sends periodic heartbeats
- Polls pending leases for its node
- Acknowledges leases and updates progress
- Starts an external agent session when the lease contains an external session payload
- Falls back to direct command execution if no external session runner is configured
- Reports completion or failure back to the control plane

## Install on a target host
Copy the `node-agent/` directory to the target machine, then run:

```bash
cd node-agent
bash install.sh
```

This installs:
- virtualenv under `~/.linx-node-agent/venv`
- runtime script under `~/.linx-node-agent/linx_node_agent.py`
- launcher command `linx-node-agent` under `~/.local/bin/linx-node-agent`

If needed, add the launcher to your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Configure an external agent runner
Set the command template used to start an external agent process.
You can configure it in three levels inside LinX:
1. Platform default: `Settings -> Project Execution`
2. Project override: `Project Detail`
3. Node override: `Execution Nodes -> Edit Host`

Or as a local fallback env var on the host:

```bash
export LINX_EXTERNAL_AGENT_COMMAND='external-agent --prompt-file "$LINX_AGENT_PROMPT_FILE"'
```

## Run the node agent
```bash
linx-node-agent   --base-url http://localhost:8000/api/v1   --token <YOUR_BEARER_TOKEN>   --project-id <PROJECT_ID>   --name "My MacBook Host"   --capability host_execution   --capability shell   --capability ops
```

## Environment passed to external agent runner
When LinX launches an external agent session, the command receives:
- `LINX_AGENT_PROMPT`
- `LINX_AGENT_PROMPT_FILE`
- `LINX_AGENT_ID`
- `LINX_AGENT_NAME`
- `LINX_AGENT_RUNTIME_TYPE`
- `LINX_PROJECT_ID`
- `LINX_RUN_ID`
- `LINX_RUN_STEP_ID`
- `LINX_WORKSPACE_ROOT`

## Current limitation
The control plane now supports external agent sessions and host registration, but the external runner command still depends on what CLI/runtime you choose to integrate.


## Run as a service

### systemd (Linux)
Use `/Users/youqilin/VIbeCodingProjects/linX/node-agent/templates/linx-node-agent.service.example` as a starting point.

Typical steps:
```bash
mkdir -p ~/.config/systemd/user
cp node-agent/templates/linx-node-agent.service.example ~/.config/systemd/user/linx-node-agent.service
systemctl --user daemon-reload
systemctl --user enable --now linx-node-agent
systemctl --user status linx-node-agent
```

### launchd (macOS)
Use `/Users/youqilin/VIbeCodingProjects/linX/node-agent/templates/com.linx.node-agent.plist.example` as a starting point.

Typical steps:
```bash
mkdir -p ~/Library/LaunchAgents
cp node-agent/templates/com.linx.node-agent.plist.example ~/Library/LaunchAgents/com.linx.node-agent.plist
launchctl unload ~/Library/LaunchAgents/com.linx.node-agent.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.linx.node-agent.plist
launchctl kickstart -k gui/$(id -u)/com.linx.node-agent
```
