"""Goal Analysis and Clarification.

This module analyzes user goals and generates clarifying questions when needed.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.1: Task Decomposition Algorithm
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from llm_providers.base import BaseLLMProvider
from llm_providers.router import get_llm_provider

logger = logging.getLogger(__name__)


@dataclass
class ClarificationQuestion:
    """A clarification question for an ambiguous goal."""

    question: str
    context: str
    importance: str  # critical, important, optional
    suggested_answers: Optional[List[str]] = None


@dataclass
class GoalAnalysis:
    """Result of goal analysis."""

    is_clear: bool
    required_capabilities: List[str]
    clarification_questions: List[ClarificationQuestion]
    complexity_score: float  # 0.0 to 1.0
    estimated_subtasks: int
    analysis_details: Dict[str, Any]


class GoalAnalyzer:
    """Analyzes user goals and generates clarification questions."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        """Initialize the goal analyzer.

        Args:
            llm_provider: LLM provider for goal analysis (uses default if None)
        """
        self.llm_provider = llm_provider or get_llm_provider()

        logger.info("GoalAnalyzer initialized")

    async def analyze_goal(
        self,
        goal_text: str,
        user_id: UUID,
        context: Optional[Dict[str, Any]] = None,
    ) -> GoalAnalysis:
        """Analyze a user goal to determine clarity and requirements.

        Args:
            goal_text: The user's goal description
            user_id: User ID for context retrieval
            context: Additional context about the user or task

        Returns:
            GoalAnalysis with clarity assessment and questions
        """
        logger.info(
            "Analyzing goal",
            extra={
                "user_id": str(user_id),
                "goal_length": len(goal_text),
            },
        )

        # Build analysis prompt
        prompt = self._build_analysis_prompt(goal_text, context)

        try:
            # Call LLM for analysis
            response = await self.llm_provider.generate(
                prompt=prompt,
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=1000,
            )

            # Parse LLM response
            analysis = self._parse_analysis_response(response, goal_text)

            logger.info(
                "Goal analysis complete",
                extra={
                    "is_clear": analysis.is_clear,
                    "num_questions": len(analysis.clarification_questions),
                    "complexity": analysis.complexity_score,
                    "estimated_subtasks": analysis.estimated_subtasks,
                },
            )

            return analysis

        except Exception as e:
            logger.error(
                "Goal analysis failed",
                extra={"error": str(e), "user_id": str(user_id)},
            )

            # Return conservative analysis on error
            return GoalAnalysis(
                is_clear=False,
                required_capabilities=[],
                clarification_questions=[
                    ClarificationQuestion(
                        question="Could you provide more details about what you want to achieve?",
                        context="Goal analysis encountered an error",
                        importance="critical",
                    )
                ],
                complexity_score=0.5,
                estimated_subtasks=3,
                analysis_details={"error": str(e)},
            )

    def _build_analysis_prompt(
        self,
        goal_text: str,
        context: Optional[Dict[str, Any]],
    ) -> str:
        """Build the LLM prompt for goal analysis.

        Args:
            goal_text: The user's goal
            context: Additional context

        Returns:
            Formatted prompt string
        """
        context_str = ""
        if context:
            context_str = f"\n\nAdditional Context:\n{context}"

        prompt = f"""Analyze the following user goal and determine if it's clear enough to execute.

Goal: "{goal_text}"{context_str}

Please analyze:
1. Is the goal clear and actionable? (yes/no)
2. What capabilities/skills are required? (list)
3. What clarifying questions should we ask? (if any)
4. Complexity score (0.0 to 1.0, where 1.0 is most complex)
5. Estimated number of subtasks (integer)

