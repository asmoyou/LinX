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
        # ============================================
        # 1. Web Search - Tavily
        # ============================================
        {
            "id": "langchain_web_search",
            "name": "Web Search - Tavily (LangChain Tool)",
            "description": "Web search using Tavily API - returns raw search results for agent to analyze",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
from tavily import TavilyClient
from typing import Optional, List
import os

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@tool
def web_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> str:
    """Search the web and return raw results for analysis.

    This tool returns original search content. The agent should analyze
    and summarize the results based on the user's needs.

    Args:
        query: The search query string
        max_results: Number of results to return (default 5, max 10 for efficiency)
        search_depth: "basic" (default, faster) or "advanced" (slower but more thorough).
                     Use "advanced" only when basic search doesn't find relevant results.
        topic: "general" (default) or "news" (for recent news articles)
        include_domains: [Advanced] Limit search to specific domains.
                        Only use when user explicitly requests specific sources.
        exclude_domains: [Advanced] Exclude specific domains from results.
                        Only use when user wants to avoid certain sources.

    Returns:
        Raw search results with titles, URLs, and content snippets.
        The agent should read through all results and provide a comprehensive summary.

    Usage Guidelines:
        - For most queries, use default parameters (just query and max_results)
        - Only use search_depth="advanced" if basic search fails to find relevant info
        - Only use domain filters when explicitly requested by user
        - After receiving results, analyze ALL content and synthesize a complete answer

    Example:
        # Simple search (recommended for most cases)
        web_search("Python async programming best practices")

        # Get more results for comprehensive research
        web_search("machine learning frameworks comparison", max_results=8)

        # News search
        web_search("AI regulation updates 2024", topic="news")

        # Domain-specific search (only when user requests)
        web_search("React hooks", include_domains=["react.dev", "github.com"])
    """
    try:
        # Cap max_results for efficiency
        max_results = min(max_results, 10)

        response = tavily_client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_domains=include_domains or [],
            exclude_domains=exclude_domains or [],
            topic=topic
        )

        results = response.get("results", [])
        if not results:
            return f"No results found for: {query}"

        # Format raw results for agent analysis
        output_parts = [f"Search results for: {query}\\n"]
        output_parts.append(f"Found {len(results)} results:\\n")
        output_parts.append("=" * 50 + "\\n")

        for i, r in enumerate(results, 1):
            output_parts.append(f"[{i}] {r['title']}")
            output_parts.append(f"URL: {r['url']}")
            output_parts.append(f"Content: {r['content']}")
            output_parts.append("-" * 40 + "\\n")

        output_parts.append("\\n[Note: Please analyze all results above and provide a comprehensive summary based on the user\\'s question.]")

        return "\\n".join(output_parts)

    except Exception as e:
        return f"Search error: {str(e)}"
