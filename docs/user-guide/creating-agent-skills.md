# Creating Agent Skills

Agent Skills are natural language instruction packages that teach AI agents how to use tools and accomplish tasks.

## Overview

Agent Skills use the SKILL.md format to provide:
- Natural language instructions for agents
- Gating requirements (required binaries, environment variables)
- Package-based distribution with supporting files
- Metadata for discovery and compatibility checking

## Quick Start

### 1. Create a SKILL.md File

Create a file named `SKILL.md` with YAML frontmatter and markdown instructions:

```markdown
---
name: Weather Forecast
emoji: 🌤️
version: 1.0.0
author: Your Name
homepage: https://github.com/yourusername/weather-skill
description: Get weather forecast and current conditions for any location
tags:
  - weather
  - api
  - forecast
gating:
  binaries:
    - curl
  env_vars:
    - WEATHER_API_KEY
  config:
    - api.weather.enabled
metadata:
  category: data
  difficulty: beginner
---

# Weather Forecast Skill

Get current weather conditions and forecasts for any location worldwide.

## Usage Examples

### Get Current Weather

```bash
curl "https://api.openweathermap.org/data/2.5/weather?q=Seattle&appid=${WEATHER_API_KEY}&units=metric"
```

### Get 5-Day Forecast

```bash
curl "https://api.openweathermap.org/data/2.5/forecast?q=London&appid=${WEATHER_API_KEY}&units=metric"
```

## Natural Language Testing

Test with queries like:
- "What's the weather in Seattle?"
- "Get the forecast for London"
- "Is it going to rain in Tokyo?"

## Configuration

Required environment variable:
- `WEATHER_API_KEY`: Your OpenWeatherMap API key

## Notes

- Temperature units: metric (Celsius), imperial (Fahrenheit), or standard (Kelvin)
- Free tier includes current weather and 5-day forecast
```

### 2. Package Your Skill

Create a ZIP or tar.gz package with your SKILL.md at the root:

```bash
weather-skill/
├── SKILL.md          # Required: Main skill definition
├── README.md         # Optional: Documentation
├── config.yaml       # Optional: Configuration template
└── assets/           # Optional: Additional resources
    └── icon.png
```

Package it:

```bash
zip -r weather-skill.zip weather-skill/
# or
tar -czf weather-skill.tar.gz weather-skill/
```

**Download Template**: You can download a complete working template from the LinX UI:
1. Go to Skills page → Click "Add Skill"
2. Select "Agent Skill" type
3. Click "Download Template" button
4. Extract and customize the template

### 3. Upload to LinX

1. Navigate to Skills page
2. Click "Create New Skill"
3. Select "Agent Skill" type
4. Upload your package file
5. Fill in name and description
6. Click "Create Skill"

## SKILL.md Format Reference

### Frontmatter (Required)

The YAML frontmatter contains metadata about your skill:

```yaml
---
name: Skill Name              # Required: Display name
emoji: 🔧                     # Optional: Icon emoji
version: 1.0.0                # Required: Semantic version
author: Your Name             # Optional: Author name
homepage: https://...         # Optional: Project URL
description: Brief description # Required: What the skill does
tags:                         # Optional: List of tags
  - category1
  - category2
gating:                       # Optional: Requirements
  binaries:                   # Required command-line tools
    - curl
    - jq
  env_vars:                   # Required environment variables
    - API_KEY
  config:                     # Required config.yaml values
    - api.enabled
metadata:                     # Optional: Additional metadata
  category: data
  difficulty: beginner
  estimated_time: "5 minutes"
---
```

### Gating Requirements

The `gating` section specifies requirements that must be met:

```yaml
gating:
  binaries:                   # Command-line tools
    - curl                    # Checks: which curl
    - jq                      # Checks: which jq
  env_vars:                   # Environment variables
    - API_KEY                 # Checks: $API_KEY is set
    - SECRET_TOKEN            # Checks: $SECRET_TOKEN is set
  config:                     # Config values
    - api.enabled             # Checks: config.yaml api.enabled = true
    - features.weather        # Checks: config.yaml features.weather exists
```

LinX automatically checks these requirements and displays eligibility status.

### Instructions (Required)

Write clear, natural language instructions with:
- **What**: What the skill does
- **How**: How to use it
- **Examples**: Concrete examples
- **Code blocks**: Actual commands to run

## Gating Requirements

Skills can specify requirements that must be met before use. LinX automatically checks these and displays eligibility status.

### Binary Requirements

Check if command-line tools are available:

```yaml
gating:
  binaries:
    - curl
    - jq
    - python3
```

LinX checks if these binaries exist on the system PATH using `which` command.

### Environment Variables

Check if environment variables are set:

```yaml
gating:
  env_vars:
    - API_KEY
    - SECRET_TOKEN
    - DATABASE_URL
```

LinX checks if these environment variables are defined (non-empty).

### Configuration Values

Check if config.yaml values are set:

```yaml
gating:
  config:
    - api.enabled
    - features.weather
    - services.database.host
```

LinX checks if these dot-notation paths exist in config.yaml and are truthy.

### Eligibility Display

Skills show their eligibility status:
- ✅ **Eligible**: All requirements met
- ⚠️ **Not Eligible**: Some requirements missing (shows which ones)

Users can see exactly what's needed to use the skill.

## Testing Your Skill

### Natural Language Testing

After uploading, test your skill with natural language:

1. Click "Test" on your skill card
2. Enter natural language input: "Get weather for Tokyo"
3. Enable "Dry Run" to simulate without executing
4. View parsed commands and simulated output

