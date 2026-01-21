"""Default skill definitions.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
from typing import List, Dict

from skill_library.skill_registry import SkillRegistry, get_skill_registry

logger = logging.getLogger(__name__)


def get_default_skill_definitions() -> List[Dict]:
    """Get default skill definitions.
    
    Returns:
        List of skill definition dictionaries
    """
    return [
        {
            "name": "data_processing",
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
            "name": "sql_query",
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
            "name": "web_scraping",
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
            "name": "statistical_analysis",
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
            "name": "visualization",
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
            "name": "text_summarization",
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
            "name": "sentiment_analysis",
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
            "name": "file_operations",
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
            "name": "api_request",
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
            "name": "json_processing",
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
                    skill_def["name"],
                    skill_def["version"],
                )
                if existing:
                    logger.info(f"Skipping existing skill: {skill_def['name']}")
                    continue
            
            # Register skill
            registry.register_skill(
                name=skill_def["name"],
                description=skill_def["description"],
                interface_definition=skill_def["interface_definition"],
                dependencies=skill_def["dependencies"],
                version=skill_def["version"],
            )
            registered_count += 1
            logger.info(f"Registered default skill: {skill_def['name']}")
            
        except Exception as e:
            logger.error(f"Failed to register skill {skill_def['name']}: {e}")
    
    logger.info(f"Registered {registered_count} default skills")
    return registered_count
