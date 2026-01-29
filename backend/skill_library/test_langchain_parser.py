"""Tests for LangChain Tool Parser.

Tests the extraction of interface definitions from @tool decorated functions.
"""

import pytest
from skill_library.langchain_parser import LangChainToolParser, parse_langchain_tool


class TestLangChainToolParser:
    """Test LangChain tool parsing functionality."""
    
    def test_parse_simple_tool(self):
        """Test parsing a simple tool with basic types."""
        code = '''
from langchain_core.tools import tool

@tool
def calculator(expression: str) -> str:
    """Evaluate mathematical expressions.
    
    Args:
        expression: Mathematical expression to evaluate
        
    Returns:
        Result of the calculation
    """
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {str(e)}"
'''
        
        interface = parse_langchain_tool(code)
        
        assert "inputs" in interface
        assert "outputs" in interface
        assert "required_inputs" in interface
        
        # Check inputs
        assert "expression" in interface["inputs"]
        assert interface["inputs"]["expression"] == "string"
        
        # Check required inputs
        assert "expression" in interface["required_inputs"]
        
        # Check outputs
        assert "result" in interface["outputs"]
        assert interface["outputs"]["result"] == "string"
    
    def test_parse_tool_with_multiple_params(self):
        """Test parsing tool with multiple parameters."""
        code = '''
from langchain_core.tools import tool

@tool
def api_call(url: str, method: str = "GET", timeout: int = 30) -> str:
    """Make an API call.
    
    Args:
        url: API endpoint URL
        method: HTTP method (default: GET)
        timeout: Request timeout in seconds (default: 30)
        
    Returns:
        API response
    """
    pass
'''
        
        interface = parse_langchain_tool(code)
        
        # Check all inputs are present
        assert "url" in interface["inputs"]
        assert "method" in interface["inputs"]
        assert "timeout" in interface["inputs"]
        
        # Check types
        assert interface["inputs"]["url"] == "string"
        assert interface["inputs"]["method"] == "string"
        assert interface["inputs"]["timeout"] == "integer"
        
        # Only url is required (others have defaults)
        assert interface["required_inputs"] == ["url"]
    
    def test_parse_tool_with_complex_types(self):
        """Test parsing tool with complex type annotations."""
        code = '''
from typing import Dict, List, Optional
from langchain_core.tools import tool

@tool
def process_data(
    data: Dict[str, any],
    filters: Optional[List[str]] = None,
    count: int = 10
) -> Dict[str, any]:
    """Process data with filters.
    
    Args:
        data: Input data dictionary
        filters: Optional list of filters
        count: Number of items to process
        
    Returns:
        Processed data
    """
    pass
'''
        
        interface = parse_langchain_tool(code)
        
        # Check inputs
        assert "data" in interface["inputs"]
        assert "filters" in interface["inputs"]
        assert "count" in interface["inputs"]
        
        # Check types
        assert interface["inputs"]["data"] == "object"
        assert interface["inputs"]["filters"] == "array"  # Optional[List] -> array
        assert interface["inputs"]["count"] == "integer"
        
        # Only data is required
        assert interface["required_inputs"] == ["data"]
        
        # Check output type
        assert interface["outputs"]["result"] == "object"
    
    def test_parse_tool_without_type_hints(self):
        """Test parsing tool without type hints."""
        code = '''
from langchain_core.tools import tool

@tool
def simple_tool(param1, param2="default"):
    """A simple tool without type hints.
    
    Args:
        param1: First parameter
        param2: Second parameter with default
        
    Returns:
        Some result
    """
    return f"{param1} {param2}"
'''
        
        interface = parse_langchain_tool(code)
        
        # Should default to string type
        assert interface["inputs"]["param1"] == "string"
        assert interface["inputs"]["param2"] == "string"
        
        # Only param1 is required
        assert interface["required_inputs"] == ["param1"]
    
    def test_parse_tool_with_no_params(self):
        """Test parsing tool with no parameters."""
        code = '''
from langchain_core.tools import tool

@tool
def get_timestamp() -> str:
    """Get current timestamp.
    
    Returns:
        Current timestamp as string
    """
    from datetime import datetime
    return datetime.now().isoformat()
'''
        
        interface = parse_langchain_tool(code)
        
        # No inputs
        assert interface["inputs"] == {}
        assert interface["required_inputs"] == []
        
        # Has output
        assert interface["outputs"]["result"] == "string"
    
    def test_parse_code_without_tool_decorator(self):
        """Test parsing code without @tool decorator."""
        code = '''
def regular_function(x: int) -> int:
    """A regular function without @tool decorator."""
    return x * 2
'''
        
        interface = parse_langchain_tool(code)
        
        # Should return default interface
        assert interface["inputs"] == {}
        assert interface["outputs"]["result"] == "string"
        assert interface["required_inputs"] == []
    
    def test_parse_invalid_syntax(self):
        """Test parsing code with syntax errors."""
        code = '''
from langchain_core.tools import tool

@tool
def broken_tool(x: str) -> str
    # Missing colon
    return x
'''
        
        interface = parse_langchain_tool(code)
        
        # Should return default interface on error
        assert interface["inputs"] == {}
        assert interface["outputs"]["result"] == "string"
        assert interface["required_inputs"] == []
    
    def test_extract_docstring(self):
        """Test extracting docstring from tool."""
        code = '''
from langchain_core.tools import tool

@tool
def my_tool(x: str) -> str:
    """This is the docstring.
    
    It has multiple lines.
    """
    return x
'''
        
        parser = LangChainToolParser()
        docstring = parser.extract_docstring(code)
        
        assert docstring is not None
        assert "This is the docstring" in docstring
        assert "multiple lines" in docstring
    
    def test_parse_tool_with_call_decorator(self):
        """Test parsing tool with @tool() call syntax."""
        code = '''
from langchain_core.tools import tool

@tool()
def my_tool(x: str) -> str:
    """Tool with call decorator."""
    return x
'''
        
        interface = parse_langchain_tool(code)
        
        assert "x" in interface["inputs"]
        assert interface["inputs"]["x"] == "string"
        assert interface["required_inputs"] == ["x"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