''',
            "dependencies": ["tavily-python"],
            "required_env": ["TAVILY_API_KEY"],
        },
        # ============================================
        # 2. Calculator (Safe Math)
        # ============================================
        {
            "id": "langchain_calculator",
            "name": "Calculator (LangChain Tool)",
            "description": "Safe mathematical calculator with support for common functions",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
import math
import operator

# Safe math operations whitelist
SAFE_OPERATIONS = {
    # Basic operators
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
    # Math functions
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    # Math module functions
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "pi": math.pi,
    "e": math.e,
}

@tool
def calculator(expression: str) -> str:
    """Evaluate mathematical expressions safely.

    Args:
        expression: Mathematical expression to evaluate

    Returns:
        Result of the calculation

    Supported operations:
        - Basic: +, -, *, /, //, %, **
        - Functions: sqrt, sin, cos, tan, log, log10, log2, exp
        - Rounding: floor, ceil, round, abs
        - Aggregation: min, max, sum
        - Constants: pi, e

    Example:
        calculator("2 + 3 * 4")  # Returns: "2 + 3 * 4 = 14"
        calculator("sqrt(16) + pi")  # Returns: "sqrt(16) + pi = 7.14159..."
        calculator("sin(pi/2)")  # Returns: "sin(pi/2) = 1.0"
    """
    try:
        # Replace common function names with safe versions
        safe_expr = expression

        # Create safe evaluation context
        safe_dict = {"__builtins__": {}}
        safe_dict.update(SAFE_OPERATIONS)

        result = eval(safe_expr, safe_dict)

        # Format result
        if isinstance(result, float):
            if result.is_integer():
                result = int(result)
            else:
                result = round(result, 10)

        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "Error: Division by zero"
    except ValueError as e:
        return f"Error: Invalid value - {str(e)}"
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"
''',
            "dependencies": [],
            "required_env": [],
        },
        # ============================================
        # 3. DateTime Tool
        # ============================================
        {
            "id": "langchain_datetime",
            "name": "DateTime Tool (LangChain Tool)",
            "description": "Date and time operations - parsing, formatting, and calculations",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
from datetime import datetime, timedelta
from typing import Optional
import time

@tool
def datetime_tool(
    operation: str,
    date_string: Optional[str] = None,
    format_pattern: str = "%Y-%m-%d %H:%M:%S",
    timezone: str = "local",
    days: int = 0,
    hours: int = 0,
    minutes: int = 0
) -> str:
    """Perform date and time operations.

    Args:
        operation: Operation to perform:
            - "now": Get current datetime
            - "parse": Parse a date string
            - "format": Format a date string to different format
            - "add": Add time to a date
            - "subtract": Subtract time from a date
            - "diff": Calculate difference between two dates
            - "timestamp": Convert to/from Unix timestamp
            - "weekday": Get day of week
        date_string: Date string to process (for parse/format/add/subtract)
        format_pattern: Output format pattern (default: "%Y-%m-%d %H:%M:%S")
        timezone: Timezone ("local" or "utc")
        days: Days to add/subtract
        hours: Hours to add/subtract
        minutes: Minutes to add/subtract

    Returns:
        Formatted date/time result

    Format patterns:
        %Y: Year (2024)
        %m: Month (01-12)
        %d: Day (01-31)
        %H: Hour 24h (00-23)
        %I: Hour 12h (01-12)
        %M: Minute (00-59)
        %S: Second (00-59)
        %p: AM/PM
        %A: Weekday name
        %B: Month name

    Example:
        datetime_tool("now")
        datetime_tool("now", format_pattern="%Y年%m月%d日")
        datetime_tool("add", date_string="2024-01-01", days=30)
        datetime_tool("parse", date_string="2024-01-15 10:30:00")
    """
    try:
        now = datetime.utcnow() if timezone == "utc" else datetime.now()

        if operation == "now":
            return now.strftime(format_pattern)

        elif operation == "timestamp":
            if date_string:
                # Convert date string to timestamp
                dt = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
                return str(int(dt.timestamp()))
            else:
                # Return current timestamp
                return str(int(time.time()))

        elif operation == "from_timestamp":
            if date_string:
                ts = int(date_string)
                dt = datetime.fromtimestamp(ts)
                return dt.strftime(format_pattern)
            return "Error: timestamp required"

        elif operation == "parse":
            if not date_string:
                return "Error: date_string required"
            # Try common formats
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%d-%m-%Y",
                "%d/%m/%Y",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_string, fmt)
                    return f"Parsed: {dt.strftime(format_pattern)}"
                except ValueError:
                    continue
            return f"Could not parse date: {date_string}"

        elif operation == "format":
            if not date_string:
                return "Error: date_string required"
            dt = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
            return dt.strftime(format_pattern)

        elif operation in ("add", "subtract"):
            base_date = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S") if date_string else now
            delta = timedelta(days=days, hours=hours, minutes=minutes)
            if operation == "subtract":
                delta = -delta
            result = base_date + delta
            return result.strftime(format_pattern)

        elif operation == "weekday":
            dt = datetime.strptime(date_string, "%Y-%m-%d") if date_string else now
            weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            return f"{dt.strftime('%Y-%m-%d')} is {weekdays[dt.weekday()]}"

        elif operation == "diff":
            if not date_string:
                return "Error: date_string required (format: date1|date2)"
            dates = date_string.split("|")
            if len(dates) != 2:
                return "Error: Provide two dates separated by | (e.g., 2024-01-01|2024-12-31)"
            dt1 = datetime.strptime(dates[0].strip(), "%Y-%m-%d")
            dt2 = datetime.strptime(dates[1].strip(), "%Y-%m-%d")
            diff = abs((dt2 - dt1).days)
            return f"Difference: {diff} days"

        else:
            return f"Unknown operation: {operation}. Available: now, parse, format, add, subtract, diff, timestamp, weekday"

    except Exception as e:
        return f"Error: {str(e)}"
