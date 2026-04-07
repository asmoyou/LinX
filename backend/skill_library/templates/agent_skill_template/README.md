# Weather Forecast Skill

A natural language skill for retrieving weather information using the OpenWeatherMap API.

**This is an example demonstrating the Simple Script Mode for Agent Skills.**

## Quick Start

1. Get an API key from [OpenWeatherMap](https://openweathermap.org/api)
2. Set the environment variable: `export WEATHER_API_KEY=your_api_key_here`
3. Install dependencies: `pip install -r requirements.txt`
4. Upload this package to LinX
5. Test with natural language: "What's the weather in Seattle?"

## Package Structure

This skill uses the **Simple Script Mode** structure:

```
weather-skill/
├── SKILL.md              # Main skill definition (required)
├── README.md             # This file (optional)
├── requirements.txt      # Python dependencies
├── scripts/              # Executable scripts
│   ├── weather_helper.py # Main weather fetching tool
│   └── utils.py          # Utility functions
└── references/           # Reference documentation (optional)
    └── .gitkeep
```

## Agent Skills Structure Modes

Agent Skills can be structured in three ways:

### 1. Simple Script Mode (This Example)

Best for most skills with straightforward scripts:

```
skill-name/
├── SKILL.md
├── scripts/
│   ├── main.py
│   └── utils.py
└── requirements.txt
```

### 2. Complete Package Mode

For complex skills requiring full Python package structure:

```
skill-name/
├── SKILL.md
├── pyproject.toml
└── src/
    └── skill_name/
        ├── __init__.py
        ├── main.py
        └── utils.py
```

### 3. Mixed Mode

For skills with both simple scripts and complex packages:

```
skill-name/
├── SKILL.md
├── scripts/          # Simple scripts
│   └── quick.py
├── src/              # Complex package
│   └── skill_name/
│       └── api.py
└── requirements.txt
```

## Key Concepts

### SKILL.md = Instructions + Executable Code

- **SKILL.md**: Teaches the agent **HOW** to use the tools
- **scripts/**: Executable code that the agent **calls**
- **{baseDir}**: Placeholder for the skill package directory path

Example from SKILL.md:
```bash
python3 {baseDir}/scripts/weather_helper.py current --location "Seattle"
```

### Configuration via Environment Variables

Agent Skills use environment variables for configuration (not config files):

```bash
export WEATHER_API_KEY=your_key_here
export API_TIMEOUT=30
```

## SKILL.md Format

The `SKILL.md` file follows the AgentSkills.io standard format:

- **Frontmatter** (YAML): Metadata including name, version, gating requirements
- **Markdown Body**: Natural language instructions and examples

### Gating Requirements

Skills can specify requirements:

```yaml
gating:
  binaries:
    - python3
    - curl
  env_vars:
    - WEATHER_API_KEY
```

The system checks these requirements and marks skills as eligible/ineligible.

## Testing

Test this skill with various natural language queries:

- Simple: "Weather in Paris"
- Detailed: "Get the 5-day forecast for Tokyo with temperature in Celsius"
- Specific: "What's the humidity in London right now?"

The agent will:
1. Read the SKILL.md instructions
2. Understand how to use the scripts
3. Execute the appropriate commands
4. Return formatted results

## Customization

You can customize this skill by:

1. Modifying the API endpoints in SKILL.md
2. Adding more usage examples
3. Updating gating requirements
4. Adding additional scripts to `scripts/`
5. Adding reference documentation to `references/`

## Reference Implementations

This structure is based on:

- **Moltbot**: 54 skills with scripts/ and src/ directories
- **Claude Code**: Plugins with hooks/, core/, utils/ directories
- **AgentSkills.io**: Standard format for agent skills

Examples:
- Moltbot `openai-image-gen`: Simple script mode
- Moltbot `local-places`: Complete package mode (FastAPI MCP server)
- Moltbot `bitwarden`: Mixed mode with scripts and references

## Support

For issues or questions:
- Check the [LinX Documentation](https://docs.linx.ai)
- Visit the [AgentSkills.io](https://agentskills.io) standard
- Review [Moltbot Skills](https://github.com/moltbot/skills) for examples
- Open an issue on GitHub

## License

By default, this template follows the license of the repository or package that distributes it.
If you publish a generated skill separately, set an explicit license for that skill before distribution.
