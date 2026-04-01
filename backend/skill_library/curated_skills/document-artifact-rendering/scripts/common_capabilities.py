from __future__ import annotations

import importlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable

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


def load_capabilities(path: str | None = None) -> Dict[str, Any]:
    capability_path = Path(path or DEFAULT_CAPABILITY_SNAPSHOT_PATH)
    if capability_path.exists():
        return json.loads(capability_path.read_text(encoding="utf-8"))
    return probe_capabilities()


def probe_capabilities() -> Dict[str, Any]:
    commands = {}
    for name in ("python3", "pip", "fc-list", "pandoc", "libreoffice"):
        binary = shutil.which(name)
        commands[name] = {
            "available": bool(binary),
            "path": binary,
            "version": _command_version(name) if binary else None,
        }

    python_modules = {}
    for module_name in ("reportlab", "pypdf", "pdfplumber"):
        try:
            module = importlib.import_module(module_name)
            python_modules[module_name] = {
                "available": True,
                "version": getattr(module, "__version__", None),
            }
        except Exception as exc:
            python_modules[module_name] = {
                "available": False,
                "version": None,
                "error": str(exc),
            }

    fonts = {
        "recommended_sans": _available_fonts(DEFAULT_PREFERRED_CJK_SANS) or list(DEFAULT_PREFERRED_CJK_SANS),
        "recommended_serif": _available_fonts(DEFAULT_PREFERRED_CJK_SERIF) or list(DEFAULT_PREFERRED_CJK_SERIF),
    }

    return {
        "version": "1",
        "sandbox": {
            "workspace_root": "/workspace",
        },
        "python_runtime": {
            "executable": shutil.which("python3") or "python3",
            "pip_target": "/opt/linx_python_deps",
            "pythonpath": "/opt/linx_python_deps",
            "python_nousersite": True,
        },
        "commands": commands,
        "python_modules": python_modules,
        "fonts": fonts,
        "renderers": {
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
                "input_extensions": [".txt", ".json", ".csv"],
            },
        },
        "verifiers": {
            "pdf_text_extractors": [
                name for name in ("pypdf", "pdfplumber") if python_modules[name]["available"]
            ]
        },
    }


def get_renderers(capabilities: Dict[str, Any]) -> Dict[str, Any]:
    return dict(capabilities.get("renderers") or {})


def first_available_font(capabilities: Dict[str, Any], preferred_key: str = "recommended_sans") -> str | None:
    fonts = capabilities.get("fonts") or {}
    for family in fonts.get(preferred_key) or []:
        if resolve_font_path(family):
            return family
    fallback_candidates = DEFAULT_PREFERRED_CJK_SANS if preferred_key == "recommended_sans" else DEFAULT_PREFERRED_CJK_SERIF
    for family in fallback_candidates:
        if resolve_font_path(family):
            return family
    return None


def resolve_font_path(font_family: str) -> str | None:
    if not font_family or not shutil.which("fc-match"):
        return None
    result = subprocess.run(
        ["fc-match", "-f", "%{file}\n", font_family],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    path = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    return path or None


def list_available_renderers(capabilities: Dict[str, Any]) -> list[str]:
    return [
        name
        for name, details in get_renderers(capabilities).items()
        if isinstance(details, dict) and details.get("available")
    ]


def _command_version(name: str) -> str | None:
    try:
        result = subprocess.run(
            [name, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else None


def _available_fonts(candidates: Iterable[str]) -> list[str]:
    available = []
    for family in candidates:
        if resolve_font_path(family):
            available.append(family)
    return available
