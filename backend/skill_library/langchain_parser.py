"""LangChain Tool Parser.

Extracts interface definitions from LangChain @tool decorated functions.

References:
- docs/backend/skill-type-classification.md
"""

import ast
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class LangChainToolParser:
    """Parse LangChain @tool decorated functions to extract interface definitions."""
    
    @staticmethod
    def extract_interface(code: str) -> Dict[str, Any]:
        """Extract interface definition from LangChain tool code.
        
        Args:
            code: Python code containing @tool decorated function
            
        Returns:
            Interface definition with inputs, outputs, and required_inputs
        """
        try:
            tree = ast.parse(code)
            
            # Find @tool decorated function
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Check if function has @tool decorator
                    has_tool_decorator = any(
                        (isinstance(dec, ast.Name) and dec.id == 'tool') or
                        (isinstance(dec, ast.Call) and 
                         isinstance(dec.func, ast.Name) and 
                         dec.func.id == 'tool')
                        for dec in node.decorator_list
                    )
                    
                    if has_tool_decorator:
                        return LangChainToolParser._parse_function_signature(node)
            
            # No @tool decorated function found
            logger.warning("No @tool decorated function found in code")
            return {
                "inputs": {},
                "outputs": {"result": "string"},
                "required_inputs": []
            }
            
        except SyntaxError as e:
            logger.error(f"Syntax error parsing code: {e}")
            return {
                "inputs": {},
                "outputs": {"result": "string"},
                "required_inputs": []
            }
        except Exception as e:
            logger.error(f"Error extracting interface: {e}", exc_info=True)
            return {
                "inputs": {},
                "outputs": {"result": "string"},
                "required_inputs": []
            }
    
    @staticmethod
    def _parse_function_signature(func_node: ast.FunctionDef) -> Dict[str, Any]:
        """Parse function signature to extract parameters and types.
        
        Args:
            func_node: AST FunctionDef node
            
        Returns:
            Interface definition dictionary
        """
        inputs = {}
        required_inputs = []
        
        # Parse function arguments
        for arg in func_node.args.args:
            arg_name = arg.arg
            
            # Skip 'self' and 'cls'
            if arg_name in ('self', 'cls'):
                continue
            
            # Extract type annotation if present
            arg_type = "string"  # Default type
            if arg.annotation:
                arg_type = LangChainToolParser._extract_type_annotation(arg.annotation)
            
            inputs[arg_name] = arg_type
        
        # Determine required inputs (those without defaults)
        num_defaults = len(func_node.args.defaults)
        num_args = len(func_node.args.args)
        num_required = num_args - num_defaults
        
        # First N arguments without defaults are required
        for i, arg in enumerate(func_node.args.args):
            if arg.arg not in ('self', 'cls') and i < num_required:
                required_inputs.append(arg.arg)
        
        # Extract return type from annotation
        output_type = "string"  # Default
        if func_node.returns:
            output_type = LangChainToolParser._extract_type_annotation(func_node.returns)
        
        return {
            "inputs": inputs,
            "outputs": {"result": output_type},
            "required_inputs": required_inputs
        }
    
    @staticmethod
    def _extract_type_annotation(annotation: ast.expr) -> str:
        """Extract type from annotation node.
        
        Args:
            annotation: AST annotation node
            
        Returns:
            Type as string
        """
        try:
            if isinstance(annotation, ast.Name):
                # Simple type: str, int, float, bool
                type_map = {
                    'str': 'string',
                    'int': 'integer',
                    'float': 'number',
                    'bool': 'boolean',
                    'dict': 'object',
                    'list': 'array',
                    'Dict': 'object',
                    'List': 'array',
                    'Any': 'any',
                    'Optional': 'any'
                }
                return type_map.get(annotation.id, 'string')
            
            elif isinstance(annotation, ast.Subscript):
                # Generic type: Optional[str], List[int], Dict[str, Any]
                if isinstance(annotation.value, ast.Name):
                    base_type = annotation.value.id
                    
                    if base_type in ('Optional', 'Union'):
                        # For Optional/Union, extract the first type
                        if isinstance(annotation.slice, ast.Tuple):
                            first_type = annotation.slice.elts[0]
                        else:
                            first_type = annotation.slice
                        return LangChainToolParser._extract_type_annotation(first_type)
                    
                    elif base_type in ('List', 'list'):
                        return 'array'
                    
                    elif base_type in ('Dict', 'dict'):
                        return 'object'
            
            elif isinstance(annotation, ast.Constant):
                # String annotation (Python 3.10+)
                return 'string'
            
            # Default fallback
            return 'string'
            
        except Exception as e:
            logger.warning(f"Error extracting type annotation: {e}")
            return 'string'
    
    @staticmethod
    def extract_docstring(code: str) -> Optional[str]:
        """Extract docstring from @tool decorated function.
        
        Args:
            code: Python code
            
        Returns:
            Docstring or None
        """
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    has_tool_decorator = any(
                        (isinstance(dec, ast.Name) and dec.id == 'tool') or
                        (isinstance(dec, ast.Call) and 
                         isinstance(dec.func, ast.Name) and 
                         dec.func.id == 'tool')
                        for dec in node.decorator_list
                    )
                    
                    if has_tool_decorator:
                        return ast.get_docstring(node)
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting docstring: {e}")
            return None


def parse_langchain_tool(code: str) -> Dict[str, Any]:
    """Parse LangChain tool code and extract interface.
    
    Convenience function for extracting interface from LangChain tool code.
    
    Args:
        code: Python code containing @tool decorated function
        
    Returns:
        Interface definition dictionary
    """
    parser = LangChainToolParser()
    return parser.extract_interface(code)
