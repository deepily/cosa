#!/usr/bin/env python3
"""
COSA Voice Interface for Claude Code Agent.

This module provides async wrappers for the cosa-voice notification tools,
enabling ClaudeCodeJob to send notifications to the UI with proper job_id
routing for job card display.

Uses asyncio.to_thread() to run blocking calls without blocking the event loop.
"""

import asyncio
import logging
import os
from typing import Optional

# Import from cosa.cli (the notification library)
from cosa.cli.notification_models import (
    NotificationRequest,
    AsyncNotificationRequest,
    NotificationResponse,
    AsyncNotificationResponse,
    NotificationType,
    NotificationPriority,
    ResponseType
)
from cosa.cli.notify_user_sync import notify_user_sync as _notify_user_sync
from cosa.cli.notify_user_async import notify_user_async as _notify_user_async

logger = logging.getLogger( __name__ )


# =============================================================================
# Sender Identity Configuration
# =============================================================================

def _get_sender_id() -> str:
    """
    Get sender_id for Claude Code job notifications.

    Ensures:
        - Returns sender_id in format: claude.code.job@{project}.deepily.ai
        - Project is detected from current working directory
        - Handles nested directory structures correctly

    Returns:
        str: Sender ID for notification identity
    """
    # Project detection - check more specific paths FIRST
    cwd = os.getcwd()

    if "/cosa" in cwd.lower() and "/lupin" not in cwd.lower():
        project = "cosa"
    elif "/planning-is-prompting" in cwd.lower():
        project = "plan"
    elif "/lupin" in cwd.lower():
        project = "lupin"
    else:
        project = os.path.basename( cwd ).lower()

    return f"claude.code.job@{project}.deepily.ai"


# Cache sender_id at module load
SENDER_ID = _get_sender_id()


# =============================================================================
# Primary Interface Functions
# =============================================================================

async def notify_progress(
    message: str,
    priority: str = "medium",
    abstract: Optional[ str ] = None,
    session_name: Optional[ str ] = None,
    job_id: Optional[ str ] = None,
    queue_name: Optional[ str ] = None
) -> None:
    """
    Send fire-and-forget progress notification.

    Non-blocking - runs in thread pool to avoid blocking event loop.

    Requires:
        - message is a non-empty string
        - priority is "low", "medium", "high", or "urgent"

    Ensures:
        - Notification is sent asynchronously
        - Returns immediately (fire-and-forget)
        - Logs warning on failure (doesn't raise)

    Args:
        message: Progress message to announce
        priority: "low", "medium", "high", or "urgent"
        abstract: Optional supplementary context (markdown, URLs, details)
        session_name: Optional human-readable session name for UI display
        job_id: Agentic job ID for routing to job cards (e.g., "cc-a1b2c3d4")
        queue_name: Optional queue where job is running (run/todo/done)
    """
    try:
        request = AsyncNotificationRequest(
            message           = message,
            notification_type = NotificationType.PROGRESS,
            priority          = NotificationPriority( priority ),
            sender_id         = SENDER_ID,
            abstract          = abstract,
            session_name      = session_name,
            job_id            = job_id,
            queue_name        = queue_name,
        )

        # Run blocking call in thread pool
        await asyncio.to_thread( _notify_user_async, request )

    except Exception as e:
        logger.warning( f"Failed to send progress notification: {e}" )


async def ask_confirmation(
    question: str,
    default: str = "no",
    timeout: int = 60,
    abstract: Optional[ str ] = None,
    job_id: Optional[ str ] = None
) -> bool:
    """
    Ask a yes/no question and return boolean result.

    Requires:
        - question is a non-empty string
        - default is "yes" or "no"
        - timeout is positive integer (1-600)

    Ensures:
        - Returns True if user said yes
        - Returns False otherwise
        - Returns default value on timeout/offline

    Args:
        question: The yes/no question to ask
        default: Default answer if timeout ("yes" or "no")
        timeout: Seconds to wait for response
        abstract: Optional supplementary context
        job_id: Agentic job ID for routing to job cards

    Returns:
        bool: True if user said yes, False otherwise
    """
    try:
        request = NotificationRequest(
            message           = question,
            response_type     = ResponseType.YES_NO,
            notification_type = NotificationType.CUSTOM,
            priority          = NotificationPriority.MEDIUM,
            timeout_seconds   = timeout,
            response_default  = default,
            sender_id         = SENDER_ID,
            abstract          = abstract,
            job_id            = job_id,
        )

        response: NotificationResponse = await asyncio.to_thread( _notify_user_sync, request )

        if response.exit_code == 0 and response.response_value:
            return response.response_value.lower().strip() == "yes"

        return default == "yes"

    except Exception as e:
        logger.warning( f"ask_confirmation failed: {e}" )
        return default == "yes"


def quick_smoke_test():
    """Quick smoke test for claude_code cosa_interface module."""
    import cosa.utils.util as cu

    cu.print_banner( "Claude Code COSA Interface Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import validation
        print( "Testing imports..." )
        assert NotificationRequest is not None
        assert NotificationType is not None
        assert ResponseType is not None
        print( "  Import valid" )

        # Test 2: Sender ID format
        print( "Testing sender ID format..." )
        assert "claude.code.job@" in SENDER_ID
        assert ".deepily.ai" in SENDER_ID
        print( f"  Sender ID: {SENDER_ID}" )

        # Test 3: Async functions exist
        print( "Testing async function signatures..." )
        import inspect
        assert inspect.iscoroutinefunction( notify_progress )
        assert inspect.iscoroutinefunction( ask_confirmation )
        print( "  Async functions have correct signatures" )

        # Test 4: notify_progress signature includes job_id
        print( "Testing notify_progress has job_id parameter..." )
        sig = inspect.signature( notify_progress )
        assert "job_id" in sig.parameters
        print( "  notify_progress supports job_id parameter" )

        print( "\n  Claude Code COSA Interface smoke test completed successfully" )

    except Exception as e:
        print( f"\n  Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
