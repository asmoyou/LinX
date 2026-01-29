# SKILL.md Format Reference

Complete reference for the SKILL.md format used in Agent Skills.

## Overview

SKILL.md is a markdown file with YAML frontmatter that contains:
1. **Frontmatter**: Metadata about the skill
2. **Instructions**: Natural language instructions for agents

## File Structure

```markdown
---
# YAML frontmatter (required)
name: skill-name
description: Brief description
homepage: https://example.com
metadata: {"key": "value"}
---

# Markdown Instructions (required)

Your natural language instructions here...
```

## Frontmatter Fields

### Required Fields

#### `name` (string, required)

Unique identifier for the skill. Must be:
- Lowercase
- Alphanumeric with hyphens
- No spaces or special characters

```yaml
name: weather-api-skill
```

#### `description` (string, required)

Brief description of what the skill does (1-2 sentences).

```yaml
description: Retrieves current weather information for any location using the Weather API
```

### Optional Fields

#### `homepage` (string, optional)

URL to the skill's homepage, documentation, or repository.

```yaml
homepage: https://github.com/username/weather-skill
```

#### `metadata` (JSON object, optional)

Additional metadata as a JSON object. Must be valid JSON on a single line.

```yaml
metadata: {"emoji": "🌤️", "version": "1.0.0", "author": "John Doe"}
```

## Metadata Structure

The `metadata` field supports these standard keys:

### `emoji` (string)

Display emoji for the skill (single emoji character).

```json
{"emoji": "🔧"}
```

### `requires` (object)

Gating requirements for the skill.

```json
{
  "requires": {
    "bins": ["curl", "jq"],
    "env": ["API_KEY"],
    "config": ["api.enabled"]
  }
}
```

#### `requires.bins` (array of strings)

Binary executables that must be available on PATH.

```json
{"requires": {"bins": ["docker", "kubectl", "helm"]}}
```

#### `requires.env` (array of strings)

Environment variables that must be set.

```json
{"requires": {"env": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]}}
```

#### `requires.config` (array of strings)

Configuration values that must be truthy (dot-notation paths).

```json
{"requires": {"config": ["features.weather", "api.enabled"]}}
```

### `os` (array of strings)

Compatible operating systems. Supported values:
- `"darwin"` - macOS
- `"linux"` - Linux
- `"win32"` - Windows

```json
{"os": ["darwin", "linux"]}
```

If omitted, skill is assumed compatible with all operating systems.

### Custom Metadata

You can add custom metadata fields:

```json
{
  "emoji": "🌤️",
  "version": "1.0.0",
  "author": "John Doe",
  "license": "MIT",
  "tags": ["weather", "api", "data"],
  "difficulty": "beginner"
}
```

## Instructions Section

The markdown content after the frontmatter contains natural language instructions.

### Structure

Use clear headings and sections:

```markdown
# Skill Name

Brief overview of what the skill does.

## Prerequisites

What's needed before using this skill.

## Usage

How to use the skill.

## Examples

Concrete examples with actual commands.

## Troubleshooting

Common issues and solutions.
```

### Code Blocks

Use fenced code blocks with language identifiers:

````markdown
```bash
curl "https://api.example.com/data"
```

```python
import requests
response = requests.get("https://api.example.com/data")
```

```json
{
  "key": "value"
}
```
````

### Placeholders

Use `${VARIABLE}` syntax for placeholders:

```markdown
```bash
curl "https://api.example.com/data?key=${API_KEY}&location=${LOCATION}"
```

Replace:
- `${API_KEY}`: Your API key
- `${LOCATION}`: City name
```

### Command Descriptions

Describe what each command does:

```markdown
## Fetch Data

Retrieve weather data from the API:

```bash
curl "https://api.weather.com/v1/current?location=${LOCATION}"
```

This returns JSON with temperature, conditions, and forecast.
```

## Complete Example

