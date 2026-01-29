# Testing Agent Skills Guide

Learn how to test Agent Skills using natural language input and dry run mode.

## Overview

Agent Skills use natural language testing instead of structured parameters:
- **Input**: Natural language description of what you want to do
- **Processing**: LinX parses commands from skill instructions
- **Output**: Simulated or actual command execution results

## Quick Start

### 1. Open Skill Tester

1. Navigate to Skills page
2. Find your agent skill
3. Click "Test" button

### 2. Enter Natural Language Input

Type what you want to do in plain language:

```
Get the weather for London
```

### 3. Choose Mode

- **Dry Run** (✓ recommended): Simulates execution, shows what would run
- **Actual Execution**: Runs commands for real

### 4. View Results

See:
- Parsed commands
- Command descriptions
- Simulated/actual output
- Execution time

## Natural Language Input

### What to Write

Write clear, specific requests:

✅ **Good Examples**:
```
Get the weather for Tokyo
Search for Python files in the current directory
Deploy version 1.0.0 to production
Fetch user data for ID 12345
```

❌ **Avoid**:
```
weather
search
deploy
get data
```

### Input Patterns

#### Location-Based

```
Get weather for [LOCATION]
Find restaurants near [ADDRESS]
Show map of [CITY]
```

#### ID-Based

```
Get user with ID [NUMBER]
Fetch order #[ORDER_ID]
Show details for [IDENTIFIER]
```

#### Action-Based

```
Deploy [VERSION] to [ENVIRONMENT]
Backup [DATABASE] to [LOCATION]
Process [FILE] with [OPTIONS]
```

#### Query-Based

```
Search for [TERM] in [SCOPE]
Find [PATTERN] matching [CRITERIA]
List [RESOURCES] where [CONDITION]
```

## Dry Run Mode

### What It Does

Dry run mode:
1. Parses commands from skill instructions
2. Replaces placeholders with your input
3. Shows what would be executed
4. **Does not run commands**
5. Generates simulated output

### When to Use

✅ **Use dry run for**:
- Testing new skills
- Verifying command parsing
- Checking placeholder replacement
- Learning how skills work
- Debugging issues

❌ **Don't use dry run for**:
- Production operations
- When you need real results
- Testing actual API responses

### Example

**Skill**: Weather API

**Input**: "Get weather for Paris"

**Dry Run Output**:
```
Parsed Commands:
  Type: bash
  Command: curl "https://api.weather.com/v1/current?location=Paris&apikey=${WEATHER_API_KEY}"
  Description: Fetch current weather data

Simulated Output:
{
  "location": "Paris",
  "temperature": 18,
  "conditions": "Partly Cloudy",
  "humidity": 65
}
```

## Actual Execution

### What It Does

Actual execution mode:
1. Parses commands from skill instructions
2. Replaces placeholders with your input
3. **Executes commands in sandbox**
4. Returns real output
5. Captures stdout/stderr

### When to Use

✅ **Use actual execution for**:
- Production operations
- Getting real API responses
- Testing with live data
- Verifying actual behavior

⚠️ **Caution**:
- Commands run in sandbox with resource limits
- Destructive operations may have side effects
- API calls consume quotas/credits
- Network requests are made

### Example

**Skill**: GitHub API

**Input**: "Get info for facebook/react repository"

**Actual Output**:
```
Parsed Commands:
  Type: bash
  Command: curl -H "Authorization: token ${GITHUB_TOKEN}" \
    "https://api.github.com/repos/facebook/react"

Actual Output:
{
  "name": "react",
  "full_name": "facebook/react",
  "description": "A declarative, efficient, and flexible JavaScript library...",
  "stargazers_count": 220000,
  "forks_count": 45000,
  "language": "JavaScript",
  "created_at": "2013-05-24T16:15:54Z"
}

Execution Time: 0.342s
```

## Understanding Results

### Parsed Commands

Shows what LinX extracted from skill instructions:

```
Parsed Commands:
  1. Type: bash
     Command: curl "https://api.example.com/data?id=123"
     Description: Fetch data from API
  
  2. Type: bash
     Command: jq '.results[]' data.json
     Description: Extract results from JSON
```

### Command Types

- **bash**: Shell commands
- **python**: Python scripts
- **api**: HTTP API calls
- **sql**: Database queries

### Placeholder Replacement

Shows how placeholders were replaced:

```
Original: curl "https://api.example.com/data?location=${LOCATION}"
Replaced: curl "https://api.example.com/data?location=London"

Placeholders:
  ${LOCATION} → London
```

### Output

#### Simulated Output (Dry Run)

Generated based on command type and expected format:

```json
{
  "status": "success",
  "data": {
    "temperature": 18,
    "conditions": "Sunny"
  }
}
```

#### Actual Output

Real command output:

```
HTTP/1.1 200 OK
Content-Type: application/json

{
  "temperature": 18.5,
  "conditions": "Partly Cloudy",
  "humidity": 65,
  "wind_speed": 12
}
```

## Testing Strategies

### 1. Start with Dry Run

Always test with dry run first:

```
1. Upload skill
2. Test with dry run ✓
3. Verify parsed commands
4. Check placeholder replacement
5. Review simulated output
6. If correct → try actual execution
```

### 2. Test Edge Cases

Test various inputs:

