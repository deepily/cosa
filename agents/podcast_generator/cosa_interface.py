#!/usr/bin/env python3
"""
COSA Voice Interface Integration Layer for Podcast Generator.

This module provides async wrappers for the cosa-voice notification tools,
bridging the async orchestrator with the blocking notification API.

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
    Get sender_id for Podcast Generator Agent notifications.

    Ensures:
        - Returns sender_id in format: podcast.gen@{project}.deepily.ai#cli
        - Project is detected from current working directory

    Returns:
        str: Sender ID for notification identity
    """
    cwd = os.getcwd()

    if "/cosa" in cwd.lower() and "/lupin" not in cwd.lower():
        project = "cosa"
    elif "/planning-is-prompting" in cwd.lower():
        project = "plan"
    elif "/lupin" in cwd.lower():
        project = "lupin"
    else:
        project = os.path.basename( cwd ).lower()

    return f"podcast.gen@{project}.deepily.ai#cli"


# Cache sender_id at module load
SENDER_ID = _get_sender_id()

# Session name for UI display (set by CLI before notifications)
SESSION_NAME: Optional[ str ] = None


# =============================================================================
# Primary Interface Functions
# =============================================================================

async def notify_progress(
    message: str,
    priority: str = "medium",
    abstract: Optional[ str ] = None,
    session_name: Optional[ str ] = None
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

    Args:
        message: Progress message to announce
        priority: "low", "medium", "high", or "urgent"
        abstract: Optional supplementary context (markdown)
        session_name: Optional human-readable session name
    """
    try:
        resolved_session_name = session_name if session_name is not None else SESSION_NAME

        request = AsyncNotificationRequest(
            message           = message,
            notification_type = NotificationType.PROGRESS,
            priority          = NotificationPriority( priority ),
            sender_id         = SENDER_ID,
            abstract          = abstract,
            session_name      = resolved_session_name,
        )

        await asyncio.to_thread( _notify_user_async, request )

    except Exception as e:
        logger.warning( f"Failed to send progress notification: {e}" )


async def ask_confirmation(
    question: str,
    default: str = "no",
    timeout: int = 60,
    abstract: Optional[ str ] = None
) -> bool:
    """
    Ask a yes/no question and return boolean result.

    Requires:
        - question is a non-empty string
        - default is "yes" or "no"

    Ensures:
        - Returns True if user said yes
        - Returns False otherwise

    Args:
        question: The yes/no question to ask
        default: Default answer if timeout
        timeout: Seconds to wait for response
        abstract: Optional supplementary context

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
        )

        response: NotificationResponse = await asyncio.to_thread( _notify_user_sync, request )

        if response.exit_code == 0 and response.response_value:
            return response.response_value.lower().strip() == "yes"

        return default == "yes"

    except Exception as e:
        logger.warning( f"ask_confirmation failed: {e}" )
        return default == "yes"


async def get_feedback(
    prompt: str,
    timeout: int = 300
) -> Optional[ str ]:
    """
    Get open-ended feedback from user via voice.

    Requires:
        - prompt is a non-empty string

    Ensures:
        - Returns user's response on success
        - Returns None on timeout or error

    Args:
        prompt: Text to speak to the user
        timeout: Maximum seconds to wait

    Returns:
        str or None: User's response
    """
    try:
        request = NotificationRequest(
            message           = prompt,
            response_type     = ResponseType.OPEN_ENDED,
            notification_type = NotificationType.CUSTOM,
            priority          = NotificationPriority.MEDIUM,
            timeout_seconds   = timeout,
            sender_id         = SENDER_ID,
        )

        response: NotificationResponse = await asyncio.to_thread( _notify_user_sync, request )

        if response.exit_code == 0:
            return response.response_value

        return None

    except Exception as e:
        logger.warning( f"get_feedback failed: {e}" )
        return None


async def present_choices(
    questions: list,
    timeout: int = 120,
    title: Optional[ str ] = None,
    abstract: Optional[ str ] = None
) -> dict:
    """
    Present multiple-choice questions and get user's selection.

    Requires:
        - questions is a list of question objects
        - Each question has: question, header, multiSelect, options

    Ensures:
        - Returns dict with "answers" key containing selections

    Args:
        questions: List of question objects with options
        timeout: Seconds to wait for response
        title: Optional title for the notification
        abstract: Optional supplementary context

    Returns:
        dict: {"answers": {...}} with selections keyed by header
    """
    try:
        message = _format_questions_for_tts( questions )

        request = NotificationRequest(
            message           = message,
            response_type     = ResponseType.MULTIPLE_CHOICE,
            notification_type = NotificationType.CUSTOM,
            priority          = NotificationPriority.MEDIUM,
            timeout_seconds   = timeout,
            response_options  = { "questions": questions },
            sender_id         = SENDER_ID,
        )

        response: NotificationResponse = await asyncio.to_thread( _notify_user_sync, request )

        if response.exit_code == 0 and response.response_value:
            import json
            try:
                return json.loads( response.response_value )
            except json.JSONDecodeError:
                return { "answers": { "response": response.response_value } }

        return { "answers": {} }

    except Exception as e:
        logger.warning( f"present_choices failed: {e}" )
        return { "answers": {} }


