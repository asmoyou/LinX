"""Alerting System for Monitoring Events.

Implements multi-channel alerting with routing, deduplication, and throttling.

References:
- Requirements 11: Monitoring and Observability
- Design Section 11.3: Alerting
- Task 5.6: Alerting
"""

import hashlib
import json
import logging
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import requests

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertCategory(Enum):
    """Alert categories."""

    SYSTEM = "system"
    APPLICATION = "application"
    SECURITY = "security"
    BUSINESS = "business"


class AlertChannel(Enum):
    """Alert delivery channels."""

    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    PAGERDUTY = "pagerduty"


class Alert:
    """Represents an alert."""

    def __init__(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        category: AlertCategory,
        source: str,
        details: Optional[Dict[str, Any]] = None,
        alert_id: Optional[str] = None,
    ):
        """Initialize alert.

        Args:
            title: Alert title
            message: Alert message
            severity: Alert severity
            category: Alert category
            source: Alert source (component/service)
            details: Additional details
            alert_id: Optional alert ID (generated if not provided)
        """
        self.title = title
        self.message = message
        self.severity = severity
        self.category = category
        self.source = source
        self.details = details or {}
        self.timestamp = datetime.utcnow()

        # Generate alert ID if not provided
        if alert_id:
            self.alert_id = alert_id
        else:
            self.alert_id = self._generate_alert_id()

    def _generate_alert_id(self) -> str:
        """Generate unique alert ID based on content.

        Returns:
            Alert ID hash
        """
        content = f"{self.title}:{self.source}:{self.category.value}"
        return hashlib.md5(content.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "source": self.source,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class AlertDeduplicator:
    """Deduplicates alerts to prevent spam."""

    def __init__(self, window_seconds: int = 300):
        """Initialize deduplicator.

        Args:
            window_seconds: Deduplication window in seconds
        """
        self.window_seconds = window_seconds
        self.seen_alerts: Dict[str, datetime] = {}

    def is_duplicate(self, alert: Alert) -> bool:
        """Check if alert is a duplicate.

        Args:
            alert: Alert to check

        Returns:
            True if duplicate within window
        """
        now = datetime.utcnow()
        alert_id = alert.alert_id

        # Clean up old entries
        self._cleanup_old_entries(now)

        # Check if we've seen this alert recently
        if alert_id in self.seen_alerts:
            last_seen = self.seen_alerts[alert_id]
            if (now - last_seen).total_seconds() < self.window_seconds:
                logger.debug(f"Alert {alert_id} is duplicate within {self.window_seconds}s window")
                return True

        # Record this alert
        self.seen_alerts[alert_id] = now
        return False

    def _cleanup_old_entries(self, now: datetime) -> None:
        """Remove old entries from seen alerts.

        Args:
            now: Current timestamp
        """
        cutoff = now - timedelta(seconds=self.window_seconds * 2)
        self.seen_alerts = {
            alert_id: timestamp
            for alert_id, timestamp in self.seen_alerts.items()
            if timestamp > cutoff
        }


class AlertThrottler:
    """Throttles alerts to prevent flooding."""

    def __init__(self, max_alerts_per_hour: int = 10):
        """Initialize throttler.

        Args:
            max_alerts_per_hour: Maximum alerts per hour per source
        """
        self.max_alerts_per_hour = max_alerts_per_hour
        self.alert_counts: Dict[str, List[datetime]] = {}

    def should_throttle(self, alert: Alert) -> bool:
        """Check if alert should be throttled.

        Args:
            alert: Alert to check

        Returns:
            True if should throttle
        """
        now = datetime.utcnow()
        source = alert.source

        # Initialize if first alert from source
        if source not in self.alert_counts:
            self.alert_counts[source] = []

        # Clean up old timestamps
        cutoff = now - timedelta(hours=1)
        self.alert_counts[source] = [ts for ts in self.alert_counts[source] if ts > cutoff]

        # Check if over limit
        if len(self.alert_counts[source]) >= self.max_alerts_per_hour:
            logger.warning(
                f"Throttling alert from {source}: "
                f"{len(self.alert_counts[source])} alerts in last hour"
            )
            return True

        # Record this alert
        self.alert_counts[source].append(now)
        return False


class EmailAlerter:
    """Sends alerts via email."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_email: str,
        use_tls: bool = True,
    ):
        """Initialize email alerter.

        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            smtp_user: SMTP username
            smtp_password: SMTP password
            from_email: From email address
            use_tls: Whether to use TLS
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.use_tls = use_tls

    def send_alert(self, alert: Alert, recipients: List[str]) -> bool:
        """Send alert via email.

        Args:
            alert: Alert to send
            recipients: List of recipient email addresses

        Returns:
            True if sent successfully
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{alert.severity.value.upper()}] {alert.title}"
            msg["From"] = self.from_email
            msg["To"] = ", ".join(recipients)

            # Create email body
            text_body = self._create_text_body(alert)
            html_body = self._create_html_body(alert)

            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(
                f"Email alert sent: {alert.title}",
                extra={"alert_id": alert.alert_id, "recipients": recipients},
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send email alert: {e}",
                extra={"alert_id": alert.alert_id},
                exc_info=True,
            )
            return False

    def _create_text_body(self, alert: Alert) -> str:
        """Create plain text email body.

        Args:
            alert: Alert

        Returns:
            Plain text body
        """
        return f"""
Alert: {alert.title}

Severity: {alert.severity.value.upper()}
Category: {alert.category.value}
Source: {alert.source}
Time: {alert.timestamp.isoformat()}

Message:
{alert.message}

Details:
{json.dumps(alert.details, indent=2)}
"""

    def _create_html_body(self, alert: Alert) -> str:
        """Create HTML email body.

        Args:
            alert: Alert

        Returns:
            HTML body
        """
        severity_colors = {
            AlertSeverity.LOW: "#28a745",
            AlertSeverity.MEDIUM: "#ffc107",
            AlertSeverity.HIGH: "#fd7e14",
            AlertSeverity.CRITICAL: "#dc3545",
        }

        color = severity_colors.get(alert.severity, "#6c757d")

        return f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <div style="border-left: 4px solid {color}; padding-left: 20px;">
        <h2 style="color: {color};">{alert.title}</h2>
        <p><strong>Severity:</strong> <span style="color: {color};">{alert.severity.value.upper()}</span></p>
        <p><strong>Category:</strong> {alert.category.value}</p>
        <p><strong>Source:</strong> {alert.source}</p>
        <p><strong>Time:</strong> {alert.timestamp.isoformat()}</p>
        <hr>
        <h3>Message</h3>
        <p>{alert.message}</p>
        <h3>Details</h3>
        <pre style="background-color: #f5f5f5; padding: 10px; border-radius: 4px;">
{json.dumps(alert.details, indent=2)}
        </pre>
    </div>
</body>
</html>
"""


class SlackAlerter:
    """Sends alerts to Slack."""

    def __init__(self, webhook_url: str):
        """Initialize Slack alerter.

        Args:
            webhook_url: Slack webhook URL
        """
        self.webhook_url = webhook_url

    def send_alert(self, alert: Alert) -> bool:
        """Send alert to Slack.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully
        """
        try:
            # Create Slack message
            payload = self._create_slack_payload(alert)

            # Send to Slack
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()

            logger.info(f"Slack alert sent: {alert.title}", extra={"alert_id": alert.alert_id})
            return True

        except Exception as e:
            logger.error(
                f"Failed to send Slack alert: {e}",
                extra={"alert_id": alert.alert_id},
                exc_info=True,
            )
            return False

    def _create_slack_payload(self, alert: Alert) -> Dict[str, Any]:
        """Create Slack message payload.

        Args:
            alert: Alert

        Returns:
            Slack payload dictionary
        """
        severity_colors = {
            AlertSeverity.LOW: "good",
            AlertSeverity.MEDIUM: "warning",
            AlertSeverity.HIGH: "warning",
            AlertSeverity.CRITICAL: "danger",
        }

        severity_emojis = {
            AlertSeverity.LOW: ":information_source:",
            AlertSeverity.MEDIUM: ":warning:",
            AlertSeverity.HIGH: ":exclamation:",
            AlertSeverity.CRITICAL: ":rotating_light:",
        }

        color = severity_colors.get(alert.severity, "#6c757d")
        emoji = severity_emojis.get(alert.severity, ":bell:")

        return {
            "text": f"{emoji} *{alert.title}*",
            "attachments": [
                {
                    "color": color,
                    "fields": [
                        {"title": "Severity", "value": alert.severity.value.upper(), "short": True},
                        {"title": "Category", "value": alert.category.value, "short": True},
                        {"title": "Source", "value": alert.source, "short": True},
                        {"title": "Time", "value": alert.timestamp.isoformat(), "short": True},
                        {"title": "Message", "value": alert.message, "short": False},
                    ],
                    "footer": "Digital Workforce Platform",
                    "ts": int(alert.timestamp.timestamp()),
                }
            ],
        }


class TeamsAlerter:
    """Sends alerts to Microsoft Teams."""

    def __init__(self, webhook_url: str):
        """Initialize Teams alerter.

        Args:
            webhook_url: Teams webhook URL
        """
        self.webhook_url = webhook_url

    def send_alert(self, alert: Alert) -> bool:
        """Send alert to Teams.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully
        """
        try:
            # Create Teams message
            payload = self._create_teams_payload(alert)

            # Send to Teams
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()

            logger.info(f"Teams alert sent: {alert.title}", extra={"alert_id": alert.alert_id})
            return True

        except Exception as e:
            logger.error(
                f"Failed to send Teams alert: {e}",
                extra={"alert_id": alert.alert_id},
                exc_info=True,
            )
            return False

    def _create_teams_payload(self, alert: Alert) -> Dict[str, Any]:
        """Create Teams message payload.

        Args:
            alert: Alert

        Returns:
            Teams payload dictionary
        """
        severity_colors = {
            AlertSeverity.LOW: "0078D4",
            AlertSeverity.MEDIUM: "FFC107",
            AlertSeverity.HIGH: "FD7E14",
            AlertSeverity.CRITICAL: "DC3545",
        }

        color = severity_colors.get(alert.severity, "6C757D")

        return {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": alert.title,
            "themeColor": color,
            "title": alert.title,
            "sections": [
                {
                    "activityTitle": f"**{alert.severity.value.upper()}** Alert",
                    "activitySubtitle": alert.timestamp.isoformat(),
                    "facts": [
                        {"name": "Category", "value": alert.category.value},
                        {"name": "Source", "value": alert.source},
                        {"name": "Severity", "value": alert.severity.value.upper()},
                    ],
                    "text": alert.message,
                }
            ],
        }


class PagerDutyAlerter:
    """Sends alerts to PagerDuty."""

    def __init__(self, integration_key: str):
        """Initialize PagerDuty alerter.

        Args:
            integration_key: PagerDuty integration key
        """
        self.integration_key = integration_key
        self.api_url = "https://events.pagerduty.com/v2/enqueue"

    def send_alert(self, alert: Alert) -> bool:
        """Send alert to PagerDuty.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully
        """
        try:
            # Create PagerDuty event
            payload = self._create_pagerduty_payload(alert)

            # Send to PagerDuty
            response = requests.post(self.api_url, json=payload, timeout=10)
            response.raise_for_status()

            logger.info(f"PagerDuty alert sent: {alert.title}", extra={"alert_id": alert.alert_id})
            return True

        except Exception as e:
            logger.error(
                f"Failed to send PagerDuty alert: {e}",
                extra={"alert_id": alert.alert_id},
                exc_info=True,
            )
            return False

    def _create_pagerduty_payload(self, alert: Alert) -> Dict[str, Any]:
        """Create PagerDuty event payload.

        Args:
            alert: Alert

        Returns:
            PagerDuty payload dictionary
        """
        severity_map = {
            AlertSeverity.LOW: "info",
            AlertSeverity.MEDIUM: "warning",
            AlertSeverity.HIGH: "error",
            AlertSeverity.CRITICAL: "critical",
        }

        return {
            "routing_key": self.integration_key,
            "event_action": "trigger",
            "dedup_key": alert.alert_id,
            "payload": {
                "summary": alert.title,
                "source": alert.source,
                "severity": severity_map.get(alert.severity, "error"),
                "timestamp": alert.timestamp.isoformat(),
                "component": alert.category.value,
                "custom_details": {"message": alert.message, **alert.details},
            },
        }


class AlertRouter:
    """Routes alerts to appropriate channels based on rules."""

    def __init__(self):
        """Initialize alert router."""
        self.routing_rules: List[Dict[str, Any]] = []

    def add_rule(
        self,
        severity: Optional[AlertSeverity] = None,
        category: Optional[AlertCategory] = None,
        channels: Optional[List[AlertChannel]] = None,
    ) -> None:
        """Add routing rule.

        Args:
            severity: Alert severity to match (None = any)
            category: Alert category to match (None = any)
            channels: Channels to route to
        """
        self.routing_rules.append(
            {"severity": severity, "category": category, "channels": channels or []}
        )

    def get_channels(self, alert: Alert) -> List[AlertChannel]:
        """Get channels for alert based on routing rules.

        Args:
            alert: Alert to route

        Returns:
            List of channels to send to
        """
        channels: Set[AlertChannel] = set()

        for rule in self.routing_rules:
            # Check if rule matches
            if rule["severity"] and rule["severity"] != alert.severity:
                continue
            if rule["category"] and rule["category"] != alert.category:
                continue

            # Add channels from matching rule
            channels.update(rule["channels"])

        return list(channels)


class AlertManager:
    """Central alert management system."""

    def __init__(
        self,
        email_alerter: Optional[EmailAlerter] = None,
        slack_alerter: Optional[SlackAlerter] = None,
        teams_alerter: Optional[TeamsAlerter] = None,
        pagerduty_alerter: Optional[PagerDutyAlerter] = None,
        deduplication_window: int = 300,
        max_alerts_per_hour: int = 10,
    ):
        """Initialize alert manager.

        Args:
            email_alerter: Email alerter instance
            slack_alerter: Slack alerter instance
            teams_alerter: Teams alerter instance
            pagerduty_alerter: PagerDuty alerter instance
            deduplication_window: Deduplication window in seconds
            max_alerts_per_hour: Maximum alerts per hour per source
        """
        self.email_alerter = email_alerter
        self.slack_alerter = slack_alerter
        self.teams_alerter = teams_alerter
        self.pagerduty_alerter = pagerduty_alerter

        self.deduplicator = AlertDeduplicator(deduplication_window)
        self.throttler = AlertThrottler(max_alerts_per_hour)
        self.router = AlertRouter()

        # Setup default routing rules
        self._setup_default_routing()

        logger.info("AlertManager initialized")

    def _setup_default_routing(self) -> None:
        """Setup default routing rules."""
        # Critical alerts go to PagerDuty and Slack
        self.router.add_rule(
            severity=AlertSeverity.CRITICAL, channels=[AlertChannel.PAGERDUTY, AlertChannel.SLACK]
        )

        # High severity to Slack and email
        self.router.add_rule(
            severity=AlertSeverity.HIGH, channels=[AlertChannel.SLACK, AlertChannel.EMAIL]
        )

        # Medium severity to email
        self.router.add_rule(severity=AlertSeverity.MEDIUM, channels=[AlertChannel.EMAIL])

        # Low severity to email only
        self.router.add_rule(severity=AlertSeverity.LOW, channels=[AlertChannel.EMAIL])

    def send_alert(self, alert: Alert, email_recipients: Optional[List[str]] = None) -> bool:
        """Send alert through appropriate channels.

        Args:
            alert: Alert to send
            email_recipients: Email recipients (if using email channel)

        Returns:
            True if sent successfully to at least one channel
        """
        # Check deduplication
        if self.deduplicator.is_duplicate(alert):
            logger.debug(f"Alert {alert.alert_id} deduplicated")
            return False

        # Check throttling
        if self.throttler.should_throttle(alert):
            logger.warning(f"Alert {alert.alert_id} throttled")
            return False

        # Get channels to send to
        channels = self.router.get_channels(alert)

        if not channels:
            logger.warning(f"No channels configured for alert {alert.alert_id}")
            return False

        # Send to each channel
        success = False
        for channel in channels:
            if channel == AlertChannel.EMAIL and self.email_alerter and email_recipients:
                if self.email_alerter.send_alert(alert, email_recipients):
                    success = True

            elif channel == AlertChannel.SLACK and self.slack_alerter:
                if self.slack_alerter.send_alert(alert):
                    success = True

            elif channel == AlertChannel.TEAMS and self.teams_alerter:
                if self.teams_alerter.send_alert(alert):
                    success = True

            elif channel == AlertChannel.PAGERDUTY and self.pagerduty_alerter:
                if self.pagerduty_alerter.send_alert(alert):
                    success = True

        return success


# Global alert manager instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get global alert manager instance.

    Returns:
        AlertManager instance
    """
    global _alert_manager

    if _alert_manager is None:
        _alert_manager = AlertManager()

    return _alert_manager


def configure_alert_manager(
    email_config: Optional[Dict[str, Any]] = None,
    slack_webhook: Optional[str] = None,
    teams_webhook: Optional[str] = None,
    pagerduty_key: Optional[str] = None,
) -> AlertManager:
    """Configure global alert manager.

    Args:
        email_config: Email configuration dictionary
        slack_webhook: Slack webhook URL
        teams_webhook: Teams webhook URL
        pagerduty_key: PagerDuty integration key

    Returns:
        Configured AlertManager instance
    """
    global _alert_manager

    email_alerter = None
    if email_config:
        email_alerter = EmailAlerter(**email_config)

    slack_alerter = None
    if slack_webhook:
        slack_alerter = SlackAlerter(slack_webhook)

    teams_alerter = None
    if teams_webhook:
        teams_alerter = TeamsAlerter(teams_webhook)

    pagerduty_alerter = None
    if pagerduty_key:
        pagerduty_alerter = PagerDutyAlerter(pagerduty_key)

    _alert_manager = AlertManager(
        email_alerter=email_alerter,
        slack_alerter=slack_alerter,
        teams_alerter=teams_alerter,
        pagerduty_alerter=pagerduty_alerter,
    )

    return _alert_manager
