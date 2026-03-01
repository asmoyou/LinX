---
# NOTE: 'name' must contain only alphanumeric characters, underscores, and hyphens
# Use snake_case or kebab-case (e.g., weather_forecast or weather-forecast)
name: weather-search
emoji: 🌤️
version: 1.1.0
author: LinX Team
homepage: https://github.com/yourusername/weather-skill
description: Get weather forecast and current conditions for any location worldwide
tags:
  - weather
  - api
  - forecast
  - data
gating:
  binaries:
    - python3
    - curl
  env_vars:
    - WEATHER_API_KEY
metadata:
  category: data
  difficulty: intermediate
  estimated_time: "5 minutes"
  language: en
---

# Weather Forecast Skill

Get current weather conditions and multi-day forecasts for any location worldwide using natural language queries.

## Description

This skill supports:
- Current temperature, humidity, wind, and conditions
- 1-5 day forecast

The main entry point is `scripts/weather_helper.py`.

## Execution Contract (MANDATORY)

Always follow this sequence to avoid retries and wrong locations:

1. Normalize location first (before any command):
- Chinese place names must be converted to English for this provider.
- For China, always include `--country CN`.
- Use specific location context for common ambiguous places:
  - `福州` -> `Fuzhou City,Fujian`
  - `仓山区` -> `Cangshan,Fuzhou`

2. Validate CLI shape first:

```bash
python3 {baseDir}/scripts/weather_helper.py --help
python3 {baseDir}/scripts/weather_helper.py current --help
```

3. Use one of these exact command forms:

```bash
# Current weather by city (preferred)
python3 {baseDir}/scripts/weather_helper.py current --location "Fuzhou City,Fujian" --country CN

# Current weather by coordinates
python3 {baseDir}/scripts/weather_helper.py current --lat 26.0745 --lon 119.2965

# Forecast (1-5 days)
python3 {baseDir}/scripts/weather_helper.py forecast --location "London" --country GB --days 5

# Resolve/inspect location candidates before weather call (recommended for ambiguous names)
python3 {baseDir}/scripts/weather_helper.py resolve --location "Fuzhou City,Fujian" --country CN
```

4. Use long options explicitly:
- Always use `--location` and `--country`.
- Do not use short option `-c` in prompts/examples.
- `-c` has legacy compatibility behavior and can be misinterpreted.

5. Do not call the script without a subcommand in your plan:
- Wrong: `python3 weather_helper.py --city 福州`
- Wrong: `python3 weather_helper.py 福州`

6. Chinese input conversion examples:
- `福州` -> `Fuzhou City,Fujian` (+ `--country CN`)
- `仓山区` -> `Cangshan,Fuzhou` (+ `--country CN`)
- If district-level query is ambiguous, run `resolve` first or use `--lat/--lon`.

## Usage Examples

### Get Current Weather

```bash
python3 {baseDir}/scripts/weather_helper.py current --location "Seattle" --country US
```

### Get 5-Day Forecast

```bash
python3 {baseDir}/scripts/weather_helper.py forecast --location "London" --country GB --days 5
```

### Get Weather by Coordinates

```bash
python3 {baseDir}/scripts/weather_helper.py current --lat 37.7749 --lon -122.4194
```

### Resolve Location Candidates (Before Querying)

```bash
python3 {baseDir}/scripts/weather_helper.py resolve --location "Cangshan,Fuzhou" --country CN
```

### Direct API Call (Fallback)

```bash
curl "https://api.openweathermap.org/data/2.5/weather?q=Seattle,US&appid=${WEATHER_API_KEY}&units=metric"
```

## Natural Language Testing

You can test this skill with natural language queries like:

- "What's the weather in Seattle?"
- "Get the forecast for London for the next 5 days"
- "Is it going to rain in Tokyo tomorrow?"
- "What's the temperature in New York right now?"

When the query contains Chinese location names, normalize to English (or pinyin) before command execution.
Then include country code explicitly (for China, `--country CN`).

## Package Contents

This skill package includes:

- **SKILL.md**: This file - natural language instructions
- **scripts/weather_helper.py**: Python script for API calls and formatting
- **scripts/utils.py**: Utility functions for data processing
- **requirements.txt**: Python dependencies
- **references/**: Additional documentation (optional)

## Configuration

This skill requires the following environment variable:

- `WEATHER_API_KEY`: Your OpenWeatherMap API key (get one at https://openweathermap.org/api)

Set it in your environment:

```bash
export WEATHER_API_KEY=your_api_key_here
```

Or add it to your `.env` file.

## Gating Requirements

This skill requires:
- **Binary**: `python3` - for running helper scripts
- **Binary**: `curl` - for direct API calls
- **Environment Variable**: `WEATHER_API_KEY` - API authentication

Note: The `api.weather.enabled` config check has been removed. Use environment variables for configuration instead.

## Error Handling

Common errors and solutions:

- **CLI argument error (exit code 2)**:
  - Run `python3 {baseDir}/scripts/weather_helper.py current --help`
  - Then retry with `current --location "<CityEnglish[,State]>" --country <Code>`
- **401 Unauthorized**: Check that `WEATHER_API_KEY` is set correctly
- **404 Not Found**:
  - First retry with English place name + `--country` (example: `Fuzhou City,Fujian` + `--country CN`)
  - If still failing, use `--lat/--lon`
- **Ambiguous location query**:
  - Run `resolve` to inspect candidates
  - Add `--country`/`--state`, or switch to coordinates
- **429 Too Many Requests**: You've exceeded the API rate limit
- **ModuleNotFoundError**: Install dependencies with `pip install -r requirements.txt`

## API Reference

- **Base URL**: `https://api.openweathermap.org/data/2.5`
- **Rate Limit**: 60 calls/minute (free tier)
- **Documentation**: https://openweathermap.org/api

## Notes

- Temperature units can be `metric` (Celsius), `imperial` (Fahrenheit), or `standard` (Kelvin)
- Location can be specified by city name, coordinates, or zip code
- Free tier includes current weather and 5-day forecast
- Python scripts handle response parsing and formatting automatically
