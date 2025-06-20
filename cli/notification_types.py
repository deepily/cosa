"""
Notification types and priority constants for Claude Code notifications

This module defines the standard notification types and priority levels
used by the Claude Code notification system.
"""

from enum import Enum
from typing import List


class NotificationType(Enum):
    """Standard notification types for Claude Code communications"""
    
    TASK = "task"           # Task completion (success/failure)
    PROGRESS = "progress"   # Progress updates during long operations  
    ALERT = "alert"         # Warnings and important messages
    CUSTOM = "custom"       # User-defined messages
    
    @classmethod
    def values(cls) -> List[str]:
        """Get list of all notification type values"""
        return [item.value for item in cls]


class NotificationPriority(Enum):
    """Priority levels for notifications"""
    
    LOW = "low"         # Background information
    MEDIUM = "medium"   # Normal notifications (default)
    HIGH = "high"       # Important messages
    URGENT = "urgent"   # Critical alerts
    
    @classmethod  
    def values(cls) -> List[str]:
        """Get list of all priority values"""
        return [item.value for item in cls]


# Default values
DEFAULT_TYPE = NotificationType.CUSTOM.value
DEFAULT_PRIORITY = NotificationPriority.MEDIUM.value

# API Configuration
DEFAULT_API_KEY = "claude_code_simple_key"
DEFAULT_SERVER_URL = "http://localhost:7999"

# Environment variable names
ENV_CLI_PATH = "COSA_CLI_PATH"
ENV_SERVER_URL = "COSA_APP_SERVER_URL"