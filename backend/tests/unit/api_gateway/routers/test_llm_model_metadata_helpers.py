"""Tests for LLM model metadata update helpers."""

from api_gateway.routers.llm import _build_updated_model_metadata


def test_build_updated_model_metadata_returns_fresh_object() -> None:
    existing = {
        "qwen3.5-35b-a3b": {
            "model_type": "chat",
            "supports_vision": False,
            "custom_fields": {"source": "detector"},
        }
    }
    incoming = {
        "model_type": "vision",
        "supports_vision": True,
        "custom_fields": {"source": "manual"},
    }

    updated = _build_updated_model_metadata(existing, "qwen3.5-35b-a3b", incoming)

    assert updated is not existing
    assert updated["qwen3.5-35b-a3b"]["supports_vision"] is True
    assert existing["qwen3.5-35b-a3b"]["supports_vision"] is False

    updated["qwen3.5-35b-a3b"]["custom_fields"]["source"] = "changed"
    assert incoming["custom_fields"]["source"] == "manual"
    assert existing["qwen3.5-35b-a3b"]["custom_fields"]["source"] == "detector"


def test_build_updated_model_metadata_handles_empty_existing() -> None:
    updated = _build_updated_model_metadata(
        None,
        "qwen3.5-35b-a3b",
        {"model_type": "vision", "supports_vision": True},
    )

    assert updated == {"qwen3.5-35b-a3b": {"model_type": "vision", "supports_vision": True}}
