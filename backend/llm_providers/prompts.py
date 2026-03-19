"""
Prompt Template System

Provides reusable prompt templates for common tasks.

References:
- Design Section 9.3: Prompt Engineering
"""

from string import Template
from typing import Any, Dict, List


class PromptTemplate:
    """Base class for prompt templates"""

    def __init__(self, template: str):
        """
        Initialize prompt template.

        Args:
            template: Template string with ${variable} placeholders
        """
        self.template = Template(template)

    def format(self, **kwargs) -> str:
        """
        Format template with provided variables.

        Args:
            **kwargs: Template variables

        Returns:
            Formatted prompt string
        """
        return self.template.safe_substitute(**kwargs)


# Agent System Prompts

AGENT_SYSTEM_PROMPT = PromptTemplate("""
You are a ${agent_type} agent with the following capabilities: ${skills}.

Your task is: ${task_description}

You have access to these tools: ${tools}

Guidelines:
- Always provide structured output in JSON format when requested
- Prioritize accuracy and cite sources when using knowledge base information
- If you're unsure about something, ask for clarification
- Break down complex tasks into smaller steps
- Document your reasoning process

Available context:
${context}
""")


# Task Decomposition Prompts

TASK_DECOMPOSITION_PROMPT = PromptTemplate("""
Given the following goal: ${goal}

Break it down into a hierarchical task structure.

For each task, identify:
1. Task description (clear and specific)
2. Required skills (from available skill set)
3. Dependencies on other tasks (task IDs)
4. Expected output format
5. Estimated complexity (low, medium, high)

Available skills: ${available_skills}

Output as JSON with the following structure:
{
  "tasks": [
    {
      "task_id": "1",
      "description": "...",
      "required_skills": ["skill1", "skill2"],
      "dependencies": [],
      "output_format": "...",
      "complexity": "medium"
    }
  ]
}
""")


# Clarification Prompts

CLARIFICATION_PROMPT = PromptTemplate("""
The user has submitted the following goal: ${goal}

This goal is ambiguous or lacks necessary details. Generate 2-5 clarifying questions
that will help you better understand the requirements.

Focus on:
- Specific requirements or constraints
- Expected output format or deliverables
- Data sources or inputs needed
- Success criteria
- Timeline or priority

Output as JSON:
{
  "questions": [
    "Question 1?",
    "Question 2?"
  ]
}
""")


# Code Generation Prompts

CODE_GENERATION_PROMPT = PromptTemplate("""
Generate ${language} code to accomplish the following task:

Task: ${task_description}

Requirements:
${requirements}

Constraints:
- Use only standard library unless specified
- Include type hints (for Python)
- Include docstrings/comments
- Handle errors appropriately
- Follow best practices for ${language}

${examples}

Output the code only, without explanations.
""")


# Summarization Prompts

SUMMARIZATION_PROMPT = PromptTemplate("""
Summarize the following content in ${max_words} words or less:

${content}

Focus on:
- Key points and main ideas
- Important facts and figures
- Actionable insights

Output format: ${output_format}
""")


# Data Analysis Prompts

DATA_ANALYSIS_PROMPT = PromptTemplate("""
Analyze the following data and provide insights:

Data: ${data}

Analysis objectives:
${objectives}

Provide:
1. Summary statistics
2. Key patterns or trends
3. Anomalies or outliers
4. Recommendations

Output as structured JSON.
""")


# Translation Prompts

TRANSLATION_PROMPT = PromptTemplate("""
Translate the following text from ${source_language} to ${target_language}:

${text}

Requirements:
- Maintain the original tone and style
- Preserve formatting
- Use appropriate cultural context
- Ensure accuracy

Output only the translated text.
""")


# Knowledge Base Query Prompts

KNOWLEDGE_QUERY_PROMPT = PromptTemplate("""
Based on the following knowledge base information, answer the user's question:

Question: ${question}

Relevant knowledge:
${knowledge_items}

Guidelines:
- Cite sources using [Source: document_name]
- If information is insufficient, state what's missing
- Provide accurate and concise answers
- Include relevant details and context

Answer:
""")


# Result Aggregation Prompts

RESULT_AGGREGATION_PROMPT = PromptTemplate("""
Aggregate the following results from multiple agents into a cohesive final result:

Task: ${task_description}

Agent results:
${agent_results}

Aggregation strategy: ${strategy}

Requirements:
- Combine complementary information
- Resolve conflicts by prioritizing more reliable sources
- Maintain consistency
- Provide a clear, unified response

Output format: ${output_format}
""")


# Memory Storage Prompts

MEMORY_CLASSIFICATION_PROMPT = PromptTemplate("""
Classify the following information for memory storage:

Information: ${information}

Context: ${context}

Determine:
1. Product surface: user_memory, skill_candidate, knowledge_base, or discard
2. Importance: low, medium, high
3. Tags: relevant keywords (3-5 tags)
4. Should this be promoted into a shared knowledge asset? (yes/no)

Output as JSON:
{
  "product_surface": "...",
  "importance": "...",
  "tags": ["tag1", "tag2"],
  "promote_to_shared_knowledge": true/false
}
""")


# Skill Generation Prompts

SKILL_GENERATION_PROMPT = PromptTemplate("""
Generate a Python function to accomplish this task:

Task description: ${task_description}

Examples:
${examples}

Requirements:
- Function must be pure (no side effects)
- No external network access
- No file system access
- Use only standard library
- Include type hints
- Include comprehensive docstring
- Handle edge cases

Generate the complete function code.
""")


def get_agent_prompt(
    agent_type: str, skills: List[str], task_description: str, tools: List[str], context: str = ""
) -> str:
    """
    Get formatted agent system prompt.

    Args:
        agent_type: Type of agent
        skills: List of agent skills
        task_description: Current task
        tools: Available tools
        context: Additional context

    Returns:
        Formatted prompt string
    """
    return AGENT_SYSTEM_PROMPT.format(
        agent_type=agent_type,
        skills=", ".join(skills),
        task_description=task_description,
        tools=", ".join(tools),
        context=context or "No additional context provided",
    )


def get_task_decomposition_prompt(goal: str, available_skills: List[str]) -> str:
    """
    Get formatted task decomposition prompt.

    Args:
        goal: User's goal
        available_skills: Available skills

    Returns:
        Formatted prompt string
    """
    return TASK_DECOMPOSITION_PROMPT.format(goal=goal, available_skills=", ".join(available_skills))


def get_clarification_prompt(goal: str) -> str:
    """
    Get formatted clarification prompt.

    Args:
        goal: User's goal

    Returns:
        Formatted prompt string
    """
    return CLARIFICATION_PROMPT.format(goal=goal)


def get_code_generation_prompt(
    language: str, task_description: str, requirements: List[str], examples: str = ""
) -> str:
    """
    Get formatted code generation prompt.

    Args:
        language: Programming language
        task_description: Task description
        requirements: List of requirements
        examples: Example code (optional)

    Returns:
        Formatted prompt string
    """
    return CODE_GENERATION_PROMPT.format(
        language=language,
        task_description=task_description,
        requirements="\n".join(f"- {req}" for req in requirements),
        examples=f"\nExamples:\n{examples}" if examples else "",
    )


def get_summarization_prompt(
    content: str, max_words: int = 100, output_format: str = "paragraph"
) -> str:
    """
    Get formatted summarization prompt.

    Args:
        content: Content to summarize
        max_words: Maximum words in summary
        output_format: Output format

    Returns:
        Formatted prompt string
    """
    return SUMMARIZATION_PROMPT.format(
        content=content, max_words=max_words, output_format=output_format
    )
