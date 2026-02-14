"""Custom exceptions for the Mission Execution System."""


class MissionError(Exception):
    """Base exception for mission-related errors."""

    def __init__(self, mission_id=None, message: str = ""):
        self.mission_id = mission_id
        super().__init__(message or f"Mission error: {mission_id}")


class MissionCancelledException(MissionError):
    """Raised when a mission is cancelled during execution."""

    def __init__(self, mission_id=None):
        super().__init__(mission_id, f"Mission {mission_id} was cancelled")


class WorkspaceError(MissionError):
    """Raised when a workspace operation fails."""

    def __init__(self, mission_id=None, message: str = ""):
        super().__init__(mission_id, message or f"Workspace error for mission {mission_id}")


class AgentExecutionError(MissionError):
    """Raised when an agent fails to execute a task."""

    def __init__(self, mission_id=None, agent_id=None, message: str = ""):
        self.agent_id = agent_id
        super().__init__(
            mission_id,
            message or f"Agent {agent_id} failed in mission {mission_id}",
        )


class MissionTimeoutError(MissionError):
    """Raised when a mission exceeds its time limit."""

    def __init__(self, mission_id=None, timeout_seconds: int = 0):
        self.timeout_seconds = timeout_seconds
        super().__init__(
            mission_id,
            f"Mission {mission_id} timed out after {timeout_seconds}s",
        )