```markdown
---
name: github-repo-info
description: Get information about a GitHub repository
homepage: https://github.com/example/github-skill
metadata: {
  "emoji": "🐙",
  "requires": {
    "bins": ["curl", "jq"],
    "env": ["GITHUB_TOKEN"]
  },
  "os": ["darwin", "linux"],
  "version": "1.0.0",
  "author": "Example User",
  "tags": ["github", "api", "repository"]
}
---

# GitHub Repository Info Skill

Get detailed information about any GitHub repository.

## Prerequisites

- GitHub personal access token
- `curl` and `jq` installed

## Usage

### Get Repository Info

```bash
curl -H "Authorization: token ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/${OWNER}/${REPO}"
```

### Extract Specific Fields

Get just the star count:

```bash
curl -H "Authorization: token ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/${OWNER}/${REPO}" | \
  jq '.stargazers_count'
```

## Examples

### Example 1: Get React Repository Info

```bash
export OWNER="facebook"
export REPO="react"
curl -H "Authorization: token ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/facebook/react"
```

### Example 2: Get Star Count

```bash
curl -H "Authorization: token ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/facebook/react" | \
  jq '.stargazers_count'
```

Output: `220000`

## Response Format

The API returns JSON with:
- `name`: Repository name
- `description`: Repository description
- `stargazers_count`: Number of stars
- `forks_count`: Number of forks
- `language`: Primary language
- `created_at`: Creation date
- `updated_at`: Last update date

## Troubleshooting

### "Bad credentials" Error

Ensure your GITHUB_TOKEN is set and valid:

```bash
echo $GITHUB_TOKEN
```

If empty, set it:

```bash
export GITHUB_TOKEN="your_token_here"
```

### "jq: command not found"

Install jq:

```bash
# macOS
brew install jq

# Linux
sudo apt-get install jq
```

## References

- [GitHub API Documentation](https://docs.github.com/en/rest)
- [jq Manual](https://stedolan.github.io/jq/manual/)
```

## Validation Rules

### Frontmatter Validation

- Must be valid YAML
- Must be enclosed in `---` delimiters
- `name` and `description` are required
- `metadata` must be valid JSON if present

### Instructions Validation

- Must not be empty
- Should contain at least one code block
- Should have clear structure with headings

## Compatibility

### Moltbot Format

LinX supports the moltbot SKILL.md format:

```markdown
---
name: skill-name
description: Brief description
metadata: {"emoji": "🔧", "requires": {"bins": ["curl"]}}
---

Instructions here...
```

### AgentSkills.io Format

LinX is compatible with the AgentSkills.io specification:

```markdown
---
name: skill-name
description: Brief description
homepage: https://example.com
---

Instructions here...
```

## Best Practices

### 1. Keep Frontmatter Simple

```yaml
# Good
name: simple-skill
description: Does one thing well

# Avoid
name: complex-skill-with-many-features-and-options
description: This skill does many things including A, B, C, D, E, F, and more...
```

### 2. Use Inline JSON for Metadata

```yaml
# Good
metadata: {"emoji": "🔧", "requires": {"bins": ["curl"]}}

# Avoid (multi-line not supported)
metadata:
  emoji: "🔧"
  requires:
    bins: ["curl"]
```

### 3. Clear Instructions

```markdown
# Good
## Usage

To fetch data, run:

```bash
curl "https://api.example.com/data"
```

# Avoid
## Usage

Use curl to get data from the API.
```

### 4. Concrete Examples

```markdown
# Good
## Example

Get weather for London:

```bash
curl "https://api.weather.com/v1/current?location=London&apikey=abc123"
```

# Avoid
## Example

Get weather for a location.
```

## References

- [AgentSkills.io Specification](https://agentskills.io)
- [Moltbot Skills](https://github.com/moltbot/skills)
- [YAML Specification](https://yaml.org/spec/)
- [Markdown Guide](https://www.markdownguide.org/)
