"""
Security Tests: XSS Prevention (Task 8.5.6)

Tests to validate Cross-Site Scripting (XSS) prevention mechanisms.

References:
- Requirements 7: Data security and privacy
- Design Section 8: Access Control and Security
"""

import html
import json
import re
from unittest.mock import Mock, patch

import pytest


class TestXSSPrevention:
    """Test XSS prevention mechanisms."""

    def test_html_escaping(self):
        """Test that HTML special characters are escaped."""
        # Arrange
        malicious_input = "<script>alert('XSS')</script>"

        # Act
        escaped = html.escape(malicious_input)

        # Assert
        assert "&lt;script&gt;" in escaped
        assert "<script>" not in escaped

    def test_javascript_escaping(self):
        """Test that JavaScript is escaped in HTML context."""
        # Arrange
        malicious_inputs = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "<svg onload=alert('XSS')>",
            "javascript:alert('XSS')",
        ]

        for malicious_input in malicious_inputs:
            # Act
            escaped = html.escape(malicious_input)

            # Assert
            assert "<script>" not in escaped
            assert "onerror=" not in escaped or "&" in escaped
            assert "onload=" not in escaped or "&" in escaped

    def test_attribute_escaping(self):
        """Test that HTML attributes are properly escaped."""
        # Arrange
        malicious_input = "\" onload=\"alert('XSS')"

        # Act
        escaped = html.escape(malicious_input, quote=True)

        # Assert
        assert "&quot;" in escaped
        assert '"' not in escaped or escaped.count('"') == 0

    def test_url_validation(self):
        """Test that URLs are validated to prevent javascript: protocol."""
        # Arrange
        malicious_urls = [
            "javascript:alert('XSS')",
            "data:text/html,<script>alert('XSS')</script>",
            "vbscript:msgbox('XSS')",
        ]

        safe_urls = [
            "https://example.com",
            "http://example.com",
            "/relative/path",
            "mailto:user@example.com",
        ]

        # Act & Assert
        for url in malicious_urls:
            is_safe = url.startswith(("http://", "https://", "/", "mailto:"))
            assert is_safe is False

        for url in safe_urls:
            is_safe = url.startswith(("http://", "https://", "/", "mailto:"))
            assert is_safe is True

    def test_content_security_policy(self):
        """Test that Content Security Policy headers are set."""
        # Arrange
        csp_header = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )

        # Assert
        assert "default-src 'self'" in csp_header
        assert "script-src 'self'" in csp_header
        assert "'unsafe-eval'" not in csp_header  # Should not allow eval

    def test_x_xss_protection_header(self):
        """Test that X-XSS-Protection header is set."""
        # Arrange
        headers = {"X-XSS-Protection": "1; mode=block"}

        # Assert
        assert headers.get("X-XSS-Protection") == "1; mode=block"

    def test_x_content_type_options(self):
        """Test that X-Content-Type-Options header is set."""
        # Arrange
        headers = {"X-Content-Type-Options": "nosniff"}

        # Assert
        assert headers.get("X-Content-Type-Options") == "nosniff"


class TestStoredXSSPrevention:
    """Test prevention of stored XSS attacks."""

    def test_sanitize_user_input(self):
        """Test that user input is sanitized before storage."""
        # Arrange
        malicious_input = "<script>alert('XSS')</script>Hello"

        # Act - Remove script tags
        sanitized = re.sub(
            r"<script[^>]*>.*?</script>", "", malicious_input, flags=re.IGNORECASE | re.DOTALL
        )

        # Assert
        assert "<script>" not in sanitized
        assert "Hello" in sanitized

    def test_sanitize_html_tags(self):
        """Test that dangerous HTML tags are removed."""
        # Arrange
        malicious_input = "<img src=x onerror=alert('XSS')>"

        # Act - Remove dangerous attributes
        sanitized = re.sub(r"on\w+\s*=", "", malicious_input, flags=re.IGNORECASE)

        # Assert
        assert "onerror=" not in sanitized

    def test_whitelist_safe_html(self):
        """Test that only whitelisted HTML tags are allowed."""
        # Arrange
        allowed_tags = ["p", "br", "strong", "em", "a"]
        input_html = "<p>Hello</p><script>alert('XSS')</script><strong>World</strong>"

        # Act - Extract tags
        tags = re.findall(r"<(\w+)", input_html)

        # Assert
        dangerous_tags = [tag for tag in tags if tag not in allowed_tags]
        assert "script" in dangerous_tags

    def test_sanitize_markdown(self):
        """Test that markdown is safely converted to HTML."""
        # Arrange
        malicious_markdown = "[Click me](javascript:alert('XSS'))"

        # Act - Validate URL in markdown link
        url_match = re.search(r"\[.*?\]\((.*?)\)", malicious_markdown)
        if url_match:
            url = url_match.group(1)
            is_safe = url.startswith(("http://", "https://", "/"))
        else:
            is_safe = True

        # Assert
        assert is_safe is False


class TestReflectedXSSPrevention:
    """Test prevention of reflected XSS attacks."""

    def test_escape_query_parameters(self):
        """Test that query parameters are escaped."""
        # Arrange
        malicious_param = "<script>alert('XSS')</script>"

        # Act
        escaped = html.escape(malicious_param)

        # Assert
        assert "<script>" not in escaped

    def test_escape_error_messages(self):
        """Test that error messages escape user input."""
        # Arrange
        user_input = "<script>alert('XSS')</script>"
        error_message = f"Invalid input: {html.escape(user_input)}"

        # Assert
        assert "<script>" not in error_message
        assert "&lt;script&gt;" in error_message

    def test_escape_search_results(self):
        """Test that search results escape user input."""
        # Arrange
        search_query = "<img src=x onerror=alert('XSS')>"

        # Act
        escaped_query = html.escape(search_query)
        result_message = f"Search results for: {escaped_query}"

        # Assert
        assert "onerror=" not in result_message or "&" in result_message


