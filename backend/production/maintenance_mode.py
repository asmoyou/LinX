"""Maintenance mode.

References:
- All requirements
- Design Section 10: Scalability and Performance
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MaintenanceWindow:
    """Maintenance window definition."""
    
    start_time: datetime
    end_time: datetime
    reason: str
    allowed_ips: List[str]
    allowed_users: List[str]


class MaintenanceMode:
    """Maintenance mode manager.
    
    Manages maintenance mode:
    - Enable/disable maintenance mode
    - Custom maintenance message
    - Whitelist IPs/users
    - Scheduled maintenance windows
    """
    
    def __init__(self, state_file: str = "/tmp/maintenance_mode.json"):
        """Initialize maintenance mode manager.
        
        Args:
            state_file: File to store maintenance state
        """
        self.state_file = Path(state_file)
        self.enabled = False
        self.message = "System is under maintenance. Please try again later."
        self.allowed_ips: List[str] = []
        self.allowed_users: List[str] = []
        self.enabled_at: Optional[datetime] = None
        self.scheduled_windows: List[MaintenanceWindow] = []
        
        # Load state from file
        self._load_state()
        
        logger.info("MaintenanceMode initialized")
    
    def enable(
        self,
        message: Optional[str] = None,
        allowed_ips: Optional[List[str]] = None,
        allowed_users: Optional[List[str]] = None,
    ):
        """Enable maintenance mode.
        
        Args:
            message: Custom maintenance message
            allowed_ips: IPs allowed during maintenance
            allowed_users: Users allowed during maintenance
        """
        self.enabled = True
        self.enabled_at = datetime.now()
        
        if message:
            self.message = message
        
        if allowed_ips:
            self.allowed_ips = allowed_ips
        
        if allowed_users:
            self.allowed_users = allowed_users
        
        self._save_state()
        
        logger.warning(
            "Maintenance mode ENABLED",
            extra={
                "maintenance_message": self.message,
                "allowed_ips": self.allowed_ips,
                "allowed_users": self.allowed_users,
            },
        )
    
    def disable(self):
        """Disable maintenance mode."""
        self.enabled = False
        self.enabled_at = None
        
        self._save_state()
        
        logger.info("Maintenance mode DISABLED")
    
    def is_enabled(self) -> bool:
        """Check if maintenance mode is enabled.
        
        Returns:
            True if enabled
        """
        # Check scheduled windows
        now = datetime.now()
        for window in self.scheduled_windows:
            if window.start_time <= now <= window.end_time:
                return True
        
        return self.enabled
    
    def is_allowed(
        self,
        ip: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Check if request is allowed during maintenance.
        
        Args:
            ip: Request IP address
            user_id: User ID
            
        Returns:
            True if allowed
        """
        if not self.is_enabled():
            return True
        
        # Check IP whitelist
        if ip and ip in self.allowed_ips:
            return True
        
        # Check user whitelist
        if user_id and user_id in self.allowed_users:
            return True
        
        return False
    
    def get_message(self) -> str:
        """Get maintenance message.
        
        Returns:
            Maintenance message
        """
        # Check if in scheduled window
        now = datetime.now()
        for window in self.scheduled_windows:
            if window.start_time <= now <= window.end_time:
                return f"{window.reason}. Expected to complete by {window.end_time.strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self.message
    
    def schedule_maintenance(
        self,
        start_time: datetime,
        end_time: datetime,
        reason: str,
        allowed_ips: Optional[List[str]] = None,
        allowed_users: Optional[List[str]] = None,
    ):
        """Schedule maintenance window.
        
        Args:
            start_time: Maintenance start time
            end_time: Maintenance end time
            reason: Maintenance reason
            allowed_ips: IPs allowed during maintenance
            allowed_users: Users allowed during maintenance
        """
        window = MaintenanceWindow(
            start_time=start_time,
            end_time=end_time,
            reason=reason,
            allowed_ips=allowed_ips or [],
            allowed_users=allowed_users or [],
        )
        
        self.scheduled_windows.append(window)
        self._save_state()
        
        logger.info(
            f"Scheduled maintenance: {start_time} to {end_time}",
            extra={"reason": reason},
        )
    
    def cancel_scheduled_maintenance(self, start_time: datetime):
        """Cancel scheduled maintenance window.
        
        Args:
            start_time: Start time of window to cancel
        """
        self.scheduled_windows = [
            w for w in self.scheduled_windows
            if w.start_time != start_time
        ]
        
        self._save_state()
        
        logger.info(f"Cancelled scheduled maintenance: {start_time}")
    
    def get_scheduled_windows(self) -> List[MaintenanceWindow]:
        """Get scheduled maintenance windows.
        
        Returns:
            List of scheduled windows
        """
        # Remove past windows
        now = datetime.now()
        self.scheduled_windows = [
            w for w in self.scheduled_windows
            if w.end_time > now
        ]
        
        return self.scheduled_windows
    
    def get_status(self) -> dict:
        """Get maintenance mode status.
        
        Returns:
            Status dictionary
        """
        return {
            "enabled": self.enabled,
            "message": self.get_message(),
            "enabled_at": (
                self.enabled_at.isoformat()
                if self.enabled_at
                else None
            ),
            "allowed_ips": self.allowed_ips,
            "allowed_users": self.allowed_users,
            "scheduled_windows": [
                {
                    "start_time": w.start_time.isoformat(),
                    "end_time": w.end_time.isoformat(),
                    "reason": w.reason,
                }
                for w in self.get_scheduled_windows()
            ],
        }
    
    def _save_state(self):
        """Save maintenance state to file."""
        state = {
            "enabled": self.enabled,
            "message": self.message,
            "allowed_ips": self.allowed_ips,
            "allowed_users": self.allowed_users,
            "enabled_at": (
                self.enabled_at.isoformat()
                if self.enabled_at
                else None
            ),
            "scheduled_windows": [
                {
                    "start_time": w.start_time.isoformat(),
                    "end_time": w.end_time.isoformat(),
                    "reason": w.reason,
                    "allowed_ips": w.allowed_ips,
                    "allowed_users": w.allowed_users,
                }
                for w in self.scheduled_windows
            ],
        }
        
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)
    
    def _load_state(self):
        """Load maintenance state from file."""
        if not self.state_file.exists():
            return
        
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
            
            self.enabled = state.get("enabled", False)
            self.message = state.get("message", self.message)
            self.allowed_ips = state.get("allowed_ips", [])
            self.allowed_users = state.get("allowed_users", [])
            
            enabled_at_str = state.get("enabled_at")
            if enabled_at_str:
                self.enabled_at = datetime.fromisoformat(enabled_at_str)
            
            # Load scheduled windows
            for window_data in state.get("scheduled_windows", []):
                window = MaintenanceWindow(
                    start_time=datetime.fromisoformat(window_data["start_time"]),
                    end_time=datetime.fromisoformat(window_data["end_time"]),
                    reason=window_data["reason"],
                    allowed_ips=window_data.get("allowed_ips", []),
                    allowed_users=window_data.get("allowed_users", []),
                )
                self.scheduled_windows.append(window)
            
            logger.info("Loaded maintenance state from file")
            
        except Exception as e:
            logger.error(f"Failed to load maintenance state: {e}")


# Global maintenance mode instance
_maintenance_mode: Optional[MaintenanceMode] = None


def get_maintenance_mode() -> MaintenanceMode:
    """Get global maintenance mode instance.
    
    Returns:
        Maintenance mode
    """
    global _maintenance_mode
    
    if _maintenance_mode is None:
        _maintenance_mode = MaintenanceMode()
    
    return _maintenance_mode
