"""Default Agent Templates.

This module provides pre-configured agent templates for common use cases.

References:
- Requirements 21: Agent Templates
- Design Section 4.2: Agent Types and Templates
"""

import logging
from typing import List, Dict, Any

from agent_framework.agent_template import AgentTemplateManager

logger = logging.getLogger(__name__)


def get_default_templates() -> List[Dict[str, Any]]:
    """Get list of default system templates.

    Returns:
        List of template configuration dictionaries
    """
    return [
        {
            "name": "Data Analyst",
            "description": "Specialized agent for data analysis, statistical processing, and visualization",
            "agent_type": "data_analyst",
            "capabilities": [
                "data_processing",
                "statistical_analysis",
                "visualization",
                "sql_query",
            ],
            "tools": ["pandas", "matplotlib", "database_connector"],
            "use_case": "Analyze datasets, generate reports, create visualizations",
        },
        {
            "name": "Content Writer",
            "description": "Specialized agent for content creation, editing, and summarization",
            "agent_type": "content_writer",
            "capabilities": [
                "text_summarization",
                "sentiment_analysis",
                "json_processing",
            ],
            "tools": ["grammar_checker", "style_analyzer", "plagiarism_detector"],
            "use_case": "Create articles, edit documents, summarize content",
        },
        {
            "name": "Code Assistant",
            "description": "Specialized agent for code generation, debugging, and review",
            "agent_type": "code_assistant",
            "capabilities": [
                "data_processing",
                "file_operations",
                "json_processing",
            ],
            "tools": ["code_executor", "linter", "test_runner", "git_interface"],
            "use_case": "Write code, debug issues, review pull requests",
        },
        {
            "name": "Research Assistant",
            "description": "Specialized agent for information gathering, research, and report compilation",
            "agent_type": "research_assistant",
            "capabilities": [
                "web_scraping",
                "text_summarization",
                "data_processing",
                "json_processing",
            ],
            "tools": ["web_scraper", "search_engine", "document_analyzer"],
            "use_case": "Gather information, research topics, compile reports",
        },
    ]


def initialize_default_templates() -> None:
    """Initialize default system templates in the database.

    This function should be called during system startup to ensure
    all default templates are available.
    """
    with AgentTemplateManager() as manager:
        existing_templates = {t.name for t in manager.list_templates(include_custom=False)}

        for template_config in get_default_templates():
            if template_config["name"] in existing_templates:
                logger.debug(
                    "Default template already exists",
                    extra={"template_name": template_config["name"]},
                )
                continue

            try:
                manager.create_template(
                    name=template_config["name"],
                    description=template_config["description"],
                    agent_type=template_config["agent_type"],
                    capabilities=template_config["capabilities"],
                    tools=template_config["tools"],
                    use_case=template_config["use_case"],
                    is_system_template=True,
                )
                logger.info(
                    "Initialized default template",
                    extra={"template_name": template_config["name"]},
                )
            except Exception as e:
                logger.error(
                    "Failed to initialize default template",
                    extra={
                        "template_name": template_config["name"],
                        "error": str(e),
                    },
                )