''',
            "dependencies": [],
            "required_env": [],
        },
        # ============================================
        # 4. JSON Tool
        # ============================================
        {
            "id": "langchain_json",
            "name": "JSON Tool (LangChain Tool)",
            "description": "JSON parsing, querying, and transformation operations",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
from typing import Optional
import json

@tool
def json_tool(
    operation: str,
    data: str,
    path: Optional[str] = None,
    value: Optional[str] = None,
    indent: int = 2
) -> str:
    """Parse, query, and transform JSON data.

    Args:
        operation: Operation to perform:
            - "parse": Parse and validate JSON
            - "format": Pretty-print JSON with indentation
            - "minify": Minify JSON (remove whitespace)
            - "get": Get value at JSON path
            - "set": Set value at JSON path
            - "keys": Get all keys at path
            - "values": Get all values at path
            - "flatten": Flatten nested JSON
            - "type": Get type of value at path
        data: JSON string to process
        path: Dot-notation path for get/set operations (e.g., "user.name", "items[0].id")
        value: Value to set (for set operation, as JSON string)
        indent: Indentation spaces for formatting (default: 2)

    Returns:
        Processed JSON result

    Example:
        json_tool("parse", '{"name": "John", "age": 30}')
        json_tool("get", '{"user": {"name": "John"}}', path="user.name")
        json_tool("set", '{"count": 1}', path="count", value="2")
        json_tool("keys", '{"a": 1, "b": 2, "c": 3}')
    """
    try:
        # Parse input JSON
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {str(e)}"

        if operation == "parse":
            return f"Valid JSON. Type: {type(obj).__name__}, Size: {len(str(obj))} chars"

        elif operation == "format":
            return json.dumps(obj, indent=indent, ensure_ascii=False)

        elif operation == "minify":
            return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)

        elif operation == "get":
            if not path:
                return json.dumps(obj, indent=indent, ensure_ascii=False)
            result = _get_json_path(obj, path)
            if isinstance(result, (dict, list)):
                return json.dumps(result, indent=indent, ensure_ascii=False)
            return str(result)

        elif operation == "set":
            if not path or value is None:
                return "Error: path and value required for set operation"
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                parsed_value = value
            result = _set_json_path(obj, path, parsed_value)
            return json.dumps(result, indent=indent, ensure_ascii=False)

        elif operation == "keys":
            target = _get_json_path(obj, path) if path else obj
            if isinstance(target, dict):
                return json.dumps(list(target.keys()), indent=indent)
            return "Error: Target is not an object"

        elif operation == "values":
            target = _get_json_path(obj, path) if path else obj
            if isinstance(target, dict):
                return json.dumps(list(target.values()), indent=indent, ensure_ascii=False)
            return "Error: Target is not an object"

        elif operation == "flatten":
            result = _flatten_json(obj)
            return json.dumps(result, indent=indent, ensure_ascii=False)

        elif operation == "type":
            target = _get_json_path(obj, path) if path else obj
            return f"Type: {type(target).__name__}"

        else:
            return f"Unknown operation: {operation}. Available: parse, format, minify, get, set, keys, values, flatten, type"

    except Exception as e:
        return f"Error: {str(e)}"

def _get_json_path(obj, path):
    """Navigate JSON using dot notation with array support."""
    parts = path.replace("[", ".[").split(".")
    current = obj
    for part in parts:
        if not part:
            continue
        if part.startswith("[") and part.endswith("]"):
            index = int(part[1:-1])
            current = current[index]
        else:
            current = current[part]
    return current

def _set_json_path(obj, path, value):
    """Set value at JSON path."""
    parts = path.replace("[", ".[").split(".")
    current = obj
    for part in parts[:-1]:
        if not part:
            continue
        if part.startswith("[") and part.endswith("]"):
            index = int(part[1:-1])
            current = current[index]
        else:
            if part not in current:
                current[part] = {}
            current = current[part]
    last_part = parts[-1]
    if last_part.startswith("[") and last_part.endswith("]"):
        index = int(last_part[1:-1])
        current[index] = value
    else:
        current[last_part] = value
    return obj

def _flatten_json(obj, prefix=""):
    """Flatten nested JSON to dot notation."""
    result = {}
    if isinstance(obj, dict):
        for key, val in obj.items():
            new_key = f"{prefix}.{key}" if prefix else key
            result.update(_flatten_json(val, new_key))
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            new_key = f"{prefix}[{i}]"
            result.update(_flatten_json(val, new_key))
    else:
        result[prefix] = obj
    return result
''',
            "dependencies": [],
            "required_env": [],
        },
        # ============================================
        # 5. Text Processing Tool
        # ============================================
        {
            "id": "langchain_text",
            "name": "Text Processing (LangChain Tool)",
            "description": "Text manipulation, analysis, and transformation operations",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
from typing import Optional
import re
from collections import Counter

@tool
def text_tool(
    operation: str,
    text: str,
    pattern: Optional[str] = None,
    replacement: Optional[str] = None,
    count: int = -1
) -> str:
    """Perform text processing and analysis operations.

    Args:
        operation: Operation to perform:
            - "length": Get text length (chars and words)
            - "upper": Convert to uppercase
            - "lower": Convert to lowercase
            - "title": Convert to title case
            - "reverse": Reverse the text
            - "trim": Remove leading/trailing whitespace
            - "replace": Replace pattern with replacement
            - "split": Split by pattern (default: whitespace)
            - "join": Join lines with pattern
            - "count": Count occurrences of pattern
            - "find": Find all matches of pattern (regex)
            - "extract": Extract text matching pattern
            - "lines": Get line count and list
            - "words": Get word frequency
            - "unique_words": Get unique words
            - "remove_duplicates": Remove duplicate lines
            - "sort_lines": Sort lines alphabetically
        text: Input text to process
        pattern: Pattern for replace/split/count/find operations
        replacement: Replacement string for replace operation
        count: Max replacements (-1 for all)

    Returns:
        Processed text result

    Example:
        text_tool("upper", "hello world")
        text_tool("replace", "hello world", pattern="world", replacement="Python")
        text_tool("find", "Contact: test@email.com", pattern=r"[\\w.-]+@[\\w.-]+")
        text_tool("words", "the quick brown fox jumps over the lazy dog")
    """
    try:
        if operation == "length":
            chars = len(text)
            words = len(text.split())
            lines = text.count("\\n") + 1
            return f"Characters: {chars}, Words: {words}, Lines: {lines}"

        elif operation == "upper":
            return text.upper()

        elif operation == "lower":
            return text.lower()

        elif operation == "title":
            return text.title()

        elif operation == "reverse":
            return text[::-1]

        elif operation == "trim":
            return text.strip()

        elif operation == "replace":
            if not pattern:
                return "Error: pattern required for replace"
            if replacement is None:
                replacement = ""
            if count == -1:
                return text.replace(pattern, replacement)
            return text.replace(pattern, replacement, count)

        elif operation == "split":
            delimiter = pattern if pattern else None
            parts = text.split(delimiter)
            return "\\n".join(f"{i+1}. {part}" for i, part in enumerate(parts))

        elif operation == "join":
            delimiter = pattern if pattern else " "
            lines = text.split("\\n")
            return delimiter.join(lines)

        elif operation == "count":
            if not pattern:
                return "Error: pattern required for count"
            count_result = text.count(pattern)
            return f"Found {count_result} occurrence(s) of '{pattern}'"

        elif operation == "find":
            if not pattern:
                return "Error: pattern required for find"
            matches = re.findall(pattern, text)
            if matches:
                return f"Found {len(matches)} match(es):\\n" + "\\n".join(f"- {m}" for m in matches)
            return "No matches found"

        elif operation == "extract":
            if not pattern:
                return "Error: pattern required for extract"
            matches = re.findall(pattern, text)
            return "\\n".join(matches) if matches else "No matches found"

        elif operation == "lines":
            lines = text.split("\\n")
            result = f"Total lines: {len(lines)}\\n\\n"
            for i, line in enumerate(lines, 1):
                result += f"{i}: {line}\\n"
            return result

        elif operation == "words":
            words = re.findall(r"\\b\\w+\\b", text.lower())
            freq = Counter(words)
            most_common = freq.most_common(20)
            result = f"Total words: {len(words)}, Unique: {len(freq)}\\n\\nTop words:\\n"
            for word, count in most_common:
                result += f"  {word}: {count}\\n"
            return result

        elif operation == "unique_words":
            words = set(re.findall(r"\\b\\w+\\b", text.lower()))
            return f"Unique words ({len(words)}):\\n" + ", ".join(sorted(words))

        elif operation == "remove_duplicates":
            lines = text.split("\\n")
            seen = set()
            unique = []
            for line in lines:
                if line not in seen:
                    seen.add(line)
                    unique.append(line)
            return f"Removed {len(lines) - len(unique)} duplicate(s)\\n\\n" + "\\n".join(unique)

        elif operation == "sort_lines":
            lines = text.split("\\n")
            return "\\n".join(sorted(lines))

        else:
            return f"Unknown operation: {operation}"

    except Exception as e:
        return f"Error: {str(e)}"
''',
            "dependencies": [],
            "required_env": [],
        },
        # ============================================
        # 6. URL Tool
        # ============================================
        {
            "id": "langchain_url",
            "name": "URL Tool (LangChain Tool)",
            "description": "URL parsing, building, and manipulation operations",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
from urllib.parse import urlparse, urlencode, parse_qs, quote, unquote, urljoin
from typing import Optional
import json

@tool
def url_tool(
    operation: str,
    url: str,
    params: Optional[str] = None
) -> str:
    """Parse, build, and manipulate URLs.

    Args:
        operation: Operation to perform:
            - "parse": Parse URL into components
            - "build": Build URL from components (params as JSON)
            - "encode": URL encode a string
            - "decode": URL decode a string
            - "add_params": Add query parameters (params as JSON)
            - "get_params": Get query parameters as JSON
            - "join": Join base URL with path
            - "domain": Extract domain from URL
            - "validate": Check if URL is valid
        url: URL or string to process
        params: Additional parameters as JSON string

    Returns:
        Processed URL or URL components

    Example:
        url_tool("parse", "https://example.com/path?foo=bar&baz=123")
        url_tool("add_params", "https://api.example.com/search", params='{"q": "test", "page": 1}')
        url_tool("encode", "hello world & special=chars")
        url_tool("join", "https://example.com/api/", params="users/123")
    """
    try:
        if operation == "parse":
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            return f"""URL Components:
  Scheme: {parsed.scheme}
  Host: {parsed.netloc}
  Path: {parsed.path}
  Query: {parsed.query}
  Fragment: {parsed.fragment}

Query Parameters:
{json.dumps(query_params, indent=2)}"""

        elif operation == "build":
            if not params:
                return "Error: params required as JSON with scheme, host, path, query"
            components = json.loads(params)
            scheme = components.get("scheme", "https")
            host = components.get("host", "")
            path = components.get("path", "")
            query = components.get("query", {})
            fragment = components.get("fragment", "")

            url = f"{scheme}://{host}{path}"
            if query:
                url += "?" + urlencode(query)
            if fragment:
                url += "#" + fragment
            return url

        elif operation == "encode":
            return quote(url, safe="")

        elif operation == "decode":
            return unquote(url)

        elif operation == "add_params":
            if not params:
                return "Error: params required as JSON"
            new_params = json.loads(params)
            parsed = urlparse(url)
            existing_params = parse_qs(parsed.query)

            # Merge parameters
            for key, value in new_params.items():
                existing_params[key] = [str(value)]

            # Rebuild URL
            query_string = urlencode({k: v[0] for k, v in existing_params.items()})
            new_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if query_string:
                new_url += "?" + query_string
            if parsed.fragment:
                new_url += "#" + parsed.fragment
            return new_url

        elif operation == "get_params":
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            # Flatten single-value lists
            flat_params = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
            return json.dumps(flat_params, indent=2)

        elif operation == "join":
            if not params:
                return "Error: params required (path to join)"
            return urljoin(url, params)

        elif operation == "domain":
            parsed = urlparse(url)
            return parsed.netloc or "Could not extract domain"

        elif operation == "validate":
            try:
                parsed = urlparse(url)
                is_valid = all([parsed.scheme, parsed.netloc])
                if is_valid:
                    return f"Valid URL: {url}"
                return f"Invalid URL: missing {'scheme' if not parsed.scheme else 'host'}"
            except Exception:
                return f"Invalid URL: {url}"

        else:
            return f"Unknown operation: {operation}. Available: parse, build, encode, decode, add_params, get_params, join, domain, validate"

    except json.JSONDecodeError:
        return "Error: Invalid JSON in params"
    except Exception as e:
        return f"Error: {str(e)}"
''',
            "dependencies": [],
            "required_env": [],
        },
        # ============================================
        # 7. Hash & Encoding Tool
        # ============================================
        {
            "id": "langchain_hash",
            "name": "Hash & Encoding (LangChain Tool)",
            "description": "Hashing, encoding, and decoding operations",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
import hashlib
import base64
import hmac
from typing import Optional

@tool
def hash_tool(
    operation: str,
    data: str,
    algorithm: str = "sha256",
    key: Optional[str] = None,
    encoding: str = "utf-8"
) -> str:
    """Perform hashing and encoding operations.

    Args:
        operation: Operation to perform:
            - "hash": Generate hash of data
            - "hmac": Generate HMAC (requires key)
            - "base64_encode": Encode to Base64
            - "base64_decode": Decode from Base64
            - "hex_encode": Encode to hexadecimal
            - "hex_decode": Decode from hexadecimal
            - "compare": Compare two hashes (timing-safe)
        data: Data to process
        algorithm: Hash algorithm (md5, sha1, sha256, sha512, sha3_256)
        key: Secret key for HMAC operations
        encoding: Text encoding (default: utf-8)

    Returns:
        Processed result (hash, encoded/decoded data)

    Example:
        hash_tool("hash", "password123")  # SHA-256 by default
        hash_tool("hash", "data", algorithm="md5")
        hash_tool("hmac", "message", key="secret_key")
        hash_tool("base64_encode", "Hello World")
        hash_tool("base64_decode", "SGVsbG8gV29ybGQ=")
    """
    try:
        if operation == "hash":
            algorithms = {
                "md5": hashlib.md5,
                "sha1": hashlib.sha1,
                "sha256": hashlib.sha256,
                "sha512": hashlib.sha512,
                "sha3_256": hashlib.sha3_256,
                "sha3_512": hashlib.sha3_512,
            }
            if algorithm not in algorithms:
                return f"Unknown algorithm: {algorithm}. Available: {', '.join(algorithms.keys())}"

            hash_obj = algorithms[algorithm](data.encode(encoding))
            return f"{algorithm.upper()}: {hash_obj.hexdigest()}"

        elif operation == "hmac":
            if not key:
                return "Error: key required for HMAC"
            algorithms = {
                "md5": "md5",
                "sha1": "sha1",
                "sha256": "sha256",
                "sha512": "sha512",
            }
            if algorithm not in algorithms:
                return f"Unknown algorithm: {algorithm}"

            h = hmac.new(
                key.encode(encoding),
                data.encode(encoding),
                algorithms[algorithm]
            )
            return f"HMAC-{algorithm.upper()}: {h.hexdigest()}"

        elif operation == "base64_encode":
            encoded = base64.b64encode(data.encode(encoding)).decode("ascii")
            return encoded

        elif operation == "base64_decode":
            try:
                decoded = base64.b64decode(data).decode(encoding)
                return decoded
            except Exception as e:
                return f"Error decoding Base64: {str(e)}"

        elif operation == "hex_encode":
            return data.encode(encoding).hex()

        elif operation == "hex_decode":
            try:
                decoded = bytes.fromhex(data).decode(encoding)
                return decoded
            except ValueError as e:
                return f"Error decoding hex: {str(e)}"

        elif operation == "compare":
            # Timing-safe comparison
            if "|" not in data:
                return "Error: Provide two hashes separated by | (hash1|hash2)"
            hash1, hash2 = data.split("|", 1)
            is_equal = hmac.compare_digest(hash1.strip(), hash2.strip())
            return f"Hashes {'match' if is_equal else 'do NOT match'}"

        else:
            return f"Unknown operation: {operation}. Available: hash, hmac, base64_encode, base64_decode, hex_encode, hex_decode, compare"

    except Exception as e:
        return f"Error: {str(e)}"
''',
            "dependencies": [],
            "required_env": [],
        },
        # ============================================
        # 8. UUID Generator
        # ============================================
        {
            "id": "langchain_uuid",
            "name": "UUID Generator (LangChain Tool)",
            "description": "Generate and validate UUIDs",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
import uuid
from typing import Optional

@tool
def uuid_tool(
    operation: str = "generate",
    value: Optional[str] = None,
    count: int = 1,
    namespace: str = "dns"
) -> str:
    """Generate and validate UUIDs.

    Args:
        operation: Operation to perform:
            - "generate": Generate random UUID (v4)
            - "generate_v1": Generate time-based UUID (v1)
            - "generate_v3": Generate MD5 hash UUID (v3, needs value)
            - "generate_v5": Generate SHA-1 hash UUID (v5, needs value)
            - "validate": Validate UUID format
            - "version": Get UUID version
            - "parse": Parse UUID and show components
        value: Input value for v3/v5 generation or validation
        count: Number of UUIDs to generate (max 100)
        namespace: Namespace for v3/v5 (dns, url, oid, x500)

    Returns:
        Generated UUID(s) or validation result

    Example:
        uuid_tool("generate")  # Single random UUID
        uuid_tool("generate", count=5)  # 5 random UUIDs
        uuid_tool("generate_v5", value="example.com", namespace="dns")
        uuid_tool("validate", value="550e8400-e29b-41d4-a716-446655440000")
    """
    try:
        namespaces = {
            "dns": uuid.NAMESPACE_DNS,
            "url": uuid.NAMESPACE_URL,
            "oid": uuid.NAMESPACE_OID,
            "x500": uuid.NAMESPACE_X500,
        }

        if operation == "generate":
            count = min(count, 100)
            uuids = [str(uuid.uuid4()) for _ in range(count)]
            if count == 1:
                return uuids[0]
            return "\\n".join(uuids)

        elif operation == "generate_v1":
            count = min(count, 100)
            uuids = [str(uuid.uuid1()) for _ in range(count)]
            if count == 1:
                return uuids[0]
            return "\\n".join(uuids)

        elif operation == "generate_v3":
            if not value:
                return "Error: value required for v3 UUID"
            ns = namespaces.get(namespace, uuid.NAMESPACE_DNS)
            return str(uuid.uuid3(ns, value))

        elif operation == "generate_v5":
            if not value:
                return "Error: value required for v5 UUID"
            ns = namespaces.get(namespace, uuid.NAMESPACE_DNS)
            return str(uuid.uuid5(ns, value))

        elif operation == "validate":
            if not value:
                return "Error: value required for validation"
            try:
                parsed = uuid.UUID(value)
                return f"Valid UUID (version {parsed.version}): {parsed}"
            except ValueError:
                return f"Invalid UUID format: {value}"

        elif operation == "version":
            if not value:
                return "Error: value required"
            try:
                parsed = uuid.UUID(value)
                return f"UUID version: {parsed.version}"
            except ValueError:
                return f"Invalid UUID: {value}"

        elif operation == "parse":
            if not value:
                return "Error: value required"
            try:
                parsed = uuid.UUID(value)
                return f"""UUID: {parsed}
Version: {parsed.version}
Variant: {parsed.variant}
Hex: {parsed.hex}
Int: {parsed.int}
URN: {parsed.urn}"""
            except ValueError:
                return f"Invalid UUID: {value}"

        else:
            return f"Unknown operation: {operation}. Available: generate, generate_v1, generate_v3, generate_v5, validate, version, parse"

    except Exception as e:
        return f"Error: {str(e)}"
''',
            "dependencies": [],
            "required_env": [],
        },
        # ============================================
        # 9. Regex Tool
        # ============================================
        {
            "id": "langchain_regex",
            "name": "Regex Tool (LangChain Tool)",
            "description": "Regular expression matching, extraction, and replacement",
            "category": "langchain_tool",
            "difficulty": "intermediate",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
import re
from typing import Optional

@tool
def regex_tool(
    operation: str,
    text: str,
    pattern: str,
    replacement: Optional[str] = None,
    flags: str = ""
) -> str:
    """Perform regular expression operations.

    Args:
        operation: Operation to perform:
            - "match": Check if pattern matches at start
            - "search": Find first match anywhere
            - "findall": Find all matches
            - "findall_groups": Find all matches with groups
            - "replace": Replace all matches
            - "split": Split by pattern
            - "validate": Check if pattern is valid
            - "test": Test if pattern matches anywhere (returns bool)
        text: Text to search/process
        pattern: Regular expression pattern
        replacement: Replacement string (for replace operation)
        flags: Regex flags (i=ignorecase, m=multiline, s=dotall, x=verbose)

    Returns:
        Match results or processed text

    Common patterns:
        Email: r"[\\w.-]+@[\\w.-]+\\.\\w+"
        URL: r"https?://[\\w.-]+(?:/[\\w./-]*)?"
        Phone: r"\\+?\\d{1,3}[-.\\s]?\\d{3,4}[-.\\s]?\\d{4}"
        IPv4: r"\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}"
        Date: r"\\d{4}-\\d{2}-\\d{2}"

    Example:
        regex_tool("findall", "Contact: john@email.com, jane@test.org", r"[\\w.-]+@[\\w.-]+")
        regex_tool("replace", "Hello World", r"World", replacement="Python")
        regex_tool("split", "a,b;c|d", r"[,;|]")
    """
    try:
        # Parse flags
        flag_map = {
            "i": re.IGNORECASE,
            "m": re.MULTILINE,
            "s": re.DOTALL,
            "x": re.VERBOSE,
        }
        regex_flags = 0
        for f in flags:
            if f in flag_map:
                regex_flags |= flag_map[f]

        if operation == "validate":
            try:
                re.compile(pattern)
                return f"Valid regex pattern: {pattern}"
            except re.error as e:
                return f"Invalid regex: {str(e)}"

        elif operation == "match":
            match = re.match(pattern, text, regex_flags)
            if match:
                return f"Match found at position 0: '{match.group()}'\\nGroups: {match.groups()}"
            return "No match at start of string"

        elif operation == "search":
            match = re.search(pattern, text, regex_flags)
            if match:
                return f"Match found at position {match.start()}: '{match.group()}'\\nGroups: {match.groups()}"
            return "No match found"

        elif operation == "findall":
            matches = re.findall(pattern, text, regex_flags)
            if matches:
                return f"Found {len(matches)} match(es):\\n" + "\\n".join(f"  - {m}" for m in matches)
            return "No matches found"

        elif operation == "findall_groups":
            compiled = re.compile(pattern, regex_flags)
            matches = list(compiled.finditer(text))
            if matches:
                results = [f"Found {len(matches)} match(es):\\n"]
                for i, m in enumerate(matches, 1):
                    results.append(f"{i}. '{m.group()}' at {m.start()}-{m.end()}")
                    if m.groups():
                        results.append(f"   Groups: {m.groups()}")
                    if m.groupdict():
                        results.append(f"   Named: {m.groupdict()}")
                return "\\n".join(results)
            return "No matches found"

        elif operation == "replace":
            if replacement is None:
                return "Error: replacement required"
            result, count = re.subn(pattern, replacement, text, flags=regex_flags)
            return f"Replaced {count} occurrence(s):\\n{result}"

        elif operation == "split":
            parts = re.split(pattern, text, flags=regex_flags)
            return f"Split into {len(parts)} parts:\\n" + "\\n".join(f"  {i+1}. '{p}'" for i, p in enumerate(parts))

        elif operation == "test":
            match = re.search(pattern, text, regex_flags)
            return "true" if match else "false"

        else:
            return f"Unknown operation: {operation}. Available: match, search, findall, findall_groups, replace, split, validate, test"

    except re.error as e:
        return f"Regex error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"
''',
            "dependencies": [],
            "required_env": [],
        },
        # ============================================
        # 10. Random Generator
        # ============================================
        {
            "id": "langchain_random",
            "name": "Random Generator (LangChain Tool)",
            "description": "Generate random numbers, strings, and make random selections",
            "category": "langchain_tool",
            "difficulty": "beginner",
            "skill_type": SkillType.LANGCHAIN_TOOL.value,
            "code": '''from langchain_core.tools import tool
import random
import string
import secrets
from typing import Optional

@tool
def random_tool(
    operation: str,
    min_val: int = 0,
    max_val: int = 100,
    count: int = 1,
    length: int = 16,
    items: Optional[str] = None,
    charset: str = "alphanumeric"
) -> str:
    """Generate random values and make random selections.

    Args:
        operation: Operation to perform:
            - "int": Generate random integer(s)
            - "float": Generate random float(s)
            - "string": Generate random string(s)
            - "password": Generate secure password
            - "choice": Random choice from items
            - "sample": Random sample from items (no duplicates)
            - "shuffle": Shuffle items
            - "bool": Random boolean
            - "hex": Generate random hex string
            - "bytes": Generate random bytes (as hex)
        min_val: Minimum value for int/float
        max_val: Maximum value for int/float
        count: Number of values to generate
        length: Length for string/password/hex
        items: Comma-separated items for choice/sample/shuffle
        charset: Character set for string generation:
            - "alphanumeric": a-z, A-Z, 0-9
            - "alpha": a-z, A-Z
            - "lowercase": a-z
            - "uppercase": A-Z
            - "digits": 0-9
            - "hex": 0-9, a-f
            - "symbols": includes special characters

    Returns:
        Generated random value(s)

    Example:
        random_tool("int", min_val=1, max_val=100)
        random_tool("string", length=20, charset="alphanumeric")
        random_tool("password", length=16)
        random_tool("choice", items="apple,banana,orange,grape")
        random_tool("sample", items="1,2,3,4,5,6,7,8,9,10", count=5)
    """
    try:
        count = min(count, 1000)
        length = min(length, 1000)

        if operation == "int":
            results = [random.randint(min_val, max_val) for _ in range(count)]
            return "\\n".join(map(str, results)) if count > 1 else str(results[0])

        elif operation == "float":
            results = [round(random.uniform(min_val, max_val), 6) for _ in range(count)]
            return "\\n".join(map(str, results)) if count > 1 else str(results[0])

        elif operation == "string":
            charsets = {
                "alphanumeric": string.ascii_letters + string.digits,
                "alpha": string.ascii_letters,
                "lowercase": string.ascii_lowercase,
                "uppercase": string.ascii_uppercase,
                "digits": string.digits,
                "hex": string.hexdigits[:16],
                "symbols": string.ascii_letters + string.digits + string.punctuation,
            }
            chars = charsets.get(charset, charsets["alphanumeric"])
            results = ["".join(random.choices(chars, k=length)) for _ in range(count)]
            return "\\n".join(results) if count > 1 else results[0]

        elif operation == "password":
            # Secure password with guaranteed character types
            results = []
            for _ in range(count):
                # Ensure at least one of each type
                password = [
                    secrets.choice(string.ascii_lowercase),
                    secrets.choice(string.ascii_uppercase),
                    secrets.choice(string.digits),
                    secrets.choice("!@#$%^&*()_+-=[]{}|"),
                ]
                # Fill the rest
                all_chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|"
                password.extend(secrets.choice(all_chars) for _ in range(length - 4))
                random.shuffle(password)
                results.append("".join(password))
            return "\\n".join(results) if count > 1 else results[0]

        elif operation == "choice":
            if not items:
                return "Error: items required (comma-separated)"
            item_list = [i.strip() for i in items.split(",")]
            results = [random.choice(item_list) for _ in range(count)]
            return "\\n".join(results) if count > 1 else results[0]

        elif operation == "sample":
            if not items:
                return "Error: items required (comma-separated)"
            item_list = [i.strip() for i in items.split(",")]
            count = min(count, len(item_list))
            result = random.sample(item_list, count)
            return ", ".join(result)

        elif operation == "shuffle":
            if not items:
                return "Error: items required (comma-separated)"
            item_list = [i.strip() for i in items.split(",")]
            random.shuffle(item_list)
            return ", ".join(item_list)

        elif operation == "bool":
            results = [str(random.choice([True, False])) for _ in range(count)]
            return "\\n".join(results) if count > 1 else results[0]

        elif operation == "hex":
            results = [secrets.token_hex(length // 2) for _ in range(count)]
            return "\\n".join(results) if count > 1 else results[0]

        elif operation == "bytes":
            results = [secrets.token_bytes(length).hex() for _ in range(count)]
            return "\\n".join(results) if count > 1 else results[0]

        else:
            return f"Unknown operation: {operation}. Available: int, float, string, password, choice, sample, shuffle, bool, hex, bytes"

    except Exception as e:
        return f"Error: {str(e)}"
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