# =============================================================================
# Feedback Analysis Utilities
# =============================================================================

def is_approval( feedback: str ) -> bool:
    """
    Determine if user feedback indicates approval.

    Args:
        feedback: User's voice response text

    Returns:
        bool: True if approval detected
    """
    if not feedback:
        return False

    approval_signals = [
        "yes", "proceed", "go ahead", "sounds good", "perfect",
        "do it", "approved", "looks good", "that works", "okay",
        "ok", "sure", "fine", "great", "excellent", "continue",
        "start", "begin", "let's go", "go for it"
    ]

    feedback_lower = feedback.lower().strip()

    for signal in approval_signals:
        if signal in feedback_lower:
            return True

    if feedback_lower in [ "y", "yep", "yup", "uh huh", "mm hmm" ]:
        return True

    return False


def is_rejection( feedback: str ) -> bool:
    """
    Determine if user feedback indicates rejection/change request.

    Args:
        feedback: User's voice response text

    Returns:
        bool: True if rejection detected
    """
    if not feedback:
        return False

    rejection_signals = [
        "no", "change", "adjust", "modify", "different",
        "instead", "rather", "stop", "wait", "hold on",
        "not quite", "actually", "but", "however"
    ]

    feedback_lower = feedback.lower().strip()

    for signal in rejection_signals:
        if signal in feedback_lower:
            return True

    return False


# =============================================================================
# Private Helpers
# =============================================================================

def _format_questions_for_tts( questions: list ) -> str:
    """
    Format questions for TTS playback.

    Returns ONLY the question text. Options are displayed in the UI
    and should NOT be included in the spoken TTS message.
    """
    total = len( questions )
    parts = []

    for i, q in enumerate( questions, 1 ):
        question_text = q.get( "question", "Please select an option" )
        multi_select = q.get( "multiSelect", False )

        # Build question intro (question text ONLY)
        if total > 1:
            part = f"Question {i} of {total}: {question_text}"
        else:
            part = question_text

        # Add multi-select hint if needed
        if multi_select:
            part += " You can select multiple options."

        # NOTE: Options are displayed in UI, not spoken in TTS
        parts.append( part )

    return " ".join( parts )


def quick_smoke_test():
    """Quick smoke test for cosa_interface module."""
    import cosa.utils.util as cu

    cu.print_banner( "Podcast Generator COSA Interface Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import validation
        print( "Testing imports..." )
        assert NotificationRequest is not None
        assert NotificationType is not None
        assert ResponseType is not None
        print( "✓ Imports valid" )

        # Test 2: Sender ID generation
        print( "Testing sender_id generation..." )
        sender_id = _get_sender_id()
        assert "podcast.gen@" in sender_id
        assert ".deepily.ai" in sender_id
        print( f"✓ Sender ID: {sender_id}" )

        # Test 3: is_approval function
        print( "Testing is_approval..." )
        assert is_approval( "yes" ) is True
        assert is_approval( "Yes, proceed" ) is True
        assert is_approval( "sounds good" ) is True
        assert is_approval( "no" ) is False
        assert is_approval( "" ) is False
        print( "✓ is_approval works correctly" )

        # Test 4: is_rejection function
        print( "Testing is_rejection..." )
        assert is_rejection( "no" ) is True
        assert is_rejection( "wait, stop" ) is True
        assert is_rejection( "change it" ) is True
        assert is_rejection( "yes" ) is False
        print( "✓ is_rejection works correctly" )

        # Test 5: _format_questions_for_tts
        print( "Testing _format_questions_for_tts..." )
        questions = [ {
            "question" : "Which option?",
            "options"  : [
                { "label": "Option A" },
                { "label": "Option B" }
            ]
        } ]
        tts = _format_questions_for_tts( questions )
        assert "Which option?" in tts
        assert "Option 1: Option A" in tts
        print( "✓ _format_questions_for_tts works" )

        # Test 6: Async function signatures
        print( "Testing async function signatures..." )
        import inspect
        assert inspect.iscoroutinefunction( notify_progress )
        assert inspect.iscoroutinefunction( ask_confirmation )
        assert inspect.iscoroutinefunction( get_feedback )
        assert inspect.iscoroutinefunction( present_choices )
        print( "✓ Async functions have correct signatures" )

        print( "\n✓ COSA Interface smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
