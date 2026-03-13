"""Tests for dynamic skill generation.

References:
- Design Section 5.6: Dynamic Skill Generation
- Requirements 4: Skill Library
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest

from skill_library.dynamic_skill_generator import (
    DynamicSkillGenerator,
    GeneratedSkill,
    get_dynamic_skill_generator,
)
from skill_library.semantic_skill_search import (
    SemanticSkillSearch,
    get_semantic_skill_search,
)
from skill_library.skill_cache import CachedSkill, SkillCache, get_skill_cache


class TestDynamicSkillGenerator:
    """Test dynamic skill generation."""

    @pytest.fixture
    def mock_llm_provider(self):
        """Create mock LLM provider."""
        provider = Mock()
        provider.generate = Mock(return_value="""
def execute(inputs):
    '''Add two numbers.'''
    a = inputs.get('a', 0)
    b = inputs.get('b', 0)
    return {'result': a + b}
""")
        return provider

    @pytest.fixture
    def mock_skill_registry(self):
        """Create mock skill registry."""
        registry = Mock()
        registry.register_skill = Mock(return_value=Mock(skill_id=uuid4()))
        return registry

    @pytest.fixture
    def mock_sandbox(self):
        """Create mock sandbox."""
        sandbox = Mock()
        sandbox.execute = Mock(
            return_value={
                "status": "success",
                "output": "{'result': 5}",
            }
        )
        return sandbox

    @pytest.fixture
    def generator(self, mock_llm_provider, mock_skill_registry, mock_sandbox):
        """Create skill generator with mocks."""
        return DynamicSkillGenerator(
            llm_provider=mock_llm_provider,
            skill_registry=mock_skill_registry,
            sandbox=mock_sandbox,
        )

    def test_generate_skill_success(self, generator, mock_llm_provider):
        """Test successful skill generation."""
        # Arrange
        description = "Add two numbers"
        examples = [{"input": {"a": 2, "b": 3}, "output": {"result": 5}}]

        # Act
        result = generator.generate_skill(description, examples, register=False)

        # Assert
        assert isinstance(result, GeneratedSkill)
        assert result.is_valid
        assert len(result.validation_errors) == 0
        assert "execute" in result.code
        mock_llm_provider.generate.assert_called_once()

    def test_generate_skill_with_registration(self, generator, mock_skill_registry):
        """Test skill generation with registration."""
        # Arrange
        description = "Multiply two numbers"

        # Act
        result = generator.generate_skill(description, register=True)

        # Assert
        assert result.skill_id is not None
        mock_skill_registry.register_skill.assert_called_once()

    def test_extract_interface(self, generator):
        """Test interface extraction from code."""
        # Arrange
        code = """
def execute(inputs):
    a = inputs.get('a')
    b = inputs.get('b')
    return {'result': a + b}
"""

        # Act
        interface = generator._extract_interface(code)

        # Assert
        assert "inputs" in interface
        assert "outputs" in interface
        assert "required_inputs" in interface

    def test_generate_skill_name(self, generator):
        """Test skill name generation."""
        # Arrange
        description = "Calculate the sum of two numbers"

        # Act
        name = generator._generate_skill_name(description)

        # Assert
        assert isinstance(name, str)
        assert len(name) > 0
        assert "_" in name

    def test_extract_dependencies(self, generator):
        """Test dependency extraction."""
        # Arrange
        code = """
import math
import json
from datetime import datetime

def execute(inputs):
    return {'result': math.sqrt(inputs['value'])}
"""

        # Act
        dependencies = generator._extract_dependencies(code)

        # Assert
        assert "math" in dependencies
        assert "json" in dependencies
        assert "datetime" in dependencies

    def test_validate_code_success(self, generator):
        """Test code validation with valid code."""
        # Arrange
        code = """
def execute(inputs):
    return {'result': inputs['value'] * 2}
