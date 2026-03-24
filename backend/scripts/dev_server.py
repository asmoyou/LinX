#!/usr/bin/env python3
"""Developer-friendly wrapper around local API Gateway startup."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

from shared.runtime_env import bootstrap_runtime_env

bootstrap_runtime_env()

from shared.config import get_config

APP_PATH = "api_gateway.main:app"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_HEALTH_URL = f"http://localhost:{DEFAULT_PORT}/health"
DEFAULT_LOG_FILE = BACKEND_ROOT / "backend.log"
STARTUP_TIMEOUT_SECONDS = 45


@dataclass(slots=True)
class DependencyCheck:
    name: str
    host: str
    port: int
    required: bool
    reachable: bool
    detail: str


def _can_connect(host: str, port: int, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "reachable"
    except OSError as exc:
        return False, str(exc)


def _parse_endpoint(endpoint: str, default_port: int) -> tuple[str, int]:
    if "://" in endpoint:
        endpoint = endpoint.split("://", 1)[1]
    if "/" in endpoint:
        endpoint = endpoint.split("/", 1)[0]
    host, sep, port_text = endpoint.partition(":")
    if not host:
        return "localhost", default_port
    if not sep:
        return host, default_port
    try:
        return host, int(port_text)
    except ValueError:
        return host, default_port


def _collect_dependency_checks() -> list[DependencyCheck]:
    config = get_config()
    checks: list[DependencyCheck] = []

    postgres = config.get_section("database.postgres") or {}
    redis = config.get_section("database.redis") or {}
    milvus = config.get_section("database.milvus") or {}
    minio = config.get_section("storage.minio") or {}

    services = [
        ("PostgreSQL", postgres.get("host", "localhost"), int(postgres.get("port", 5432)), True),
        ("Redis", redis.get("host", "localhost"), int(redis.get("port", 6379)), False),
        ("Milvus", milvus.get("host", "localhost"), int(milvus.get("port", 19530)), False),
    ]

    for name, host, port, required in services:
        reachable, detail = _can_connect(str(host), port)
        checks.append(
            DependencyCheck(
                name=name,
                host=str(host),
                port=port,
                required=required,
                reachable=reachable,
                detail=detail,
            )
        )

    minio_endpoint = str(minio.get("endpoint", "localhost:9000"))
    minio_host, minio_port = _parse_endpoint(minio_endpoint, 9000)
    reachable, detail = _can_connect(minio_host, minio_port)
    checks.append(
        DependencyCheck(
            name="MinIO",
            host=minio_host,
            port=minio_port,
            required=False,
            reachable=reachable,
            detail=detail,
        )
    )

    return checks


def _health_summary(health_url: str = DEFAULT_HEALTH_URL) -> tuple[bool, str]:
    try:
        with urlopen(health_url, timeout=2) as response:
            payload = response.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            body = payload
        return True, f"healthy at {health_url}: {body}"
    except Exception as exc:  # pragma: no cover - exercised via CLI
        return False, str(exc)


def _port_in_use(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    reachable, _ = _can_connect(probe_host, port, timeout=0.5)
    return reachable


def _print_checks(checks: Iterable[DependencyCheck]) -> tuple[bool, bool]:
    has_blocker = False
    has_warning = False
    print("Dependency preflight:")
    for check in checks:
        if check.reachable:
            print(f"  [OK] {check.name:<10} {check.host}:{check.port}")
            continue

        label = "ERROR" if check.required else "WARN "
        if check.required:
            has_blocker = True
        else:
            has_warning = True
        print(f"  [{label}] {check.name:<10} {check.host}:{check.port} ({check.detail})")
    return has_blocker, has_warning


def run_preflight(host: str, port: int, health_url: str) -> int:
    checks = _collect_dependency_checks()
    has_blocker, has_warning = _print_checks(checks)

    if _port_in_use(host, port):
        healthy, detail = _health_summary(health_url)
        if healthy:
            print(f"  [ERROR] API port {port} is already serving traffic: {detail}")
        else:
            print(f"  [ERROR] API port {port} is already occupied and health check failed: {detail}")
        has_blocker = True

    if has_blocker:
        print("Preflight failed. Fix the blocking items above before starting the backend.")
        return 1

    if has_warning:
        print("Preflight passed with warnings. Startup will continue, but some features may degrade.")
    else:
        print("Preflight passed.")
    return 0


def _tail_lines(path: Path, line_count: int = 40) -> list[str]:
    if not path.exists():
        return [f"<missing log file: {path}>"]

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [f"<failed to read log file: {exc}>"]
    return lines[-line_count:]


def _build_uvicorn_command(host: str, port: int, log_level: str, reload_enabled: bool) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        APP_PATH,
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        log_level,
    ]
    if reload_enabled:
        command.append("--reload")
    return command


def run_console(args: argparse.Namespace) -> int:
    if run_preflight(args.host, args.port, args.health_url) != 0:
        return 1

    command = _build_uvicorn_command(args.host, args.port, args.log_level, reload_enabled=True)
    print(f"Starting API Gateway in foreground on http://localhost:{args.port}")
    return subprocess.run(command, cwd=BACKEND_ROOT).returncode


def run_log_mode(args: argparse.Namespace) -> int:
    if run_preflight(args.host, args.port, args.health_url) != 0:
        return 1

    log_path = Path(args.log_file).resolve()
    command = _build_uvicorn_command(args.host, args.port, args.log_level, reload_enabled=True)

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n=== Starting local backend at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        log_file.flush()
        process = subprocess.Popen(
            command,
            cwd=BACKEND_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    print(f"Started API Gateway logging to {log_path}")
    print(f"Waiting for health check at {args.health_url} ...")

    deadline = time.time() + args.startup_timeout
    while time.time() < deadline:
        if process.poll() is not None:
            print(f"Backend exited during startup with code {process.returncode}.")
            print("Recent log output:")
            for line in _tail_lines(log_path):
                print(f"  {line}")
            return process.returncode or 1

        healthy, detail = _health_summary(args.health_url)
        if healthy:
            print(f"Backend is ready. {detail}")
            print(f"PID: {process.pid}")
            print(f"Logs: tail -f {log_path}")
            return 0
        time.sleep(1)

    print("Backend process is still running, but the health endpoint did not become ready in time.")
    print("Recent log output:")
    for line in _tail_lines(log_path):
        print(f"  {line}")
    return 1


def run_status(args: argparse.Namespace) -> int:
    healthy, detail = _health_summary(args.health_url)
    if healthy:
        print(f"Backend status: {detail}")
        return 0

    print(f"Backend status: unavailable ({detail})")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--host", default=DEFAULT_HOST)
    common.add_argument("--port", type=int, default=DEFAULT_PORT)
    common.add_argument("--health-url", default=DEFAULT_HEALTH_URL)

    preflight_parser = subparsers.add_parser("preflight", parents=[common])
    preflight_parser.set_defaults(handler=run_preflight)

    console_parser = subparsers.add_parser("console", parents=[common])
    console_parser.add_argument("--log-level", default="info")
    console_parser.set_defaults(handler=run_console)

    log_parser = subparsers.add_parser("log", parents=[common])
    log_parser.add_argument("--log-level", default="debug")
    log_parser.add_argument("--log-file", default=str(DEFAULT_LOG_FILE))
    log_parser.add_argument("--startup-timeout", type=int, default=STARTUP_TIMEOUT_SECONDS)
    log_parser.set_defaults(handler=run_log_mode)

    status_parser = subparsers.add_parser("status", parents=[common])
    status_parser.set_defaults(handler=run_status)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "preflight":
        return args.handler(args.host, args.port, args.health_url)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
