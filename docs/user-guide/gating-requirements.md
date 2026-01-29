# Gating Requirements Guide

Learn how to use gating requirements to ensure Agent Skills run only when dependencies are met.

## Overview

Gating requirements allow skills to declare:
- Required binary executables
- Required environment variables
- Required configuration values
- Compatible operating systems

LinX checks these requirements before allowing skill execution, preventing errors and providing clear feedback.

## Why Use Gating?

### Without Gating

```markdown
## Usage

```bash
docker build -t myapp .
```
```

**Problem**: Fails with "docker: command not found" if Docker isn't installed.

### With Gating

```yaml
metadata: {"requires": {"bins": ["docker"]}}
```

**Benefit**: LinX shows "Requirements not met: docker not found" before execution.

## Declaring Requirements

Add requirements in the `metadata` field of SKILL.md frontmatter:

```yaml
---
name: my-skill
description: My skill description
metadata: {
  "requires": {
    "bins": ["binary1", "binary2"],
    "env": ["VAR1", "VAR2"],
    "config": ["path.to.value"]
  },
  "os": ["darwin", "linux"]
}
---
```

## Binary Requirements

### Syntax

```json
{"requires": {"bins": ["curl", "jq", "python3"]}}
```

### How It Works

LinX checks if each binary exists on the system PATH using `which` (Unix) or `where` (Windows).

### Examples

#### Single Binary

```json
{"requires": {"bins": ["curl"]}}
```

Checks for `curl` command.

#### Multiple Binaries

```json
{"requires": {"bins": ["docker", "docker-compose", "kubectl"]}}
```

All three must be available.

#### Version-Specific (Not Enforced)

```json
{"requires": {"bins": ["python3", "node"]}}
```

Note: LinX only checks existence, not versions. Document version requirements in instructions.

### Common Binaries

```json
// Web/API
{"requires": {"bins": ["curl", "wget", "httpie"]}}

// Data Processing
{"requires": {"bins": ["jq", "yq", "xmllint"]}}

// Development
{"requires": {"bins": ["git", "npm", "python3", "node"]}}

// DevOps
{"requires": {"bins": ["docker", "kubectl", "terraform", "ansible"]}}

// System
{"requires": {"bins": ["ssh", "scp", "rsync"]}}
```

## Environment Variable Requirements

### Syntax

```json
{"requires": {"env": ["API_KEY", "SECRET_TOKEN"]}}
```

### How It Works

LinX checks if each environment variable is set (non-empty value).

### Examples

#### API Keys

```json
{"requires": {"env": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]}}
```

#### AWS Credentials

```json
{"requires": {"env": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]}}
```

#### Custom Configuration

```json
{"requires": {"env": ["APP_ENV", "DATABASE_URL", "REDIS_URL"]}}
```

### Best Practices

#### Document in Instructions

```markdown
## Prerequisites

Set required environment variables:

```bash
export API_KEY="your_api_key_here"
export SECRET_TOKEN="your_secret_token"
```

Check they're set:

```bash
echo $API_KEY
echo $SECRET_TOKEN
```
```

#### Provide Examples

```markdown
## Configuration

### Option 1: Export Directly

```bash
export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"
```

### Option 2: Use .env File

Create `.env`:

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

Load it:

```bash
source .env
```
```

## Configuration Requirements

### Syntax

```json
{"requires": {"config": ["api.enabled", "features.weather"]}}
```

### How It Works

LinX checks `config.yaml` for these dot-notation paths and verifies they're truthy.

### Examples

#### Feature Flags

```json
{"requires": {"config": ["features.weather", "features.maps"]}}
```

Checks `config.yaml`:

```yaml
features:
  weather: true
  maps: true
```

#### API Configuration

```json
{"requires": {"config": ["api.enabled", "api.base_url"]}}
```

Checks:

```yaml
api:
  enabled: true
  base_url: "https://api.example.com"
```

#### Nested Paths

```json
{"requires": {"config": ["services.external.weather.enabled"]}}
```

Checks:

```yaml
services:
  external:
    weather:
      enabled: true
```

### Truthy Values

These values are considered truthy:
- `true` (boolean)
- Non-empty strings
- Non-zero numbers
- Non-empty arrays/objects

These are falsy:
- `false` (boolean)
- `null`
- Empty string `""`
- Zero `0`
- Empty array `[]`
- Empty object `{}`

## OS Compatibility

### Syntax

```json
{"os": ["darwin", "linux"]}
```

### Supported Values

- `"darwin"` - macOS
- `"linux"` - Linux
- `"win32"` - Windows

### Examples

#### Unix Only

```json
{"os": ["darwin", "linux"]}
```

Skill works on macOS and Linux, not Windows.

#### macOS Only

```json
{"os": ["darwin"]}
```

Skill requires macOS-specific features.

#### Cross-Platform

```json
{"os": ["darwin", "linux", "win32"]}
```

Or omit `os` field entirely for cross-platform skills.

### Platform-Specific Commands

Document platform differences:

```markdown
## Installation

### macOS

```bash
brew install tool
```

### Linux

```bash
sudo apt-get install tool
```

### Windows

```powershell
choco install tool
```
```

