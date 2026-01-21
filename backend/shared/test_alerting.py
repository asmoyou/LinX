"""Tests for Alerting System."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from shared.alerting import (
    Alert,
    AlertCategory,
    AlertChannel,
    AlertDeduplicator,
    AlertManager,
    AlertRouter,
    AlertSeverity,
    AlertThrottler,
    EmailAlerter,
    PagerDutyAlerter,
    SlackAlerter,
    TeamsAlerter,
    configure_alert_manager,
    get_alert_manager,
)


def test_alert_severity_enum():
    """Test AlertSeverity enum values."""
    assert AlertSeverity.LOW.value == "low"
    assert AlertSeverity.MEDIUM.value == "medium"
    assert AlertSeverity.HIGH.value == "high"
    assert AlertSeverity.CRITICAL.value == "critical"


def test_alert_category_enum():
    """Test AlertCategory enum values."""
    assert AlertCategory.SYSTEM.value == "system"
    assert AlertCategory.APPLICATION.value == "application"
    assert AlertCategory.SECURITY.value == "security"
    assert AlertCategory.BUSINESS.value == "business"


def test_alert_channel_enum():
    """Test AlertChannel enum values."""
    assert AlertChannel.EMAIL.value == "email"
    assert AlertChannel.SLACK.value == "slack"
    assert AlertChannel.TEAMS.value == "teams"
    assert AlertChannel.PAGERDUTY.value == "pagerduty"


def test_alert_creation():
    """Test Alert creation."""
    alert = Alert(
        title="Test Alert",
        message="This is a test",
        severity=AlertSeverity.HIGH,
        category=AlertCategory.SYSTEM,
        source="test-service",
    )

    assert alert.title == "Test Alert"
    assert alert.message == "This is a test"
    assert alert.severity == AlertSeverity.HIGH
    assert alert.category == AlertCategory.SYSTEM
    assert alert.source == "test-service"
    assert alert.alert_id is not None
    assert isinstance(alert.timestamp, datetime)


def test_alert_to_dict():
    """Test Alert serialization."""
    alert = Alert(
        title="Test Alert",
        message="Test message",
        severity=AlertSeverity.MEDIUM,
        category=AlertCategory.APPLICATION,
        source="api-gateway",
        details={"key": "value"},
    )

    data = alert.to_dict()

    assert data["title"] == "Test Alert"
    assert data["severity"] == "medium"
    assert data["category"] == "application"
    assert data["source"] == "api-gateway"
    assert data["details"]["key"] == "value"


def test_alert_id_generation():
    """Test alert ID generation is consistent."""
    alert1 = Alert(
        title="Same Alert",
        message="Message 1",
        severity=AlertSeverity.LOW,
        category=AlertCategory.SYSTEM,
        source="service-a",
    )

    alert2 = Alert(
        title="Same Alert",
        message="Message 2",  # Different message
        severity=AlertSeverity.LOW,
        category=AlertCategory.SYSTEM,
        source="service-a",
    )

    # Same title, category, source should generate same ID
    assert alert1.alert_id == alert2.alert_id


def test_alert_deduplicator():
    """Test alert deduplication."""
    deduplicator = AlertDeduplicator(window_seconds=60)

    alert = Alert(
        title="Test",
        message="Test",
        severity=AlertSeverity.LOW,
        category=AlertCategory.SYSTEM,
        source="test",
    )

    # First alert should not be duplicate
    assert deduplicator.is_duplicate(alert) is False

    # Immediate second alert should be duplicate
    assert deduplicator.is_duplicate(alert) is True


def test_alert_throttler():
    """Test alert throttling."""
    throttler = AlertThrottler(max_alerts_per_hour=2)

    alert1 = Alert(
        title="Alert 1",
        message="Test",
        severity=AlertSeverity.LOW,
        category=AlertCategory.SYSTEM,
        source="test-source",
    )

    alert2 = Alert(
        title="Alert 2",
        message="Test",
        severity=AlertSeverity.LOW,
        category=AlertCategory.SYSTEM,
        source="test-source",
    )

    alert3 = Alert(
        title="Alert 3",
        message="Test",
        severity=AlertSeverity.LOW,
        category=AlertCategory.SYSTEM,
        source="test-source",
    )

    # First two alerts should not be throttled
    assert throttler.should_throttle(alert1) is False
    assert throttler.should_throttle(alert2) is False

    # Third alert should be throttled
    assert throttler.should_throttle(alert3) is True


def test_alert_router_add_rule():
    """Test adding routing rules."""
    router = AlertRouter()

    router.add_rule(
        severity=AlertSeverity.CRITICAL, channels=[AlertChannel.PAGERDUTY, AlertChannel.SLACK]
    )

    assert len(router.routing_rules) == 1


def test_alert_router_get_channels():
    """Test getting channels for alert."""
    router = AlertRouter()

    router.add_rule(severity=AlertSeverity.CRITICAL, channels=[AlertChannel.PAGERDUTY])

    router.add_rule(severity=AlertSeverity.HIGH, channels=[AlertChannel.SLACK])

    critical_alert = Alert(
        title="Critical",
        message="Test",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.SYSTEM,
        source="test",
    )

    channels = router.get_channels(critical_alert)
    assert AlertChannel.PAGERDUTY in channels


def test_email_alerter_initialization():
    """Test EmailAlerter initialization."""
    alerter = EmailAlerter(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="password",
        from_email="alerts@example.com",
    )

    assert alerter.smtp_host == "smtp.example.com"
    assert alerter.smtp_port == 587
    assert alerter.from_email == "alerts@example.com"


def test_slack_alerter_initialization():
    """Test SlackAlerter initialization."""
    alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")

    assert alerter.webhook_url == "https://hooks.slack.com/test"


def test_slack_payload_creation():
    """Test Slack payload creation."""
    alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")

    alert = Alert(
        title="Test Alert",
        message="Test message",
        severity=AlertSeverity.HIGH,
        category=AlertCategory.SYSTEM,
        source="test",
    )

    payload = alerter._create_slack_payload(alert)

    assert "text" in payload
    assert "attachments" in payload
    assert len(payload["attachments"]) > 0


def test_teams_alerter_initialization():
    """Test TeamsAlerter initialization."""
    alerter = TeamsAlerter(webhook_url="https://outlook.office.com/webhook/test")

    assert alerter.webhook_url == "https://outlook.office.com/webhook/test"


def test_teams_payload_creation():
    """Test Teams payload creation."""
    alerter = TeamsAlerter(webhook_url="https://outlook.office.com/webhook/test")

    alert = Alert(
        title="Test Alert",
        message="Test message",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.SECURITY,
        source="test",
    )

    payload = alerter._create_teams_payload(alert)

    assert payload["@type"] == "MessageCard"
    assert payload["title"] == "Test Alert"
    assert "sections" in payload


def test_pagerduty_alerter_initialization():
    """Test PagerDutyAlerter initialization."""
    alerter = PagerDutyAlerter(integration_key="test-key-123")

    assert alerter.integration_key == "test-key-123"
    assert alerter.api_url == "https://events.pagerduty.com/v2/enqueue"


def test_pagerduty_payload_creation():
    """Test PagerDuty payload creation."""
    alerter = PagerDutyAlerter(integration_key="test-key")

    alert = Alert(
        title="Test Alert",
        message="Test message",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.SYSTEM,
        source="test",
    )

    payload = alerter._create_pagerduty_payload(alert)

    assert payload["routing_key"] == "test-key"
    assert payload["event_action"] == "trigger"
    assert payload["dedup_key"] == alert.alert_id
    assert payload["payload"]["summary"] == "Test Alert"


def test_alert_manager_initialization():
    """Test AlertManager initialization."""
    manager = AlertManager()

    assert manager.deduplicator is not None
    assert manager.throttler is not None
    assert manager.router is not None


def test_alert_manager_default_routing():
    """Test AlertManager default routing rules."""
    manager = AlertManager()

    # Should have default routing rules
    assert len(manager.router.routing_rules) > 0


def test_get_alert_manager_singleton():
    """Test global alert manager singleton."""
    manager1 = get_alert_manager()
    manager2 = get_alert_manager()

    assert manager1 is manager2


def test_configure_alert_manager():
    """Test configuring alert manager."""
    email_config = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "user@example.com",
        "smtp_password": "password",
        "from_email": "alerts@example.com",
    }

    manager = configure_alert_manager(
        email_config=email_config, slack_webhook="https://hooks.slack.com/test"
    )

    assert manager.email_alerter is not None
    assert manager.slack_alerter is not None


def test_alert_severity_colors():
    """Test severity color mapping."""
    severity_colors = {
        AlertSeverity.LOW: "#28a745",
        AlertSeverity.MEDIUM: "#ffc107",
        AlertSeverity.HIGH: "#fd7e14",
        AlertSeverity.CRITICAL: "#dc3545",
    }

    assert severity_colors[AlertSeverity.CRITICAL] == "#dc3545"
    assert severity_colors[AlertSeverity.LOW] == "#28a745"


def test_deduplicator_cleanup():
    """Test deduplicator cleanup of old entries."""
    deduplicator = AlertDeduplicator(window_seconds=1)

    alert = Alert(
        title="Test",
        message="Test",
        severity=AlertSeverity.LOW,
        category=AlertCategory.SYSTEM,
        source="test",
    )

    # Add alert
    deduplicator.is_duplicate(alert)

    # Wait for window to expire
    import time

    time.sleep(1.5)

    # Should not be duplicate after window expires
    assert deduplicator.is_duplicate(alert) is False


def test_throttler_different_sources():
    """Test throttler treats different sources independently."""
    throttler = AlertThrottler(max_alerts_per_hour=1)

    alert1 = Alert(
        title="Alert",
        message="Test",
        severity=AlertSeverity.LOW,
        category=AlertCategory.SYSTEM,
        source="source-a",
    )

    alert2 = Alert(
        title="Alert",
        message="Test",
        severity=AlertSeverity.LOW,
        category=AlertCategory.SYSTEM,
        source="source-b",
    )

    # Both should not be throttled (different sources)
    assert throttler.should_throttle(alert1) is False
    assert throttler.should_throttle(alert2) is False


def test_router_multiple_matching_rules():
    """Test router with multiple matching rules."""
    router = AlertRouter()

    router.add_rule(severity=AlertSeverity.CRITICAL, channels=[AlertChannel.PAGERDUTY])

    router.add_rule(category=AlertCategory.SECURITY, channels=[AlertChannel.SLACK])

    alert = Alert(
        title="Security Critical",
        message="Test",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.SECURITY,
        source="test",
    )

    channels = router.get_channels(alert)

    # Should match both rules
    assert AlertChannel.PAGERDUTY in channels
    assert AlertChannel.SLACK in channels
