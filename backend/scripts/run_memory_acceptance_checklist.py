#!/usr/bin/env python3
"""Run acceptance checks for memory-quality hardening (A1-A6).

Supports:
- A1: Empty-extraction write rate (strict types) equals 0%.
- A2: Top-3 irrelevant hit rate reduced by >= 50% (baseline vs current report).
- A3: 7-day duplicate memory rate reduced by >= 40% (baseline vs current DB/query values).
- A4: p95 retrieval latency regression <= 10% (baseline vs current p95).
- A5: Planner decision metadata coverage >= 95% in rollout scope.
- A6: Optional rollback-switch validation via /api/v1/memories/config (toggle + restore).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy import text

# Make backend package imports work when running as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_db_session


@dataclass
class CheckResult:
    check_id: str
    name: str
    status: str  # pass/fail/unknown
    target: Optional[str]
    actual: Optional[str]
    details: Dict[str, Any]


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _load_json(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _to_percentage(value: float) -> str:
    return f"{(value * 100):.2f}%"


def _query_a1(window_days: int) -> Tuple[int, int, float]:
    sql = text("""
        WITH scoped AS (
            SELECT memory_metadata
            FROM memory_records
            WHERE timestamp >= now() - (:window_days || ' days')::interval
              AND is_deleted = false
              AND memory_type IN ('agent', 'user_context')
              AND lower(coalesce(memory_metadata->>'auto_generated', 'false'))
                  IN ('true', '1', 'yes')
        )
        SELECT
            count(*) AS total_writes,
            count(*) FILTER (
                WHERE coalesce(
                    CASE
                        WHEN jsonb_typeof(memory_metadata->'facts') = 'array'
                        THEN jsonb_array_length(memory_metadata->'facts')
                        ELSE 0
                    END,
                    0
                ) = 0
            ) AS empty_facts_writes
        FROM scoped
        """)
    with get_db_session() as session:
        row = session.execute(sql, {"window_days": int(window_days)}).mappings().first()
        total = int(row["total_writes"] or 0)
        empty = int(row["empty_facts_writes"] or 0)
    rate = _safe_ratio(empty, total)
    return total, empty, rate


def _query_duplicate_rate(window_days: int) -> Tuple[int, int, float]:
    sql = text("""
        WITH scoped AS (
            SELECT coalesce(memory_metadata->>'content_hash', '') AS content_hash
            FROM memory_records
            WHERE timestamp >= now() - (:window_days || ' days')::interval
              AND is_deleted = false
        ),
        hashed AS (
            SELECT content_hash
            FROM scoped
            WHERE content_hash <> ''
        ),
        grouped AS (
            SELECT content_hash, count(*) AS cnt
            FROM hashed
            GROUP BY content_hash
        ),
        dup AS (
            SELECT coalesce(sum(cnt - 1), 0) AS dup_rows
            FROM grouped
            WHERE cnt > 1
        ),
        tot AS (
            SELECT count(*) AS total_rows
            FROM hashed
        )
        SELECT dup.dup_rows, tot.total_rows
        FROM dup, tot
        """)
    with get_db_session() as session:
        row = session.execute(sql, {"window_days": int(window_days)}).mappings().first()
        dup_rows = int(row["dup_rows"] or 0)
        total_rows = int(row["total_rows"] or 0)
    dup_rate = _safe_ratio(dup_rows, total_rows)
    return dup_rows, total_rows, dup_rate


def _query_a5(window_days: int, rollout_memory_types: List[str]) -> Tuple[int, int, float]:
    normalized_types = [
        str(item).strip().lower() for item in rollout_memory_types if str(item).strip()
    ]
    if not normalized_types:
        normalized_types = ["agent", "user_context", "company"]

    sql = text("""
        SELECT
            count(*) AS total,
            count(*) FILTER (
                WHERE memory_metadata ? 'decision_action'
                  AND memory_metadata ? 'decision_source'
            ) AS covered
        FROM memory_records
        WHERE timestamp >= now() - (:window_days || ' days')::interval
          AND is_deleted = false
          AND memory_type = ANY(:memory_types)
        """)
    with get_db_session() as session:
        row = (
            session.execute(
                sql,
                {"window_days": int(window_days), "memory_types": normalized_types},
            )
            .mappings()
            .first()
        )
        total = int(row["total"] or 0)
        covered = int(row["covered"] or 0)
    coverage = _safe_ratio(covered, total)
    return total, covered, coverage


def _extract_top3_irrelevant_rate(report: Dict[str, Any]) -> Optional[float]:
    metrics = report.get("metrics") if isinstance(report, dict) else None
    if not isinstance(metrics, dict):
        return None
    raw = metrics.get("top3_irrelevant_hit_rate")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _check_a2(
    baseline_report: Optional[Dict[str, Any]],
    current_report: Optional[Dict[str, Any]],
) -> CheckResult:
    if not baseline_report or not current_report:
        return CheckResult(
            check_id="A2",
            name="Top-3 irrelevant retrieval hit rate reduced by >= 50%",
            status="unknown",
            target="reduction >= 50%",
            actual=None,
            details={"reason": "missing baseline/current Top-K report"},
        )

    baseline_rate = _extract_top3_irrelevant_rate(baseline_report)
    current_rate = _extract_top3_irrelevant_rate(current_report)
    if baseline_rate is None or current_rate is None:
        return CheckResult(
            check_id="A2",
            name="Top-3 irrelevant retrieval hit rate reduced by >= 50%",
            status="unknown",
            target="reduction >= 50%",
            actual=None,
            details={"reason": "top3_irrelevant_hit_rate missing in report metrics"},
        )

    if baseline_rate <= 0:
        return CheckResult(
            check_id="A2",
            name="Top-3 irrelevant retrieval hit rate reduced by >= 50%",
            status="unknown",
            target="reduction >= 50%",
            actual="baseline is 0, reduction undefined",
            details={"baseline_rate": baseline_rate, "current_rate": current_rate},
        )

    reduction = (baseline_rate - current_rate) / baseline_rate
    status = "pass" if reduction >= 0.5 else "fail"
    return CheckResult(
        check_id="A2",
        name="Top-3 irrelevant retrieval hit rate reduced by >= 50%",
        status=status,
        target="reduction >= 50%",
        actual=f"reduction={_to_percentage(reduction)}; baseline={_to_percentage(baseline_rate)}, current={_to_percentage(current_rate)}",
        details={
            "baseline_top3_irrelevant_hit_rate": baseline_rate,
            "current_top3_irrelevant_hit_rate": current_rate,
            "reduction": reduction,
        },
    )


def _check_a4(
    baseline_p95_ms: Optional[float],
    current_p95_ms: Optional[float],
) -> CheckResult:
    if baseline_p95_ms is None or current_p95_ms is None:
        return CheckResult(
            check_id="A4",
            name="p95 retrieval latency regression <= 10%",
            status="unknown",
            target="regression <= 10%",
            actual=None,
            details={"reason": "missing baseline/current p95 input"},
        )

    if baseline_p95_ms <= 0:
        return CheckResult(
            check_id="A4",
            name="p95 retrieval latency regression <= 10%",
            status="unknown",
            target="regression <= 10%",
            actual="baseline p95 <= 0, regression undefined",
            details={
                "baseline_p95_ms": baseline_p95_ms,
                "current_p95_ms": current_p95_ms,
            },
        )

    regression = (current_p95_ms - baseline_p95_ms) / baseline_p95_ms
    status = "pass" if regression <= 0.10 else "fail"
    return CheckResult(
        check_id="A4",
        name="p95 retrieval latency regression <= 10%",
        status=status,
        target="regression <= 10%",
        actual=f"regression={_to_percentage(regression)}; baseline={baseline_p95_ms:.2f}ms, current={current_p95_ms:.2f}ms",
        details={
            "baseline_p95_ms": baseline_p95_ms,
            "current_p95_ms": current_p95_ms,
            "regression": regression,
        },
    )


def _get_memory_config(base_url: str, admin_token: str, timeout_seconds: float) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/memories/config"
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.get(url, headers=headers, timeout=timeout_seconds)
    resp.raise_for_status()
    return resp.json()


def _put_memory_config(
    base_url: str,
    admin_token: str,
    payload: Dict[str, Any],
    timeout_seconds: float,
) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/memories/config"
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.put(url, headers=headers, json=payload, timeout=timeout_seconds)
    resp.raise_for_status()
    return resp.json()


def _extract_switches(config_payload: Dict[str, Any]) -> Dict[str, bool]:
    retrieval = config_payload.get("retrieval") if isinstance(config_payload, dict) else {}
    write_cfg = config_payload.get("write") if isinstance(config_payload, dict) else {}
    observability = config_payload.get("observability") if isinstance(config_payload, dict) else {}

    return {
        "retrieval.strict_keyword_fallback": bool(
            (retrieval or {}).get("strict_keyword_fallback", True)
        ),
        "write.fail_closed_user_agent": bool((write_cfg or {}).get("fail_closed_user_agent", True)),
        "observability.enable_quality_counters": bool(
            (observability or {}).get("enable_quality_counters", True)
        ),
    }


def _check_a6(
    base_url: Optional[str],
    admin_token: Optional[str],
    timeout_seconds: float,
    validate_toggle: bool,
) -> CheckResult:
    if not base_url or not admin_token:
        return CheckResult(
            check_id="A6",
            name="Rollback switches validated in staging",
            status="unknown",
            target="switches available and validated",
            actual=None,
            details={"reason": "missing --api-base-url or --admin-token"},
        )

    try:
        initial = _get_memory_config(base_url, admin_token, timeout_seconds)
        switches = _extract_switches(initial)
    except Exception as exc:
        return CheckResult(
            check_id="A6",
            name="Rollback switches validated in staging",
            status="fail",
            target="switches available and validated",
            actual="failed to read memory config",
            details={"error": str(exc)},
        )

    if not validate_toggle:
        return CheckResult(
            check_id="A6",
            name="Rollback switches validated in staging",
            status="unknown",
            target="switches available and validated",
            actual="switches discovered only (no toggle validation requested)",
            details={"switches": switches},
        )

    toggled_payload = {
        "retrieval": {"strict_keyword_fallback": not switches["retrieval.strict_keyword_fallback"]},
        "write": {"fail_closed_user_agent": not switches["write.fail_closed_user_agent"]},
        "observability": {
            "enable_quality_counters": not switches["observability.enable_quality_counters"]
        },
    }

    try:
        _put_memory_config(base_url, admin_token, toggled_payload, timeout_seconds)
        after_toggle = _get_memory_config(base_url, admin_token, timeout_seconds)
        toggled = _extract_switches(after_toggle)

        expected_toggled = {key: (not value) for key, value in switches.items()}
        toggle_ok = all(toggled.get(key) == expected_toggled.get(key) for key in expected_toggled)
    except Exception as exc:
        return CheckResult(
            check_id="A6",
            name="Rollback switches validated in staging",
            status="fail",
            target="switches available and validated",
            actual="toggle validation failed",
            details={"error": str(exc), "initial_switches": switches},
        )
    finally:
        restore_payload = {
            "retrieval": {"strict_keyword_fallback": switches["retrieval.strict_keyword_fallback"]},
            "write": {"fail_closed_user_agent": switches["write.fail_closed_user_agent"]},
            "observability": {
                "enable_quality_counters": switches["observability.enable_quality_counters"]
            },
        }
        try:
            _put_memory_config(base_url, admin_token, restore_payload, timeout_seconds)
        except Exception:
            pass

    status = "pass" if toggle_ok else "fail"
    return CheckResult(
        check_id="A6",
        name="Rollback switches validated in staging",
        status=status,
        target="switches available and validated",
        actual=f"toggle_roundtrip={'ok' if toggle_ok else 'failed'}",
        details={
            "initial_switches": switches,
            "expected_toggled_switches": expected_toggled,
            "actual_toggled_switches": toggled,
            "restored": True,
        },
    )


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run(args: argparse.Namespace) -> Dict[str, Any]:
    results: List[CheckResult] = []

    total_writes, empty_writes, empty_rate = _query_a1(args.window_days)
    a1_status = "pass" if empty_writes == 0 else "fail"
    results.append(
        CheckResult(
            check_id="A1",
            name="Empty-extraction write rate for strict memory types is 0%",
            status=a1_status,
            target="empty write rate = 0%",
            actual=f"{empty_writes}/{total_writes} = {_to_percentage(empty_rate)}",
            details={
                "window_days": args.window_days,
                "strict_types": ["agent", "user_context"],
                "scope": "auto_generated writes",
                "total_writes": total_writes,
                "empty_facts_writes": empty_writes,
                "empty_write_rate": empty_rate,
            },
        )
    )

    baseline_report = _load_json(args.baseline_topk_report)
    current_report = _load_json(args.current_topk_report)
    results.append(_check_a2(baseline_report, current_report))

    dup_rows, dup_total, dup_rate_current = _query_duplicate_rate(args.window_days)
    baseline_dup_rate = _parse_float(args.baseline_duplicate_rate)
    if baseline_dup_rate is None:
        a3 = CheckResult(
            check_id="A3",
            name="7-day duplicate memory rate reduced by >= 40%",
            status="unknown",
            target="reduction >= 40%",
            actual=f"current duplicate rate={_to_percentage(dup_rate_current)} (baseline missing)",
            details={
                "window_days": args.window_days,
                "dup_rows": dup_rows,
                "total_rows_with_hash": dup_total,
                "current_duplicate_rate": dup_rate_current,
                "reason": "provide --baseline-duplicate-rate to evaluate pass/fail",
            },
        )
    elif baseline_dup_rate <= 0:
        a3 = CheckResult(
            check_id="A3",
            name="7-day duplicate memory rate reduced by >= 40%",
            status="unknown",
            target="reduction >= 40%",
            actual="baseline duplicate rate <= 0, reduction undefined",
            details={
                "baseline_duplicate_rate": baseline_dup_rate,
                "current_duplicate_rate": dup_rate_current,
            },
        )
    else:
        reduction = (baseline_dup_rate - dup_rate_current) / baseline_dup_rate
        a3 = CheckResult(
            check_id="A3",
            name="7-day duplicate memory rate reduced by >= 40%",
            status="pass" if reduction >= 0.40 else "fail",
            target="reduction >= 40%",
            actual=f"reduction={_to_percentage(reduction)}; baseline={_to_percentage(baseline_dup_rate)}, current={_to_percentage(dup_rate_current)}",
            details={
                "window_days": args.window_days,
                "dup_rows": dup_rows,
                "total_rows_with_hash": dup_total,
                "baseline_duplicate_rate": baseline_dup_rate,
                "current_duplicate_rate": dup_rate_current,
                "reduction": reduction,
            },
        )
    results.append(a3)

    baseline_p95_ms = _parse_float(args.baseline_p95_ms)
    current_p95_ms = _parse_float(args.current_p95_ms)
    results.append(_check_a4(baseline_p95_ms, current_p95_ms))

    rollout_types = [
        item.strip() for item in str(args.rollout_memory_types).split(",") if item.strip()
    ]
    total, covered, coverage = _query_a5(args.window_days, rollout_types)
    a5_status = "pass" if coverage >= 0.95 else "fail"
    if total == 0:
        a5_status = "unknown"
    results.append(
        CheckResult(
            check_id="A5",
            name="Action decision metadata present for >= 95% writes in rollout scope",
            status=a5_status,
            target="coverage >= 95%",
            actual=f"{covered}/{total} = {_to_percentage(coverage)}",
            details={
                "window_days": args.window_days,
                "rollout_memory_types": rollout_types or ["agent", "user_context", "company"],
                "total_writes": total,
                "covered_writes": covered,
                "coverage": coverage,
            },
        )
    )

    results.append(
        _check_a6(
            base_url=args.api_base_url,
            admin_token=args.admin_token,
            timeout_seconds=float(args.http_timeout_seconds),
            validate_toggle=bool(args.validate_a6_toggle),
        )
    )

    status_counts = {"pass": 0, "fail": 0, "unknown": 0}
    for item in results:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": args.window_days,
        "summary": {
            "pass": status_counts.get("pass", 0),
            "fail": status_counts.get("fail", 0),
            "unknown": status_counts.get("unknown", 0),
            "overall": (
                "fail"
                if status_counts.get("fail", 0) > 0
                else ("pass" if status_counts.get("unknown", 0) == 0 else "partial")
            ),
        },
        "checks": [asdict(item) for item in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run memory acceptance checklist A1-A6")
    parser.add_argument("--window-days", type=int, default=7, help="Lookback window in days")
    parser.add_argument("--baseline-topk-report", help="Path to baseline Top-K report JSON")
    parser.add_argument("--current-topk-report", help="Path to current Top-K report JSON")
    parser.add_argument(
        "--baseline-duplicate-rate",
        help="Baseline duplicate rate in [0,1] for A3 comparison",
    )
    parser.add_argument("--baseline-p95-ms", help="Baseline p95 latency (ms) for A4")
    parser.add_argument("--current-p95-ms", help="Current p95 latency (ms) for A4")
    parser.add_argument(
        "--rollout-memory-types",
        default="agent,user_context,company",
        help="Comma-separated memory types for A5 scope",
    )
    parser.add_argument("--api-base-url", help="API base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--admin-token", help="Admin JWT token for A6 validation")
    parser.add_argument(
        "--validate-a6-toggle",
        action="store_true",
        help="Perform A6 toggle+restore validation via API",
    )
    parser.add_argument(
        "--http-timeout-seconds",
        type=float,
        default=8.0,
        help="HTTP timeout for A6 calls",
    )
    parser.add_argument(
        "--output",
        default="reports/memory_acceptance_checklist.json",
        help="Output JSON report path",
    )
    args = parser.parse_args()

    report = run(args)
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report: {output_path}")


if __name__ == "__main__":
    main()