### Example Test

**Input**: "Get the current weather for Paris"

**Parsed Commands**:
```bash
curl "https://api.weather.com/v1/current?location=Paris&apikey=${WEATHER_API_KEY}"
```

**Simulated Output**:
```json
{
  "location": "Paris",
  "temperature": 18,
  "conditions": "Partly Cloudy"
}
```

## Best Practices

### 1. Clear Instructions

✅ **Good**:
```markdown
To search for a file, use the `find` command:

```bash
find /path/to/search -name "filename"
```

Replace `/path/to/search` with the directory and `filename` with the file name.
```

❌ **Bad**:
```markdown
Use find command to search files.
```

### 2. Concrete Examples

Always provide working examples with actual values:

```markdown
## Example

Search for Python files in the current directory:

```bash
find . -name "*.py"
```
```

### 3. Explain Placeholders

Make it clear what needs to be replaced:

```markdown
Replace `${VARIABLE}` with your actual value:
- `${API_KEY}`: Your API key from the dashboard
- `${LOCATION}`: City name (e.g., "London", "Tokyo")
```

### 4. Include Error Handling

```markdown
## Troubleshooting

If you get "command not found":
- Install curl: `brew install curl` (macOS) or `apt-get install curl` (Linux)

If you get "unauthorized":
- Check that WEATHER_API_KEY is set: `echo $WEATHER_API_KEY`
```

### 5. Minimal Package Size

Keep packages under 50MB:
- Include only necessary files
- Compress large files
- Use `.gitignore` patterns to exclude build artifacts

## Advanced Features

### Multiple Commands

Skills can include multiple commands:

```markdown
## Step 1: Fetch Data

```bash
curl "https://api.example.com/data" > data.json
```

## Step 2: Process Data

```bash
jq '.results[]' data.json
```

## Step 3: Clean Up

```bash
rm data.json
```
```

### API Calls

Document API endpoints clearly:

```markdown
## API Endpoint

```bash
POST https://api.example.com/v1/process
Content-Type: application/json

{
  "input": "${INPUT_TEXT}",
  "options": {
    "format": "json"
  }
}
```
```

### Python Scripts

Include Python code blocks:

```markdown
## Python Script

```python
import requests

def get_weather(location):
    api_key = os.environ['WEATHER_API_KEY']
    url = f"https://api.weather.com/v1/current"
    params = {"location": location, "apikey": api_key}
    response = requests.get(url, params=params)
    return response.json()
```
```

## Examples

### Simple API Skill

```markdown
---
name: IP Lookup
emoji: 🌐
version: 1.0.0
description: Get IP address information
gating:
  binaries:
    - curl
metadata:
  category: network
  difficulty: beginner
---

# IP Lookup Skill

Get information about an IP address.

## Usage

```bash
curl "https://ipapi.co/${IP_ADDRESS}/json/"
```

## Example

```bash
curl "https://ipapi.co/8.8.8.8/json/"
```
```

### Complex Skill with Requirements

```markdown
---
name: Docker Deploy
emoji: 🐳
version: 1.0.0
author: DevOps Team
homepage: https://github.com/example/docker-deploy
description: Deploy application using Docker
tags:
  - docker
  - deployment
  - devops
gating:
  binaries:
    - docker
    - docker-compose
  env_vars:
    - DOCKER_REGISTRY
    - DEPLOY_TOKEN
  config:
    - docker.enabled
metadata:
  category: deployment
  difficulty: advanced
  estimated_time: "10 minutes"
---

# Docker Deploy Skill

Deploy applications using Docker and Docker Compose.

## Prerequisites

- Docker installed and running
- Docker Compose v2+
- Registry credentials configured

## Usage

### 1. Build Image

```bash
docker build -t ${DOCKER_REGISTRY}/${APP_NAME}:${VERSION} .
```

### 2. Push to Registry

```bash
echo ${DEPLOY_TOKEN} | docker login ${DOCKER_REGISTRY} -u deploy --password-stdin
docker push ${DOCKER_REGISTRY}/${APP_NAME}:${VERSION}
```

### 3. Deploy

```bash
docker-compose -f docker-compose.prod.yml up -d
```

## Example

Deploy version 1.0.0:

```bash
export APP_NAME="myapp"
export VERSION="1.0.0"
docker build -t registry.example.com/myapp:1.0.0 .
docker push registry.example.com/myapp:1.0.0
docker-compose -f docker-compose.prod.yml up -d
```
```

## Troubleshooting

### Package Upload Fails

**Error**: "Package too large"
- **Solution**: Reduce package size to under 50MB
- Remove unnecessary files
- Compress large assets

**Error**: "SKILL.md not found"
- **Solution**: Ensure SKILL.md is at the package root
- Check file name is exactly `SKILL.md` (case-sensitive)

### Gating Requirements Not Met

**Warning**: "Requirements not met"
- Check which requirements are missing in the skill card
- Install missing binaries
- Set required environment variables
- Enable required config values

### Test Fails

**Error**: "Command not found"
- Verify binary requirements are met
- Check PATH includes required tools

**Error**: "Unauthorized"
- Verify environment variables are set
- Check API keys are valid

## References

- [SKILL.md Format Specification](./skill-md-format.md)
- [Gating Requirements Guide](./gating-requirements.md)
- [Testing Agent Skills](./testing-agent-skills.md)
- [AgentSkills.io](https://agentskills.io) - Official specification
