"""Task Result Collection and Aggregation.

Collects and aggregates results from completed tasks.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.3: Result Aggregation
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import Task as TaskModel
from llm_providers import BaseLLMProvider, get_llm_provider

logger = logging.getLogger(__name__)


class AggregationStrategy(Enum):
    """Result aggregation strategy."""

    CONCATENATION = "concatenation"
    SUMMARIZATION = "summarization"
    STRUCTURED_MERGE = "structured_merge"
    VOTING = "voting"


@dataclass
class CollectedResult:
    """A collected task result."""

    task_id: UUID
    result: Dict[str, Any]
    status: str
    completed_at: Optional[str]


class ResultCollector:
    """Collects and aggregates task results."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        """Initialize result collector.

        Args:
            llm_provider: LLM provider for summarization
        """
        self.llm_provider = llm_provider or get_llm_provider()

        logger.info("ResultCollector initialized")

    def select_aggregation_strategy(
        self,
        results: List[CollectedResult],
        task_type: Optional[str] = None,
    ) -> AggregationStrategy:
        """Automatically select the best aggregation strategy.

        Args:
            results: List of collected results
            task_type: Optional task type hint

        Returns:
            Selected aggregation strategy
        """
        if not results:
            return AggregationStrategy.CONCATENATION

        # Check if results are text-heavy (good for summarization).
        total_text_length = 0
        has_text_fields = True
        all_text_envelopes = True
        text_field_keys = {"output", "result"}

        for result in results:
            if not isinstance(result.result, dict):
                has_text_fields = False
                all_text_envelopes = False
                continue

            keys = set(result.result.keys())
            if "output" in result.result:
                total_text_length += len(str(result.result["output"]))
            elif "result" in result.result:
                total_text_length += len(str(result.result["result"]))
            else:
                has_text_fields = False

            if not keys.issubset(text_field_keys):
                all_text_envelopes = False

        # Prefer summarization for large free-text payloads, even when wrapped in dicts.
        if has_text_fields and total_text_length > 1000 and len(results) > 2:
            return AggregationStrategy.SUMMARIZATION

        # Check if results are structured (JSON-like)
        all_structured = all(isinstance(r.result, dict) and len(r.result) > 0 for r in results)
        if all_structured:
            # Check if results have similar structure
            if len(results) > 1:
                first_keys = set(results[0].result.keys())
                similar_structure = all(set(r.result.keys()) == first_keys for r in results[1:])

                # Exclude plain text envelopes like {"output": "..."} from structured merge.
                if similar_structure and not all_text_envelopes:
                    return AggregationStrategy.STRUCTURED_MERGE

        # Check if multiple similar results (good for voting)
        if len(results) >= 3:
            # Simple heuristic: if results are similar length, might be voting scenario
            lengths = [len(str(r.result)) for r in results]
            avg_length = sum(lengths) / len(lengths)
            similar_lengths = all(abs(length - avg_length) < avg_length * 0.3 for length in lengths)

            if similar_lengths:
                return AggregationStrategy.VOTING

        # Default to concatenation
        return AggregationStrategy.CONCATENATION

    def collect_results(
        self,
        task_ids: List[UUID],
        user_id: UUID,
    ) -> List[CollectedResult]:
        """Collect results from multiple tasks.

        Args:
            task_ids: List of task IDs
            user_id: User ID for authorization

        Returns:
            List of collected results
        """
        results = []

        with get_db_session() as session:
            for task_id in task_ids:
                task = (
                    session.query(TaskModel)
                    .filter(
                        TaskModel.task_id == task_id,
                        TaskModel.created_by_user_id == user_id,
                    )
                    .first()
                )

                if task:
                    results.append(
                        CollectedResult(
                            task_id=task_id,
                            result=task.result or {},
                            status=task.status,
                            completed_at=(
                                task.completed_at.isoformat() if task.completed_at else None
                            ),
                        )
                    )

        logger.info(
            "Results collected",
            extra={
                "num_tasks": len(task_ids),
                "collected": len(results),
            },
        )

        return results

    async def aggregate_results(
        self,
        results: List[CollectedResult],
        strategy: AggregationStrategy = AggregationStrategy.CONCATENATION,
    ) -> Dict[str, Any]:
        """Aggregate multiple results into one.

        Args:
            results: List of collected results
            strategy: Aggregation strategy

        Returns:
            Aggregated result
        """
        logger.info(
            "Aggregating results",
            extra={
                "num_results": len(results),
                "strategy": strategy.value,
            },
        )

        if not results:
            return {"aggregated": None, "count": 0}

        if strategy == AggregationStrategy.CONCATENATION:
            return self._concatenate_results(results)
        elif strategy == AggregationStrategy.SUMMARIZATION:
            return await self._summarize_results(results)
        elif strategy == AggregationStrategy.STRUCTURED_MERGE:
            return self._merge_structured_results(results)
        elif strategy == AggregationStrategy.VOTING:
            return self._vote_on_results(results)
        else:
            return {"error": f"Unknown strategy: {strategy}"}

    def _concatenate_results(
        self,
        results: List[CollectedResult],
    ) -> Dict[str, Any]:
        """Concatenate results sequentially.

        Args:
            results: List of results

        Returns:
            Concatenated result
        """
        outputs = []

        for result in results:
            if "output" in result.result:
                outputs.append(str(result.result["output"]))
            elif "result" in result.result:
                outputs.append(str(result.result["result"]))

        concatenated = "\n\n".join(outputs)

        return {
            "strategy": "concatenation",
            "aggregated_output": concatenated,
            "source_count": len(results),
            "sources": [str(r.task_id) for r in results],
        }

    async def _summarize_results(
        self,
        results: List[CollectedResult],
    ) -> Dict[str, Any]:
        """Summarize results using LLM.

        Args:
            results: List of results

        Returns:
            Summarized result
        """
        # Collect all outputs
        outputs = []
        for result in results:
            if "output" in result.result:
                outputs.append(str(result.result["output"]))
            elif "result" in result.result:
                outputs.append(str(result.result["result"]))

        if not outputs:
            return {
                "strategy": "summarization",
                "summary": "No outputs to summarize",
                "source_count": 0,
            }

        # Build summarization prompt
        combined_text = "\n\n---\n\n".join(outputs)
        prompt = f"""Summarize the following task results into a concise, coherent summary:

