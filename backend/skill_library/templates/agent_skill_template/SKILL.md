---
name: Weather Forecast
emoji: 🌤️
version: 1.0.0
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

This skill allows agents to retrieve weather information including:
- Current temperature, humidity, and conditions
- 5-day weather forecast
- Severe weather alerts
- Historical weather data

The skill includes Python helper scripts for data processing and formatting.

## Usage Examples

### Get Current Weather

Use the Python helper script for formatted output:

```bash
python3 {baseDir}/scripts/weather_helper.py current --location "Seattle"
```

Or use direct API call:

```bash
curl "https://api.openweathermap.org/data/2.5/weather?q=Seattle&appid=${WEATHER_API_KEY}&units=metric"
```

**Expected Output:**
```
Seattle Weather:
Temperature: 15.5°C
Conditions: Scattered clouds
Humidity: 72%
Wind: 12 km/h
```

### Get 5-Day Forecast

```bash
python3 {baseDir}/scripts/weather_helper.py forecast --location "London" --days 5
```

### Get Weather by Coordinates

```bash
python3 {baseDir}/scripts/weather_helper.py current --lat 37.7749 --lon -122.4194
```

## Natural Language Testing

You can test this skill with natural language queries like:

- "What's the weather in Seattle?"
- "Get the forecast for London for the next 5 days"
- "Is it going to rain in Tokyo tomorrow?"
- "What's the temperature in New York right now?"

The agent will automatically use the appropriate Python scripts or API calls.

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

- **401 Unauthorized**: Check that `WEATHER_API_KEY` is set correctly
- **404 Not Found**: Verify the location name is spelled correctly
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
