"""Sandbox capability probing and snapshot persistence helpers."""

from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from shared.datetime_utils import utcnow
from virtualization.container_manager import get_container_manager
from virtualization.sandbox_runtime_env import build_python_runtime_summary, build_sandbox_runtime_env

logger = logging.getLogger(__name__)

CAPABILITY_SNAPSHOT_VERSION = "1"
DEFAULT_CAPABILITY_SNAPSHOT_PATH = "/workspace/.linx_runtime/capabilities.json"
DEFAULT_PREFERRED_CJK_SANS = [
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei",
]
DEFAULT_PREFERRED_CJK_SERIF = [
    "Noto Serif CJK SC",
    "AR PL UMing CN",
]
DEFAULT_FONT_ALIASES = {
    "SimHei": ["Noto Sans CJK SC", "WenQuanYi Zen Hei"],
    "SimSun": ["Noto Serif CJK SC", "AR PL UMing CN"],
    "Microsoft YaHei": ["WenQuanYi Micro Hei", "Noto Sans CJK SC"],
    "PingFang SC": ["Noto Sans CJK SC"],
}


def build_document_toolchain_summary(snapshot: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Build prompt-friendly document toolchain summary."""
    if isinstance(snapshot, Mapping):
        renderers = snapshot.get("renderers") or {}
        fonts = snapshot.get("fonts") or {}
        commands = snapshot.get("commands") or {}
        available_renderers = [
            name for name, details in renderers.items() if isinstance(details, Mapping) and details.get("available")
        ]
        available_commands = [
            name for name, details in commands.items() if isinstance(details, Mapping) and details.get("available")
        ]
        preferred_fonts = list(fonts.get("recommended_sans") or DEFAULT_PREFERRED_CJK_SANS)
    else:
        available_renderers = ["libreoffice_pdf", "pandoc_docx_bridge", "reportlab_text_pdf"]
        available_commands = ["python3", "pip", "fc-list", "pandoc", "libreoffice"]
        preferred_fonts = list(DEFAULT_PREFERRED_CJK_SANS)

    return {
        "renderers": available_renderers,
        "preferred_cjk_fonts": preferred_fonts,
        "commands": available_commands,
    }


def _probe_command(container_manager, container_id: str, command_name: str) -> Dict[str, Any]:
    shell_command = (
        "command -v {name} >/dev/null 2>&1 || exit 42; "
        "path=$(command -v {name}); "
        "version=$({name} --version 2>/dev/null | head -n 1 || true); "
        'printf "%s\\n%s" "$path" "$version"'
    ).format(name=shlex.quote(command_name))
    exit_code, stdout, stderr = container_manager.exec_in_container(
        container_id=container_id,
        command=f"/bin/sh -lc {shlex.quote(shell_command)}",
    )
    if exit_code != 0:
        return {
            "available": False,
            "path": None,
            "version": None,
            "error": (stderr or stdout or "").strip() or None,
        }
    lines = (stdout or "").splitlines()
    return {
        "available": True,
        "path": lines[0].strip() if lines else None,
        "version": lines[1].strip() if len(lines) > 1 else None,
    }


def _probe_python_module(
    container_manager,
    container_id: str,
    module_name: str,
    *,
    runtime_environment: Optional[Mapping[str, object]] = None,
) -> Dict[str, Any]:
    python_code = (
        "import importlib, json\n"
        f"module = importlib.import_module({module_name!r})\n"
        "print(json.dumps({'version': getattr(module, '__version__', None)}))\n"
    )
    exit_code, stdout, stderr = container_manager.exec_in_container(
        container_id=container_id,
        command=f"python3 -c {shlex.quote(python_code)}",
        environment=build_sandbox_runtime_env(runtime_environment),
    )
    if exit_code != 0:
        return {
            "available": False,
            "version": None,
            "error": (stderr or stdout or "").strip() or None,
        }

    try:
        payload = json.loads((stdout or "{}").strip())
    except json.JSONDecodeError:
        payload = {}
    return {
        "available": True,
        "version": payload.get("version"),
    }


def _probe_font_families(container_manager, container_id: str) -> Dict[str, Any]:
    exit_code, stdout, stderr = container_manager.exec_in_container(
        container_id=container_id,
        command="/bin/sh -lc 'fc-list : family 2>/dev/null || true'",
    )
    available_families = set()
    if exit_code == 0 and stdout:
        for line in stdout.splitlines():
            for family in line.split(","):
                normalized = family.strip()
                if normalized:
                    available_families.add(normalized)

    preferred_sans = [family for family in DEFAULT_PREFERRED_CJK_SANS if family in available_families]
    preferred_serif = [family for family in DEFAULT_PREFERRED_CJK_SERIF if family in available_families]
    if not preferred_sans:
        preferred_sans = list(DEFAULT_PREFERRED_CJK_SANS)
    if not preferred_serif:
        preferred_serif = list(DEFAULT_PREFERRED_CJK_SERIF)

    return {
        "recommended_sans": preferred_sans,
        "recommended_serif": preferred_serif,
        "aliases": DEFAULT_FONT_ALIASES,
        "error": None if exit_code == 0 else (stderr or stdout or "").strip() or None,
    }


def probe_sandbox_capabilities(
    container_id: str,
    *,
    container_manager=None,
    runtime_environment: Optional[Mapping[str, object]] = None,
    sandbox_backend: str = "docker_enhanced",
    workspace_root_virtual: str = "/workspace",
    network_access: bool = True,
) -> Dict[str, Any]:
    """Probe commands/modules/fonts/renderers available in a sandbox container."""
    manager = container_manager or get_container_manager()
    runtime_summary = build_python_runtime_summary(runtime_environment)

    commands = {
        "python3": _probe_command(manager, container_id, "python3"),
        "pip": _probe_command(manager, container_id, "pip"),
        "fc-list": _probe_command(manager, container_id, "fc-list"),
        "pandoc": _probe_command(manager, container_id, "pandoc"),
        "libreoffice": _probe_command(manager, container_id, "libreoffice"),
    }
    python_modules = {
        "reportlab": _probe_python_module(
            manager,
            container_id,
            "reportlab",
            runtime_environment=runtime_environment,
        ),
        "pypdf": _probe_python_module(
            manager,
            container_id,
            "pypdf",
            runtime_environment=runtime_environment,
        ),
        "pdfplumber": _probe_python_module(
            manager,
            container_id,
            "pdfplumber",
            runtime_environment=runtime_environment,
        ),
    }
    fonts = _probe_font_families(manager, container_id)

    renderers = {
        "libreoffice_pdf": {
            "available": bool(commands["libreoffice"]["available"]),
            "input_extensions": [".doc", ".docx", ".ppt", ".pptx", ".odt", ".html", ".htm"],
        },
        "pandoc_docx_bridge": {
            "available": bool(commands["pandoc"]["available"] and commands["libreoffice"]["available"]),
            "input_extensions": [".md", ".markdown"],
        },
        "reportlab_text_pdf": {
            "available": bool(python_modules["reportlab"]["available"]),
            "input_extensions": [".txt", ".md", ".json", ".csv"],
        },
    }
    verifiers = {
        "pdf_text_extractors": [
            name for name in ("pypdf", "pdfplumber") if python_modules[name]["available"]
        ]
    }

    return {
        "version": CAPABILITY_SNAPSHOT_VERSION,
        "generated_at": utcnow().isoformat(),
        "sandbox": {
            "backend": sandbox_backend,
            "workspace_root": workspace_root_virtual,
            "network_access": bool(network_access),
        },
        "python_runtime": runtime_summary,
        "commands": commands,
        "python_modules": python_modules,
        "fonts": fonts,
        "renderers": renderers,
        "verifiers": verifiers,
    }


def write_capability_snapshot(
    container_id: str,
    snapshot: Mapping[str, Any],
    *,
    path: str = DEFAULT_CAPABILITY_SNAPSHOT_PATH,
    container_manager=None,
) -> None:
    """Persist capability snapshot into sandbox workspace."""
    manager = container_manager or get_container_manager()
    parent_dir = str(Path(path).parent)
    manager.exec_in_container(
        container_id=container_id,
        command=f"mkdir -p {parent_dir}",
    )
    manager.write_file_to_container(
        container_id=container_id,
        file_path=path,
        content=json.dumps(dict(snapshot), ensure_ascii=False, indent=2),
        mode=0o644,
    )


def probe_and_write_sandbox_capabilities(
    container_id: str,
    *,
    container_manager=None,
    runtime_environment: Optional[Mapping[str, object]] = None,
    sandbox_backend: str = "docker_enhanced",
    workspace_root_virtual: str = "/workspace",
    network_access: bool = True,
    path: str = DEFAULT_CAPABILITY_SNAPSHOT_PATH,
) -> Dict[str, Any]:
    """Probe current sandbox capabilities and persist the JSON snapshot."""
    snapshot = probe_sandbox_capabilities(
        container_id,
        container_manager=container_manager,
        runtime_environment=runtime_environment,
        sandbox_backend=sandbox_backend,
        workspace_root_virtual=workspace_root_virtual,
        network_access=network_access,
    )
    write_capability_snapshot(
        container_id,
        snapshot,
        path=path,
        container_manager=container_manager,
    )
    return snapshot