{combined_text}

Summary:"""

        try:
            summary = await self.llm_provider.generate(
                prompt=prompt,
                temperature=0.5,
                max_tokens=500,
            )

            return {
                "strategy": "summarization",
                "summary": summary.strip(),
                "source_count": len(results),
                "sources": [str(r.task_id) for r in results],
            }

        except Exception as e:
            logger.error(
                "Summarization failed",
                extra={"error": str(e)},
            )

            # Fallback to concatenation
            return self._concatenate_results(results)

    def _merge_structured_results(
        self,
        results: List[CollectedResult],
    ) -> Dict[str, Any]:
        """Merge structured (JSON) results.

        Args:
            results: List of results

        Returns:
            Merged result
        """
        merged = {
            "strategy": "structured_merge",
            "results": [],
            "source_count": len(results),
        }

        for result in results:
            merged["results"].append(
                {
                    "task_id": str(result.task_id),
                    "data": result.result,
                    "status": result.status,
                }
            )

        return merged

    def _vote_on_results(
        self,
        results: List[CollectedResult],
    ) -> Dict[str, Any]:
        """Select best result by voting.

        Args:
            results: List of results

        Returns:
            Best result
        """
        # Simple voting: select most common result
        # In a real implementation, this could use more sophisticated voting

        if not results:
            return {"strategy": "voting", "winner": None}

        # For now, just return the first successful result
        for result in results:
            if result.status == "completed":
                return {
                    "strategy": "voting",
                    "winner": result.result,
                    "winner_task_id": str(result.task_id),
                    "candidate_count": len(results),
                }

        # No successful results, return first one
        return {
            "strategy": "voting",
            "winner": results[0].result,
            "winner_task_id": str(results[0].task_id),
            "candidate_count": len(results),
        }

    async def collect_and_aggregate_subtasks(
        self,
        parent_task_id: UUID,
        user_id: UUID,
        strategy: AggregationStrategy = AggregationStrategy.CONCATENATION,
    ) -> Dict[str, Any]:
        """Collect and aggregate results from all subtasks.

        Args:
            parent_task_id: Parent task ID
            user_id: User ID
            strategy: Aggregation strategy

        Returns:
            Aggregated result
        """
        # Get all subtasks
        with get_db_session() as session:
            subtasks = (
                session.query(TaskModel)
                .filter(
                    TaskModel.parent_task_id == parent_task_id,
                    TaskModel.created_by_user_id == user_id,
                )
                .all()
            )

            subtask_ids = [task.task_id for task in subtasks]

        # Collect results
        results = self.collect_results(subtask_ids, user_id)

        # Aggregate
        aggregated = await self.aggregate_results(results, strategy)

        # Store aggregated result in parent task
        with get_db_session() as session:
            parent_task = (
                session.query(TaskModel)
                .filter(
                    TaskModel.task_id == parent_task_id,
                )
                .first()
            )

            if parent_task:
                parent_task.result = aggregated
                session.commit()

        logger.info(
            "Subtask results aggregated",
            extra={
                "parent_task_id": str(parent_task_id),
                "num_subtasks": len(subtask_ids),
            },
        )

        return aggregated


class ResultDelivery:
    """Handles final result delivery to users."""

    def __init__(self):
        """Initialize result delivery."""
        logger.info("ResultDelivery initialized")

    async def deliver_result(
        self,
        task_id: UUID,
        user_id: UUID,
        result: Dict[str, Any],
        delivery_method: str = "database",
    ) -> bool:
        """Deliver final result to user.

        Args:
            task_id: Task ID
            user_id: User ID
            result: Final aggregated result
            delivery_method: Delivery method (database, webhook, email)

        Returns:
            True if delivery successful
        """
        logger.info(
            "Delivering result to user",
            extra={
                "task_id": str(task_id),
                "user_id": str(user_id),
                "delivery_method": delivery_method,
            },
        )

        if delivery_method == "database":
            return await self._deliver_to_database(task_id, user_id, result)
        elif delivery_method == "webhook":
            return await self._deliver_via_webhook(task_id, user_id, result)
        elif delivery_method == "email":
            return await self._deliver_via_email(task_id, user_id, result)
        else:
            logger.error(f"Unknown delivery method: {delivery_method}")
            return False

    async def _deliver_to_database(
        self,
        task_id: UUID,
        user_id: UUID,
        result: Dict[str, Any],
    ) -> bool:
        """Store result in database.

        Args:
            task_id: Task ID
            user_id: User ID
            result: Result to store

        Returns:
            True if successful
        """
        try:
            with get_db_session() as session:
                task = (
                    session.query(TaskModel)
                    .filter(
                        TaskModel.task_id == task_id,
                        TaskModel.created_by_user_id == user_id,
                    )
                    .first()
                )

                if not task:
                    logger.error(
                        "Task not found for result delivery",
                        extra={"task_id": str(task_id)},
                    )
                    return False

                # Update task with final result
                task.result = result
                task.status = "completed"

                # Add delivery metadata
                if not task.result:
                    task.result = {}

                task.result["delivered_at"] = str(datetime.utcnow())
                task.result["delivery_method"] = "database"

                session.commit()

            logger.info(
                "Result delivered to database",
                extra={"task_id": str(task_id)},
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to deliver result to database",
                extra={"error": str(e), "task_id": str(task_id)},
            )
            return False

    async def _deliver_via_webhook(
        self,
        task_id: UUID,
        user_id: UUID,
        result: Dict[str, Any],
    ) -> bool:
        """Deliver result via webhook.

        Args:
            task_id: Task ID
            user_id: User ID
            result: Result to deliver

        Returns:
            True if successful
        """
        # Placeholder for webhook delivery
        # In a real implementation, this would:
        # 1. Get user's webhook URL from database
        # 2. Send HTTP POST request with result
        # 3. Handle retries and failures

        logger.info(
            "Webhook delivery not yet implemented",
            extra={"task_id": str(task_id)},
        )

        # Fallback to database delivery
        return await self._deliver_to_database(task_id, user_id, result)

    async def _deliver_via_email(
        self,
        task_id: UUID,
        user_id: UUID,
        result: Dict[str, Any],
    ) -> bool:
        """Deliver result via email.

        Args:
            task_id: Task ID
            user_id: User ID
            result: Result to deliver

        Returns:
            True if successful
        """
        # Placeholder for email delivery
        # In a real implementation, this would:
        # 1. Get user's email from database
        # 2. Format result as email
        # 3. Send via SMTP

        logger.info(
            "Email delivery not yet implemented",
            extra={"task_id": str(task_id)},
        )

        # Fallback to database delivery
        return await self._deliver_to_database(task_id, user_id, result)

    def format_result_for_user(
        self,
        result: Dict[str, Any],
        format_type: str = "json",
    ) -> str:
        """Format result for user consumption.

        Args:
            result: Result to format
            format_type: Format type (json, text, html)

        Returns:
            Formatted result string
        """
        if format_type == "json":
            import json

            return json.dumps(result, indent=2)

        elif format_type == "text":
            # Convert to readable text
            lines = []

            if "strategy" in result:
                lines.append(f"Aggregation Strategy: {result['strategy']}")

            if "summary" in result:
                lines.append(f"\nSummary:\n{result['summary']}")

            if "aggregated_output" in result:
                lines.append(f"\nResult:\n{result['aggregated_output']}")

            if "winner" in result:
                lines.append(f"\nSelected Result:\n{result['winner']}")

            return "\n".join(lines)

        elif format_type == "html":
            # Convert to HTML
            html = "<div class='task-result'>"

            if "strategy" in result:
                html += f"<p><strong>Strategy:</strong> {result['strategy']}</p>"

            if "summary" in result:
                html += f"<div class='summary'><h3>Summary</h3><p>{result['summary']}</p></div>"

            if "aggregated_output" in result:
                html += f"<div class='output'><h3>Result</h3><pre>{result['aggregated_output']}</pre></div>"

            html += "</div>"
            return html

        else:
            return str(result)


# Import datetime for delivery timestamps
from datetime import datetime
