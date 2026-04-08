#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import gettempdir
from threading import Thread
from typing import Literal
from typing import Any
import tarfile
import zipfile


MAX_CAPTURE_CHARS = 30000
MAX_TOOL_ITERATIONS = 8


class FatalRuntimeStop(RuntimeError):
    pass


def build_runtime_status_payload(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    state_path = state_path_for(config_path)
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    return {
        "agent_id": config.get("agent_id"),
        "runtime_version": config.get("runtime_version"),
        "desired_version": config.get("desired_version"),
        "host_name": config.get("host_name"),
        "host_os": config.get("host_os"),
        "host_arch": config.get("host_arch"),
        "runtime_home": config.get("runtime_home"),
        "python_executable": config.get("python_executable"),
        "local_status_url": config.get("local_status_url"),
        "local_status_port": config.get("local_status_port"),
        "last_dispatch_action": state.get("last_dispatch_action"),
        "last_dispatch_status": state.get("last_dispatch_status"),
        "last_dispatch_error_message": state.get("last_dispatch_error_message"),
        "state": state,
    }


def start_local_status_server(config_path: Path, config: dict[str, Any]) -> tuple[ThreadingHTTPServer, str, int]:
    requested_port = int(config.get("local_status_port") or 0)

    class RuntimeStatusHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            payload = build_runtime_status_payload(config_path, config)
            if self.path in {"/state", "/health"}:
                body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            state_blob = html.escape(json.dumps(payload, indent=2, ensure_ascii=False))
            dispatch_action = html.escape(str(payload.get("last_dispatch_action") or "none"))
            dispatch_status = html.escape(str(payload.get("last_dispatch_status") or "unknown"))
            dispatch_error = html.escape(str(payload.get("last_dispatch_error_message") or ""))
            runtime_version = html.escape(str(payload.get("runtime_version") or "unknown"))
            desired_version = html.escape(str(payload.get("desired_version") or "unknown"))
            body = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>LinX External Runtime</title>
    <style>
      body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 32px; color: #18181b; background: #fafafa; }}
      .card {{ max-width: 960px; margin: 0 auto; background: white; border: 1px solid #e4e4e7; border-radius: 16px; padding: 24px; }}
      h1 {{ margin-top: 0; font-size: 24px; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 20px; }}
      .tile {{ background: #f4f4f5; padding: 16px; border-radius: 12px; }}
      .label {{ color: #71717a; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }}
      .value {{ margin-top: 8px; font-size: 18px; font-weight: 600; }}
      pre {{ overflow: auto; background: #f4f4f5; padding: 16px; border-radius: 12px; }}
      .muted {{ color: #52525b; }}
      .error {{ color: #b91c1c; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>LinX External Runtime</h1>
      <p class="muted">Local read-only diagnostics for this Runtime Host.</p>
      <div class="grid">
        <div class="tile">
          <div class="label">Runtime Version</div>
          <div class="value">{runtime_version}</div>
        </div>
        <div class="tile">
          <div class="label">Desired Version</div>
          <div class="value">{desired_version}</div>
        </div>
        <div class="tile">
          <div class="label">Last Action</div>
          <div class="value">{dispatch_action}</div>
        </div>
        <div class="tile">
          <div class="label">Last Action Status</div>
          <div class="value">{dispatch_status}</div>
        </div>
      </div>
      {"<p class='error'>Last action error: " + dispatch_error + "</p>" if dispatch_error else ""}
      <pre>{state_blob}</pre>
    </div>
  </body>
</html>""".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", requested_port), RuntimeStatusHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_port = int(server.server_address[1])
    local_status_url = f"http://127.0.0.1:{actual_port}/"
    config["local_status_port"] = actual_port
    config["local_status_url"] = local_status_url
    return server, local_status_url, actual_port


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LinX external runtime")
    parser.add_argument("--config", required=True, help="Path to runtime config JSON")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def state_path_for(config_path: Path) -> Path:
    return config_path.with_name("runtime-state.json")


def normalize_os_name(value: str | None = None) -> str:
    candidate = (value or platform.system()).strip().lower()
    if candidate.startswith("darwin") or candidate.startswith("mac"):
        return "darwin"
    if candidate.startswith("win"):
        return "windows"
    return "linux"


def normalize_arch_name(value: str | None = None) -> str:
    candidate = (value or platform.machine()).strip().lower()
    if candidate in {"x86_64", "amd64"}:
        return "amd64"
    if candidate in {"arm64", "aarch64"}:
        return "arm64"
    return candidate or "unknown"


def detect_machine_token_source() -> str:
    os_name = normalize_os_name()
    if os_name == "linux":
        machine_id = Path("/etc/machine-id")
        if machine_id.exists():
            return machine_id.read_text(encoding="utf-8").strip()
    if os_name == "darwin":
        try:
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            result = None
        if result and "IOPlatformUUID" in result.stdout:
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split("=", 1)[-1].replace('"', "").strip()
    if os_name == "windows":
        try:
            result = subprocess.run(
                [
                    "reg",
                    "query",
                    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography",
                    "/v",
                    "MachineGuid",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            result = None
        if result:
            for line in result.stdout.splitlines():
                if "MachineGuid" in line:
                    return line.split()[-1].strip()
    return f"{socket.gethostname()}::{platform.platform()}"


def detect_host_fingerprint() -> str:
    return hashlib.sha256(detect_machine_token_source().encode("utf-8")).hexdigest()


def headers(machine_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {machine_token}",
        "Content-Type": "application/json",
    }


def request_json(
    *,
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    request_headers: dict[str, str] | None = None,
    timeout: int = 30,
    allow_statuses: set[int] | None = None,
) -> tuple[int, dict[str, Any] | None]:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url=url, data=body, method=method.upper())
    for key, value in (request_headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else None
            return int(response.status), parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        parsed = json.loads(raw) if raw else None
        if allow_statuses and exc.code in allow_statuses:
            return exc.code, parsed
        if exc.code == 401:
            raise FatalRuntimeStop(parsed.get("detail") if isinstance(parsed, dict) else "external_agent_machine_token_invalid") from exc
        raise


def write_prompt_file(workspace_root: Path, dispatch_id: str, prompt: str) -> Path:
    prompt_file = workspace_root / ".linx" / f"{dispatch_id}.prompt.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")
    return prompt_file


def clear_workspace_root(workspace_root: Path) -> None:
    if workspace_root.exists():
        shutil.rmtree(workspace_root, ignore_errors=True)
    workspace_root.mkdir(parents=True, exist_ok=True)


def safe_extract_archive_bytes(archive_bytes: bytes, workspace_root: Path) -> None:
    target_root = workspace_root.resolve()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            candidate = (target_root / member.name).resolve()
            if candidate != target_root and target_root not in candidate.parents:
                raise ValueError(f"Blocked unsafe archive member: {member.name}")
        archive.extractall(path=target_root)


def build_workspace_archive_bytes(workspace_root: Path) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        archive.add(workspace_root, arcname=".")
    data = buffer.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def summarize_workspace(workspace_root: Path) -> tuple[int, int]:
    total_bytes = 0
    total_files = 0
    if not workspace_root.exists():
        return total_bytes, total_files
    for item in workspace_root.rglob("*"):
        if not item.is_file():
            continue
        try:
            total_bytes += int(item.stat().st_size)
            total_files += 1
        except OSError:
            continue
    return total_bytes, total_files


def post_dispatch_event(
    *,
    config: dict[str, Any],
    dispatch_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    url = f"{config['control_plane']}/api/v1/external-runtime/dispatches/{dispatch_id}/events"
    _status, data = request_json(
        url=url,
        method="POST",
        payload={"event_type": event_type, "payload": payload},
        request_headers=headers(str(config["machine_token"])),
        timeout=60,
    )
    return data


def download_conversation_workspace_snapshot(
    *,
    config: dict[str, Any],
    conversation_id: str,
) -> dict[str, Any] | None:
    status, data = request_json(
        url=(
            f"{config['control_plane']}/api/v1/external-runtime/conversations/"
            f"{conversation_id}/workspace/download"
        ),
        request_headers=headers(str(config["machine_token"])),
        timeout=180,
        allow_statuses={404},
    )
    if status == 404:
        return None
    return data or None


def upload_conversation_workspace_snapshot(
    *,
    config: dict[str, Any],
    conversation_id: str,
    workspace_root: Path,
) -> dict[str, Any] | None:
    archive_bytes, checksum = build_workspace_archive_bytes(workspace_root)
    workspace_bytes, workspace_files = summarize_workspace(workspace_root)
    _status, data = request_json(
        url=(
            f"{config['control_plane']}/api/v1/external-runtime/conversations/"
            f"{conversation_id}/workspace/upload"
        ),
        method="POST",
        payload={
            "archive_base64": base64.b64encode(archive_bytes).decode("utf-8"),
            "workspace_bytes_estimate": workspace_bytes,
            "workspace_file_count_estimate": workspace_files,
            "snapshot_status": "ready",
        },
        request_headers=headers(str(config["machine_token"])),
        timeout=300,
    )
    response = data or {}
    response.setdefault("checksum", checksum)
    response.setdefault("size_bytes", len(archive_bytes))
    return response


def download_run_workspace_snapshot(
    *,
    config: dict[str, Any],
    run_id: str,
) -> dict[str, Any] | None:
    status, data = request_json(
        url=f"{config['control_plane']}/api/v1/external-runtime/runs/{run_id}/workspace/download",
        request_headers=headers(str(config["machine_token"])),
        timeout=180,
        allow_statuses={404},
    )
    if status == 404:
        return None
    return data or None


def upload_run_workspace_snapshot(
    *,
    config: dict[str, Any],
    run_id: str,
    workspace_root: Path,
) -> dict[str, Any] | None:
    archive_bytes, checksum = build_workspace_archive_bytes(workspace_root)
    workspace_bytes, workspace_files = summarize_workspace(workspace_root)
    _status, data = request_json(
        url=f"{config['control_plane']}/api/v1/external-runtime/runs/{run_id}/workspace/upload",
        method="POST",
        payload={
            "archive_base64": base64.b64encode(archive_bytes).decode("utf-8"),
            "workspace_bytes_estimate": workspace_bytes,
            "workspace_file_count_estimate": workspace_files,
            "snapshot_status": "ready",
        },
        request_headers=headers(str(config["machine_token"])),
        timeout=300,
    )
    response = data or {}
    response.setdefault("checksum", checksum)
    response.setdefault("size_bytes", len(archive_bytes))
    return response


def restore_conversation_workspace_if_needed(
    *,
    config: dict[str, Any],
    conversation_id: str,
    workspace_root: Path,
) -> int | None:
    if workspace_root.exists():
        try:
            if any(workspace_root.iterdir()):
                return None
        except OSError:
            pass
    snapshot_payload = download_conversation_workspace_snapshot(
        config=config,
        conversation_id=conversation_id,
    )
    if not snapshot_payload:
        return None
    archive_base64 = str(snapshot_payload.get("archive_base64") or "").strip()
    if not archive_base64:
        return None
    archive_bytes = base64.b64decode(archive_base64.encode("utf-8"))
    expected_checksum = str(snapshot_payload.get("checksum") or "").strip()
    if expected_checksum:
        digest = hashlib.sha256(archive_bytes).hexdigest()
        if digest != expected_checksum:
            raise ValueError("Conversation workspace snapshot checksum mismatch")
    clear_workspace_root(workspace_root)
    safe_extract_archive_bytes(archive_bytes, workspace_root)
    return int(snapshot_payload.get("generation") or 0)


def restore_run_workspace_if_needed(
    *,
    config: dict[str, Any],
    run_id: str,
    workspace_root: Path,
) -> bool:
    if workspace_root.exists():
        try:
            if any(workspace_root.iterdir()):
                return False
        except OSError:
            pass
    snapshot_payload = download_run_workspace_snapshot(config=config, run_id=run_id)
    if not snapshot_payload:
        return False
    archive_base64 = str(snapshot_payload.get("archive_base64") or "").strip()
    if not archive_base64:
        return False
    archive_bytes = base64.b64decode(archive_base64.encode("utf-8"))
    clear_workspace_root(workspace_root)
    safe_extract_archive_bytes(archive_bytes, workspace_root)
    return True


def normalize_workspace_attachment_path(value: Any) -> str | None:
    normalized = str(value or "").replace("\\", "/").strip().lstrip("/")
    normalized = normalized.strip("/")
    if not normalized or ".." in normalized:
        return None
    return normalized


def resolve_workspace_path(workspace_root: Path, relative_path: str) -> Path:
    candidate = (workspace_root / relative_path).resolve()
    root = workspace_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Blocked unsafe workspace path: {relative_path}")
    return candidate


def download_runtime_attachment_bytes(*, config: dict[str, Any], storage_ref: str) -> bytes:
    query = urllib.parse.urlencode({"storage_ref": storage_ref})
    url = f"{config['control_plane']}/api/v1/external-runtime/attachments/download?{query}"
    request = urllib.request.Request(url=url, method="GET")
    for key, value in headers(str(config["machine_token"])).items():
        if key.lower() == "content-type":
            continue
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise FatalRuntimeStop("external_agent_machine_token_invalid") from exc
        raise


def hydrate_conversation_attachments(
    *,
    config: dict[str, Any],
    attachments: list[dict[str, Any]],
    workspace_root: Path,
) -> int:
    written = 0
    for attachment in attachments:
        storage_ref = str(attachment.get("storage_ref") or "").strip()
        workspace_path = normalize_workspace_attachment_path(attachment.get("workspace_path"))
        if not storage_ref or not workspace_path:
            continue
        destination = resolve_workspace_path(workspace_root, workspace_path)
        if destination.exists():
            continue
        payload = download_runtime_attachment_bytes(config=config, storage_ref=storage_ref)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        written += 1
    return written


def call_llm_proxy(
    *,
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    temperature: Any = None,
    max_tokens: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messages": messages,
        "tools": tools,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    _status, data = request_json(
        url=f"{config['control_plane']}/api/v1/external-runtime/llm/chat",
        method="POST",
        payload=payload,
        request_headers=headers(str(config["machine_token"])),
        timeout=180,
    )
    return data or {}


def build_bash_tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": (
                    "Execute one shell command on the bound Runtime Host inside the current "
                    "workspace. Use this to inspect files, edit project contents, and run local checks."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute.",
                        }
                    },
                    "required": ["command"],
                },
            },
        }
    ]


def normalize_tool_call_arguments(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def execute_bash_tool(*, workspace_root: Path, command: str) -> tuple[bool, str]:
    env = os.environ.copy()
    env["LINX_WORKSPACE_ROOT"] = str(workspace_root)
    process = subprocess.run(
        command,
        cwd=str(workspace_root),
        shell=True,
        text=True,
        capture_output=True,
        timeout=300,
        env=env,
    )
    stdout = str(process.stdout or "")[-MAX_CAPTURE_CHARS:]
    stderr = str(process.stderr or "")[-MAX_CAPTURE_CHARS:]
    summary_parts = [
        f"command={command}",
        f"returncode={process.returncode}",
    ]
    if stdout:
        summary_parts.append(f"stdout:\n{stdout}")
    if stderr:
        summary_parts.append(f"stderr:\n{stderr}")
    return process.returncode == 0, "\n\n".join(summary_parts).strip()


def collect_workspace_artifacts(workspace_root: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    candidates = []
    for preferred in ("output", "workspace/output"):
        candidate = workspace_root / preferred
        if candidate.exists():
            candidates.append(candidate)
    root = candidates[0] if candidates else workspace_root
    if not root.exists():
        return artifacts
    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        try:
            relative = item.relative_to(workspace_root)
            artifacts.append(
                {
                    "name": item.name,
                    "path": f"/workspace/{str(relative).replace(os.sep, '/')}",
                    "size": int(item.stat().st_size),
                    "is_dir": False,
                }
            )
        except OSError:
            continue
        if len(artifacts) >= 50:
            break
    return artifacts


def build_runtime_messages(
    *,
    system_prompt: str,
    history: list[dict[str, Any]],
    current_message: dict[str, Any],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)
    messages.append(current_message)
    return messages


def run_native_agent_loop(
    *,
    dispatch: dict[str, Any],
    config: dict[str, Any],
    workspace_root: Path,
    system_prompt: str,
    history: list[dict[str, Any]],
    current_message: dict[str, Any],
    temperature: Any = None,
    max_tokens: Any = None,
) -> tuple[bool, dict[str, Any], str | None, None]:
    dispatch_id = str(dispatch.get("dispatch_id") or "dispatch")
    workspace_root.mkdir(parents=True, exist_ok=True)
    messages = build_runtime_messages(
        system_prompt=system_prompt,
        history=history,
        current_message=current_message,
    )
    tools = build_bash_tool_schema()
    rounds: list[dict[str, Any]] = []
    post_dispatch_event(
        config=config,
        dispatch_id=dispatch_id,
        event_type="start",
        payload={"type": "start", "content": "Remote execution started on Runtime Host."},
    )
    for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
        post_dispatch_event(
            config=config,
            dispatch_id=dispatch_id,
            event_type="thinking",
            payload={"type": "thinking", "content": f"Runtime Host reasoning round {iteration}."},
        )
        llm_result = call_llm_proxy(
            config=config,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = str(llm_result.get("content") or "")
        tool_calls = list(llm_result.get("tool_calls") or [])
        usage = dict(llm_result.get("usage") or {})
        finish_reason = str(llm_result.get("finish_reason") or "").strip() or None
        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                }
            )
            round_record = {
                "roundNumber": iteration,
                "thinking": content,
                "content": "",
                "statusMessages": [],
                "toolCalls": [],
            }
            for tool_call in tool_calls:
                args = normalize_tool_call_arguments(
                    tool_call.get("args")
                    or tool_call.get("arguments")
                    or ((tool_call.get("function") or {}).get("arguments"))
                )
                command = str(args.get("command") or "").strip()
                if not command:
                    continue
                tool_label = f"bash: {command}"
                post_dispatch_event(
                    config=config,
                    dispatch_id=dispatch_id,
                    event_type="tool_call",
                    payload={"type": "tool_call", "content": tool_label},
                )
                ok, tool_output = execute_bash_tool(
                    workspace_root=workspace_root,
                    command=command,
                )
                event_type = "tool_result" if ok else "tool_error"
                post_dispatch_event(
                    config=config,
                    dispatch_id=dispatch_id,
                    event_type=event_type,
                    payload={"type": event_type, "content": tool_output},
                )
                round_record["toolCalls"].append(
                    {
                        "name": "bash",
                        "arguments": {"command": command},
                        "success": ok,
                        "result": tool_output,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "content": tool_output,
                        "tool_call_id": str(tool_call.get("id") or ""),
                    }
                )
            if usage:
                round_record["stats"] = usage
            rounds.append(round_record)
            continue

        final_output = content.strip()
        if final_output:
            post_dispatch_event(
                config=config,
                dispatch_id=dispatch_id,
                event_type="content",
                payload={"type": "content", "content": final_output},
            )
        result_payload = {
            "assistant_message": final_output,
            "final_output": final_output,
            "usage": usage,
            "finish_reason": finish_reason,
            "rounds": rounds,
            "workspace_root": str(workspace_root),
            "artifacts": collect_workspace_artifacts(workspace_root),
        }
        return True, result_payload, None, None

    return (
        False,
        {
            "assistant_message": "",
            "rounds": rounds,
            "workspace_root": str(workspace_root),
        },
        "Runtime Host exceeded the maximum native tool iterations.",
        None,
    )


def execute_dispatch(
    dispatch: dict[str, Any],
    config: dict[str, Any],
    *,
    config_path: Path,
) -> tuple[
    bool,
    dict[str, Any],
    str | None,
    Literal["reexec", "unregister_and_shutdown"] | None,
]:
    request_payload = dispatch.get("request_payload") or {}
    control_action = str(request_payload.get("control_action") or "").strip().lower()
    if control_action == "update_runtime":
        ok, result_payload, error_message = perform_self_update(
            config=config,
            config_path=config_path,
        )
        return ok, result_payload, error_message, ("reexec" if ok else None)
    if control_action == "uninstall_runtime":
        return (
            True,
            {
                "mode": "uninstall_runtime",
                "restart_required": False,
                "cleanup_required": True,
            },
            None,
            "unregister_and_shutdown",
        )
    source_type = str(dispatch.get("source_type") or "").strip().lower()
    dispatch_id = str(dispatch.get("dispatch_id") or "dispatch")
    if source_type == "conversation_turn":
        conversation_id = str(request_payload.get("conversation_id") or "").strip() or dispatch_id
        workspace_root = (
            Path(str(config.get("runtime_home") or Path(gettempdir()) / "linx-external-runtime"))
            / "workspaces"
            / "conversations"
            / conversation_id
            / "workspace"
        )
        restored_generation = restore_conversation_workspace_if_needed(
            config=config,
            conversation_id=conversation_id,
            workspace_root=workspace_root,
        )
        if restored_generation is not None:
            post_dispatch_event(
                config=config,
                dispatch_id=dispatch_id,
                event_type="info",
                payload={
                    "type": "info",
                    "content": (
                        f"Restored conversation workspace snapshot generation {restored_generation} "
                        "from the control plane."
                    ),
                },
            )
        hydrated_attachments = hydrate_conversation_attachments(
            config=config,
            attachments=list(request_payload.get("attachments") or []),
            workspace_root=workspace_root,
        )
        if hydrated_attachments:
            post_dispatch_event(
                config=config,
                dispatch_id=dispatch_id,
                event_type="info",
                payload={
                    "type": "info",
                    "content": (
                        f"Downloaded {hydrated_attachments} attachment file(s) into "
                        "/workspace/input/ on the Runtime Host."
                    ),
                },
            )
        system_prompt = str(request_payload.get("system_prompt") or "").strip()
        if system_prompt:
            system_prompt = (
                f"{system_prompt}\n\n"
                "You are executing on the user's bound Runtime Host. "
                "Use the bash tool whenever you need to inspect or modify files on this machine. "
                "Do not claim file changes unless you executed the necessary commands."
            )
        else:
            system_prompt = (
                "You are LinX's native external agent executor running on the user's Runtime Host. "
                "Use the bash tool whenever local host access is needed. "
                "Do not claim file changes unless you executed the necessary commands."
            )
        ok, result_payload, error_message, followup_action = run_native_agent_loop(
            dispatch=dispatch,
            config=config,
            workspace_root=workspace_root,
            system_prompt=system_prompt,
            history=list(request_payload.get("conversation_history") or []),
            current_message=dict(request_payload.get("current_message") or {"role": "user", "content": ""}),
            temperature=request_payload.get("temperature"),
            max_tokens=request_payload.get("max_tokens"),
        )
        if ok:
            snapshot_payload = upload_conversation_workspace_snapshot(
                config=config,
                conversation_id=conversation_id,
                workspace_root=workspace_root,
            )
            snapshot_generation = int((snapshot_payload or {}).get("generation") or 0)
            result_payload["snapshot_generation"] = snapshot_generation
            if snapshot_generation:
                post_dispatch_event(
                    config=config,
                    dispatch_id=dispatch_id,
                    event_type="info",
                    payload={
                        "type": "info",
                        "content": (
                            f"Uploaded conversation workspace snapshot generation {snapshot_generation} "
                            "to the control plane."
                        ),
                    },
                )
        return ok, result_payload, error_message, followup_action
    if source_type == "project_run_step":
        prompt = str(request_payload.get("execution_prompt") or "").strip()
        run_id = str(request_payload.get("run_id") or dispatch_id).strip() or dispatch_id
        workspace_root = (
            Path(str(config.get("runtime_home") or Path(gettempdir()) / "linx-external-runtime"))
            / "workspaces"
            / "runs"
            / run_id
            / "workspace"
        )
        restored_run_workspace = restore_run_workspace_if_needed(
            config=config,
            run_id=run_id,
            workspace_root=workspace_root,
        )
        if restored_run_workspace:
            post_dispatch_event(
                config=config,
                dispatch_id=dispatch_id,
                event_type="info",
                payload={
                    "type": "info",
                    "content": "Restored project run workspace from the control plane.",
                },
            )
        write_prompt_file(workspace_root, dispatch_id, prompt)
        system_prompt = (
            "You are LinX's native external project executor running on the target Runtime Host. "
            "Work inside the provided workspace root. Use the bash tool for file inspection, edits, "
            "and local validation. Produce the requested project step result directly on this machine."
        )
        ok, result_payload, error_message, followup_action = run_native_agent_loop(
            dispatch=dispatch,
            config=config,
            workspace_root=workspace_root,
            system_prompt=system_prompt,
            history=[],
            current_message={"role": "user", "content": prompt},
            temperature=request_payload.get("temperature"),
            max_tokens=request_payload.get("max_tokens"),
        )
        if ok:
            upload_run_workspace_snapshot(
                config=config,
                run_id=run_id,
                workspace_root=workspace_root,
            )
            post_dispatch_event(
                config=config,
                dispatch_id=dispatch_id,
                event_type="info",
                payload={
                    "type": "info",
                    "content": "Uploaded updated project run workspace to the control plane.",
                },
            )
        return ok, result_payload, error_message, followup_action

    launch_command_template = str(request_payload.get("launch_command_template") or "").strip()
    if not launch_command_template:
        return (
            False,
            {
                "mode": "native_executor",
                "lease_note": "Dispatch source type is not supported by this Runtime Host.",
            },
            "Dispatch source type is not supported by this Runtime Host.",
            None,
        )

    prompt = str(request_payload.get("execution_prompt") or "").strip()
    workspace_root = Path(
        str(request_payload.get("run_workspace_root") or Path(gettempdir()) / "linx-external-runtime")
    )
    workspace_root.mkdir(parents=True, exist_ok=True)
    prompt_file = write_prompt_file(workspace_root, dispatch_id, prompt)
    env = os.environ.copy()
    env.update(
        {
            "LINX_AGENT_PROMPT": prompt,
            "LINX_AGENT_PROMPT_FILE": str(prompt_file),
            "LINX_AGENT_ID": str(dispatch.get("agent_id") or config.get("agent_id") or ""),
            "LINX_AGENT_NAME": str(request_payload.get("agent_name") or ""),
            "LINX_AGENT_RUNTIME_TYPE": str(dispatch.get("runtime_type") or ""),
            "LINX_PROJECT_ID": str(request_payload.get("project_id") or ""),
            "LINX_RUN_ID": str(request_payload.get("run_id") or ""),
            "LINX_RUN_STEP_ID": str(request_payload.get("run_step_id") or ""),
            "LINX_WORKSPACE_ROOT": str(workspace_root),
            "LINX_AGENT_DISPATCH_ID": dispatch_id,
            "LINX_AGENT_TASK_TITLE": str(request_payload.get("task_title") or ""),
        }
    )
    process = subprocess.run(
        launch_command_template,
        cwd=str(workspace_root),
        shell=True,
        text=True,
        capture_output=True,
        timeout=1800,
        env=env,
    )
    result_payload = {
        "mode": "launch_command_template",
        "launch_command_template": launch_command_template,
        "launch_command_source": request_payload.get("launch_command_source"),
        "returncode": process.returncode,
        "stdout": process.stdout[-MAX_CAPTURE_CHARS:],
        "stderr": process.stderr[-MAX_CAPTURE_CHARS:],
        "workspace_root": str(workspace_root),
        "prompt_file": str(prompt_file),
    }
    if process.returncode != 0:
        return False, result_payload, f"Launch command exited with {process.returncode}", None
    return True, result_payload, None, None


def perform_self_update(
    *,
    config: dict[str, Any],
    config_path: Path,
) -> tuple[bool, dict[str, Any], str | None]:
    control_plane = str(config.get("control_plane") or "").rstrip("/")
    host_os = normalize_os_name(str(config.get("host_os") or ""))
    host_arch = normalize_arch_name(str(config.get("host_arch") or ""))
    manifest_url = f"{control_plane}/api/v1/external-runtime/artifacts/manifest"
    _status, manifest = request_json(url=manifest_url, timeout=30)
    artifacts = (manifest or {}).get("artifacts") or []
    artifact = next(
        (
            record
            for record in artifacts
            if record.get("os") == host_os and record.get("arch") == host_arch
        ),
        None,
    )
    if artifact is None:
        return False, {"mode": "update_runtime"}, f"Artifact not found for {host_os}/{host_arch}"

    runtime_home = Path(str(config.get("runtime_home") or Path(sys.argv[0]).resolve().parent.parent))
    download_dir = runtime_home / "download"
    extract_dir = download_dir / "extracted"
    download_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = download_dir / (
        "runtime.zip" if host_os == "windows" else "runtime.tar.gz"
    )

    urllib.request.urlretrieve(str(artifact["download_path"]), artifact_path)
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    if digest != str(artifact.get("sha256") or ""):
        return False, {"mode": "update_runtime"}, "Downloaded artifact checksum mismatch"

    if extract_dir.exists():
        for child in extract_dir.iterdir():
            if child.is_dir():
                for nested in child.rglob("*"):
                    if nested.is_file():
                        nested.unlink()
                for nested in sorted(child.rglob("*"), reverse=True):
                    if nested.is_dir():
                        nested.rmdir()
                child.rmdir()
            else:
                child.unlink()
    extract_dir.mkdir(parents=True, exist_ok=True)
    if host_os == "windows":
        with zipfile.ZipFile(artifact_path, "r") as archive:
            archive.extractall(extract_dir)
    else:
        with tarfile.open(artifact_path, "r:gz") as archive:
            archive.extractall(extract_dir)

    script_source = next(extract_dir.rglob("linx_external_runtime.py"), None)
    if script_source is None:
        return False, {"mode": "update_runtime"}, "Runtime script was not found inside the downloaded artifact."

    script_path = Path(sys.argv[0]).resolve()
    script_path.write_bytes(script_source.read_bytes())
    script_path.chmod(0o755)
    config["runtime_version"] = str(artifact.get("version") or config.get("runtime_version") or "")
    config["desired_version"] = config["runtime_version"]
    save_json(config_path, config)
    return True, {
        "mode": "update_runtime",
        "updated_version": config["runtime_version"],
        "restart_required": True,
    }, None


def unregister_binding(config: dict[str, Any]) -> None:
    control_plane = str(config.get("control_plane") or "").rstrip("/")
    machine_token = str(config.get("machine_token") or "").strip()
    if not control_plane or not machine_token:
        return
    request_json(
        url=f"{control_plane}/api/v1/external-runtime/self-unregister",
        method="POST",
        payload={},
        request_headers=headers(machine_token),
        timeout=20,
    )


def post_dispatch_progress(
    *,
    config: dict[str, Any],
    dispatch_id: str,
    suffix: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    url = f"{config['control_plane']}/api/v1/external-runtime/dispatches/{dispatch_id}/{suffix}"
    _status, data = request_json(
        url=url,
        method="POST",
        payload=payload,
        request_headers=headers(str(config["machine_token"])),
        timeout=120,
    )
    return data


def heartbeat(config: dict[str, Any]) -> dict[str, Any] | None:
    payload = {
        "host_name": socket.gethostname(),
        "host_os": normalize_os_name(config.get("host_os")),
        "host_arch": normalize_arch_name(config.get("host_arch")),
        "host_fingerprint": detect_host_fingerprint(),
        "current_version": config.get("runtime_version"),
        "status": "online",
        "metadata": {
            "runtime_home": str(config.get("runtime_home") or ""),
            "local_status_url": str(config.get("local_status_url") or ""),
            "local_status_port": config.get("local_status_port"),
            "last_dispatch_action": config.get("last_dispatch_action"),
            "last_dispatch_status": config.get("last_dispatch_status"),
            "last_dispatch_error_message": config.get("last_dispatch_error_message"),
        },
    }
    url = f"{config['control_plane']}/api/v1/external-runtime/heartbeat"
    _status, data = request_json(
        url=url,
        method="POST",
        payload=payload,
        request_headers=headers(str(config["machine_token"])),
        timeout=60,
    )
    return data


def update_check(config: dict[str, Any]) -> dict[str, Any] | None:
    url = f"{config['control_plane']}/api/v1/external-runtime/update-check"
    _status, data = request_json(
        url=url,
        request_headers=headers(str(config["machine_token"])),
        timeout=30,
    )
    return data


def next_dispatch(config: dict[str, Any]) -> dict[str, Any] | None:
    url = f"{config['control_plane']}/api/v1/external-runtime/dispatches/next"
    status, data = request_json(
        url=url,
        request_headers=headers(str(config["machine_token"])),
        timeout=30,
        allow_statuses={404},
    )
    if status == 404:
        return None
    return data


def write_state(config_path: Path, payload: dict[str, Any]) -> None:
    save_json(state_path_for(config_path), payload)


def merge_state(config_path: Path, patch: dict[str, Any]) -> None:
    current = {}
    state_path = state_path_for(config_path)
    if state_path.exists():
        try:
            current = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    current.update(patch)
    write_state(config_path, current)


def run() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    if not config.get("python_executable"):
        config["python_executable"] = sys.executable
    server, local_status_url, local_status_port = start_local_status_server(config_path, config)
    save_json(config_path, config)
    write_state(
        config_path,
        {
            "status": "starting",
            "started_at": time.time(),
            "local_status_url": local_status_url,
            "local_status_port": local_status_port,
        },
    )
    last_update_check = 0.0
    update_check_interval = max(int(config.get("heartbeat_interval_seconds") or 20) * 30, 300)

    while True:
        try:
            heartbeat_response = heartbeat(config)
            heartbeat_interval = int(
                (heartbeat_response or {}).get("heartbeat_interval_seconds")
                or config.get("heartbeat_interval_seconds")
                or 20
            )
            config["heartbeat_interval_seconds"] = heartbeat_interval
            merge_state(
                config_path,
                {
                    "status": "online",
                    "last_heartbeat_at": time.time(),
                    "update_available": bool((heartbeat_response or {}).get("update_available")),
                    "desired_version": (heartbeat_response or {}).get("desired_version"),
                    "local_status_url": local_status_url,
                    "local_status_port": local_status_port,
                },
            )
            if time.time() - last_update_check >= update_check_interval:
                last_update_check = time.time()
                update_response = update_check(config) or {}
                merge_state(
                    config_path,
                    {
                        "status": "online",
                        "last_heartbeat_at": time.time(),
                        "update_available": bool(update_response.get("update_available")),
                        "desired_version": update_response.get("desired_version"),
                        "local_status_url": local_status_url,
                        "local_status_port": local_status_port,
                    },
                )
            dispatch = next_dispatch(config)
            if dispatch is None:
                time.sleep(int(config.get("dispatch_poll_interval_seconds") or 25))
                continue
            dispatch_id = str(dispatch.get("dispatch_id"))
            request_payload = dispatch.get("request_payload") or {}
            merge_state(
                config_path,
                {
                    "last_dispatch_id": dispatch_id,
                    "last_dispatch_action": str(
                        request_payload.get("control_action")
                        or request_payload.get("task_title")
                        or dispatch.get("source_type")
                        or "dispatch"
                    ),
                    "last_dispatch_status": "acked",
                    "last_dispatch_started_at": time.time(),
                    "last_dispatch_error_message": None,
                },
            )
            config["last_dispatch_action"] = str(
                request_payload.get("control_action")
                or request_payload.get("task_title")
                or dispatch.get("source_type")
                or "dispatch"
            )
            config["last_dispatch_status"] = "acked"
            config["last_dispatch_error_message"] = None
            post_dispatch_progress(
                config=config,
                dispatch_id=dispatch_id,
                suffix="ack",
                payload={"status": "acked", "result_payload": {"connected": True}},
            )
            post_dispatch_progress(
                config=config,
                dispatch_id=dispatch_id,
                suffix="progress",
                payload={"status": "running", "result_payload": {}},
            )
            merge_state(
                config_path,
                {
                    "last_dispatch_status": "running",
                },
            )
            config["last_dispatch_status"] = "running"
            ok, result_payload, error_message, followup_action = execute_dispatch(
                dispatch,
                config,
                config_path=config_path,
            )
            if ok:
                post_dispatch_progress(
                    config=config,
                    dispatch_id=dispatch_id,
                    suffix="complete",
                    payload={"status": "completed", "result_payload": result_payload},
                )
                merge_state(
                    config_path,
                    {
                        "last_dispatch_status": "completed",
                        "last_dispatch_completed_at": time.time(),
                        "last_dispatch_error_message": None,
                    },
                )
                config["last_dispatch_status"] = "completed"
                config["last_dispatch_error_message"] = None
                if followup_action == "reexec":
                    os.execv(
                        str(config.get("python_executable") or sys.executable),
                        [
                            str(config.get("python_executable") or sys.executable),
                            str(Path(sys.argv[0]).resolve()),
                            "--config",
                            str(config_path),
                        ],
                    )
                if followup_action == "unregister_and_shutdown":
                    unregister_binding(config)
                    config["machine_token"] = ""
                    save_json(config_path, config)
                    merge_state(
                        config_path,
                        {
                            "status": "stopped",
                            "stopped_at": time.time(),
                            "last_dispatch_status": "completed",
                            "last_dispatch_error_message": None,
                        },
                    )
                    server.shutdown()
                    return 0
            else:
                post_dispatch_progress(
                    config=config,
                    dispatch_id=dispatch_id,
                    suffix="fail",
                    payload={
                        "status": "failed",
                        "result_payload": result_payload,
                        "error_message": error_message,
                    },
                )
                merge_state(
                    config_path,
                    {
                        "last_dispatch_status": "failed",
                        "last_dispatch_completed_at": time.time(),
                        "last_dispatch_error_message": error_message,
                    },
                )
                config["last_dispatch_status"] = "failed"
                config["last_dispatch_error_message"] = error_message
        except FatalRuntimeStop as exc:
            merge_state(
                config_path,
                {
                    "status": "stopped",
                    "stopped_at": time.time(),
                    "last_error_message": str(exc),
                    "local_status_url": local_status_url,
                    "local_status_port": local_status_port,
                },
            )
            server.shutdown()
            return 0
        except Exception as exc:  # pragma: no cover - defensive runtime loop
            merge_state(
                config_path,
                {
                    "status": "error",
                    "last_error_message": str(exc),
                    "failed_at": time.time(),
                    "local_status_url": local_status_url,
                    "local_status_port": local_status_port,
                },
            )
            time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(run())
