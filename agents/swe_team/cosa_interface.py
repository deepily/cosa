#!/usr/bin/env python3
"""
COSA Voice Interface Integration Layer for SWE Team Agent.

Role-aware notification wrappers that bridge the async orchestrator
with the blocking notification API. Each notification carries a
role-specific sender_id for routing and display.

Uses asyncio.to_thread() to run blocking calls without blocking the event loop.

CONTRACT:
    This module is the orchestrator's notification layer. It provides:
    - Role-aware sender IDs (swe.lead@, swe.coder@, swe.tester@)
    - job_id routing for CJ Flow integration
    - Blocking confirmations and decisions (ask_confirmation, request_decision)
    - Fire-and-forget progress notifications (notify_progress)

    Use this module when:
    - Inside the orchestrator or any component called by the orchestrator
    - You need role-specific sender identity for notification routing
    - You need job_id passthrough for CJ Flow job card routing

    Do NOT use this module for:
    - Standalone CLI usage outside the orchestrator context
    - Simple one-off notifications (use voice_io.py instead)

    See also: voice_io.py — standalone/CLI wrapper for voice-first I/O
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
from cosa.utils.notification_utils import format_questions_for_tts, convert_questions_for_api

logger = logging.getLogger( __name__ )


# =============================================================================
# Sender Identity Configuration
# =============================================================================

def _get_base_sender_prefix() -> str:
    """
    Get project-aware base prefix for SWE Team sender IDs.

    Ensures:
        - Returns "swe" (prefix for all SWE Team sender IDs)
        - Project detection handled in full sender_id construction

    Returns:
        str: "swe"
    """
    return "swe"


def _get_project() -> str:
    """
    Detect project from current working directory.

    Ensures:
        - Returns project name for sender_id construction
        - Handles nested directory structures

    Returns:
        str: Project name (e.g., "lupin", "cosa")
    """
    cwd = os.getcwd()

    if "/cosa" in cwd.lower() and "/lupin" not in cwd.lower():
        return "cosa"
    elif "/planning-is-prompting" in cwd.lower():
        return "plan"
    elif "/lupin" in cwd.lower():
        return "lupin"
    else:
        return os.path.basename( cwd ).lower()


def get_sender_id( role: str = "lead", session_id: str = None ) -> str:
    """
    Construct sender_id for a given SWE Team agent role.

    Requires:
        - role is a valid role name string

    Ensures:
        - Returns sender_id in format: swe.{role}@{project}.deepily.ai[#{session_id}]
        - Conforms to existing Lupin sender_id regex

    Args:
        role: The agent role name (lead, coder, tester, etc.)
        session_id: Optional session ID suffix

    Returns:
        str: Sender ID string
    """
    base = f"swe.{role}@{PROJECT}.deepily.ai"
    if session_id:
        # Strip user-scope suffix (::user_id) — only the base hash is needed for routing
        base_id = session_id.split( "::" )[ 0 ] if "::" in session_id else session_id
        return f"{base}#{base_id}"
    return base


# Cache at module load
PROJECT = _get_project()

# Session name for UI display (set by orchestrator before notifications)
SESSION_NAME: Optional[ str ] = None

# Session ID for sender_id suffix (set by orchestrator)
SESSION_ID: Optional[ str ] = None


# =============================================================================
# Primary Interface Functions
# =============================================================================

async def notify_progress(
    message: str,
    role: str = "lead",
    priority: str = "medium",
    abstract: Optional[ str ] = None,
    session_name: Optional[ str ] = None,
    job_id: Optional[ str ] = None,
    queue_name: Optional[ str ] = None,
    progress_group_id: Optional[ str ] = None,
) -> None:
    """
    Send fire-and-forget progress notification from a specific agent role.

    Requires:
        - message is a non-empty string
        - role is a valid role name
        - priority is "low", "medium", "high", or "urgent"

    Ensures:
        - Notification is sent asynchronously with role-specific sender_id
        - Returns immediately (fire-and-forget)
        - Logs warning on failure (doesn't raise)

    Args:
        message: Progress message to announce
        role: Agent role sending the notification
        priority: "low", "medium", "high", or "urgent"
        abstract: Optional supplementary context (markdown, URLs, details)
        session_name: Optional human-readable session name
        job_id: Optional agentic job ID for routing to job cards
        queue_name: Optional queue where job is running
        progress_group_id: Optional progress group ID (pg-{8 hex chars}) for in-place DOM updates
    """
    try:
        resolved_session_name = session_name if session_name is not None else SESSION_NAME

        request = AsyncNotificationRequest(
            message           = message,
            notification_type = NotificationType.PROGRESS,
            priority          = NotificationPriority( priority ),
            sender_id         = get_sender_id( role, SESSION_ID ),
            abstract          = abstract,
            session_name      = resolved_session_name,
            job_id            = job_id,
            queue_name        = queue_name,
            progress_group_id = progress_group_id,
        )

        await asyncio.to_thread( _notify_user_async, request )

    except Exception as e:
        logger.warning( f"Failed to send progress notification: {e}" )


async def ask_confirmation(
    question: str,
    role: str = "lead",
    default: str = "no",
    timeout: int = 120,
    abstract: Optional[ str ] = None,
) -> bool:
    """
    Ask a yes/no question and return boolean result.

    Routes through SmartRouter for availability (human or proxy).

    Requires:
        - question is a non-empty string
        - default is "yes" or "no"

    Ensures:
        - Returns True if user/proxy said yes
        - Returns False otherwise
        - Returns default value on timeout

    Args:
        question: The yes/no question to ask
        role: Agent role asking the question
        default: Default answer if timeout
        timeout: Seconds to wait for response
        abstract: Optional supplementary context

    Returns:
        bool: True if approved, False otherwise
    """
    try:
        request = NotificationRequest(
            message           = question,
            response_type     = ResponseType.YES_NO,
            notification_type = NotificationType.CUSTOM,
            priority          = NotificationPriority.HIGH,
            timeout_seconds   = timeout,
            response_default  = default,
            sender_id         = get_sender_id( role, SESSION_ID ),
            abstract          = abstract,
        )

        response: NotificationResponse = await asyncio.to_thread( _notify_user_sync, request )

        if response.exit_code == 0 and response.response_value:
            return response.response_value.lower().strip().startswith( "yes" )

        return default == "yes"

    except Exception as e:
        logger.warning( f"ask_confirmation failed: {e}" )
        return default == "yes"


async def request_decision(
    question: str,
    options: list,
    role: str = "lead",
    timeout: int = 300,
    abstract: Optional[ str ] = None,
) -> dict:
    """
    Present multiple-choice decision to user/proxy.

    For architectural and design decisions that need explicit selection.

    Requires:
        - question is a non-empty string
        - options is a list of question objects

    Ensures:
        - Returns dict with "answers" key containing selections
        - Returns empty answers on timeout/failure

    Args:
        question: The decision question
        options: List of question objects with header, options, multiSelect
        role: Agent role requesting the decision
        timeout: Seconds to wait
        abstract: Optional supplementary context

    Returns:
        dict: {"answers": {...}} with selections
    """
    try:
        message = format_questions_for_tts( options )

        request = NotificationRequest(
            message           = message,
            response_type     = ResponseType.MULTIPLE_CHOICE,
            notification_type = NotificationType.CUSTOM,
            priority          = NotificationPriority.HIGH,
            timeout_seconds   = timeout,
            response_options  = convert_questions_for_api( options ),
            sender_id         = get_sender_id( role, SESSION_ID ),
            abstract          = abstract,
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
        logger.warning( f"request_decision failed: {e}" )
        return { "answers": {} }


async def get_feedback(
    prompt: str,
    role: str = "lead",
    timeout: int = 300,
) -> Optional[ str ]:
    """
    Get open-ended feedback from user via voice.

    Requires:
        - prompt is a non-empty string

    Ensures:
        - Returns user's transcribed voice response on success
        - Returns None on timeout, error, or no response

    Args:
        prompt: Text to speak to the user
        role: Agent role requesting feedback
        timeout: Maximum seconds to wait

    Returns:
        str or None: User's transcribed response
    """
    try:
        request = NotificationRequest(
            message           = prompt,
            response_type     = ResponseType.OPEN_ENDED,
            notification_type = NotificationType.CUSTOM,
            priority          = NotificationPriority.HIGH,
            timeout_seconds   = timeout,
            sender_id         = get_sender_id( role, SESSION_ID ),
        )

        response: NotificationResponse = await asyncio.to_thread( _notify_user_sync, request )

        if response.exit_code == 0:
            return response.response_value

        return None

    except Exception as e:
        logger.warning( f"get_feedback failed: {e}" )
        return None


# =============================================================================
# Feedback Analysis Utilities (reuse deep_research patterns)
# =============================================================================

def is_approval( feedback: str ) -> bool:
    """
    Determine if user feedback indicates approval.

    Requires:
        - feedback is a string

    Ensures:
        - Returns True if feedback contains approval signals
        - Returns False otherwise

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
    Determine if user feedback indicates rejection.

    Requires:
        - feedback is a string

    Ensures:
        - Returns True if feedback contains rejection signals
        - Returns False otherwise

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


def quick_smoke_test():
    """Quick smoke test for SWE Team cosa_interface module."""
    import cosa.utils.util as cu

    cu.print_banner( "SWE Team COSA Interface Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import validation
        print( "Testing imports..." )
        assert NotificationRequest is not None
        assert NotificationType is not None
        assert ResponseType is not None
        print( "✓ Imports valid" )

        # Test 2: Sender ID generation
        print( "Testing sender ID generation..." )
        sid = get_sender_id( "lead" )
        assert "swe.lead@" in sid
        assert ".deepily.ai" in sid
        sid_session = get_sender_id( "coder", "abc123" )
        assert sid_session.endswith( "#abc123" )
        # Test compound hash stripping (Bug F fix)
        sid_compound = get_sender_id( "lead", "swe-4637f1cd::0cf47e2d-d5a1-4cd4-addf-79810fd32b15" )
        assert sid_compound.endswith( "#swe-4637f1cd" ), f"Expected stripped hash, got: {sid_compound}"
        assert "::" not in sid_compound, f"Compound hash not stripped: {sid_compound}"
        print( f"✓ Sender IDs: {sid}, {sid_session}, {sid_compound}" )

        # Test 3: is_approval
        print( "Testing is_approval..." )
        assert is_approval( "yes" ) is True
        assert is_approval( "sounds good" ) is True
        assert is_approval( "no" ) is False
        assert is_approval( "" ) is False
        assert is_approval( None ) is False  # type: ignore
        print( "✓ is_approval works correctly" )

        # Test 4: is_rejection
        print( "Testing is_rejection..." )
        assert is_rejection( "no" ) is True
        assert is_rejection( "wait, stop" ) is True
        assert is_rejection( "yes" ) is False
        assert is_rejection( "" ) is False
        print( "✓ is_rejection works correctly" )

        # Test 5: Async function signatures
        print( "Testing async function signatures..." )
        import inspect
        assert inspect.iscoroutinefunction( notify_progress )
        assert inspect.iscoroutinefunction( ask_confirmation )
        assert inspect.iscoroutinefunction( request_decision )
        assert inspect.iscoroutinefunction( get_feedback )
        print( "✓ Async functions have correct signatures" )

        # Test 6: notify_progress has role parameter
        print( "Testing role-aware signatures..." )
        sig = inspect.signature( notify_progress )
        assert "role" in sig.parameters
        assert "job_id" in sig.parameters
        sig = inspect.signature( ask_confirmation )
        assert "role" in sig.parameters
        print( "✓ All functions accept role parameter" )

        print( "\n✓ SWE Team COSA Interface smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