## Complete Examples

### Example 1: Docker Deployment Skill

```yaml
---
name: docker-deploy
description: Deploy applications using Docker
metadata: {
  "emoji": "🐳",
  "requires": {
    "bins": ["docker", "docker-compose"],
    "env": ["DOCKER_REGISTRY", "DEPLOY_TOKEN"],
    "config": ["docker.enabled"]
  },
  "os": ["darwin", "linux"]
}
---
```

**Requirements**:
- Docker and Docker Compose installed
- Registry credentials in environment
- Docker feature enabled in config
- Running on macOS or Linux

### Example 2: AWS CLI Skill

```yaml
---
name: aws-s3-sync
description: Sync files to AWS S3
metadata: {
  "emoji": "☁️",
  "requires": {
    "bins": ["aws"],
    "env": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]
  }
}
---
```

**Requirements**:
- AWS CLI installed
- AWS credentials configured
- Works on all platforms (no OS restriction)

### Example 3: Python Data Processing

```yaml
---
name: data-analysis
description: Analyze CSV data with Python
metadata: {
  "emoji": "📊",
  "requires": {
    "bins": ["python3", "pip"],
    "env": ["DATA_SOURCE_URL"]
  }
}
---
```

**Requirements**:
- Python 3 and pip installed
- Data source URL configured
- Cross-platform compatible

## Gating Status Display

### In UI

Skills show gating status:

```
✅ All requirements met
   ✓ curl found
   ✓ jq found
   ✓ API_KEY set
   ✓ api.enabled = true
   ✓ Compatible with darwin

⚠️ Requirements not met
   ✗ docker not found
   ✓ kubectl found
   ✗ KUBE_CONFIG not set
   ✓ Compatible with darwin
```

### Skill Card

Agent skill cards display:
- Required binaries
- Required environment variables
- Eligibility status
- Warning if requirements not met

## Testing Requirements

### Check Locally

Before uploading, verify requirements:

```bash
# Check binaries
which curl
which jq
which docker

# Check environment variables
echo $API_KEY
echo $SECRET_TOKEN

# Check config (if using LinX config)
cat config.yaml | grep -A 5 "api:"
```

### Dry Run Testing

Use dry run mode to test without executing:

1. Upload skill
2. Click "Test"
3. Enable "Dry Run"
4. Enter test input
5. View parsed commands (no execution)

## Troubleshooting

### Binary Not Found

**Error**: "docker not found"

**Solutions**:
1. Install the binary:
   ```bash
   # macOS
   brew install docker
   
   # Linux
   sudo apt-get install docker.io
   ```

2. Add to PATH:
   ```bash
   export PATH="/path/to/binary:$PATH"
   ```

3. Verify:
   ```bash
   which docker
   ```

### Environment Variable Not Set

**Error**: "API_KEY not set"

**Solutions**:
1. Set the variable:
   ```bash
   export API_KEY="your_key_here"
   ```

2. Add to shell profile:
   ```bash
   echo 'export API_KEY="your_key_here"' >> ~/.bashrc
   source ~/.bashrc
   ```

3. Verify:
   ```bash
   echo $API_KEY
   ```

### Config Value Not Found

**Error**: "api.enabled not found in config"

**Solutions**:
1. Check config file exists:
   ```bash
   ls config.yaml
   ```

2. Add the value:
   ```yaml
   api:
     enabled: true
   ```

3. Verify:
   ```bash
   cat config.yaml | grep -A 2 "api:"
   ```

### OS Incompatibility

**Error**: "Skill not compatible with win32"

**Solutions**:
1. Use a compatible OS (macOS or Linux)
2. Use WSL (Windows Subsystem for Linux) on Windows
3. Contact skill author for Windows support

## Best Practices

### 1. Minimal Requirements

Only require what's absolutely necessary:

```json
// Good - minimal
{"requires": {"bins": ["curl"]}}

// Avoid - excessive
{"requires": {"bins": ["curl", "wget", "httpie", "aria2"]}}
```

### 2. Document Installation

Always document how to install requirements:

```markdown
## Prerequisites

Install required tools:

```bash
# macOS
brew install curl jq

# Linux
sudo apt-get install curl jq
```

Set environment variables:

```bash
export API_KEY="your_key_here"
```
```

### 3. Graceful Degradation

Consider optional features:

```markdown
## Optional: Enhanced Output

For pretty-printed JSON, install jq:

```bash
brew install jq
```

Then use:

```bash
curl "https://api.example.com/data" | jq '.'
```

Without jq, raw JSON is still returned.
```

### 4. Clear Error Messages

In instructions, explain what happens if requirements aren't met:

```markdown
## Troubleshooting

### "docker: command not found"

Docker is not installed. Install it:
- macOS: Download from docker.com
- Linux: `sudo apt-get install docker.io`
```

## References

- [Creating Agent Skills](./creating-agent-skills.md)
- [SKILL.md Format Reference](./skill-md-format.md)
- [Testing Agent Skills](./testing-agent-skills.md)
