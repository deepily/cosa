#!/usr/bin/env python3
"""
COSA Voice Interface Integration Layer for Deep Research.

This module provides async wrappers for the cosa-voice notification tools,
bridging the async orchestrator with the blocking notification API.

Uses AgentNotificationDispatcher for shared async dispatch logic.
Module-level SENDER_ID and SESSION_NAME remain mutable for runtime
configuration by job.py and cli.py callers.
"""

import logging
from typing import Optional

# Import from cosa.cli for backward-compatible re-exports
from cosa.cli.notification_models import (
    NotificationRequest,
    AsyncNotificationRequest,
    NotificationResponse,
    AsyncNotificationResponse,
    NotificationType,
    NotificationPriority,
    ResponseType
)
from cosa.utils.notification_utils import format_questions_for_tts, convert_questions_for_api

# Shared utilities
from cosa.agents.utils.sender_id import build_sender_id
from cosa.agents.utils.feedback_analysis import (
    is_approval, is_rejection, extract_feedback_intent,
    APPROVAL_SIGNALS, REJECTION_SIGNALS
)
from cosa.agents.utils.agent_notification_dispatcher import AgentNotificationDispatcher

logger = logging.getLogger( __name__ )


# =============================================================================
# Sender Identity Configuration
# =============================================================================

AGENT_TYPE = "deep.research"

# Internal dispatcher instance for shared async dispatch logic
_dispatcher = AgentNotificationDispatcher( agent_type=AGENT_TYPE )


def _get_sender_id() -> str:
    """
    Get sender_id for Deep Research Agent notifications.

    Ensures:
        - Returns sender_id in format: deep.research@{project}.deepily.ai
        - Project is detected from current working directory

    Returns:
        str: Sender ID for notification identity
    """
    return _dispatcher.build_sender_id()


# Cache sender_id at module load (avoids repeated os.getcwd calls)
# NOTE: Mutable — job.py and cli.py callers may append suffixes at runtime
SENDER_ID = _get_sender_id()

# Session name for UI display (set by CLI/job before notifications)
SESSION_NAME: Optional[ str ] = None


# =============================================================================
# Primary Interface Functions
# =============================================================================

async def notify_progress(
    message: str,
    priority: str = "medium",
    abstract: Optional[ str ] = None,
    session_name: Optional[ str ] = None,
    job_id: Optional[ str ] = None,
    queue_name: Optional[ str ] = None,
    progress_group_id: Optional[ str ] = None
) -> None:
    """
    Send fire-and-forget progress notification.

    Non-blocking — runs in thread pool to avoid blocking event loop.

    Args:
        message: Progress message to announce
        priority: "low", "medium", "high", or "urgent"
        abstract: Optional supplementary context (markdown, URLs, details)
        session_name: Optional human-readable session name for UI display
        job_id: Optional agentic job ID for routing to job cards
        queue_name: Optional queue where job is running
        progress_group_id: Optional progress group ID for in-place DOM updates
    """
    _dispatcher.sender_id    = SENDER_ID
    _dispatcher.session_name = SESSION_NAME
    await _dispatcher.notify_progress(
        message, priority=priority, abstract=abstract,
        session_name=session_name, job_id=job_id,
        queue_name=queue_name, progress_group_id=progress_group_id
    )


async def ask_confirmation(
    question: str,
    default: str = "no",
    timeout: int = 60,
    abstract: Optional[ str ] = None
) -> bool:
    """
    Ask a yes/no question and return boolean result.

    Args:
        question: The yes/no question to ask
        default: Default answer if timeout ("yes" or "no")
        timeout: Seconds to wait for response
        abstract: Optional supplementary context

    Returns:
        bool: True if user said yes, False otherwise
    """
    _dispatcher.sender_id = SENDER_ID
    return await _dispatcher.ask_confirmation(
        question, default=default, timeout=timeout, abstract=abstract
    )


async def get_feedback(
    prompt: str,
    timeout: int = 300
) -> Optional[ str ]:
    """
    Get open-ended feedback from user via voice.

    Args:
        prompt: Text to speak to the user
        timeout: Maximum seconds to wait for response

    Returns:
        str or None: User's transcribed voice response
    """
    _dispatcher.sender_id = SENDER_ID
    return await _dispatcher.get_feedback( prompt, timeout=timeout )


