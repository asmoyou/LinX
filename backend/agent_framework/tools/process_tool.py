"""Process Tool for managing background processes.

This module provides a LangChain tool for monitoring and controlling
background processes started with the bash tool.

References:
- Requirements: .kiro/specs/code-execution-improvement/requirements.md
- Design: .kiro/specs/code-execution-improvement/design.md
- OpenClaw: examples-of-reference/openclaw/skills/coding-agent/SKILL.md
"""

import json
import logging
from typing import Optional
from uuid import UUID

from langchain_core.tools import Tool

from agent_framework.tools.process_manager import get_process_manager

logger = logging.getLogger(__name__)


def create_process_tool(agent_id: UUID, user_id: UUID) -> Tool:
    """Create process management tool for agent.
    
    Args:
        agent_id: Agent UUID
        user_id: User UUID
    
    Returns:
        LangChain Tool for process management
    """
    process_manager = get_process_manager()
    
    def process_action(
        action: str,
        session_id: Optional[str] = None,
        data: Optional[str] = None,
        offset: int = 0,
        limit: int = 1000
    ) -> str:
        """Manage background processes.
        
        Args:
            action: Action to perform (list, poll, log, write, submit, kill)
            session_id: Session ID (required for most actions)
            data: Data to write (for write/submit actions)
            offset: Output offset in lines (for log action)
            limit: Output limit in lines (for log action, default: 1000)
        
        Returns:
            Action result
        
        Actions:
            - list: List all running/recent sessions
            - poll: Check if session is still running
            - log: Get session output (with optional offset/limit)
            - write: Send raw data to stdin
            - submit: Send data + newline (like typing and pressing Enter)
            - kill: Terminate the session
        
        Examples:
            # List all sessions
            process(action="list")
            
            # Check if process is running
            process(action="poll", session_id="abc-123")
            
            # Get process output
            process(action="log", session_id="abc-123")
            
            # Get output with pagination
            process(action="log", session_id="abc-123", offset=100, limit=50)
            
            # Send input to process
            process(action="write", session_id="abc-123", data="hello")
            
            # Submit input (with Enter)
            process(action="submit", session_id="abc-123", data="yes")
            
            # Kill process
            process(action="kill", session_id="abc-123")
        """
        try:
            if action == "list":
                sessions = process_manager.list_sessions()
                if not sessions:
                    return "No active or recent sessions"
                
                output = f"📋 **Background Sessions** ({len(sessions)} total)\n\n"
                for session in sessions:
                    status_emoji = {
                        "running": "🟢",
                        "completed": "✅",
                        "failed": "❌",
                        "killed": "🛑"
                    }.get(session["status"], "❓")
                    
                    output += f"{status_emoji} **{session['session_id'][:8]}...** - {session['status']}\n"
                    output += f"   Command: {session['command']}\n"
                    output += f"   Started: {session['started_at']}\n"
                    if session['completed_at']:
                        output += f"   Completed: {session['completed_at']}\n"
                    if session['exit_code'] is not None:
                        output += f"   Exit code: {session['exit_code']}\n"
                    output += "\n"
                
                return output
            
            elif action == "poll":
                if not session_id:
                    return "❌ Error: session_id required for poll action"
                
                status = process_manager.poll(session_id)
                
                status_messages = {
                    "running": f"🟢 Process is **running**",
                    "completed": f"✅ Process **completed** successfully",
                    "failed": f"❌ Process **failed**",
                    "killed": f"🛑 Process was **killed**",
                    "not_found": f"❓ Session **not found**: {session_id}"
                }
                
                return status_messages.get(status.value, f"Status: {status.value}")
            
            elif action == "log":
                if not session_id:
                    return "❌ Error: session_id required for log action"
                
                output = process_manager.get_output(session_id, offset, limit)
                
                if not output or output.startswith("Session not found"):
                    return f"❌ {output}"
                
                # Add header
                result = f"📄 **Process Output** (session: {session_id[:8]}...)\n"
                result += f"Showing lines {offset} to {offset + limit}\n\n"
                result += "```\n"
                result += output
                result += "\n```\n"
                
                return result
            
            elif action == "write":
                if not session_id:
                    return "❌ Error: session_id required for write action"
                if data is None:
                    return "❌ Error: data required for write action"
                
                success = process_manager.write_input(session_id, data)
                
                if success:
                    return f"✅ Data written to process stdin"
                else:
                    return f"❌ Failed to write data (process may not be running)"
            
            elif action == "submit":
                if not session_id:
                    return "❌ Error: session_id required for submit action"
                if data is None:
                    return "❌ Error: data required for submit action"
                
                success = process_manager.submit_input(session_id, data)
                
                if success:
                    return f"✅ Data submitted to process (with newline)"
                else:
                    return f"❌ Failed to submit data (process may not be running)"
            
            elif action == "kill":
                if not session_id:
                    return "❌ Error: session_id required for kill action"
                
                success = process_manager.kill(session_id)
                
                if success:
                    return f"🛑 Process terminated"
                else:
                    return f"❌ Failed to kill process (may already be stopped)"
            
            else:
                return f"❌ Unknown action: {action}\n\nValid actions: list, poll, log, write, submit, kill"
        
        except Exception as e:
            logger.error(f"Process action failed: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"
    
    return Tool(
        name="process",
        description=(
            "Manage background processes. "
            "Actions: list (show all), poll (check status), log (get output), "
            "write (send input), submit (send input + Enter), kill (terminate). "
            "Use with session_id from bash tool background execution."
        ),
        func=process_action
    )