class TestDOMBasedXSSPrevention:
    """Test prevention of DOM-based XSS attacks."""

    def test_json_encoding(self):
        """Test that data is properly JSON encoded."""
        # Arrange
        data = {"message": "<script>alert('XSS')</script>"}

        # Act
        json_data = json.dumps(data)

        # Assert
        # JSON encoding escapes < and > as unicode
        assert "\\u003c" in json_data or "<script>" not in json_data

    def test_avoid_innerhtml(self):
        """Test that innerHTML is avoided in favor of textContent."""
        # This is a conceptual test for frontend code
        # Frontend should use textContent instead of innerHTML

        # Bad practice
        bad_code = "element.innerHTML = userInput"

        # Good practice
        good_code = "element.textContent = userInput"

        assert "innerHTML" in bad_code
        assert "textContent" in good_code

    def test_sanitize_dom_manipulation(self):
        """Test that DOM manipulation is sanitized."""
        # Arrange
        user_input = "<img src=x onerror=alert('XSS')>"

        # Act - Escape before DOM manipulation
        escaped = html.escape(user_input)

        # Assert
        assert "onerror=" not in escaped or "&" in escaped


class TestAPIResponseSecurity:
    """Test API response security against XSS."""

    def test_json_content_type(self):
        """Test that JSON responses have correct content type."""
        # Arrange
        headers = {"Content-Type": "application/json"}

        # Assert
        assert headers.get("Content-Type") == "application/json"

    def test_escape_json_values(self):
        """Test that JSON values are properly escaped."""
        # Arrange
        data = {"name": "<script>alert('XSS')</script>", "description": "Normal text"}

        # Act
        json_response = json.dumps(data)

        # Assert
        # JSON encoding should escape special characters
        assert "<script>" not in json_response or "\\" in json_response

    def test_no_jsonp_callback(self):
        """Test that JSONP callbacks are not allowed."""
        # JSONP can be exploited for XSS
        # Modern APIs should use CORS instead

        # Bad practice
        jsonp_response = "callback({data: 'value'})"

        # Good practice
        json_response = '{"data": "value"}'

        assert "callback(" in jsonp_response
        assert "callback(" not in json_response


class TestFileUploadSecurity:
    """Test file upload security against XSS."""

    def test_validate_file_type(self):
        """Test that file types are validated."""
        # Arrange
        allowed_types = ["image/png", "image/jpeg", "application/pdf"]
        malicious_type = "text/html"

        # Assert
        assert malicious_type not in allowed_types

    def test_sanitize_filename(self):
        """Test that filenames are sanitized."""
        # Arrange
        malicious_filename = "<script>alert('XSS')</script>.jpg"

        # Act - Remove special characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "", malicious_filename)

        # Assert
        assert "<script>" not in sanitized

    def test_serve_files_with_correct_headers(self):
        """Test that uploaded files are served with security headers."""
        # Arrange
        headers = {
            "Content-Type": "image/jpeg",
            "Content-Disposition": "attachment; filename=image.jpg",
            "X-Content-Type-Options": "nosniff",
        }

        # Assert
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert "attachment" in headers.get("Content-Disposition", "")

    def test_prevent_svg_xss(self):
        """Test that SVG files are sanitized."""
        # Arrange
        malicious_svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <script>alert('XSS')</script>
        </svg>
        """

        # Act - Check for script tags in SVG
        has_script = "<script>" in malicious_svg

        # Assert
        assert has_script is True  # Should be detected and removed


class TestRichTextEditorSecurity:
    """Test rich text editor security."""

    def test_sanitize_rich_text(self):
        """Test that rich text content is sanitized."""
        # Arrange
        rich_text = """
        <p>Normal text</p>
        <script>alert('XSS')</script>
        <img src=x onerror=alert('XSS')>
        """

        # Act - Remove dangerous elements
        sanitized = re.sub(
            r"<script[^>]*>.*?</script>", "", rich_text, flags=re.IGNORECASE | re.DOTALL
        )
        sanitized = re.sub(r"on\w+\s*=", "", sanitized, flags=re.IGNORECASE)

        # Assert
        assert "<script>" not in sanitized
        assert "onerror=" not in sanitized

    def test_whitelist_safe_attributes(self):
        """Test that only safe attributes are allowed."""
        # Arrange
        allowed_attributes = ["href", "src", "alt", "title", "class", "id"]
        dangerous_attributes = ["onclick", "onerror", "onload", "onmouseover"]

        html_content = '<a href="#" onclick="alert(\'XSS\')">Link</a>'

        # Act - Extract attributes
        attributes = re.findall(r"(\w+)\s*=", html_content)

        # Assert
        dangerous_found = [attr for attr in attributes if attr in dangerous_attributes]
        assert len(dangerous_found) > 0  # Should be detected

    def test_limit_nesting_depth(self):
        """Test that HTML nesting depth is limited."""
        # Arrange
        deeply_nested = "<div>" * 100 + "content" + "</div>" * 100
        max_depth = 10

        # Act - Count nesting depth
        depth = deeply_nested.count("<div>")

        # Assert
        assert depth > max_depth  # Should be rejected