async def present_choices(
    questions: list,
    timeout: int = 120
) -> dict:
    """
    Present multiple-choice questions and get user's selection.

    Args:
        questions: List of question objects with options
        timeout: Seconds to wait for response

    Returns:
        dict: {"answers": {...}} with selections keyed by header
    """
    _dispatcher.sender_id = SENDER_ID
    return await _dispatcher.present_choices( questions, timeout=timeout )


# =============================================================================
# Feedback Analysis Utilities
# =============================================================================
# NOTE: is_approval(), is_rejection(), and extract_feedback_intent() are now
# imported from cosa.agents.utils.feedback_analysis (see imports above).
# They remain available at module level for backward compatibility.


def quick_smoke_test():
    """Quick smoke test for cosa_interface module."""
    import cosa.utils.util as cu

    cu.print_banner( "COSA Interface Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import validation
        print( "Testing imports..." )
        assert NotificationRequest is not None
        assert NotificationType is not None
        assert ResponseType is not None
        print( "✓ Imports valid" )

        # Test 2: is_approval function
        print( "Testing is_approval..." )
        assert is_approval( "yes" ) is True
        assert is_approval( "Yes, proceed" ) is True
        assert is_approval( "sounds good" ) is True
        assert is_approval( "no" ) is False
        assert is_approval( "" ) is False
        assert is_approval( None ) is False  # type: ignore
        print( "✓ is_approval works correctly" )

        # Test 3: is_rejection function
        print( "Testing is_rejection..." )
        assert is_rejection( "no" ) is True
        assert is_rejection( "wait, stop" ) is True
        assert is_rejection( "change it" ) is True
        assert is_rejection( "yes" ) is False
        assert is_rejection( "" ) is False
        print( "✓ is_rejection works correctly" )

        # Test 4: extract_feedback_intent
        print( "Testing extract_feedback_intent..." )
        intent = extract_feedback_intent( "yes, go ahead" )
        assert intent[ "is_approval" ] is True
        assert intent[ "is_rejection" ] is False
        assert intent[ "feedback_type" ] == "approval"

        intent = extract_feedback_intent( "no, change it" )
        assert intent[ "is_approval" ] is False
        assert intent[ "is_rejection" ] is True
        assert intent[ "feedback_type" ] == "change_request"

        intent = extract_feedback_intent( "focus on performance" )
        assert intent[ "is_approval" ] is False
        assert intent[ "is_rejection" ] is False
        assert intent[ "feedback_type" ] == "additional_context"
        print( "✓ extract_feedback_intent works correctly" )

        # Test 5: format_questions_for_tts (imported from notification_utils)
        print( "Testing format_questions_for_tts..." )
        questions = [ {
            "question" : "Which option?",
            "options"  : [
                { "label": "Option A" },
                { "label": "Option B" }
            ]
        } ]
        tts = format_questions_for_tts( questions )
        assert "Which option?" in tts
        assert "Option" not in tts  # Options NOT in TTS - they appear in UI only
        print( "✓ format_questions_for_tts works correctly" )

        # Test 6: convert_questions_for_api (imported from notification_utils)
        print( "Testing convert_questions_for_api..." )
        questions = [ {
            "question"    : "Which themes?",
            "header"      : "Themes",
            "multiSelect" : True,
            "options"     : [ { "label": "A" }, { "label": "B" } ]
        } ]
        converted = convert_questions_for_api( questions )
        assert "questions" in converted
        assert converted[ "questions" ][ 0 ][ "multi_select" ] is True
        assert "multiSelect" not in converted[ "questions" ][ 0 ]
        print( "✓ convert_questions_for_api correctly converts multiSelect -> multi_select" )

        # Test 7: Async functions exist (can't fully test without running server)
        print( "Testing async function signatures..." )
        import inspect
        assert inspect.iscoroutinefunction( notify_progress )
        assert inspect.iscoroutinefunction( ask_confirmation )
        assert inspect.iscoroutinefunction( get_feedback )
        assert inspect.iscoroutinefunction( present_choices )
        print( "✓ Async functions have correct signatures" )

        # Test 8: Dispatcher is properly configured
        print( "Testing dispatcher configuration..." )
        assert _dispatcher.agent_type == "deep.research"
        assert "deep.research@" in _dispatcher.sender_id
        print( f"✓ Dispatcher sender_id: {_dispatcher.sender_id}" )

        print( "\n✓ COSA Interface smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
