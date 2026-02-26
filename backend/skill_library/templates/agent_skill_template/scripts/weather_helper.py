"""
Weather Helper Script

This script provides helper functions for fetching and formatting weather data.
It can be called from the command line or imported as a module.
"""

import os
import sys
import argparse
from typing import Dict, Any, Optional
from utils import format_temperature, format_wind_speed, get_weather_emoji


def _resolve_location_to_coords(location: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Resolve a location string to coordinates via OpenWeather geocoding API."""
    import requests

    geo_url = "https://api.openweathermap.org/geo/1.0/direct"
    geo_params = {
        "q": location,
        "limit": 1,
        "appid": api_key,
    }
    response = requests.get(geo_url, params=geo_params, timeout=30)
    response.raise_for_status()
    items = response.json()
    if not items:
        return None
    item = items[0]
    if "lat" not in item or "lon" not in item:
        return None
    return item


def _fetch_weather_with_fallback(
    *,
    endpoint: str,
    api_key: str,
    units: str,
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict[str, Any]:
    """Fetch weather data and fallback to geocoding for location-based 404 errors."""
    import requests

    if lat is not None and lon is not None:
        params: Dict[str, Any] = {"lat": lat, "lon": lon, "appid": api_key, "units": units}
    elif location:
        params = {"q": location, "appid": api_key, "units": units}
    else:
        raise ValueError("A location string or both lat/lon must be provided")

    response = requests.get(endpoint, params=params, timeout=30)
    try:
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        is_location_404 = (
            response.status_code == 404
            and location
            and lat is None
            and lon is None
        )
        if not is_location_404:
            raise

        geo_item = _resolve_location_to_coords(location, api_key)
        if not geo_item:
            raise ValueError(
                f"Location '{location}' not found. Try '<City,CountryCode>' (e.g. 'Fuzhou,CN') "
                "or use coordinates with --lat/--lon."
            ) from exc

        fallback_params = {
            "lat": geo_item["lat"],
            "lon": geo_item["lon"],
            "appid": api_key,
            "units": units,
        }
        fallback_response = requests.get(endpoint, params=fallback_params, timeout=30)
        fallback_response.raise_for_status()
        return fallback_response.json()


def get_current_weather(
    location: Optional[str] = None,
    units: str = "metric",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Get current weather for a location.
    
    Args:
        location: City name (optional when coordinates are provided)
        units: Temperature units (metric, imperial, standard)
        lat: Latitude (optional, requires lon)
        lon: Longitude (optional, requires lat)
        
    Returns:
        Formatted weather data
    """
    api_key = os.environ.get('WEATHER_API_KEY')
    if not api_key:
        raise ValueError("WEATHER_API_KEY environment variable not set")

    if (lat is None) != (lon is None):
        raise ValueError("Both lat and lon must be provided together")

    data = _fetch_weather_with_fallback(
        endpoint="https://api.openweathermap.org/data/2.5/weather",
        api_key=api_key,
        units=units,
        location=location,
        lat=lat,
        lon=lon,
    )
    
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
    from datetime import datetime
    
    api_key = os.environ.get('WEATHER_API_KEY')
    if not api_key:
        raise ValueError("WEATHER_API_KEY environment variable not set")

    data = _fetch_weather_with_fallback(
        endpoint="https://api.openweathermap.org/data/2.5/forecast",
        api_key=api_key,
        units=units,
        location=location,
    )
    
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
    current_parser.add_argument("location_pos", nargs="?", help="Location name (positional)")
    current_parser.add_argument(
        "--location", "-l", "--city", dest="location", required=False, help="Location name"
    )
    current_parser.add_argument("--units", "-u", default="metric", 
                               choices=["metric", "imperial", "standard"],
                               help="Temperature units")
    current_parser.add_argument("--lat", type=float, help="Latitude")
    current_parser.add_argument("--lon", type=float, help="Longitude")
    
    # Forecast command
    forecast_parser = subparsers.add_parser("forecast", help="Get weather forecast")
    forecast_parser.add_argument("location_pos", nargs="?", help="Location name (positional)")
    forecast_parser.add_argument(
        "--location", "-l", "--city", dest="location", required=False, help="Location name"
    )
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
            location = args.location or args.location_pos
            if location is None and (args.lat is None or args.lon is None):
                parser.error(
                    "current requires --location/-l (or --city / positional <location>), "
                    "or both --lat and --lon"
                )
            weather = get_current_weather(location, args.units, lat=args.lat, lon=args.lon)
            print_current_weather(weather)
        elif args.command == "forecast":
            location = args.location or args.location_pos
            if not location:
                parser.error(
                    "forecast requires --location/-l (or --city / positional <location>)"
                )
            forecasts = get_forecast(location, args.days, args.units)
            print_forecast(forecasts)
        
        return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
