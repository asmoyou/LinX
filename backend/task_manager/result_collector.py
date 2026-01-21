"""Task Result Collection and Aggregation.

Collects and aggregates results from completed tasks.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.3: Result Aggregation
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from uuid import UUID
from enum import Enum

from database.connection import get_db_session
from database.models import Task as TaskModel
from llm_providers import get_llm_provider, LLMProvider

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
    
    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        """Initialize result collector.
        
        Args:
            llm_provider: LLM provider for summarization
        """
        self.llm_provider = llm_provider or get_llm_provider()
        
        logger.info("ResultCollector initialized")
    
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
                task = session.query(TaskModel).filter(
                    TaskModel.task_id == task_id,
                    TaskModel.created_by_user_id == user_id,
                ).first()
                
                if task:
                    results.append(
                        CollectedResult(
                            task_id=task_id,
                            result=task.result or {},
                            status=task.status,
                            completed_at=task.completed_at.isoformat() if task.completed_at else None,
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
            merged["results"].append({
                "task_id": str(result.task_id),
                "data": result.result,
                "status": result.status,
            })
        
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
            subtasks = session.query(TaskModel).filter(
                TaskModel.parent_task_id == parent_task_id,
                TaskModel.created_by_user_id == user_id,
            ).all()
            
            subtask_ids = [task.task_id for task in subtasks]
        
        # Collect results
        results = self.collect_results(subtask_ids, user_id)
        
        # Aggregate
        aggregated = await self.aggregate_results(results, strategy)
        
        # Store aggregated result in parent task
        with get_db_session() as session:
            parent_task = session.query(TaskModel).filter(
                TaskModel.task_id == parent_task_id,
            ).first()
            
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
