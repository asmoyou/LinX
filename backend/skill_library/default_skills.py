"""Default skill definitions.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
from typing import Dict, List

from skill_library.skill_registry import SkillRegistry, get_skill_registry

logger = logging.getLogger(__name__)


def get_default_skill_definitions() -> List[Dict]:
    """Get default skill definitions.

    Returns:
        List of skill definition dictionaries
    """
    return [
        {
            "skill_slug": "data_processing",
            "display_name": "Data Processing",
            "description": "Process and transform data using pandas",
            "interface_definition": {
                "inputs": {
                    "data": "array",
                    "operation": "string",
                    "parameters": "dict",
                },
                "outputs": {
                    "result": "array",
                    "metadata": "dict",
                },
                "required_inputs": ["data", "operation"],
            },
            "dependencies": ["pandas", "numpy"],
            "version": "1.0.0",
        },
        {
            "skill_slug": "sql_query",
            "display_name": "SQL Query",
            "description": "Execute SQL queries against databases",
            "interface_definition": {
                "inputs": {
                    "query": "string",
                    "database": "string",
                    "parameters": "dict",
                },
                "outputs": {
                    "results": "array",
                    "row_count": "integer",
                },
                "required_inputs": ["query", "database"],
            },
            "dependencies": ["psycopg2", "sqlalchemy"],
            "version": "1.0.0",
        },
        {
            "skill_slug": "web_scraping",
            "display_name": "Web Scraping",
            "description": "Scrape data from web pages",
            "interface_definition": {
                "inputs": {
                    "url": "string",
                    "selectors": "dict",
                    "options": "dict",
                },
                "outputs": {
                    "data": "dict",
                    "status": "string",
                },
                "required_inputs": ["url"],
            },
            "dependencies": ["requests", "beautifulsoup4"],
            "version": "1.0.0",
        },
        {
            "skill_slug": "statistical_analysis",
            "display_name": "Statistical Analysis",
            "description": "Perform statistical analysis on datasets",
            "interface_definition": {
                "inputs": {
                    "data": "array",
                    "analysis_type": "string",
                    "parameters": "dict",
                },
                "outputs": {
                    "statistics": "dict",
                    "visualizations": "array",
                },
                "required_inputs": ["data", "analysis_type"],
            },
            "dependencies": ["pandas", "scipy", "numpy"],
            "version": "1.0.0",
        },
        {
            "skill_slug": "visualization",
            "display_name": "Visualization",
            "description": "Create data visualizations and charts",
            "interface_definition": {
                "inputs": {
                    "data": "array",
                    "chart_type": "string",
                    "options": "dict",
                },
                "outputs": {
                    "chart": "string",
                    "format": "string",
                },
                "required_inputs": ["data", "chart_type"],
            },
            "dependencies": ["matplotlib", "seaborn"],
            "version": "1.0.0",
        },
        {
            "skill_slug": "text_summarization",
            "display_name": "Text Summarization",
            "description": "Summarize long text documents",
            "interface_definition": {
                "inputs": {
                    "text": "string",
                    "max_length": "integer",
                    "method": "string",
                },
                "outputs": {
                    "summary": "string",
                    "compression_ratio": "float",
                },
                "required_inputs": ["text"],
            },
            "dependencies": [],
            "version": "1.0.0",
        },
        {
            "skill_slug": "sentiment_analysis",
            "display_name": "Sentiment Analysis",
            "description": "Analyze sentiment of text",
            "interface_definition": {
                "inputs": {
                    "text": "string",
                    "language": "string",
                },
                "outputs": {
                    "sentiment": "string",
                    "score": "float",
                    "confidence": "float",
                },
                "required_inputs": ["text"],
            },
            "dependencies": ["nltk"],
            "version": "1.0.0",
        },
        {
            "skill_slug": "file_operations",
            "display_name": "File Operations",
            "description": "Perform file system operations",
            "interface_definition": {
                "inputs": {
                    "operation": "string",
                    "path": "string",
                    "parameters": "dict",
                },
                "outputs": {
                    "result": "any",
                    "status": "string",
                },
                "required_inputs": ["operation", "path"],
            },
            "dependencies": [],
            "version": "1.0.0",
        },
        {
            "skill_slug": "api_request",
            "display_name": "API Request",
            "description": "Make HTTP API requests",
            "interface_definition": {
                "inputs": {
                    "url": "string",
                    "method": "string",
                    "headers": "dict",
                    "body": "any",
                },
                "outputs": {
                    "response": "any",
                    "status_code": "integer",
                },
                "required_inputs": ["url", "method"],
            },
            "dependencies": ["requests"],
            "version": "1.0.0",
        },
        {
            "skill_slug": "json_processing",
            "display_name": "JSON Processing",
            "description": "Parse and manipulate JSON data",
            "interface_definition": {
                "inputs": {
                    "data": "any",
                    "operation": "string",
                    "parameters": "dict",
                },
                "outputs": {
                    "result": "any",
                },
                "required_inputs": ["data", "operation"],
            },
            "dependencies": [],
            "version": "1.0.0",
        },
    ]


def register_default_skills(
    skill_registry: SkillRegistry = None,
    skip_existing: bool = True,
) -> int:
    """Register all default skills.

    Args:
        skill_registry: SkillRegistry instance
        skip_existing: Whether to skip skills that already exist

    Returns:
        Number of skills registered
    """
    registry = skill_registry or get_skill_registry()
    skills = get_default_skill_definitions()
    registered_count = 0

    for skill_def in skills:
        try:
            # Check if skill already exists
            if skip_existing:
                existing = registry.get_skill_by_name(
                    skill_def["skill_slug"],
                    skill_def["version"],
                )
                if existing:
                    logger.info(f"Skipping existing skill: {skill_def['skill_slug']}")
                    continue

            # Register skill
            registry.register_skill(
                skill_slug=skill_def["skill_slug"],
                display_name=skill_def["display_name"],
                description=skill_def["description"],
                interface_definition=skill_def["interface_definition"],
                dependencies=skill_def["dependencies"],
                version=skill_def["version"],
                access_level="public",
            )
            registered_count += 1
            logger.info(f"Registered default skill: {skill_def['skill_slug']}")

        except Exception as e:
            logger.error(f"Failed to register skill {skill_def['skill_slug']}: {e}")

    logger.info(f"Registered {registered_count} default skills")
    return registered_count
