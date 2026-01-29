"""
Weather Helper Script

This script provides helper functions for fetching and formatting weather data.
It can be called from the command line or imported as a module.
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, Optional
from utils import format_temperature, format_wind_speed, get_weather_emoji


def get_current_weather(location: str, units: str = "metric") -> Dict[str, Any]:
    """
    Get current weather for a location.
    
    Args:
        location: City name or coordinates
        units: Temperature units (metric, imperial, standard)
        
    Returns:
        Formatted weather data
    """
    import requests
    
    api_key = os.environ.get('WEATHER_API_KEY')
    if not api_key:
        raise ValueError("WEATHER_API_KEY environment variable not set")
    
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": location,
        "appid": api_key,
        "units": units
    }
    
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    
    # Format the response
    return {
        "location": data["name"],
        "temperature": format_temperature(data["main"]["temp"], units),
        "feels_like": format_temperature(data["main"]["feels_like"], units),
        "conditions": data["weather"][0]["description"].title(),
        "emoji": get_weather_emoji(data["weather"][0]["main"]),
        "humidity": f"{data['main']['humidity']}%",
        "wind": format_wind_speed(data["wind"]["speed"], units),
        "pressure": f"{data['main']['pressure']} hPa"
    }


def get_forecast(location: str, days: int = 5, units: str = "metric") -> list:
    """
    Get weather forecast for a location.
    
    Args:
        location: City name
        days: Number of days (1-5)
        units: Temperature units
        
    Returns:
        List of daily forecasts
    """
    import requests
    from datetime import datetime
    
    api_key = os.environ.get('WEATHER_API_KEY')
    if not api_key:
        raise ValueError("WEATHER_API_KEY environment variable not set")
    
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "q": location,
        "appid": api_key,
        "units": units
    }
    
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    
    # Group by day and get daily summary
    daily_forecasts = []
    current_date = None
    day_data = []
    
    for item in data["list"][:days * 8]:  # 8 forecasts per day
        dt = datetime.fromtimestamp(item["dt"])
        date_str = dt.strftime("%Y-%m-%d")
        
        if date_str != current_date:
            if day_data:
                daily_forecasts.append(_summarize_day(day_data, units))
            current_date = date_str
            day_data = [item]
        else:
            day_data.append(item)
    
    if day_data:
        daily_forecasts.append(_summarize_day(day_data, units))
    
    return daily_forecasts[:days]


def _summarize_day(day_data: list, units: str) -> Dict[str, Any]:
    """Summarize a day's forecast data."""
    from datetime import datetime
    
    temps = [item["main"]["temp"] for item in day_data]
    conditions = [item["weather"][0]["main"] for item in day_data]
    
    # Most common condition
    condition = max(set(conditions), key=conditions.count)
    
    return {
        "date": datetime.fromtimestamp(day_data[0]["dt"]).strftime("%Y-%m-%d"),
        "day": datetime.fromtimestamp(day_data[0]["dt"]).strftime("%A"),
        "temp_min": format_temperature(min(temps), units),
        "temp_max": format_temperature(max(temps), units),
        "conditions": condition,
        "emoji": get_weather_emoji(condition)
    }


def print_current_weather(weather: Dict[str, Any]) -> None:
    """Print formatted current weather."""
    print(f"\n{weather['emoji']} {weather['location']} Weather:")
    print(f"  Temperature: {weather['temperature']}")
    print(f"  Feels like: {weather['feels_like']}")
    print(f"  Conditions: {weather['conditions']}")
    print(f"  Humidity: {weather['humidity']}")
    print(f"  Wind: {weather['wind']}")
    print(f"  Pressure: {weather['pressure']}\n")


def print_forecast(forecasts: list) -> None:
    """Print formatted forecast."""
    print("\n📅 Weather Forecast:\n")
    for forecast in forecasts:
        print(f"{forecast['emoji']} {forecast['day']} ({forecast['date']})")
        print(f"  {forecast['temp_min']} - {forecast['temp_max']}")
        print(f"  {forecast['conditions']}\n")


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(description="Weather Helper")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Current weather command
    current_parser = subparsers.add_parser("current", help="Get current weather")
    current_parser.add_argument("--location", "-l", required=True, help="Location name")
    current_parser.add_argument("--units", "-u", default="metric", 
                               choices=["metric", "imperial", "standard"],
                               help="Temperature units")
    current_parser.add_argument("--lat", type=float, help="Latitude")
    current_parser.add_argument("--lon", type=float, help="Longitude")
    
    # Forecast command
    forecast_parser = subparsers.add_parser("forecast", help="Get weather forecast")
    forecast_parser.add_argument("--location", "-l", required=True, help="Location name")
    forecast_parser.add_argument("--days", "-d", type=int, default=5, 
                                choices=range(1, 6), help="Number of days")
    forecast_parser.add_argument("--units", "-u", default="metric",
                                choices=["metric", "imperial", "standard"],
                                help="Temperature units")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == "current":
            weather = get_current_weather(args.location, args.units)
            print_current_weather(weather)
        elif args.command == "forecast":
            forecasts = get_forecast(args.location, args.days, args.units)
            print_forecast(forecasts)
        
        return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
