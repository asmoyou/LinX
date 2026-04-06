#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_STATE_PATH = Path.home() / ".linx_node_agent_state.json"
DEFAULT_EXTERNAL_AGENT_COMMAND = os.environ.get("LINX_EXTERNAL_AGENT_COMMAND")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LinX external runtime node agent")
    parser.add_argument("--base-url", required=True, help="API base URL, e.g. http://localhost:8000/api/v1")
    parser.add_argument("--token", required=True, help="Bearer token")
    parser.add_argument("--project-id", required=True, help="Project ID to bind this node to")
    parser.add_argument("--name", required=True, help="Display name for this node")
    parser.add_argument("--type", default="external_cli", help="Node type")
    parser.add_argument("--capability", action="append", default=[], help="Capability string (repeatable)")
    parser.add_argument("--agent-command", default=DEFAULT_EXTERNAL_AGENT_COMMAND, help="Command used to run an external agent session")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH), help="Local state file path")
    parser.add_argument("--heartbeat-seconds", type=int, default=10)
    parser.add_argument("--poll-seconds", type=int, default=5)
    return parser.parse_args()


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def register_node(args: argparse.Namespace, state_path: Path) -> str:
    response = requests.post(
        f"{args.base_url}/execution-nodes/register",
        headers=headers(args.token),
        json={
            "project_id": args.project_id,
            "name": args.name,
            "node_type": args.type,
            "capabilities": args.capability,
            "config": {"hostname": os.uname().nodename if hasattr(os, 'uname') else None},
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    save_state(state_path, {"node_id": data["node_id"]})
    return data["node_id"]


def heartbeat(args: argparse.Namespace, node_id: str) -> None:
    response = requests.post(
        f"{args.base_url}/execution-nodes/{node_id}/heartbeat",
        headers=headers(args.token),
        json={"status": "online", "config": {"last_heartbeat": time.time(), "agent_command": bool(args.agent_command)}},
        timeout=30,
    )
    response.raise_for_status()


def poll_leases(args: argparse.Namespace, node_id: str) -> list[dict[str, Any]]:
    response = requests.get(
        f"{args.base_url}/execution-nodes/{node_id}/leases",
        headers=headers(args.token),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def post_progress(args: argparse.Namespace, node_id: str, lease_id: str, suffix: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{args.base_url}/execution-nodes/{node_id}/leases/{lease_id}/{suffix}",
        headers=headers(args.token),
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _prepare_workdir(path_str: str) -> Path:
    workdir = Path(path_str or "/tmp/linx_external_runtime")
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir


def _write_prompt_file(workdir: Path, lease_payload: dict[str, Any], prompt: str) -> Path:
    session_id = str(lease_payload.get("external_agent_session_id") or "external-session")
    prompt_file = workdir / ".linx" / f"{session_id}.prompt.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")
    return prompt_file


def _run_external_agent_session(agent_command: str, lease_payload: dict[str, Any], workspace_root: Path) -> tuple[bool, dict[str, Any], str | None]:
    agent_meta = lease_payload.get("agent") or {}
    prompt = str(agent_meta.get("execution_prompt") or "").strip()
    if not prompt:
        return False, {"lease_note": "No execution prompt supplied for external agent session."}, "No execution prompt supplied for external agent session."

    prompt_file = _write_prompt_file(workspace_root, lease_payload, prompt)
    env = os.environ.copy()
    env.update(
        {
            "LINX_AGENT_PROMPT": prompt,
            "LINX_AGENT_PROMPT_FILE": str(prompt_file),
            "LINX_AGENT_ID": str(agent_meta.get("agent_id") or ""),
            "LINX_AGENT_NAME": str(agent_meta.get("agent_name") or ""),
            "LINX_AGENT_RUNTIME_TYPE": str(agent_meta.get("runtime_type") or ""),
            "LINX_PROJECT_ID": str(lease_payload.get("project_id") or ""),
            "LINX_RUN_ID": str(lease_payload.get("run_id") or ""),
            "LINX_RUN_STEP_ID": str(lease_payload.get("run_step_id") or ""),
            "LINX_WORKSPACE_ROOT": str(workspace_root),
        }
    )
    process = subprocess.run(
        agent_command,
        cwd=str(workspace_root),
        shell=True,
        text=True,
        capture_output=True,
        timeout=1800,
        env=env,
    )
    result_payload = {
        "mode": "external_agent_session",
        "agent_command": agent_command,
        "returncode": process.returncode,
        "stdout": process.stdout[-30000:],
        "stderr": process.stderr[-30000:],
        "workspace_root": str(workspace_root),
        "prompt_file": str(prompt_file),
    }
    if process.returncode != 0:
        return False, result_payload, f"External agent command exited with {process.returncode}"
    return True, result_payload, None


def _run_direct_command(lease_payload: dict[str, Any], workspace_root: Path) -> tuple[bool, dict[str, Any], str | None]:
    step = lease_payload.get("step") or {}
    input_payload = step.get("input_payload") or {}
    command = input_payload.get("command")
    if not command:
        return False, {"lease_note": "No external agent command configured and no direct command provided in lease payload."}, "No external agent command configured and no direct command provided in lease payload."
    process = subprocess.run(
        command,
        cwd=str(workspace_root),
        shell=True,
        text=True,
        capture_output=True,
        timeout=900,
    )
    result_payload = {
        "mode": "direct_command",
        "command": command,
        "returncode": process.returncode,
        "stdout": process.stdout[-30000:],
        "stderr": process.stderr[-30000:],
        "workspace_root": str(workspace_root),
    }
    if process.returncode != 0:
        return False, result_payload, f"Command exited with {process.returncode}"
    return True, result_payload, None


def execute_lease(args: argparse.Namespace, lease: dict[str, Any]) -> tuple[bool, dict[str, Any], str | None]:
    lease_payload = lease.get("lease_payload") or {}
    workspace_root = _prepare_workdir(str(lease_payload.get("workspace_root") or "/tmp/linx_external_runtime"))
    resolved_agent_command = str(lease_payload.get("external_agent_command_template") or args.agent_command or "").strip()
    if resolved_agent_command and lease_payload.get("external_agent_session_id"):
        return _run_external_agent_session(resolved_agent_command, lease_payload, workspace_root)
    return _run_direct_command(lease_payload, workspace_root)


def main() -> int:
    args = parse_args()
    state_path = Path(args.state_path)
    state = load_state(state_path)
    node_id = state.get("node_id") or register_node(args, state_path)
    last_heartbeat = 0.0
    while True:
        now = time.time()
        if now - last_heartbeat >= args.heartbeat_seconds:
            heartbeat(args, node_id)
            last_heartbeat = now
        leases = poll_leases(args, node_id)
        for lease in leases:
            lease_id = lease["lease_id"]
            post_progress(args, node_id, lease_id, "ack", {"status": "connected", "result_payload": {"mode": "external_agent_session" if (args.agent_command and lease.get('lease_payload', {}).get('external_agent_session_id')) else "direct_command"}})
            post_progress(args, node_id, lease_id, "progress", {"status": "running", "result_payload": {}})
            ok, result_payload, error_message = execute_lease(args, lease)
            if ok:
                post_progress(args, node_id, lease_id, "complete", {"status": "completed", "result_payload": result_payload})
            else:
                post_progress(args, node_id, lease_id, "fail", {"status": "failed", "result_payload": result_payload, "error_message": error_message})
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
