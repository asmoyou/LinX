#!/usr/bin/env python3
"""Evaluate memory retrieval Top-K relevance on a labeled dataset.

Dataset formats:
1) JSON array
2) JSONL (one object per line)

Each case supports these fields:
- case_id: optional stable id
- query: required retrieval query text
- memory_type: optional (agent/company/user_context/task_context), default company
- user_id: optional but recommended for scoped retrieval
- agent_id: optional (required for agent scope in most real runs)
- task_id: optional (task_context scope)
- top_k: optional, default from CLI
- min_similarity: optional float
- expected_memory_ids: optional list[int|str]
- expected_keywords: optional list[str]
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agent_framework.agent_memory_interface import AgentMemoryInterface, get_agent_memory_interface
from memory_system.memory_interface import MemoryType, SearchQuery
from memory_system.memory_system import get_memory_system


def _load_cases(dataset_path: Path) -> List[Dict[str, Any]]:
    raw = dataset_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    if dataset_path.suffix.lower() == ".jsonl":
        cases: List[Dict[str, Any]] = []
        for idx, line in enumerate(raw.splitlines(), start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError(f"Invalid JSONL row {idx}: expected object")
            cases.append(payload)
        return cases

    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("JSON dataset must be a list of case objects")
    cases = [item for item in payload if isinstance(item, dict)]
    return cases


def _coerce_memory_type(raw: Any) -> MemoryType:
    text = str(raw or "company").strip().lower()
    alias_map = {
        "agent_memory": "agent",
        "company_memory": "company",
    }
    normalized = alias_map.get(text, text)
    try:
        return MemoryType(normalized)
    except Exception:
        return MemoryType.COMPANY


def _to_dict(item: Any) -> Dict[str, Any]:
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if isinstance(item, dict):
        return dict(item)
    return {
        "id": getattr(item, "id", None),
        "content": getattr(item, "content", ""),
        "memory_type": getattr(getattr(item, "memory_type", None), "value", None)
        or getattr(item, "memory_type", None),
        "metadata": getattr(item, "metadata", {}) or {},
        "similarity_score": getattr(item, "similarity_score", None),
    }


def _is_relevant(
    item: Dict[str, Any],
    expected_ids: set[str],
    expected_keywords: List[str],
) -> bool:
    item_id = str(item.get("id") or "").strip()
    if expected_ids and item_id in expected_ids:
        return True

    content = str(item.get("content") or "").casefold()
    for keyword in expected_keywords:
        normalized = str(keyword or "").strip().casefold()
        if normalized and normalized in content:
            return True
    return False


def _retrieve_case_results(
    case: Dict[str, Any],
    *,
    default_top_k: int,
    agent_interface: AgentMemoryInterface,
) -> List[Dict[str, Any]]:
    memory_type = _coerce_memory_type(case.get("memory_type"))
    query = str(case.get("query") or "").strip()
    if not query:
        raise ValueError("Case is missing non-empty 'query'")

    top_k = max(int(case.get("top_k") or default_top_k), 1)
    min_similarity = case.get("min_similarity")
    if min_similarity is not None:
        min_similarity = float(min_similarity)

    user_id = case.get("user_id")
    agent_id = case.get("agent_id")
    task_id = case.get("task_id")

    if memory_type == MemoryType.AGENT and agent_id and user_id:
        results = agent_interface.retrieve_agent_memory(
            agent_id=agent_id,
            user_id=user_id,
            query=query,
            top_k=top_k,
            min_similarity=min_similarity,
        )
    elif memory_type == MemoryType.COMPANY and user_id:
        results = agent_interface.retrieve_company_memory(
            user_id=user_id,
            query=query,
            top_k=top_k,
            min_similarity=min_similarity,
        )
    else:
        search_query = SearchQuery(
            query_text=query,
            memory_type=memory_type,
            user_id=str(user_id) if user_id else None,
            agent_id=str(agent_id) if agent_id else None,
            task_id=str(task_id) if task_id else None,
            top_k=top_k,
            min_similarity=min_similarity,
        )
        results = get_memory_system().retrieve_memories(search_query)

    return [_to_dict(item) for item in results[:top_k]]


def _evaluate_cases(cases: List[Dict[str, Any]], *, default_top_k: int) -> Dict[str, Any]:
    agent_interface = get_agent_memory_interface()
    case_reports: List[Dict[str, Any]] = []

    top1_hit_count = 0
    top3_hit_count = 0
    topk_hit_count = 0
    total_expected = 0
    total_relevant_hits = 0
    top3_total_hits = 0
    top3_irrelevant_hits = 0

    source_breakdown: Dict[str, int] = {}

    for idx, case in enumerate(cases, start=1):
        case_id = str(case.get("case_id") or f"case-{idx}")
        expected_ids = {
            str(v).strip() for v in (case.get("expected_memory_ids") or []) if str(v).strip()
        }
        expected_keywords = [
            str(v).strip() for v in (case.get("expected_keywords") or []) if str(v).strip()
        ]
        if not expected_ids and not expected_keywords:
            raise ValueError(
                f"{case_id}: at least one of expected_memory_ids or expected_keywords is required"
            )

        results = _retrieve_case_results(
            case, default_top_k=default_top_k, agent_interface=agent_interface
        )
        relevance_flags = [_is_relevant(item, expected_ids, expected_keywords) for item in results]

        relevant_hits = sum(1 for flag in relevance_flags if flag)
        expected_count = max(len(expected_ids), len(expected_keywords), 1)
        top1_hit = bool(relevance_flags[:1] and relevance_flags[0])
        top3_hit = any(relevance_flags[:3])
        topk_hit = any(relevance_flags)

        if top1_hit:
            top1_hit_count += 1
        if top3_hit:
            top3_hit_count += 1
        if topk_hit:
            topk_hit_count += 1

        total_expected += expected_count
        total_relevant_hits += min(relevant_hits, expected_count)
        top3_total_hits += min(len(results), 3)
        top3_irrelevant_hits += sum(1 for flag in relevance_flags[:3] if not flag)

        for item in results:
            metadata = item.get("metadata") or {}
            source = str(metadata.get("search_method") or "semantic").strip().lower() or "semantic"
            source_breakdown[source] = source_breakdown.get(source, 0) + 1

        case_reports.append(
            {
                "case_id": case_id,
                "query": case.get("query"),
                "memory_type": _coerce_memory_type(case.get("memory_type")).value,
                "expected_memory_ids": sorted(expected_ids),
                "expected_keywords": expected_keywords,
                "top_k": len(results),
                "top1_hit": top1_hit,
                "top3_hit": top3_hit,
                "topk_hit": topk_hit,
                "relevant_hits": relevant_hits,
                "retrieved": [
                    {
                        "id": item.get("id"),
                        "memory_type": item.get("memory_type"),
                        "score": item.get("similarity_score") or item.get("relevance_score"),
                        "source": str(
                            (item.get("metadata") or {}).get("search_method") or "semantic"
                        ),
                        "relevant": relevance_flags[pos],
                        "content_preview": str(item.get("content") or "")[:160],
                    }
                    for pos, item in enumerate(results)
                ],
            }
        )

    total_cases = max(len(cases), 1)
    recall_at_k = total_relevant_hits / max(total_expected, 1)
    top3_irrelevant_rate = top3_irrelevant_hits / max(top3_total_hits, 1)

    return {
        "evaluated_at": datetime.utcnow().isoformat() + "Z",
        "total_cases": len(cases),
        "metrics": {
            "top1_hit_rate": round(top1_hit_count / total_cases, 4),
            "top3_hit_rate": round(top3_hit_count / total_cases, 4),
            "topk_hit_rate": round(topk_hit_count / total_cases, 4),
            "recall_at_k": round(recall_at_k, 4),
            "top3_irrelevant_hit_rate": round(top3_irrelevant_rate, 4),
        },
        "retrieval_source_breakdown": source_breakdown,
        "cases": case_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate memory retrieval Top-K relevance")
    parser.add_argument("--dataset", required=True, help="Path to JSON/JSONL evaluation dataset")
    parser.add_argument("--top-k", type=int, default=5, help="Default top-k when case omits top_k")
    parser.add_argument(
        "--output",
        default="reports/memory_retrieval_topk_report.json",
        help="Output report JSON path",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cases = _load_cases(dataset_path)
    report = _evaluate_cases(cases, default_top_k=max(int(args.top_k), 1))
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "dataset": str(dataset_path),
                "output": str(output_path),
                "total_cases": report["total_cases"],
                "metrics": report["metrics"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