Respond in JSON format:
{{
    "is_clear": true/false,
    "required_capabilities": ["capability1", "capability2"],
    "clarification_questions": [
        {{
            "question": "...",
            "context": "...",
            "importance": "critical/important/optional",
            "suggested_answers": ["option1", "option2"]
        }}
    ],
    "complexity_score": 0.0-1.0,
    "estimated_subtasks": integer,
    "reasoning": "explanation"
}}"""

        return prompt

    def _parse_analysis_response(
        self,
        response: str,
        goal_text: str,
    ) -> GoalAnalysis:
        """Parse LLM response into GoalAnalysis.

        Args:
            response: LLM response text
            goal_text: Original goal text

        Returns:
            Parsed GoalAnalysis
        """
        import json

        try:
            # Try to parse JSON response
            data = json.loads(response)

            # Parse clarification questions
            questions = []
            for q in data.get("clarification_questions", []):
                questions.append(
                    ClarificationQuestion(
                        question=q.get("question", ""),
                        context=q.get("context", ""),
                        importance=q.get("importance", "important"),
                        suggested_answers=q.get("suggested_answers"),
                    )
                )

            return GoalAnalysis(
                is_clear=data.get("is_clear", False),
                required_capabilities=data.get("required_capabilities", []),
                clarification_questions=questions,
                complexity_score=float(data.get("complexity_score", 0.5)),
                estimated_subtasks=int(data.get("estimated_subtasks", 3)),
                analysis_details={
                    "reasoning": data.get("reasoning", ""),
                    "raw_response": response,
                },
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(
                "Failed to parse LLM response, using heuristics",
                extra={"error": str(e)},
            )

            # Fallback to heuristic analysis
            return self._heuristic_analysis(goal_text, response)

    def _heuristic_analysis(
        self,
        goal_text: str,
        llm_response: str,
    ) -> GoalAnalysis:
        """Perform heuristic analysis when LLM parsing fails.

        Args:
            goal_text: Original goal text
            llm_response: Raw LLM response

        Returns:
            GoalAnalysis based on heuristics
        """
        # Simple heuristics
        word_count = len(goal_text.split())
        has_specifics = any(
            keyword in goal_text.lower()
            for keyword in ["analyze", "create", "generate", "process", "calculate"]
        )

        is_clear = word_count >= 5 and has_specifics
        complexity = min(1.0, word_count / 50.0)
        estimated_subtasks = max(1, min(10, word_count // 10))

        questions = []
        if not is_clear:
            questions.append(
                ClarificationQuestion(
                    question="Could you provide more specific details about what you want to achieve?",
                    context="Goal appears to be too vague",
                    importance="critical",
                )
            )

        return GoalAnalysis(
            is_clear=is_clear,
            required_capabilities=["general"],
            clarification_questions=questions,
            complexity_score=complexity,
            estimated_subtasks=estimated_subtasks,
            analysis_details={
                "method": "heuristic",
                "word_count": word_count,
                "llm_response": llm_response,
            },
        )

    async def refine_goal_with_answers(
        self,
        original_goal: str,
        questions: List[ClarificationQuestion],
        answers: Dict[str, str],
    ) -> str:
        """Refine a goal based on clarification answers.

        Args:
            original_goal: Original goal text
            questions: List of questions that were asked
            answers: Dictionary mapping question to answer

        Returns:
            Refined goal text
        """
        logger.info(
            "Refining goal with clarification answers",
            extra={"num_answers": len(answers)},
        )

        # Build refinement prompt
        qa_pairs = "\n".join(
            f"Q: {q.question}\nA: {answers.get(q.question, 'Not answered')}" for q in questions
        )

        prompt = f"""Original Goal: "{original_goal}"

Clarification Questions and Answers:
{qa_pairs}

Please rewrite the goal to incorporate the clarification answers, making it more specific and actionable.

Refined Goal:"""

        try:
            response = await self.llm_provider.generate(
                prompt=prompt,
                temperature=0.5,
                max_tokens=500,
            )

            refined_goal = response.strip()

            logger.info(
                "Goal refined successfully",
                extra={"original_length": len(original_goal), "refined_length": len(refined_goal)},
            )

            return refined_goal

        except Exception as e:
            logger.error(
                "Goal refinement failed",
                extra={"error": str(e)},
            )

            # Return original goal with answers appended
            return f"{original_goal}\n\nAdditional details: {'; '.join(answers.values())}"