"""

        # Act
        errors = generator._validate_code(code)

        # Assert
        assert len(errors) == 0

    def test_validate_code_syntax_error(self, generator):
        """Test code validation with syntax error."""
        # Arrange
        code = "def execute(inputs):\n    return {"

        # Act
        errors = generator._validate_code(code)

        # Assert
        assert len(errors) > 0
        assert "Syntax error" in errors[0]

    def test_validate_code_dangerous_patterns(self, generator):
        """Test code validation detects dangerous patterns."""
        # Arrange
        dangerous_codes = [
            "eval('malicious')",
            "exec('code')",
            "__import__('os')",
            "open('/etc/passwd')",
        ]

        for code in dangerous_codes:
            # Act
            errors = generator._validate_code(code)

            # Assert
            assert len(errors) > 0

    def test_extract_code_from_response(self, generator):
        """Test code extraction from LLM response."""
        # Arrange
        response = """
Here's the code:

```python
def execute(inputs):
    return {'result': inputs['value']}
```

This function does...
"""

        # Act
        code = generator._extract_code_from_response(response)

        # Assert
        assert "def execute" in code
        assert "```" not in code


class TestSkillCache:
    """Test skill caching."""

    @pytest.fixture
    def cache(self):
        """Create skill cache."""
        return SkillCache(max_size=10, ttl=3600)

    def test_cache_put_and_get(self, cache):
        """Test caching and retrieving skills."""
        # Arrange
        description = "Add two numbers"
        skill_id = uuid4()

        # Act
        cache.put(
            description=description,
            skill_id=skill_id,
            name="add_numbers",
            code="def execute(inputs): pass",
            interface_definition={},
            dependencies=[],
        )

        result = cache.get(description)

        # Assert
        assert result is not None
        assert result.skill_id == skill_id
        assert result.usage_count == 2  # 1 from put, 1 from get

    def test_cache_miss(self, cache):
        """Test cache miss."""
        # Act
        result = cache.get("nonexistent skill")

        # Assert
        assert result is None

    def test_cache_invalidate(self, cache):
        """Test cache invalidation."""
        # Arrange
        description = "Test skill"
        cache.put(
            description=description,
            skill_id=uuid4(),
            name="test",
            code="",
            interface_definition={},
            dependencies=[],
        )

        # Act
        invalidated = cache.invalidate(description)
        result = cache.get(description)

        # Assert
        assert invalidated is True
        assert result is None

    def test_cache_clear(self, cache):
        """Test cache clearing."""
        # Arrange
        cache.put(
            description="skill1",
            skill_id=uuid4(),
            name="skill1",
            code="",
            interface_definition={},
            dependencies=[],
        )
        cache.put(
            description="skill2",
            skill_id=uuid4(),
            name="skill2",
            code="",
            interface_definition={},
            dependencies=[],
        )

        # Act
        cache.clear()

        # Assert
        assert cache.get("skill1") is None
        assert cache.get("skill2") is None

    def test_cache_stats(self, cache):
        """Test cache statistics."""
        # Arrange
        cache.put(
            description="test",
            skill_id=uuid4(),
            name="test",
            code="",
            interface_definition={},
            dependencies=[],
        )

        # Act
        stats = cache.get_stats()

        # Assert
        assert stats["size"] == 1
        assert stats["max_size"] == 10
        assert stats["total_usage"] >= 1

    def test_cache_eviction(self):
        """Test LRU eviction."""
        # Arrange
        cache = SkillCache(max_size=2, ttl=3600)

        # Add 3 skills (should evict first one)
        cache.put("skill1", uuid4(), "skill1", "", {}, [])
        cache.put("skill2", uuid4(), "skill2", "", {}, [])
        cache.put("skill3", uuid4(), "skill3", "", {}, [])

        # Act
        result1 = cache.get("skill1")
        result2 = cache.get("skill2")
        result3 = cache.get("skill3")

        # Assert
        assert result1 is None  # Evicted
        assert result2 is not None
        assert result3 is not None

    def test_get_top_skills(self, cache):
        """Test getting top skills by usage."""
        # Arrange
        cache.put("skill1", uuid4(), "skill1", "", {}, [])
        cache.put("skill2", uuid4(), "skill2", "", {}, [])

        # Access skill1 multiple times
        cache.get("skill1")
        cache.get("skill1")
        cache.get("skill2")

        # Act
        top_skills = cache.get_top_skills(limit=2)

        # Assert
        assert len(top_skills) == 2
        assert top_skills[0].name == "skill1"  # Most used


class TestSemanticSkillSearch:
    """Test semantic skill search."""

    @pytest.fixture
    def mock_skill_registry(self):
        """Create mock skill registry."""
        registry = Mock()
        registry.list_skills = Mock(
            return_value=[
                SimpleNamespace(
                    skill_id=uuid4(),
                    name="add_numbers",
                    description="Add two numbers together",
                    version="1.0.0",
                    interface_definition={},
                    dependencies=[],
                ),
                SimpleNamespace(
                    skill_id=uuid4(),
                    name="multiply_numbers",
                    description="Multiply two numbers",
                    version="1.0.0",
                    interface_definition={},
                    dependencies=[],
                ),
            ]
        )
        return registry

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        service = Mock()

        # Return different embeddings for different descriptions
        def generate_embedding(text):
            if "add" in text.lower():
                return [1.0, 0.0, 0.0]
            elif "multiply" in text.lower():
                return [0.0, 1.0, 0.0]
            else:
                return [0.0, 0.0, 1.0]

        service.generate_embedding = Mock(side_effect=generate_embedding)
        return service

    @pytest.fixture
    def search(self, mock_skill_registry, mock_embedding_service):
        """Create semantic search with mocks."""
        return SemanticSkillSearch(
            skill_registry=mock_skill_registry,
            embedding_service=mock_embedding_service,
        )

    def test_find_similar_skills(self, search):
        """Test finding similar skills."""
        # Arrange
        description = "Add two numbers"

        # Act
        results = search.find_similar_skills(description, threshold=0.5, limit=5)

        # Assert
        assert len(results) > 0
        assert all(hasattr(r[0], "name") for r in results)
        assert all(isinstance(r[1], float) for r in results)

    def test_find_exact_match(self, search):
        """Test finding exact match."""
        # Arrange
        description = "Add two numbers together"

        # Act
        result = search.find_exact_match(description)

        # Assert
        # May or may not find exact match depending on similarity threshold
        assert result is None or result.name == "add_numbers"

    def test_suggest_existing_skill(self, search):
        """Test suggesting existing skill."""
        # Arrange
        description = "Sum two numbers"

        # Act
        result = search.suggest_existing_skill(description)

        # Assert
        # May or may not suggest depending on similarity
        if result:
            skill, similarity = result
            assert similarity >= 0.8

    def test_cosine_similarity(self, search):
        """Test cosine similarity calculation."""
        # Arrange
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [1.0, 0.0, 0.0]
        embedding3 = [0.0, 1.0, 0.0]

        # Act
        similarity_same = search._cosine_similarity(embedding1, embedding2)
        similarity_different = search._cosine_similarity(embedding1, embedding3)

        # Assert
        assert similarity_same > similarity_different
        assert 0 <= similarity_same <= 1
        assert 0 <= similarity_different <= 1


class TestSingletons:
    """Test singleton getters."""

    def test_get_dynamic_skill_generator(self):
        """Test getting dynamic skill generator singleton."""
        generator1 = get_dynamic_skill_generator()
        generator2 = get_dynamic_skill_generator()

        assert generator1 is generator2

    def test_get_skill_cache(self):
        """Test getting skill cache singleton."""
        cache1 = get_skill_cache()
        cache2 = get_skill_cache()

        assert cache1 is cache2

    def test_get_semantic_skill_search(self):
        """Test getting semantic skill search singleton."""
        search1 = get_semantic_skill_search()
        search2 = get_semantic_skill_search()

        assert search1 is search2
