#!/usr/bin/env python3
"""
COSA Voice Interface Integration Layer.

This module provides async wrappers for the cosa-voice notification tools,
bridging the async orchestrator with the blocking notification API.

Uses asyncio.to_thread() to run blocking calls without blocking the event loop.
This allows other async tasks to continue while waiting for human feedback.
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
    Get sender_id for Deep Research Agent notifications.

    Ensures:
        - Returns sender_id in format: deep.research@{project}.deepily.ai
        - Project is detected from current working directory
        - Handles nested directory structures correctly

    Returns:
        str: Sender ID for notification identity
    """
    # Project detection - check more specific paths FIRST
    # (cosa is a subdirectory of lupin, so check cosa before lupin)
    cwd = os.getcwd()

    if "/cosa" in cwd.lower() and "/lupin" not in cwd.lower():
        # Standalone cosa repo (not nested in lupin)
        project = "cosa"
    elif "/planning-is-prompting" in cwd.lower():
        project = "plan"
    elif "/lupin" in cwd.lower():
        # Lupin project (includes nested cosa subdirectory)
        project = "lupin"
    else:
        project = os.path.basename( cwd ).lower()

    return f"deep.research@{project}.deepily.ai"


# Cache sender_id at module load (avoids repeated os.getcwd calls)
SENDER_ID = _get_sender_id()

# Session name for UI display (set by CLI before notifications)
SESSION_NAME: Optional[str] = None


# =============================================================================
# Primary Interface Functions
# =============================================================================

async def notify_progress(
    message: str,
    priority: str = "medium",
    abstract: Optional[str] = None,
    session_name: Optional[str] = None
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
    """
    try:
        # Use module-level SESSION_NAME if not explicitly provided
        resolved_session_name = session_name if session_name is not None else SESSION_NAME

        request = AsyncNotificationRequest(
            message           = message,
            notification_type = NotificationType.PROGRESS,
            priority          = NotificationPriority( priority ),
            sender_id         = SENDER_ID,
            abstract          = abstract,
            session_name      = resolved_session_name,
        )

        # Run blocking call in thread pool
        await asyncio.to_thread( _notify_user_async, request )

    except Exception as e:
        logger.warning( f"Failed to send progress notification: {e}" )


async def ask_confirmation(
    question: str,
    default: str = "no",
    timeout: int = 60,
    abstract: Optional[str] = None
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
        - Logs warning on failure

    Args:
        question: The yes/no question to ask
        default: Default answer if timeout ("yes" or "no")
        timeout: Seconds to wait for response
        abstract: Optional supplementary context (plan details, URLs, markdown)

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
) -> Optional[str]:
    """
    Get open-ended feedback from user via voice.

    Blocking call that speaks prompt via TTS, waits for user voice response.

    Requires:
        - prompt is a non-empty string
        - timeout is positive integer (1-600)

    Ensures:
        - Returns user's transcribed voice response on success
        - Returns None on timeout, error, or no response
        - Logs warning on failure

    Args:
        prompt: Text to speak to the user
        timeout: Maximum seconds to wait for response

    Returns:
        str or None: User's transcribed voice response
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
    timeout: int = 120
) -> dict:
    """
    Present multiple-choice questions and get user's selection.

    Requires:
        - questions is a list of question objects
        - Each question has: question, header, multiSelect, options
        - timeout is positive integer (1-600)

    Ensures:
        - Returns dict with "answers" key containing selections
        - Answers keyed by question header
        - Returns empty answers on timeout/failure

    Args:
        questions: List of question objects with options
        timeout: Seconds to wait for response

    Returns:
        dict: {"answers": {...}} with selections keyed by header
    """
    try:
        # Build TTS-friendly message
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

    Requires:
        - feedback is a string

    Ensures:
        - Returns True if feedback contains approval signals
        - Returns False otherwise

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

    Requires:
        - feedback is a string

    Ensures:
        - Returns True if feedback contains rejection signals
        - Returns False otherwise

    Args:
        feedback: User's voice response text

    Returns:
        bool: True if rejection/change request detected
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


def extract_feedback_intent( feedback: str ) -> dict:
    """
    Extract structured intent from user feedback.

    Requires:
        - feedback is a string

    Ensures:
        - Returns dict with is_approval, is_rejection, raw_feedback, feedback_type
        - feedback_type is "approval", "change_request", or "additional_context"

    Args:
        feedback: User's voice response text

    Returns:
        dict: Structured intent analysis
    """
    return {
        "is_approval"   : is_approval( feedback ),
        "is_rejection"  : is_rejection( feedback ),
        "raw_feedback"  : feedback,
        "feedback_type" : (
            "approval" if is_approval( feedback )
            else "change_request" if is_rejection( feedback )
            else "additional_context"
        ),
    }


# =============================================================================
# Private Helpers
# =============================================================================

def _format_questions_for_tts( questions: list ) -> str:
    """
    Format questions for TTS playback.

    Requires:
        - questions is a list of question dicts

    Ensures:
        - Returns TTS-friendly string
        - Multi-question: "Question N of X: ..."
        - Single question: Just the question text

    Args:
        questions: List of question objects

    Returns:
        str: TTS-friendly message
    """
    total = len( questions )
    parts = []

    for i, q in enumerate( questions, 1 ):
        question_text = q.get( "question", "Please select an option" )
        options = q.get( "options", [] )

        if total > 1:
            part = f"Question {i} of {total}: {question_text}"
        else:
            part = question_text

        option_texts = [
            f"Option {j}: {opt.get( 'label', f'Option {j}' )}"
            for j, opt in enumerate( options, 1 )
        ]
        part += " " + ". ".join( option_texts ) + "."
        parts.append( part )

    return " ".join( parts )


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
        assert "Option 2: Option B" in tts
        print( "✓ _format_questions_for_tts works correctly" )

        # Test 6: Async functions exist (can't fully test without running server)
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
