"""
Weather Helper Script

This script provides helper functions for fetching and formatting weather data.
It can be called from the command line or imported as a module.
"""

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from utils import format_temperature, format_wind_speed, get_weather_emoji

GEO_DIRECT_ENDPOINT = "https://api.openweathermap.org/geo/1.0/direct"
CURRENT_ENDPOINT = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_ENDPOINT = "https://api.openweathermap.org/data/2.5/forecast"

# Common Chinese location aliases to improve geocoding precision.
# Fallback transliteration via pypinyin is used for entries not listed here.
CHINESE_LOCATION_ALIASES = {
    "中国": "China",
    "北京": "Beijing",
    "上海": "Shanghai",
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "杭州": "Hangzhou",
    "南京": "Nanjing",
    "天津": "Tianjin",
    "天津市": "Tianjin",
    "重庆": "Chongqing",
    "福州": "Fuzhou City,Fujian",
    "福州市": "Fuzhou City,Fujian",
    "仓山": "Cangshan,Fuzhou",
    "仓山区": "Cangshan,Fuzhou",
}

CHINESE_ADMIN_SUFFIXES = (
    "特别行政区",
    "自治区",
    "自治州",
    "自治县",
    "地区",
    "盟",
    "州",
    "省",
    "市",
    "区",
    "县",
)

SUPPORTED_COMMANDS = {"current", "forecast", "resolve"}


def _get_api_key() -> str:
    """Read and validate the OpenWeather API key."""
    api_key = os.environ.get("WEATHER_API_KEY")
    if not api_key:
        raise ValueError("WEATHER_API_KEY environment variable not set")
    return api_key


def _contains_cjk(text: str) -> bool:
    """Detect if text contains CJK characters."""
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            return True
    return False


def _normalize_country(country: Optional[str]) -> Optional[str]:
    """Normalize country code to uppercase."""
    if not country:
        return None
    return country.strip().upper()


def _is_likely_country_code(value: str) -> bool:
    """Return True when value looks like an ISO alpha-2 country code."""
    token = value.strip()
    return len(token) == 2 and token.isascii() and token.isalpha()


def _rewrite_ambiguous_short_country_flag(argv: List[str]) -> List[str]:
    """
    Rewrite ambiguous '-c' flag:
    - '-c CN' -> '--country CN'
    - '-c 福州' -> '--location 福州'

    This keeps backward compatibility with legacy prompt habits where '-c' was
    mistakenly used for city/location.
    """
    rewritten: List[str] = []
    idx = 0
    while idx < len(argv):
        token = argv[idx]
        if token != "-c":
            rewritten.append(token)
            idx += 1
            continue

        next_value = argv[idx + 1] if idx + 1 < len(argv) else None
        if not next_value or next_value.startswith("-"):
            rewritten.append("--country")
            idx += 1
            continue

        if _is_likely_country_code(next_value):
            rewritten.append("--country")
        else:
            rewritten.append("--location")
        rewritten.append(next_value)
        idx += 2

    return rewritten


def _rewrite_legacy_argv(argv: List[str]) -> List[str]:
    """
    Rewrite legacy CLI shapes to explicit subcommand form.

    Supported rewrites:
    - weather_helper.py 福州
      -> weather_helper.py current --location 福州
    - weather_helper.py -c 福州
      -> weather_helper.py current --location 福州
    - weather_helper.py --location 福州 --country CN
      -> weather_helper.py current --location 福州 --country CN
    """
    if not argv:
        return argv

    normalized = _rewrite_ambiguous_short_country_flag(argv)
    first = normalized[0]

    if first in {"-h", "--help"}:
        return normalized
    if first in SUPPORTED_COMMANDS:
        return normalized

    if first.startswith("-"):
        return ["current", *normalized]

    return ["current", "--location", first, *normalized[1:]]


def _strip_chinese_admin_suffix(text: str) -> str:
    """Strip common Chinese administrative suffixes from a location token."""
    stripped = text.strip()
    for suffix in CHINESE_ADMIN_SUFFIXES:
        if stripped.endswith(suffix) and len(stripped) > len(suffix):
            return stripped[: -len(suffix)]
    return stripped


