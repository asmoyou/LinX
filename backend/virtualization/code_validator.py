"""Code Validator for static analysis and security checks.

This module provides code validation functionality to detect dangerous patterns
and ensure code safety before execution.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.4: Code Execution Workflow
"""

import ast
import logging
import re
from dataclasses import dataclass
from typing import List, Set, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of code validation."""
    
    safe: bool
    issues: List[str]
    warnings: List[str] = None
    
    def __post_init__(self):
        """Initialize warnings list if None."""
        if self.warnings is None:
            self.warnings = []


class CodeValidator:
    """Validator for code security and safety checks."""
    
    # Dangerous patterns for different languages
    DANGEROUS_PATTERNS = {
        "python": [
            (r'import\s+os\b', "OS module access"),
            (r'import\s+subprocess\b', "Subprocess execution"),
            (r'import\s+socket\b', "Network socket access"),
            (r'import\s+sys\b', "System module access"),
            (r'eval\s*\(', "Dynamic code evaluation"),
            (r'exec\s*\(', "Dynamic code execution"),
            (r'__import__\s*\(', "Dynamic imports"),
            (r'compile\s*\(', "Code compilation"),
            (r'open\s*\(', "File operations"),
            (r'file\s*\(', "File operations"),
            (r'input\s*\(', "User input"),
            (r'raw_input\s*\(', "User input"),
            (r'globals\s*\(', "Global namespace access"),
            (r'locals\s*\(', "Local namespace access"),
            (r'vars\s*\(', "Variable namespace access"),
            (r'dir\s*\(', "Directory listing"),
            (r'getattr\s*\(', "Attribute access"),
            (r'setattr\s*\(', "Attribute modification"),
            (r'delattr\s*\(', "Attribute deletion"),
            (r'__.*__', "Dunder methods"),
        ],
        "javascript": [
            (r'require\s*\(', "Module require"),
            (r'import\s+.*\s+from', "ES6 imports"),
            (r'eval\s*\(', "Dynamic code evaluation"),
            (r'Function\s*\(', "Function constructor"),
            (r'setTimeout\s*\(', "Async execution"),
            (r'setInterval\s*\(', "Async execution"),
            (r'XMLHttpRequest', "Network requests"),
            (r'fetch\s*\(', "Network requests"),
            (r'WebSocket', "WebSocket connections"),
            (r'process\.', "Process access"),
            (r'fs\.', "Filesystem access"),
            (r'child_process', "Child process execution"),
        ],
    }
    
    # Allowed safe modules for Python
    SAFE_PYTHON_MODULES = {
        'math', 'random', 'datetime', 'json', 'collections',
        'itertools', 'functools', 're', 'string', 'decimal',
    }
    
    def __init__(self):
        """Initialize the code validator."""
        self.logger = logging.getLogger(__name__)
    
    def validate_code(self, code: str, language: str = "python") -> ValidationResult:
        """Validate code for security issues.
        
        Args:
            code: Source code to validate
            language: Programming language (python, javascript, etc.)
        
        Returns:
            ValidationResult with safety status and issues
        """
        issues = []
        warnings = []
        
        self.logger.debug(
            "Validating code",
            extra={
                "language": language,
                "code_length": len(code),
            },
        )
        
        # Check for dangerous patterns
        pattern_issues = self._check_dangerous_patterns(code, language)
        issues.extend(pattern_issues)
        
        # Language-specific validation
        if language == "python":
            syntax_issues, syntax_warnings = self._validate_python_syntax(code)
            issues.extend(syntax_issues)
            warnings.extend(syntax_warnings)
            
            import_issues = self._check_python_imports(code)
            issues.extend(import_issues)
        
        elif language == "javascript":
            syntax_issues = self._validate_javascript_syntax(code)
            issues.extend(syntax_issues)
        
        # Check code length
        if len(code) > 10000:
            warnings.append("Code is very long (>10000 characters)")
        
        safe = len(issues) == 0
        
        if not safe:
            self.logger.warning(
                "Code validation failed",
                extra={
                    "language": language,
                    "issue_count": len(issues),
                    "issues": issues[:5],  # Log first 5 issues
                },
            )
        else:
            self.logger.debug("Code validation passed")
        
        return ValidationResult(
            safe=safe,
            issues=issues,
            warnings=warnings,
        )
    
    def _check_dangerous_patterns(self, code: str, language: str) -> List[str]:
        """Check for dangerous patterns in code.
        
        Args:
            code: Source code
            language: Programming language
        
        Returns:
            List of detected issues
        """
        issues = []
        patterns = self.DANGEROUS_PATTERNS.get(language, [])
        
        for pattern, description in patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(f"Dangerous pattern detected: {description} ({pattern})")
        
        return issues
    
    def _validate_python_syntax(self, code: str) -> tuple[List[str], List[str]]:
        """Validate Python syntax using AST.
        
        Args:
            code: Python source code
        
        Returns:
            Tuple of (issues, warnings)
        """
        issues = []
        warnings = []
        
        try:
            tree = ast.parse(code)
            
            # Check for dangerous AST nodes
            for node in ast.walk(tree):
                # Check for exec/eval
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['eval', 'exec', 'compile', '__import__']:
                            issues.append(f"Dangerous function call: {node.func.id}")
                
                # Check for file operations
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['open', 'file']:
                            issues.append(f"File operation detected: {node.func.id}")
                
                # Check for attribute access to dangerous modules
                if isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name):
                        if node.value.id in ['os', 'sys', 'subprocess']:
                            issues.append(f"Access to dangerous module: {node.value.id}")
                
                # Warn about complex constructs
                if isinstance(node, ast.Lambda):
                    warnings.append("Lambda function detected")
                
                if isinstance(node, ast.ListComp) or isinstance(node, ast.DictComp):
                    warnings.append("Comprehension detected")
        
        except SyntaxError as e:
            issues.append(f"Syntax error: {e}")
        except Exception as e:
            issues.append(f"Parse error: {e}")
        
        return issues, warnings
    
    def _check_python_imports(self, code: str) -> List[str]:
        """Check Python imports for safety.
        
        Args:
            code: Python source code
        
        Returns:
            List of import-related issues
        """
        issues = []
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name not in self.SAFE_PYTHON_MODULES:
                            issues.append(f"Unsafe import: {alias.name}")
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module not in self.SAFE_PYTHON_MODULES:
                        issues.append(f"Unsafe import from: {node.module}")
        
        except Exception as e:
            # Already handled in syntax validation
            pass
        
        return issues
    
    def _validate_javascript_syntax(self, code: str) -> List[str]:
        """Validate JavaScript syntax (basic checks).
        
        Args:
            code: JavaScript source code
        
        Returns:
            List of syntax issues
        """
        issues = []
        
        # Basic bracket matching
        brackets = {'(': ')', '[': ']', '{': '}'}
        stack = []
        
        for char in code:
            if char in brackets.keys():
                stack.append(char)
            elif char in brackets.values():
                if not stack:
                    issues.append("Unmatched closing bracket")
                    break
                opening = stack.pop()
                if brackets[opening] != char:
                    issues.append("Mismatched brackets")
                    break
        
        if stack:
            issues.append("Unclosed brackets")
        
        return issues
    
    def get_safe_builtins(self) -> Set[str]:
        """Get set of safe Python builtins.
        
        Returns:
            Set of safe builtin names
        """
        safe_builtins = {
            # Type constructors
            'int', 'float', 'str', 'bool', 'list', 'dict', 'tuple', 'set',
            # Type checking
            'isinstance', 'issubclass', 'type',
            # Iteration
            'range', 'enumerate', 'zip', 'map', 'filter',
            # Math
            'abs', 'min', 'max', 'sum', 'round', 'pow',
            # String
            'len', 'sorted', 'reversed',
            # Other safe functions
            'print', 'format',
        }
        
        return safe_builtins


# Global validator instance
_code_validator: Optional[CodeValidator] = None


def get_code_validator() -> CodeValidator:
    """Get the global code validator instance.
    
    Returns:
        CodeValidator instance
    """
    global _code_validator
    if _code_validator is None:
        _code_validator = CodeValidator()
    return _code_validator
