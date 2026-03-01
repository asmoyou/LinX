"""Tests for weather skill template helper script behavior."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
import requests


def _load_weather_helper_module():
    """Load template weather_helper.py as a module for direct unit testing."""
    backend_dir = Path(__file__).resolve().parents[3]
    script_path = (
        backend_dir
        / "skill_library"
        / "templates"
        / "agent_skill_template"
        / "scripts"
        / "weather_helper.py"
    )
    module_name = "weather_helper_template_test_module"

    if module_name in sys.modules:
        del sys.modules[module_name]

    sys.path.insert(0, str(script_path.parent))
    try:
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load module from {script_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class _DummyResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")


def test_current_weather_normalizes_chinese_input_to_english(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_weather_helper_module()
    monkeypatch.setenv("WEATHER_API_KEY", "dummy-key")

    calls: List[Dict[str, Any]] = []

    def fake_get(url: str, params: Dict[str, Any], timeout: int) -> _DummyResponse:
        calls.append({"url": url, "params": dict(params), "timeout": timeout})
        if "geo/1.0/direct" in url:
            assert params["q"] == "Fuzhou City,Fujian,CN"
            return _DummyResponse(
                [
                    {
                        "name": "Fuzhou City",
                        "state": "Fujian",
                        "country": "CN",
                        "lat": 26.0745,
                        "lon": 119.2965,
                    }
                ]
            )
        if "data/2.5/weather" in url:
            assert "q" not in params
            assert params["lat"] == 26.0745
            assert params["lon"] == 119.2965
            return _DummyResponse(
                {
                    "main": {
                        "temp": 24.2,
                        "feels_like": 25.0,
                        "humidity": 78,
                        "pressure": 1009,
                    },
                    "wind": {"speed": 2.4},
                    "weather": [{"main": "Clouds", "description": "broken clouds"}],
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(requests, "get", fake_get)

    result = module.get_current_weather(location="福州")
    assert result["location"] == "Fuzhou City, Fujian, CN"
    assert result["resolved_location"]["country"] == "CN"
    assert len(calls) == 2


def test_resolve_location_raises_on_ambiguity_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_weather_helper_module()
    monkeypatch.setenv("WEATHER_API_KEY", "dummy-key")

    def fake_get(url: str, params: Dict[str, Any], timeout: int) -> _DummyResponse:
        assert "geo/1.0/direct" in url
        return _DummyResponse(
            [
                {"name": "Springfield", "state": "Illinois", "country": "US", "lat": 39.78, "lon": -89.64},
                {"name": "Springfield", "state": "Queensland", "country": "AU", "lat": -27.67, "lon": 152.90},
            ]
        )

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(ValueError, match="Ambiguous location query"):
        module.resolve_location("Springfield")


def test_resolve_location_allow_ambiguous_returns_top_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_weather_helper_module()
    monkeypatch.setenv("WEATHER_API_KEY", "dummy-key")

    def fake_get(url: str, params: Dict[str, Any], timeout: int) -> _DummyResponse:
        assert "geo/1.0/direct" in url
        return _DummyResponse(
            [
                {"name": "Springfield", "state": "Illinois", "country": "US", "lat": 39.78, "lon": -89.64},
                {"name": "Springfield", "state": "Queensland", "country": "AU", "lat": -27.67, "lon": 152.90},
            ]
        )

    monkeypatch.setattr(requests, "get", fake_get)

    resolved = module.resolve_location("Springfield", strict_resolve=False)
    assert resolved["country"] == "US"
    assert resolved["state"] == "Illinois"


def test_district_query_is_transliterated_with_city_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_weather_helper_module()
    monkeypatch.setenv("WEATHER_API_KEY", "dummy-key")

    seen_query: Dict[str, str] = {}

    def fake_get(url: str, params: Dict[str, Any], timeout: int) -> _DummyResponse:
        assert "geo/1.0/direct" in url
        seen_query["q"] = params["q"]
        return _DummyResponse(
            [
                {
                    "name": "Cangshan",
                    "state": "Fujian",
                    "country": "CN",
                    "lat": 26.03,
                    "lon": 119.30,
                }
            ]
        )

    monkeypatch.setattr(requests, "get", fake_get)

    candidates = module.list_location_candidates("仓山区,福州")
    assert seen_query["q"] == "Cangshan,Fuzhou City,Fujian,CN"
    assert candidates[0]["name"] == "Cangshan"


def test_rewrite_legacy_args_supports_city_short_flag() -> None:
    module = _load_weather_helper_module()

    rewritten = module._rewrite_legacy_argv(["-c", "福州"])
    assert rewritten == ["current", "--location", "福州"]

    rewritten_with_command = module._rewrite_legacy_argv(["current", "-c", "福州"])
    assert rewritten_with_command == ["current", "--location", "福州"]


def test_rewrite_legacy_args_keeps_country_short_flag() -> None:
    module = _load_weather_helper_module()

    rewritten = module._rewrite_legacy_argv(["current", "-c", "CN", "--location", "Fuzhou"])
    assert rewritten == ["current", "--country", "CN", "--location", "Fuzhou"]
