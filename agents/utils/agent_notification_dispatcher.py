#!/usr/bin/env python3
"""
Shared Agent Notification Dispatcher for COSA Agents.

Encapsulates the common async wrapper + notification dispatch pattern that
was previously copy-pasted across every agent's cosa_interface.py. All
methods use asyncio.to_thread() to bridge the blocking notification API
with async agent orchestrators.

Usage:
    dispatcher = AgentNotificationDispatcher( agent_type="deep.research" )
    await dispatcher.notify_progress( "Starting research..." )
    approved  = await dispatcher.ask_confirmation( "Proceed?" )
    feedback  = await dispatcher.get_feedback( "Any preferences?" )
    selection = await dispatcher.present_choices( questions, timeout=120 )

For role-aware agents (SWE Team):
    dispatcher = AgentNotificationDispatcher(
        agent_type="swe", supports_role=True, default_priority="high"
    )
    await dispatcher.notify_progress( "Planning...", role="lead" )
"""

import asyncio
import json
import logging
from typing import Optional

from lupin_cli.notifications.notification_models import (
    NotificationRequest,
    AsyncNotificationRequest,
    NotificationResponse,
    NotificationType,
    NotificationPriority,
    ResponseType
)
from lupin_cli.notifications.notify_user_sync import notify_user_sync as _notify_user_sync
from lupin_cli.notifications.notify_user_async import notify_user_async as _notify_user_async
from cosa.utils.notification_utils import format_questions_for_tts, convert_questions_for_api
from cosa.agents.utils.sender_id import build_sender_id

logger = logging.getLogger( __name__ )


