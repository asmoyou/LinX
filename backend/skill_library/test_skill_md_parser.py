"""Unit tests for SKILL.md parser.

References:
- Requirements: Agent Skills Redesign
- Design: SKILL.md Parser component
"""

import pytest
from skill_library.skill_md_parser import SkillMdParser, SkillMetadata, ParsedSkill


class TestSkillMdParser:
    """Test SKILL.md parser."""

    def test_parse_valid_skill_md(self):
        """Test parsing valid SKILL.md."""
        content = """---
name: weather
description: Get current weather and forecasts
homepage: https://wttr.in/:help
metadata: {"moltbot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
---

# Weather

Use wttr.in for weather information.

Quick one-liner:
```bash
curl -s "wttr.in/London?format=3"
```
"""
        parser = SkillMdParser()
        parsed = parser.parse(content)
        
        assert parsed.metadata.name == "weather"
        assert parsed.metadata.description == "Get current weather and forecasts"
        assert parsed.metadata.homepage == "https://wttr.in/:help"
        assert parsed.metadata.emoji == "🌤️"
        assert parsed.metadata.requires_bins == ["curl"]
        assert "Use wttr.in" in parsed.instructions
        assert parsed.raw_content == content

    def test_parse_minimal_skill_md(self):
        """Test parsing minimal SKILL.md with only required fields."""
        content = """---
name: simple_skill
description: A simple skill
---

# Simple Skill

This is a simple skill with minimal metadata.
"""
        parser = SkillMdParser()
        parsed = parser.parse(content)
        
        assert parsed.metadata.name == "simple_skill"
        assert parsed.metadata.description == "A simple skill"
        assert parsed.metadata.homepage is None
        assert parsed.metadata.emoji is None
        assert parsed.metadata.requires_bins == []
        assert "simple skill" in parsed.instructions

    def test_parse_missing_name(self):
        """Test parsing SKILL.md without name."""
        content = """---
description: Missing name
---

# Content
"""
        parser = SkillMdParser()
        
        with pytest.raises(ValueError, match="Missing required field: name"):
            parser.parse(content)

    def test_parse_missing_description(self):
        """Test parsing SKILL.md without description."""
        content = """---
name: test
---

# Content
"""
        parser = SkillMdParser()
        
        with pytest.raises(ValueError, match="Missing required field: description"):
            parser.parse(content)

    def test_parse_invalid_yaml(self):
        """Test parsing SKILL.md with invalid YAML."""
        content = """---
name: test
description: test
invalid yaml here: [
---

# Content
"""
        parser = SkillMdParser()
        
        with pytest.raises(ValueError, match="Invalid SKILL.md format"):
            parser.parse(content)

    def test_parse_invalid_metadata_json(self):
        """Test parsing SKILL.md with invalid metadata JSON."""
        content = """---
name: test
description: test
metadata: '{"invalid json'
---

# Content
"""
        parser = SkillMdParser()
        
        with pytest.raises(ValueError, match="Invalid metadata JSON"):
            parser.parse(content)

    def test_parse_with_multiple_requirements(self):
        """Test parsing SKILL.md with multiple requirement types."""
        content = """---
name: complex_skill
description: A complex skill with multiple requirements
metadata: {"moltbot":{"requires":{"bins":["curl","jq"],"env":["API_KEY"],"config":["browser.enabled"]},"os":["darwin","linux"]}}
---

# Complex Skill

This skill has multiple requirements.
"""
        parser = SkillMdParser()
        parsed = parser.parse(content)
        
        assert parsed.metadata.requires_bins == ["curl", "jq"]
        assert parsed.metadata.requires_env == ["API_KEY"]
        assert parsed.metadata.requires_config == ["browser.enabled"]
        assert parsed.metadata.os_filter == ["darwin", "linux"]

    def test_validate_valid_skill(self):
        """Test validation of valid skill."""
        content = """---
name: valid_skill
description: A valid skill
homepage: https://example.com
---

# Valid Skill

This is valid.
"""
        parser = SkillMdParser()
        parsed = parser.parse(content)
        errors = parser.validate(parsed)
        
        assert errors == []

    def test_validate_empty_instructions(self):
        """Test validation fails for empty instructions."""
        content = """---
name: empty_skill
description: Empty instructions
---

"""
        parser = SkillMdParser()
        parsed = parser.parse(content)
        errors = parser.validate(parsed)
        
        assert "instructions cannot be empty" in errors

    def test_validate_invalid_name_format(self):
        """Test validation fails for invalid name format."""
        content = """---
name: "invalid name with spaces"
description: Invalid name
---

# Content
"""
        parser = SkillMdParser()
        parsed = parser.parse(content)
        errors = parser.validate(parsed)
        
        assert any("alphanumeric" in err for err in errors)

    def test_validate_invalid_homepage_url(self):
        """Test validation fails for invalid homepage URL."""
        content = """---
name: test_skill
description: Test
homepage: not-a-url
---

# Content
"""
        parser = SkillMdParser()
        parsed = parser.parse(content)
        errors = parser.validate(parsed)
        
        assert any("valid HTTP" in err for err in errors)

    def test_validate_invalid_os_filter(self):
        """Test validation fails for invalid OS filter."""
        content = """---
name: test_skill
description: Test
metadata: {"moltbot":{"os":["invalid_os","darwin"]}}
---

# Content
"""
        parser = SkillMdParser()
        parsed = parser.parse(content)
        errors = parser.validate(parsed)
        
        assert any("invalid OS values" in err for err in errors)

    def test_parse_moltbot_weather_example(self):
        """Test parsing the moltbot weather.md example."""
        content = """---
name: weather
description: Get current weather and forecasts (no API key required).
homepage: https://wttr.in/:help
metadata: {"moltbot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
---

# Weather

Two free services, no API keys needed.

## wttr.in (primary)

Quick one-liner:
```bash
curl -s "wttr.in/London?format=3"
# Output: London: ⛅️ +8°C
```

Compact format:
```bash
curl -s "wttr.in/London?format=%l:+%c+%t+%h+%w"
# Output: London: ⛅️ +8°C 71% ↙5km/h
```

Full forecast:
```bash
curl -s "wttr.in/London?T"
```

Format codes: `%c` condition · `%t` temp · `%h` humidity · `%w` wind · `%l` location · `%m` moon

Tips:
- URL-encode spaces: `wttr.in/New+York`
- Airport codes: `wttr.in/JFK`
- Units: `?m` (metric) `?u` (USCS)
- Today only: `?1` · Current only: `?0`
- PNG: `curl -s "wttr.in/Berlin.png" -o /tmp/weather.png`

## Open-Meteo (fallback, JSON)

Free, no key, good for programmatic use:
```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&current_weather=true"
```

Find coordinates for a city, then query. Returns JSON with temp, windspeed, weathercode.

Docs: https://open-meteo.com/en/docs
"""
        parser = SkillMdParser()
        parsed = parser.parse(content)
        
        assert parsed.metadata.name == "weather"
        assert parsed.metadata.description == "Get current weather and forecasts (no API key required)."
        assert parsed.metadata.homepage == "https://wttr.in/:help"
        assert parsed.metadata.emoji == "🌤️"
        assert parsed.metadata.requires_bins == ["curl"]
        assert "wttr.in" in parsed.instructions
        assert "Open-Meteo" in parsed.instructions
        
        # Validate
        errors = parser.validate(parsed)
        assert errors == []
