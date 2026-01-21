# Testing Guide

Comprehensive testing guide for the Digital Workforce Platform.

## Overview

This guide covers testing strategies, tools, and best practices for ensuring code quality and reliability.

## Test Infrastructure

### Test Runner

Use the provided test runner script:

```bash
cd backend
./run_tests.sh
```

Options:
- `-v` or `--verbose`: Verbose output
- `-vv` or `--very-verbose`: Very verbose output
- `-m MARKER`: Run tests with specific marker
- `-k KEYWORD`: Run tests matching keyword
- `--fast`: Skip slow tests
- `--slow`: Run only slow tests

### Test Configuration

Test configuration is in `backend/pytest.ini`:
- Test discovery patterns
- Coverage settings
- Markers for test categorization
- Asyncio mode configuration

## Current Test Status

### Overall Coverage

- **Total Tests**: 106 passing
- **Overall Coverage**: 8%
- **Target Coverage**: 80%

### Module Coverage

| Module | Tests | Coverage | Status |
|--------|-------|----------|--------|
| API Gateway | 27 tests | 89% pass rate | ✅ Good |
| Access Control | 403 tests | 87% pass rate | ✅ Good |
| Memory System | 31 tests | 94% pass rate | ✅ Good |
| LLM Providers | 16 tests | 75% pass rate | ⚠️ Needs work |
| Shared Utilities | High | 24.6% | ⚠️ Needs work |
| Agent Framework | Tests exist | Import errors | ❌ Blocked |
| Task Manager | Tests exist | Import errors | ❌ Blocked |
| Knowledge Base | Tests exist | Import errors | ❌ Blocked |

### Known Issues

1. **LangChain API Changes**: Agent Framework and Task Manager tests fail due to LangChain API changes
   - `AgentExecutor` import path changed
   - `create_react_agent` import path changed
   - Solution: Update imports to use new LangChain API

2. **Import Dependencies**: Some modules have circular import issues
   - Knowledge Base: `get_minio_client` function name mismatch
   - Solution: Fix function names and imports

3. **Async Context Managers**: LLM Provider tests have async context manager issues
   - Solution: Update test fixtures to properly handle async contexts

## Test Categories

### Unit Tests

Test individual components in isolation:

```python
def test_function_behavior():
    """Test specific function behavior."""
    result = my_function(input_data)
    assert result == expected_output
```

### Integration Tests

Test component interactions:

```python
@pytest.mark.integration
async def test_api_to_database():
    """Test API Gateway to Database integration."""
    # Test code here
```

### End-to-End Tests

Test complete user workflows:

```python
@pytest.mark.e2e
async def test_user_registration_flow():
    """Test complete user registration workflow."""
    # Test code here
```

## Writing Tests

### Test Structure

```python
"""Test module docstring.

References:
- Requirements X.Y: Description
- Design Section Z: Description
"""

import pytest
from unittest.mock import Mock, patch

from module import function_to_test


@pytest.fixture
def sample_data():
    """Provide sample test data."""
    return {"key": "value"}


class TestFeature:
    """Test feature functionality."""
    
    def test_basic_behavior(self, sample_data):
        """Test basic behavior with sample data."""
        result = function_to_test(sample_data)
        assert result is not None
    
    def test_error_handling(self):
        """Test error handling."""
        with pytest.raises(ValueError):
            function_to_test(invalid_data)
```

### Mocking

Use mocks for external dependencies:

```python
@patch('module.external_service')
def test_with_mock(mock_service):
    """Test with mocked external service."""
    mock_service.return_value = "mocked_response"
    result = function_using_service()
    assert result == "expected_result"
    mock_service.assert_called_once()
```

### Async Tests

Test async functions:

```python
@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await async_function()
    assert result is not None
```

## Test Markers

Use markers to categorize tests:

```python
@pytest.mark.unit
def test_unit():
    """Unit test."""
    pass

@pytest.mark.integration
def test_integration():
    """Integration test."""
    pass

@pytest.mark.slow
def test_slow_operation():
    """Slow test."""
    pass

@pytest.mark.api
def test_api_endpoint():
    """API test."""
    pass
```

## Coverage Requirements

### Target Coverage

- **Overall**: 80% minimum
- **Critical modules**: 90% minimum
  - Access Control
  - API Gateway
  - Authentication
  - Data encryption

### Measuring Coverage

```bash
# Run tests with coverage
pytest --cov=. --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html
```

### Coverage Exclusions

Exclude from coverage:
- Test files
- `__init__.py` files
- Abstract methods
- Debug code
- Type checking blocks

## Best Practices

### Test Naming

- Use descriptive names: `test_function_behavior_with_valid_input`
- Follow pattern: `test_<function>_<scenario>_<expected>`

### Test Independence

- Each test should be independent
- Use fixtures for setup/teardown
- Don't rely on test execution order

### Test Data

- Use fixtures for reusable test data
- Keep test data minimal and focused
- Use factories for complex objects

### Assertions

- One logical assertion per test
- Use descriptive assertion messages
- Test both success and failure cases

### Performance

- Keep tests fast (< 1 second each)
- Mark slow tests with `@pytest.mark.slow`
- Use mocks to avoid external dependencies

## Continuous Integration

Tests run automatically on:
- Pull requests
- Commits to main branch
- Scheduled daily runs

CI pipeline includes:
- Unit tests
- Integration tests
- Coverage reporting
- Security scanning
- Code quality checks

## Troubleshooting

### Common Issues

**Import Errors**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

**Database Connection Errors**
```bash
# Use test database
export DATABASE_URL="postgresql://test:test@localhost/test_db"
```

**Async Test Failures**
```python
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Use correct marker
@pytest.mark.asyncio
async def test_async():
    pass
```

## Next Steps

To reach 80% coverage:

1. **Fix Import Issues**
   - Update LangChain imports in Agent Framework
   - Fix function name mismatches
   - Resolve circular dependencies

2. **Add Missing Tests**
   - Virtualization module
   - Skill Library
   - Message Bus
   - Object Storage

3. **Improve Existing Tests**
   - Add edge case tests
   - Test error conditions
   - Add integration tests

4. **Run Tests Regularly**
   - Before committing code
   - After fixing bugs
   - When adding features

## References

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