def _to_english_location_token(token: str) -> str:
    """
    Convert one location token to English for providers that do not support Chinese.

    Priority:
    1) built-in alias map
    2) pypinyin transliteration if available
    """
    token = token.strip()
    if not token:
        raise ValueError("Empty location token")
    if not _contains_cjk(token):
        return token

    alias = CHINESE_LOCATION_ALIASES.get(token)
    if alias:
        return alias

    without_suffix = _strip_chinese_admin_suffix(token)
    alias = CHINESE_LOCATION_ALIASES.get(without_suffix)
    if alias:
        return alias

    try:
        from pypinyin import lazy_pinyin
    except Exception as exc:
        raise ValueError(
            "Chinese location detected but transliteration is unavailable. "
            "Please use English location names or coordinates."
        ) from exc

    syllables = [s for s in lazy_pinyin(without_suffix, errors="ignore") if s]
    if not syllables:
        raise ValueError(
            f"Failed to transliterate Chinese location token '{token}'. "
            "Please provide English location name or coordinates."
        )
    return "".join(part.capitalize() for part in syllables)


def _normalize_location_for_provider(location: str) -> str:
    """Normalize location query for providers that require English location names."""
    segments = [segment.strip() for segment in location.split(",") if segment.strip()]
    if not segments:
        raise ValueError("Location cannot be empty")
    expanded_tokens: List[str] = []
    for segment in segments:
        converted = _to_english_location_token(segment)
        for token in converted.split(","):
            token = token.strip()
            if token:
                expanded_tokens.append(token)

    # Deduplicate exact tokens while preserving order.
    deduped_tokens: List[str] = []
    seen_lower = set()
    for token in expanded_tokens:
        lowered = token.lower()
        if lowered in seen_lower:
            continue
        seen_lower.add(lowered)
        deduped_tokens.append(token)

    # If both "X" and "X City" exist, keep the more specific "X City".
    city_bases = {
        token.lower().removesuffix(" city").strip()
        for token in deduped_tokens
        if token.lower().endswith(" city")
    }
    if city_bases:
        deduped_tokens = [
            token
            for token in deduped_tokens
            if token.lower().endswith(" city") or token.lower().strip() not in city_bases
        ]

    return ",".join(deduped_tokens)


def _build_geocode_query(location: str, country: Optional[str], state: Optional[str]) -> str:
    """Build geocoding query string."""
    parts = [location.strip()]
    if state:
        parts.append(state.strip())
    if country:
        parts.append(country.strip())
    return ",".join(parts)


def _format_candidate_label(item: Dict[str, Any]) -> str:
    """Format one geocoding candidate into a readable location label."""
    name = item.get("name") or "Unknown"
    state = item.get("state")
    country = item.get("country")
    pieces = [name]
    if state:
        pieces.append(state)
    if country:
        pieces.append(country)
    return ", ".join(pieces)


def _candidate_summary(item: Dict[str, Any]) -> str:
    """Create one-line summary for candidate diagnostics."""
    lat = item.get("lat")
    lon = item.get("lon")
    return f"{_format_candidate_label(item)} (lat={lat}, lon={lon})"


def _fetch_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """GET JSON from a remote endpoint with error propagation."""
    import requests

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Unexpected API response format")
    return payload


