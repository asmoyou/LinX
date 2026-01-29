"""
Utility functions for weather data processing.
"""

from typing import Dict


def format_temperature(temp: float, units: str) -> str:
    """
    Format temperature with appropriate unit symbol.
    
    Args:
        temp: Temperature value
        units: Unit system (metric, imperial, standard)
        
    Returns:
        Formatted temperature string
    """
    symbols = {
        "metric": "°C",
        "imperial": "°F",
        "standard": "K"
    }
    return f"{temp:.1f}{symbols.get(units, '°C')}"


def format_wind_speed(speed: float, units: str) -> str:
    """
    Format wind speed with appropriate unit.
    
    Args:
        speed: Wind speed value
        units: Unit system
        
    Returns:
        Formatted wind speed string
    """
    if units == "imperial":
        return f"{speed:.1f} mph"
    else:
        return f"{speed:.1f} m/s"


def get_weather_emoji(condition: str) -> str:
    """
    Get emoji for weather condition.
    
    Args:
        condition: Weather condition name
        
    Returns:
        Emoji character
    """
    emoji_map = {
        "Clear": "☀️",
        "Clouds": "☁️",
        "Rain": "🌧️",
        "Drizzle": "🌦️",
        "Thunderstorm": "⛈️",
        "Snow": "❄️",
        "Mist": "🌫️",
        "Fog": "🌫️",
        "Haze": "🌫️",
        "Smoke": "🌫️",
        "Dust": "🌪️",
        "Sand": "🌪️",
        "Ash": "🌋",
        "Squall": "💨",
        "Tornado": "🌪️"
    }
    return emoji_map.get(condition, "🌤️")


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (celsius * 9/5) + 32


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (fahrenheit - 32) * 5/9


def parse_location(location_str: str) -> Dict[str, str]:
    """
    Parse location string into components.
    
    Args:
        location_str: Location string (e.g., "Seattle, WA, US")
        
    Returns:
        Dictionary with location components
    """
    parts = [p.strip() for p in location_str.split(",")]
    
    result = {"city": parts[0]}
    
    if len(parts) > 1:
        result["state"] = parts[1]
    if len(parts) > 2:
        result["country"] = parts[2]
    
    return result
