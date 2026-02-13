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

import os
import requests
from typing import Optional

from cosa.agents.notification_proxy.cosa_interface import SENDER_ID
from cosa.agents.notification_proxy.config import DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT
from cosa.utils.config_loader import get_api_config, load_api_key


def notify( message, priority="low", host=DEFAULT_SERVER_HOST, port=DEFAULT_SERVER_PORT, target_user=None, debug=False ):
    """
    Send a fire-and-forget notification about the proxy agent's status.

    Requires:
        - message is a non-empty string
        - priority is one of: low, medium, high, urgent
        - Lupin server is running at host:port

    Ensures:
        - Sends POST to /api/notify with proxy's SENDER_ID
        - Authenticates with X-API-Key header
        - Returns True on success, False on error
        - Never raises exceptions (fire-and-forget)

    Args:
        message: Status message to announce
        priority: Notification priority level
        host: Server hostname
        port: Server port
        target_user: Target user email (defaults from LUPIN_TEST_INTERACTIVE_MOCK_JOBS_EMAIL env var)
        debug: Enable debug output

    Returns:
        bool: True if notification was sent successfully
    """
    if target_user is None:
        target_user = os.environ.get( "LUPIN_TEST_INTERACTIVE_MOCK_JOBS_EMAIL", "ricardo.felipe.ruiz@gmail.com" )

    url = f"http://{host}:{port}/api/notify"

    params = {
        "message"     : message,
        "type"        : "progress",
        "priority"    : priority,
        "target_user" : target_user,
        "sender_id"   : SENDER_ID,
    }

    # Load API key for authentication
    headers = {}
    try:
        env     = os.getenv( "LUPIN_ENV", "local" )
        config  = get_api_config( env )
        api_key = load_api_key( config[ "api_key_file" ] )
        headers[ "X-API-Key" ] = api_key
    except Exception as e:
        if debug: print( f"[VoiceIO] Failed to load API key: {e}" )

    try:
        response = requests.post( url, params=params, headers=headers, timeout=5 )
        if debug: print( f"[VoiceIO] Notification sent: {response.status_code}" )
        return response.status_code == 200
    except Exception as e:
        if debug: print( f"[VoiceIO] Notification failed: {e}" )
        return False