class AgentNotificationDispatcher:
    """
    Shared async notification dispatcher for COSA agents.

    Configurable via constructor for agent-specific behavior:
    - agent_type: Sender identity prefix (e.g., "deep.research")
    - default_priority: Default notification priority level
    - supports_role: Whether this agent uses role-aware sender IDs

    Attributes:
        sender_id: Current sender_id string (mutable for runtime suffixes)
        session_name: Optional session name for UI display
        session_id: Optional session ID for role-aware agents
    """

    def __init__(
        self,
        agent_type: str,
        default_priority: str = "medium",
        supports_role: bool = False,
        default_suffix: str = None
    ):
        """
        Initialize the dispatcher.

        Requires:
            - agent_type is a non-empty string

        Ensures:
            - Dispatcher ready to send notifications
            - sender_id computed from agent_type + auto-detected project

        Args:
            agent_type: Agent identifier prefix (e.g., "deep.research", "swe")
            default_priority: Default priority for blocking calls ("medium", "high")
            supports_role: If True, methods accept a `role` parameter for role-aware sender IDs
            default_suffix: Optional default suffix for sender_id (e.g., "cli")
        """
        self.agent_type       = agent_type
        self.default_priority = default_priority
        self.supports_role    = supports_role
        self.default_suffix   = default_suffix

        # Mutable state — job.py callers can modify these at runtime
        self.sender_id    = build_sender_id( agent_type, suffix=default_suffix )
        self.session_name = None
        self.session_id   = None  # For role-aware agents (SWE Team)

    def build_sender_id( self, suffix: str = None ) -> str:
        """
        Rebuild sender_id with an optional new suffix.

        Useful when job.py needs to append a job hash:
            dispatcher.sender_id = dispatcher.build_sender_id( suffix=self.id_hash )

        Args:
            suffix: Optional suffix (replaces default_suffix for this call)

        Returns:
            str: Newly constructed sender_id
        """
        return build_sender_id( self.agent_type, suffix=suffix or self.default_suffix )

    def _resolve_sender_id( self, role: str = None ) -> str:
        """
        Resolve the sender_id for a notification call.

        For role-aware agents, constructs a role-specific sender_id.
        For standard agents, returns self.sender_id.

        Args:
            role: Optional role name for role-aware agents

        Returns:
            str: Resolved sender_id
        """
        if self.supports_role and role:
            suffix = None
            if self.session_id:
                # Strip user-scope suffix (::user_id) — only the base hash is needed
                suffix = self.session_id.split( "::" )[ 0 ] if "::" in self.session_id else self.session_id
            return build_sender_id( f"{self.agent_type}.{role}", suffix=suffix )
        return self.sender_id

    # =========================================================================
    # Primary Interface Methods
    # =========================================================================

    async def notify_progress(
        self,
        message: str,
        priority: str = None,
        abstract: Optional[ str ] = None,
        session_name: Optional[ str ] = None,
        job_id: Optional[ str ] = None,
        queue_name: Optional[ str ] = None,
        progress_group_id: Optional[ str ] = None,
        role: str = None
    ) -> None:
        """
        Send fire-and-forget progress notification.

        Non-blocking — runs in thread pool to avoid blocking event loop.

        Args:
            message: Progress message to announce
            priority: "low", "medium", "high", or "urgent" (default: self.default_priority)
            abstract: Optional supplementary context (markdown, URLs)
            session_name: Optional human-readable session name for UI display
            job_id: Optional agentic job ID for routing to job cards
            queue_name: Optional queue where job is running
            progress_group_id: Optional progress group ID for in-place DOM updates
            role: Optional agent role (for role-aware dispatchers)
        """
        try:
            resolved_session_name = session_name if session_name is not None else self.session_name

            request = AsyncNotificationRequest(
                message           = message,
                notification_type = NotificationType.PROGRESS,
                priority          = NotificationPriority( priority or self.default_priority ),
                sender_id         = self._resolve_sender_id( role ),
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
        self,
        question: str,
        default: str = "no",
        timeout: int = 60,
        abstract: Optional[ str ] = None,
        job_id: Optional[ str ] = None,
        role: str = None
    ) -> bool:
        """
        Ask a yes/no question and return boolean result.

        Args:
            question: The yes/no question to ask
            default: Default answer if timeout ("yes" or "no")
            timeout: Seconds to wait for response
            abstract: Optional supplementary context
            job_id: Optional job ID for routing
            role: Optional agent role (for role-aware dispatchers)

        Returns:
            bool: True if user said yes, False otherwise
        """
        try:
            request = NotificationRequest(
                message           = question,
                response_type     = ResponseType.YES_NO,
                notification_type = NotificationType.CUSTOM,
                priority          = NotificationPriority( self.default_priority ),
                timeout_seconds   = timeout,
                response_default  = default,
                sender_id         = self._resolve_sender_id( role ),
                abstract          = abstract,
                job_id            = job_id,
            )

            response: NotificationResponse = await asyncio.to_thread( _notify_user_sync, request )

            if response.exit_code == 0 and response.response_value:
                return response.response_value.lower().strip().startswith( "yes" )

            return default == "yes"

        except Exception as e:
            logger.warning( f"ask_confirmation failed: {e}" )
            return default == "yes"

    async def get_feedback(
        self,
        prompt: str,
        timeout: int = 300,
        role: str = None
    ) -> Optional[ str ]:
        """
        Get open-ended feedback from user via voice.

        Args:
            prompt: Text to speak to the user
            timeout: Maximum seconds to wait
            role: Optional agent role (for role-aware dispatchers)

        Returns:
            str or None: User's transcribed voice response
        """
        try:
            request = NotificationRequest(
                message           = prompt,
                response_type     = ResponseType.OPEN_ENDED,
                notification_type = NotificationType.CUSTOM,
                priority          = NotificationPriority( self.default_priority ),
                timeout_seconds   = timeout,
                sender_id         = self._resolve_sender_id( role ),
            )

            response: NotificationResponse = await asyncio.to_thread( _notify_user_sync, request )

            if response.exit_code == 0:
                return response.response_value

            return None

        except Exception as e:
            logger.warning( f"get_feedback failed: {e}" )
            return None

    async def present_choices(
        self,
        questions: list,
        timeout: int = 120,
        title: Optional[ str ] = None,
        abstract: Optional[ str ] = None,
        role: str = None
    ) -> dict:
        """
        Present multiple-choice questions and get user's selection.

        Args:
            questions: List of question objects with options
            timeout: Seconds to wait for response
            title: Optional title for the notification
            abstract: Optional supplementary context
            role: Optional agent role (for role-aware dispatchers)

        Returns:
            dict: {"answers": {...}} with selections keyed by header
        """
        try:
            message = format_questions_for_tts( questions )

            request = NotificationRequest(
                message           = message,
                response_type     = ResponseType.MULTIPLE_CHOICE,
                notification_type = NotificationType.CUSTOM,
                priority          = NotificationPriority( self.default_priority ),
                timeout_seconds   = timeout,
                response_options  = convert_questions_for_api( questions ),
                sender_id         = self._resolve_sender_id( role ),
                abstract          = abstract,
                title             = title,
            )

            response: NotificationResponse = await asyncio.to_thread( _notify_user_sync, request )

            if response.exit_code == 0 and response.response_value:
                try:
                    return json.loads( response.response_value )
                except json.JSONDecodeError:
                    return { "answers": { "response": response.response_value } }

            return { "answers": {} }

        except Exception as e:
            logger.warning( f"present_choices failed: {e}" )
            return { "answers": {} }