def _fetch_json_list(url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """GET JSON list from a remote endpoint with basic validation."""
    import requests

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Unexpected geocoding response format")
    return [item for item in payload if isinstance(item, dict)]


def list_location_candidates(
    location: str,
    *,
    country: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Resolve location string to up to `limit` geocoding candidates.

    Args:
        location: User-entered location text
        country: Optional country code (ISO 3166-1 alpha-2)
        state: Optional state/province hint
        limit: Max candidates to return (1-10)
    """
    if not location or not location.strip():
        raise ValueError("Location cannot be empty")
    if limit < 1 or limit > 10:
        raise ValueError("limit must be between 1 and 10")

    api_key = _get_api_key()
    original_location = location.strip()
    country = _normalize_country(country)

    normalized_location = _normalize_location_for_provider(original_location)
    normalized_state = _normalize_location_for_provider(state) if state else None

    # Provider requires English location names; for Chinese input default to CN unless provided.
    if _contains_cjk(original_location) and not country:
        country = "CN"

    query = _build_geocode_query(normalized_location, country=country, state=normalized_state)

    items = _fetch_json_list(
        GEO_DIRECT_ENDPOINT,
        {
            "q": query,
            "limit": limit,
            "appid": api_key,
        },
    )

    if items:
        return items

    # Retry with looser query when state hint may be too specific.
    if normalized_state:
        fallback_query = _build_geocode_query(normalized_location, country=country, state=None)
        items = _fetch_json_list(
            GEO_DIRECT_ENDPOINT,
            {
                "q": fallback_query,
                "limit": limit,
                "appid": api_key,
            },
        )
        if items:
            return items

    hint = "Try '<City,CountryCode>' such as 'Fuzhou,CN' or pass --lat/--lon."
    if _contains_cjk(original_location):
        hint = (
            f"Chinese location '{original_location}' was normalized to "
            f"'{normalized_location}'. Try a more specific English name (for example "
            "'Cangshan,Fuzhou,CN') or use coordinates via --lat/--lon."
        )
    raise ValueError(f"Location '{original_location}' not found. {hint}")


def _suggest_candidates(candidates: List[Dict[str, Any]], max_items: int = 3) -> str:
    """Format top candidates for an ambiguity error."""
    suggestions = []
    for idx, item in enumerate(candidates[:max_items], start=1):
        suggestions.append(f"{idx}. {_candidate_summary(item)}")
    return "\n".join(suggestions)


def resolve_location(
    location: str,
    *,
    country: Optional[str] = None,
    state: Optional[str] = None,
    strict_resolve: bool = True,
) -> Dict[str, Any]:
    """
    Resolve location to a single candidate with optional strict ambiguity checks.

    If `strict_resolve=True` and resolution is ambiguous, raises ValueError with
    candidate suggestions instead of silently picking the first result.
    """
    country = _normalize_country(country)
    candidates = list_location_candidates(location, country=country, state=state, limit=5)
    normalized_state = _normalize_location_for_provider(state) if state else None

    if country:
        country_filtered = [
            item for item in candidates if _normalize_country(item.get("country")) == country
        ]
        if country_filtered:
            candidates = country_filtered

    if normalized_state:
        state_filtered = [
            item
            for item in candidates
            if (item.get("state") or "").strip().lower() == normalized_state.strip().lower()
        ]
        if state_filtered:
            candidates = state_filtered

    if len(candidates) == 1:
        return candidates[0]

    if strict_resolve:
        top = _suggest_candidates(candidates, max_items=5)
        raise ValueError(
            "Ambiguous location query. Please specify --country/--state or use --lat/--lon.\n"
            f"Candidates:\n{top}"
        )

    return candidates[0]


def _resolve_target(
    *,
    location: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    country: Optional[str],
    state: Optional[str],
    strict_resolve: bool,
) -> Dict[str, Any]:
    """Resolve location inputs to one coordinate target."""
    if (lat is None) != (lon is None):
        raise ValueError("Both lat and lon must be provided together")

    if lat is not None and lon is not None:
        return {
            "name": "Coordinate Query",
            "country": country,
            "state": state,
            "lat": lat,
            "lon": lon,
            "resolution_source": "coordinates",
        }

    if not location:
        raise ValueError("Location is required when --lat/--lon are not provided")

    resolved = resolve_location(
        location=location,
        country=country,
        state=state,
        strict_resolve=strict_resolve,
    )
    resolved["resolution_source"] = "geocoding"
    return resolved


def _fetch_weather_by_coords(endpoint: str, lat: float, lon: float, units: str) -> Dict[str, Any]:
    """Fetch weather payload with coordinates."""
    api_key = _get_api_key()
    return _fetch_json(
        endpoint,
        {
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": units,
        },
    )


def get_current_weather(
    location: Optional[str] = None,
    units: str = "metric",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    country: Optional[str] = None,
    state: Optional[str] = None,
    strict_resolve: bool = True,
) -> Dict[str, Any]:
    """
    Get current weather for a location.

    Args:
        location: City/district name (optional when coordinates are provided)
        units: Temperature units (metric, imperial, standard)
        lat: Latitude (optional, requires lon)
        lon: Longitude (optional, requires lat)
        country: Optional country code for disambiguation
        state: Optional state/province for disambiguation
        strict_resolve: If true, fail on ambiguous location instead of guessing
    """
    target = _resolve_target(
        location=location,
        lat=lat,
        lon=lon,
        country=country,
        state=state,
        strict_resolve=strict_resolve,
    )

    data = _fetch_weather_by_coords(
        endpoint=CURRENT_ENDPOINT,
        lat=float(target["lat"]),
        lon=float(target["lon"]),
        units=units,
    )

    resolved_label = _format_candidate_label(target)

    return {
        "location": resolved_label,
        "temperature": format_temperature(data["main"]["temp"], units),
        "feels_like": format_temperature(data["main"]["feels_like"], units),
        "conditions": data["weather"][0]["description"].title(),
        "emoji": get_weather_emoji(data["weather"][0]["main"]),
        "humidity": f"{data['main']['humidity']}%",
        "wind": format_wind_speed(data["wind"]["speed"], units),
        "pressure": f"{data['main']['pressure']} hPa",
        "resolved_location": {
            "name": target.get("name"),
            "state": target.get("state"),
            "country": target.get("country"),
            "lat": target.get("lat"),
            "lon": target.get("lon"),
            "source": target.get("resolution_source"),
        },
    }


def _get_forecast_with_context(
    *,
    location: Optional[str],
    days: int,
    units: str,
    lat: Optional[float],
    lon: Optional[float],
    country: Optional[str],
    state: Optional[str],
    strict_resolve: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Resolve location, fetch forecast, and return both forecast + location context."""
    from datetime import datetime

    target = _resolve_target(
        location=location,
        lat=lat,
        lon=lon,
        country=country,
        state=state,
        strict_resolve=strict_resolve,
    )

    data = _fetch_weather_by_coords(
        endpoint=FORECAST_ENDPOINT,
        lat=float(target["lat"]),
        lon=float(target["lon"]),
        units=units,
    )

    daily_forecasts: List[Dict[str, Any]] = []
    current_date = None
    day_data: List[Dict[str, Any]] = []

    for item in data["list"][: days * 8]:
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

    return daily_forecasts[:days], target


def get_forecast(
    location: Optional[str],
    days: int = 5,
    units: str = "metric",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    country: Optional[str] = None,
    state: Optional[str] = None,
    strict_resolve: bool = True,
) -> List[Dict[str, Any]]:
    """
    Get weather forecast for a location.

    Args:
        location: City/district name (optional when coordinates are provided)
        days: Number of days (1-5)
        units: Temperature units
        lat: Latitude (optional, requires lon)
        lon: Longitude (optional, requires lat)
        country: Optional country code for disambiguation
        state: Optional state/province for disambiguation
        strict_resolve: If true, fail on ambiguous location instead of guessing
    """
    forecasts, _ = _get_forecast_with_context(
        location=location,
        days=days,
        units=units,
        lat=lat,
        lon=lon,
        country=country,
        state=state,
        strict_resolve=strict_resolve,
    )
    return forecasts


def _summarize_day(day_data: List[Dict[str, Any]], units: str) -> Dict[str, Any]:
    """Summarize one day's forecast data."""
    from datetime import datetime

    temps = [item["main"]["temp"] for item in day_data]
    conditions = [item["weather"][0]["main"] for item in day_data]
    condition = max(set(conditions), key=conditions.count)

    return {
        "date": datetime.fromtimestamp(day_data[0]["dt"]).strftime("%Y-%m-%d"),
        "day": datetime.fromtimestamp(day_data[0]["dt"]).strftime("%A"),
        "temp_min": format_temperature(min(temps), units),
        "temp_max": format_temperature(max(temps), units),
        "conditions": condition,
        "emoji": get_weather_emoji(condition),
    }


def print_current_weather(weather: Dict[str, Any]) -> None:
    """Print formatted current weather."""
    print(f"\n{weather['emoji']} {weather['location']} Weather:")
    print(f"  Temperature: {weather['temperature']}")
    print(f"  Feels like: {weather['feels_like']}")
    print(f"  Conditions: {weather['conditions']}")
    print(f"  Humidity: {weather['humidity']}")
    print(f"  Wind: {weather['wind']}")
    print(f"  Pressure: {weather['pressure']}")

    resolved = weather.get("resolved_location") or {}
    if resolved.get("lat") is not None and resolved.get("lon") is not None:
        print(f"  Coordinates: {resolved['lat']}, {resolved['lon']}")
    print()


def print_forecast(forecasts: List[Dict[str, Any]], location_label: Optional[str] = None) -> None:
    """Print formatted forecast."""
    if location_label:
        print(f"\n📅 Weather Forecast for {location_label}:\n")
    else:
        print("\n📅 Weather Forecast:\n")

    for forecast in forecasts:
        print(f"{forecast['emoji']} {forecast['day']} ({forecast['date']})")
        print(f"  {forecast['temp_min']} - {forecast['temp_max']}")
        print(f"  {forecast['conditions']}\n")


def print_location_candidates(candidates: List[Dict[str, Any]]) -> None:
    """Print location candidates from geocoding results."""
    print("\n📍 Location candidates:\n")
    for idx, candidate in enumerate(candidates, start=1):
        print(f"{idx}. {_candidate_summary(candidate)}")
    print()


def _add_shared_location_args(parser: argparse.ArgumentParser, include_days: bool = False) -> None:
    """Add shared location arguments used by current/forecast commands."""
    parser.add_argument("location_pos", nargs="?", help="Location name (positional)")
    parser.add_argument(
        "--location",
        "-l",
        "--city",
        dest="location",
        required=False,
        help="Location name (city/district)",
    )
    parser.add_argument(
        "--country",
        "-C",
        required=False,
        help="Country code for disambiguation (example: CN, US, GB)",
    )
    parser.add_argument("--state", "-s", required=False, help="State/province for disambiguation")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument(
        "--allow-ambiguous",
        action="store_true",
        help="Allow ambiguous location names and use the top geocoding candidate",
    )
    parser.add_argument(
        "--units",
        "-u",
        default="metric",
        choices=["metric", "imperial", "standard"],
        help="Temperature units",
    )
    if include_days:
        parser.add_argument(
            "--days",
            "-d",
            type=int,
            default=5,
            choices=range(1, 6),
            help="Number of days",
        )


def main() -> int:
    """Command-line interface."""
    parser = argparse.ArgumentParser(description="Weather Helper")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    current_parser = subparsers.add_parser("current", help="Get current weather")
    _add_shared_location_args(current_parser, include_days=False)

    forecast_parser = subparsers.add_parser("forecast", help="Get weather forecast")
    _add_shared_location_args(forecast_parser, include_days=True)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve location to coordinates")
    resolve_parser.add_argument("location_pos", nargs="?", help="Location name (positional)")
    resolve_parser.add_argument(
        "--location",
        "-l",
        "--city",
        dest="location",
        required=False,
        help="Location name (city/district)",
    )
    resolve_parser.add_argument(
        "--country",
        "-C",
        required=False,
        help="Country code for disambiguation (example: CN, US, GB)",
    )
    resolve_parser.add_argument("--state", "-s", required=False, help="State/province hint")
    resolve_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        choices=range(1, 11),
        help="Max candidates (1-10)",
    )

    args = parser.parse_args(_rewrite_legacy_argv(sys.argv[1:]))
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
            weather = get_current_weather(
                location=location,
                units=args.units,
                lat=args.lat,
                lon=args.lon,
                country=args.country,
                state=args.state,
                strict_resolve=not args.allow_ambiguous,
            )
            print_current_weather(weather)
            return 0

        if args.command == "forecast":
            location = args.location or args.location_pos
            if location is None and (args.lat is None or args.lon is None):
                parser.error(
                    "forecast requires --location/-l (or --city / positional <location>), "
                    "or both --lat and --lon"
                )
            forecasts, target = _get_forecast_with_context(
                location=location,
                days=args.days,
                units=args.units,
                lat=args.lat,
                lon=args.lon,
                country=args.country,
                state=args.state,
                strict_resolve=not args.allow_ambiguous,
            )
            print_forecast(forecasts, location_label=_format_candidate_label(target))
            return 0

        if args.command == "resolve":
            location = args.location or args.location_pos
            if not location:
                parser.error("resolve requires --location/-l (or --city / positional <location>)")
            candidates = list_location_candidates(
                location=location,
                country=args.country,
                state=args.state,
                limit=args.limit,
            )
            print_location_candidates(candidates)
            return 0

        parser.print_help()
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