```
Normal: "Get weather for London"
Empty: "Get weather for "
Special chars: "Get weather for São Paulo"
Long input: "Get weather for London, United Kingdom, Europe"
Numbers: "Get user with ID 12345"
```

### 3. Test Error Conditions

Try inputs that should fail:

```
Missing data: "Get weather for NonexistentCity"
Invalid format: "Get weather for 12345"
Unauthorized: Test without API key set
```

### 4. Test Multiple Commands

For skills with multiple steps:

```
Input: "Deploy version 1.0.0"

Expected:
  1. Build image
  2. Push to registry
  3. Deploy to cluster
  4. Verify deployment
```

### 5. Test with Real Data

After dry run succeeds, test with actual execution:

```
1. Dry run: Verify commands ✓
2. Actual: Test with non-critical data
3. Actual: Test with production data (if safe)
```

## Common Issues

### Issue 1: No Commands Parsed

**Symptom**: "No commands found in skill instructions"

**Causes**:
- Skill has no code blocks
- Code blocks have no language identifier
- Instructions are empty

**Solution**:
```markdown
Add code blocks with language:

```bash
curl "https://api.example.com/data"
```
```

### Issue 2: Placeholder Not Replaced

**Symptom**: Command still shows `${VARIABLE}`

**Causes**:
- Input doesn't match expected pattern
- Placeholder name doesn't match input
- Skill instructions unclear

**Solution**:
```markdown
Be explicit about placeholders:

Replace `${LOCATION}` with the city name from your input.

Example: "Get weather for Tokyo" → ${LOCATION} = "Tokyo"
```

### Issue 3: Command Fails

**Symptom**: "Command execution failed"

**Causes**:
- Binary not found
- Environment variable not set
- API endpoint unreachable
- Invalid credentials

**Solution**:
1. Check gating requirements
2. Verify environment variables
3. Test command manually
4. Check API status

### Issue 4: Unexpected Output

**Symptom**: Output doesn't match expected format

**Causes**:
- API changed response format
- Command syntax error
- Wrong endpoint
- Missing parameters

**Solution**:
1. Test command manually
2. Check API documentation
3. Update skill instructions
4. Verify placeholder replacement

## Best Practices

### 1. Test Incrementally

```
Step 1: Test with dry run
Step 2: Verify one command at a time
Step 3: Test full workflow
Step 4: Test with actual execution
Step 5: Test edge cases
```

### 2. Document Test Cases

In skill instructions:

```markdown
## Test Cases

### Test 1: Basic Usage

Input: "Get weather for London"
Expected: Temperature and conditions for London

### Test 2: Multiple Locations

Input: "Get weather for Tokyo, Paris, and New York"
Expected: Weather data for all three cities

### Test 3: Error Handling

Input: "Get weather for InvalidCity"
Expected: Error message about location not found
```

### 3. Use Realistic Data

```
Good: "Get weather for London"
Better: "Get current weather conditions for London, UK"
Best: "Get weather for London, UK including temperature, humidity, and 5-day forecast"
```

### 4. Verify Security

Before actual execution:
- Check what commands will run
- Verify no sensitive data in commands
- Ensure API keys are not logged
- Confirm destructive operations are intentional

### 5. Monitor Execution

Watch for:
- Execution time (should be reasonable)
- Resource usage (memory, CPU)
- Network requests (count, size)
- Error rates

## Advanced Testing

### Testing with Variables

Set environment variables before testing:

```bash
export API_KEY="test_key_123"
export ENVIRONMENT="staging"
```

Then test:

```
Input: "Deploy to staging"
Expected: Uses ENVIRONMENT=staging
```

### Testing Multi-Step Skills

For skills with multiple commands:

```
Input: "Process data file data.csv"

Expected Steps:
  1. Validate file exists
  2. Parse CSV data
  3. Transform data
  4. Save results
  5. Generate report

Verify each step in dry run before actual execution.
```

### Testing with Mock Data

Create test data files:

```bash
# Create test file
echo '{"test": "data"}' > test-data.json

# Test skill
Input: "Process test-data.json"
```

### Performance Testing

Test with various input sizes:

```
Small: "Process 10 records"
Medium: "Process 1000 records"
Large: "Process 100000 records"

Monitor:
- Execution time
- Memory usage
- Success rate
```

## Troubleshooting

### Debug Mode

Enable verbose output:

```
Input: "Get weather for London [DEBUG]"

Output includes:
- Raw skill instructions
- Parsing steps
- Placeholder matching
- Command construction
- Execution details
```

### Manual Testing

Test commands manually:

```bash
# Copy command from parsed output
curl "https://api.weather.com/v1/current?location=London&apikey=${WEATHER_API_KEY}"

# Run in terminal
# Compare output with skill test result
```

### Log Analysis

Check logs for details:

```
2026-01-29 13:00:00 - INFO - Parsing skill instructions
2026-01-29 13:00:00 - INFO - Found 3 code blocks
2026-01-29 13:00:00 - INFO - Extracted 3 commands
2026-01-29 13:00:01 - INFO - Replaced 2 placeholders
2026-01-29 13:00:01 - INFO - Executing command 1/3
2026-01-29 13:00:02 - INFO - Command completed successfully
```

## References

- [Creating Agent Skills](./creating-agent-skills.md)
- [SKILL.md Format Reference](./skill-md-format.md)
- [Gating Requirements Guide](./gating-requirements.md)