def quick_smoke_test():
    """Quick smoke test for AgentNotificationDispatcher."""
    import inspect
    import cosa.utils.util as cu

    cu.print_banner( "AgentNotificationDispatcher Smoke Test", prepend_nl=True )

    try:
        # Test 1: Basic instantiation
        print( "Testing basic instantiation..." )
        d = AgentNotificationDispatcher( agent_type="deep.research" )
        assert "deep.research@" in d.sender_id
        assert ".deepily.ai" in d.sender_id
        assert d.supports_role is False
        assert d.default_priority == "medium"
        print( f"  sender_id: {d.sender_id}" )

        # Test 2: With suffix
        print( "Testing instantiation with suffix..." )
        d = AgentNotificationDispatcher( agent_type="podcast.gen", default_suffix="cli" )
        assert d.sender_id.endswith( "#cli" )
        print( f"  sender_id: {d.sender_id}" )

        # Test 3: Role-aware
        print( "Testing role-aware dispatcher..." )
        d = AgentNotificationDispatcher( agent_type="swe", supports_role=True, default_priority="high" )
        assert d.supports_role is True
        assert d.default_priority == "high"
        resolved = d._resolve_sender_id( "lead" )
        assert "swe.lead@" in resolved
        print( f"  role='lead' -> {resolved}" )

        # Test 4: Role-aware with session_id
        print( "Testing role-aware with session_id..." )
        d.session_id = "abc123::user42"
        resolved = d._resolve_sender_id( "coder" )
        assert "swe.coder@" in resolved
        assert resolved.endswith( "#abc123" )
        assert "::" not in resolved
        print( f"  role='coder', session_id='abc123::user42' -> {resolved}" )

        # Test 5: build_sender_id helper
        print( "Testing build_sender_id helper..." )
        d = AgentNotificationDispatcher( agent_type="deep.research" )
        new_sid = d.build_sender_id( suffix="jobhash123" )
        assert new_sid.endswith( "#jobhash123" )
        print( f"  build_sender_id(suffix='jobhash123') -> {new_sid}" )

        # Test 6: Mutable sender_id
        print( "Testing mutable sender_id..." )
        d.sender_id = d.build_sender_id( suffix="custom" )
        assert d.sender_id.endswith( "#custom" )
        print( f"  Mutated sender_id: {d.sender_id}" )

        # Test 7: Async method signatures
        print( "Testing async method signatures..." )
        assert inspect.iscoroutinefunction( d.notify_progress )
        assert inspect.iscoroutinefunction( d.ask_confirmation )
        assert inspect.iscoroutinefunction( d.get_feedback )
        assert inspect.iscoroutinefunction( d.present_choices )
        print( "  All methods are async" )

        # Test 8: notify_progress signature has all expected params
        print( "Testing notify_progress signature..." )
        sig = inspect.signature( d.notify_progress )
        expected = [ "message", "priority", "abstract", "session_name", "job_id", "queue_name", "progress_group_id", "role" ]
        for param in expected:
            assert param in sig.parameters, f"Missing: {param}"
        print( "  All expected parameters present" )

        # Test 9: Standard dispatcher (no role) ignores role param
        print( "Testing standard dispatcher ignores role..." )
        d = AgentNotificationDispatcher( agent_type="deep.research" )
        d.sender_id = "deep.research@lupin.deepily.ai#test"
        resolved = d._resolve_sender_id( role="anything" )
        assert resolved == "deep.research@lupin.deepily.ai#test"
        print( "  Role ignored for non-role-aware dispatcher" )

        print( "\n  AgentNotificationDispatcher smoke test completed successfully" )

    except Exception as e:
        print( f"\n  Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
