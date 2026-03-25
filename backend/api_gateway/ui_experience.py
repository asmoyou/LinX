"""Shared UI experience models for API Gateway routes."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from shared.platform_settings import DEFAULT_UI_EXPERIENCE_SETTINGS, merge_ui_experience_settings

MotionPreference = Literal["auto", "full", "reduced", "off"]


class UiExperienceSettings(BaseModel):
    """Platform-wide UI motion settings."""

    default_motion_preference: MotionPreference = "auto"
    emergency_disable_motion: bool = False
    telemetry_sample_rate: float = Field(default=0.2, ge=0.0, le=1.0)

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None = None) -> "UiExperienceSettings":
        return cls(**merge_ui_experience_settings(value or DEFAULT_UI_EXPERIENCE_SETTINGS))
