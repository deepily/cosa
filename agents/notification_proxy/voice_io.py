#!/usr/bin/env python3
"""
Voice notification wrapper for the Notification Proxy Agent.

Sends fire-and-forget status notifications about the proxy's own state:
connected, answering, disconnected, errors. Uses the same REST API pattern
as cosa.agents.claude_code.cosa_interface but with its own SENDER_ID.

References:
    - src/cosa/agents/claude_code/cosa_interface.py (notify_progress pattern)
    - src/cosa/cli/notification_models.py (AsyncNotificationRequest)
"""

import requests
from typing import Optional

from cosa.agents.notification_proxy.cosa_interface import SENDER_ID
from cosa.agents.notification_proxy.config import DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT


def notify( message, priority="low", host=DEFAULT_SERVER_HOST, port=DEFAULT_SERVER_PORT, debug=False ):
    """
    Send a fire-and-forget notification about the proxy agent's status.

    Requires:
        - message is a non-empty string
        - priority is one of: low, medium, high, urgent
        - Lupin server is running at host:port

    Ensures:
        - Sends POST to /api/notify with proxy's SENDER_ID
        - Returns True on success, False on error
        - Never raises exceptions (fire-and-forget)

    Args:
        message: Status message to announce
        priority: Notification priority level
        host: Server hostname
        port: Server port
        debug: Enable debug output

    Returns:
        bool: True if notification was sent successfully
    """
    url = f"http://{host}:{port}/api/notify"

    params = {
        "message"     : message,
        "type"        : "progress",
        "priority"    : priority,
        "target_user" : "ricardo.felipe.ruiz@gmail.com",
        "sender_id"   : SENDER_ID,
    }

    try:
        response = requests.post( url, params=params, timeout=5 )
        if debug: print( f"[VoiceIO] Notification sent: {response.status_code}" )
        return response.status_code == 200
    except Exception as e:
        if debug: print( f"[VoiceIO] Notification failed: {e}" )
        return False
