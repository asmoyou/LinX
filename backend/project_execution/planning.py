from __future__ import annotations

from typing import Any, Optional


def normalize_execution_mode(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"project_sandbox", "external_runtime"}:
        return normalized
    return "auto"


def infer_step_kind(title: str, description: Optional[str], execution_mode: Optional[str] = None) -> str:
    normalized_execution_mode = normalize_execution_mode(execution_mode)
    if normalized_execution_mode == "external_runtime":
        return "host_action"
    combined = f"{title} {description or ''}".lower()
    host_keywords = ["deploy", "docker", "ssh", "terminal", "服务器", "宿主机", "browser", "浏览器"]
    if normalized_execution_mode != "project_sandbox" and any(keyword in combined for keyword in host_keywords):
        return "host_action"
    if any(keyword in combined for keyword in ["review", "评审", "审查", "检查", "verify", "验证", "测试"]):
        return "review"
    if any(keyword in combined for keyword in ["write", "文档", "攻略", "总结", "方案", "plan", "计划"]):
        return "writing"
    if any(keyword in combined for keyword in ["research", "调研", "搜索", "旅游", "分析", "调查"]):
        return "research"
    return "implementation"


def is_complex_task(title: str, description: Optional[str]) -> bool:
    combined = f"{title} {description or ''}"
    complexity_markers = ["并且", "然后", "以及", "同时", "review", "验证", "部署", "方案", "研究", "research"]
    return len(combined) > 120 or any(marker.lower() in combined.lower() for marker in complexity_markers)


def build_step_definitions(
    title: str,
    description: Optional[str],
    execution_mode: Optional[str] = None,
) -> list[dict[str, Any]]:
    normalized_execution_mode = normalize_execution_mode(execution_mode)
    first_kind = infer_step_kind(title, description, execution_mode=normalized_execution_mode)
    if first_kind == "host_action":
        return [
            {
                "name": title,
                "step_kind": "host_action",
                "executor_kind": "execution_node",
                "sequence": 0,
                "execution_mode": normalized_execution_mode,
            }
        ]
    if not is_complex_task(title, description):
        return [
            {
                "name": title,
                "step_kind": first_kind,
                "executor_kind": "agent",
                "sequence": 0,
                "execution_mode": normalized_execution_mode,
            }
        ]
    middle_kind = "writing" if first_kind == "research" else first_kind
    return [
        {
            "name": f"Research: {title}",
            "step_kind": "research",
            "executor_kind": "agent",
            "sequence": 0,
            "execution_mode": normalized_execution_mode,
        },
        {
            "name": title,
            "step_kind": middle_kind,
            "executor_kind": "agent",
            "sequence": 1,
            "execution_mode": normalized_execution_mode,
        },
        {
            "name": f"Review: {title}",
            "step_kind": "review",
            "executor_kind": "agent",
            "sequence": 2,
            "execution_mode": normalized_execution_mode,
        },
    ]
