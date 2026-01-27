"""Skill templates library.

Provides pre-built templates for common skill patterns.

Simplified two-tier system:
- LangChain Tool: Simple standardized functions
- Agent Skill: Flexible skills

References:
- docs/backend/skill-type-classification.md
"""

from typing import Dict, List
from skill_library.skill_types import SkillType


def get_skill_templates() -> List[Dict]:
    """Get all available skill templates.

    Returns:
        List of template definitions
    """
    return [
        # === LangChain Tools (Simple Functions) ===
        {
            "id": "langchain_web_search",
            "name": "Web Search (LangChain Tool)",
            "description": "Simple web search using Tavily API - standard LangChain tool",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
from tavily import TavilyClient
import os

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@tool
def web_search(query: str, max_results: int = 10) -> str:
    """Search the internet for information.
    
    Args:
        query: The search query string
        max_results: Maximum number of results to return
        
    Returns:
        Formatted search results with titles, URLs, and snippets
    """
    response = tavily_client.search(
        query=query,
        max_results=max_results,
        search_depth="basic"
    )
    
    results = []
    for r in response.get("results", []):
        results.append(f"**{r['title']}**\\nURL: {r['url']}\\n{r['content']}\\n")
    
    return "\\n---\\n".join(results) if results else "No results found"
''',
            "dependencies": ["tavily-python"],
            "required_env": ["TAVILY_API_KEY"],
        },
        {
            "id": "langchain_calculator",
            "name": "Calculator (LangChain Tool)",
            "description": "Simple calculator - standard LangChain tool",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool

@tool
def calculator(expression: str) -> str:
    """Evaluate mathematical expressions.
    
    Args:
        expression: Mathematical expression to evaluate (e.g., "2 + 2", "10 * 5")
        
    Returns:
        Result of the calculation
    """
    try:
        # Safe evaluation - only allows basic math operations
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"
''',
            "dependencies": [],
            "required_env": [],
        },
        
        # === Agent Skills (Flexible) ===
        {
            "id": "agent_api_call",
            "name": "HTTP API Call (Agent Skill)",
            "description": "Flexible HTTP API client - Claude Code style agent skill",
            "category": "agent_skill",
            "difficulty": "beginner",
            "skill_type": SkillType.AGENT_SKILL.value,
            "code": '''from langchain_core.tools import tool
import requests
from typing import Dict, Any, Optional

@tool
def api_call(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> str:
    """Make HTTP API requests with full control.
    
    Args:
        url: The API endpoint URL
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        headers: Optional request headers
        body: Optional request body (for POST/PUT/PATCH)
        timeout: Request timeout in seconds
        
    Returns:
        API response as JSON string
    """
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            json=body,
            timeout=timeout
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.Timeout:
        return f"Error: Request timed out after {timeout} seconds"
    except requests.exceptions.RequestException as e:
        return f"Error: {str(e)}"
''',
            "dependencies": ["requests"],
            "required_env": [],
        },
        {
            "id": "agent_data_analysis",
            "name": "Data Analysis (Agent Skill)",
            "description": "Advanced data analysis with pandas - Claude Code style",
            "category": "agent_skill",
            "difficulty": "intermediate",
            "skill_type": SkillType.AGENT_SKILL.value,
            "code": '''from langchain_core.tools import tool
import pandas as pd
import json
from typing import List, Dict, Any

@tool
def analyze_data(data: str, operation: str, column: str = None) -> str:
    """Analyze data using pandas operations.
    
    Args:
        data: JSON string of data (list of dicts)
        operation: Operation to perform (describe, sum, mean, count, groupby, filter)
        column: Column name for operations (optional)
        
    Returns:
        Analysis results as formatted string
    """
    try:
        # Parse JSON data
        data_list = json.loads(data)
        df = pd.DataFrame(data_list)
        
        if operation == "describe":
            return df.describe().to_string()
        elif operation == "sum" and column:
            return f"{column} sum: {df[column].sum()}"
        elif operation == "mean" and column:
            return f"{column} mean: {df[column].mean()}"
        elif operation == "count":
            return f"Total rows: {len(df)}\\nColumns: {', '.join(df.columns)}"
        elif operation == "info":
            return df.info()
        else:
            return f"Unknown operation: {operation}. Available: describe, sum, mean, count, info"
    except Exception as e:
        return f"Error analyzing data: {str(e)}"
''',
            "dependencies": ["pandas"],
            "required_env": [],
        },
        {
            "id": "agent_file_operations",
            "name": "File Operations (Agent Skill)",
            "description": "Read and write files - Claude Code style",
            "category": "agent_skill",
            "difficulty": "beginner",
            "skill_type": SkillType.AGENT_SKILL.value,
            "code": '''from langchain_core.tools import tool
import os
from pathlib import Path

@tool
def file_operations(
    operation: str,
    file_path: str,
    content: str = None,
    encoding: str = "utf-8"
) -> str:
    """Perform file operations (read, write, append, exists).
    
    Args:
        operation: Operation to perform (read, write, append, exists, delete)
        file_path: Path to the file
        content: Content to write/append (for write/append operations)
        encoding: File encoding (default: utf-8)
        
    Returns:
        Operation result or file contents
    """
    try:
        if operation == "read":
            if not os.path.exists(file_path):
                return f"Error: File not found: {file_path}"
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
                
        elif operation == "write":
            if content is None:
                return "Error: content parameter required for write operation"
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
            
        elif operation == "append":
            if content is None:
                return "Error: content parameter required for append operation"
            with open(file_path, 'a', encoding=encoding) as f:
                f.write(content)
            return f"Successfully appended to {file_path}"
            
        elif operation == "exists":
            return f"File exists: {os.path.exists(file_path)}"
            
        elif operation == "delete":
            if os.path.exists(file_path):
                os.remove(file_path)
                return f"Successfully deleted {file_path}"
            return f"File not found: {file_path}"
            
        else:
            return f"Unknown operation: {operation}. Available: read, write, append, exists, delete"
            
    except Exception as e:
        return f"Error: {str(e)}"
''',
            "dependencies": [],
            "required_env": [],
        },
    ]


def get_template_by_id(template_id: str) -> Dict:
    """Get a specific template by ID.

    Args:
        template_id: Template identifier

    Returns:
        Template definition or None if not found
    """
    templates = get_skill_templates()
    for template in templates:
        if template["id"] == template_id:
            return template
    return None


def get_templates_by_skill_type(skill_type: SkillType) -> List[Dict]:
    """Get templates filtered by skill type.

    Args:
        skill_type: Skill type

    Returns:
        List of matching templates
    """
    templates = get_skill_templates()
    return [t for t in templates if t["skill_type"] == skill_type]

