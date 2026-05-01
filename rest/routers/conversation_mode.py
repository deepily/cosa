"""
Cosa-voice conversation mode endpoints.

Per-session "conversation mode" toggle backed by the SessionStart bridge file
at ~/.claude/sessions/cc-{PPID}.json. When conversation_mode_active=True, Claude
auto-calls notify(full_text, suppress_ding=True) after every assistant turn so
the user can hold a voice dialogue at a distance (notification UI listening via
TTS rather than reading the terminal). Default = False (notification mode).

Activation surfaces (all four converge here or on the cosa-voice MCP tool):
    - Voice phrase: "enter conversation mode" → MCP enter_conversation_mode()
    - Slash command: /conversation-mode-on → MCP enter_conversation_mode()
    - MCP tool: enter_conversation_mode() / exit_conversation_mode() (writes bridge directly)
    - UI toggle button: POST to this router (writes bridge AND broadcasts WS event)

The bridge file is the single source of truth. UI clients hold a localStorage
read-through cache, hydrated by the GET endpoint and the conversation_mode_changed
WebSocket event broadcast on POST.

Generated on: 2026-04-27
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..middleware.api_key_auth import require_api_key_or_jwt
from ..notification_fifo_queue import NotificationFifoQueue

# Bridge helpers live in the parent Lupin tree, but importing them is fine
# (only git ops on src/cosa/ are restricted from parent context — imports are not).
from lupin_cli.claude_code.hooks.lib.session_bridge import (
    get_conversation_mode, set_conversation_mode, find_session_path_by_id,
    find_active_conversation_sessions, build_sender_id_for_cc
)


router = APIRouter( prefix="/api/cosa-voice", tags=[ "cosa-voice" ] )

# Module-level lock serializes activate-POSTs so the scan + displace + activate
# sequence is atomic within this process. If two tabs POST concurrently to
# activate different sessions, the lock ensures one fully completes (including
# displacing the other's previously-active session) before the second runs.
# Single-process uvicorn assumed — see "Risks / gotchas" #7 in the design doc
# addendum at src/rnd/v0.1.7/2026.04.27-conversation-mode-design.md §11 for
# the multi-worker caveat.
_conversation_mode_lock = asyncio.Lock()


# ── Dependency injection (mirrors notifications.router pattern) ──────────────

def get_notification_queue():
    """
    Dependency to get the singleton NotificationFifoQueue from main module.

    Ensures:
        - Returns the singleton NotificationFifoQueue instance
        - Raises ImportError if main module not yet initialized
    """
    import fastapi_app.main as main_module
    return main_module.jobs_notification_queue


# ── Models ───────────────────────────────────────────────────────────────────

class ConversationModeBody( BaseModel ):
    """
    POST body for setting conversation mode.

    Requires:
        - active is a bool (True to enter conversation mode, False to exit)
    """
    active: bool


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/conversation-mode/{session_id}",
    summary     = "Get conversation mode flag for a session",
    description = "Returns the conversation_mode_active flag from the cosa-voice session bridge file."
)
async def get_conversation_mode_endpoint(
    session_id: str,
    authenticated_user_id: Annotated[ str, Depends( require_api_key_or_jwt ) ]
) -> JSONResponse:
    """
    Read conversation_mode_active for the given Claude Code session_id.

    Requires:
        - session_id is a non-empty string (full UUID or 8-char prefix)
        - Caller is authenticated (JWT or API key)

    Ensures:
        - Returns 200 with {session_id, active: bool} when bridge exists
        - Returns 404 when no bridge file matches the session_id
        - Defaults active=False when bridge exists but flag is missing

    Args:
        session_id: Claude Code session ID to look up
        authenticated_user_id: Auth dependency (unused but required for gating)

    Returns:
        JSONResponse: {"session_id": str, "active": bool}
    """
    if not find_session_path_by_id( session_id ):
        raise HTTPException( status_code=404, detail=f"No active session bridge found for session_id={session_id}" )

    active = get_conversation_mode( session_id )
    return JSONResponse( content={ "session_id": session_id, "active": active } )


@router.post(
    "/conversation-mode/{session_id}",
    summary     = "Set conversation mode flag for a session",
    description = "Writes conversation_mode_active to the bridge file and broadcasts a conversation_mode_changed WebSocket event so all connected UI tabs sync."
)
async def set_conversation_mode_endpoint(
    session_id: str,
    body: ConversationModeBody,
    authenticated_user_id: Annotated[ str, Depends( require_api_key_or_jwt ) ],
    notification_queue: NotificationFifoQueue = Depends( get_notification_queue )
) -> JSONResponse:
    """
    Flip conversation_mode_active for the given session_id and broadcast.

    Requires:
        - session_id is a non-empty string (full UUID or 8-char prefix)
        - body.active is a bool
        - Caller is authenticated

    Ensures:
        - Writes conversation_mode_active to the matching bridge file
        - Returns 200 with {session_id, active, broadcast_delivered} on success
        - Returns 404 if no bridge matches
        - Returns 500 if bridge found but write failed
        - Broadcasts conversation_mode_changed event to the authenticated user's
          WebSocket sessions (other tabs of the same user). Broadcast failures are
          logged but do not fail the endpoint — the bridge write is the canonical
          state.

    Args:
        session_id: Claude Code session ID to flip
        body: { active: bool }
        authenticated_user_id: Auth dependency, also used as broadcast target
        ws_manager: WebSocketManager dependency

    Returns:
        JSONResponse: {"session_id", "active", "broadcast_delivered": bool}
    """
    if not find_session_path_by_id( session_id ):
        raise HTTPException( status_code=404, detail=f"No active session bridge found for session_id={session_id}" )

    # Mutual exclusion: when activating, scan for any OTHER session currently
    # holding conversation mode and displace them atomically. The lock makes
    # the scan + displace + activate sequence indivisible so two parallel
    # POSTs can't both end up "active." On deactivate (active=false), there's
    # nothing to coordinate, so we skip the lock to avoid needless contention.
    displaced_sessions = []

    if body.active:
        async with _conversation_mode_lock:
            others = find_active_conversation_sessions( exclude_session_id=session_id )
            for _other_path, other_sid in others:
                if not set_conversation_mode( other_sid, False ):
                    print( f"[CONVERSATION-MODE] ⚠️ Failed to displace session {other_sid} (bridge write failed)" )
                    continue
                displaced_sessions.append( other_sid )
                # Broadcast displaced event so the affected session's tabs flip
                # their toggle, unpin the card, and pause any in-flight TTS.
                # Routed through the canonical notification subsystem with a
                # custom type value (see 2026.04.29 ws-event-cleanup R&D doc).
                try:
                    notification_queue.push_notification(
                        message            = "",
                        type               = "conversation_mode_changed",
                        user_id            = authenticated_user_id,
                        sender_id          = build_sender_id_for_cc( other_sid ),
                        suppress_ding      = True,
                        response_requested = False,
                        payload            = {
                            "session_id"   : other_sid,
                            "active"       : False,
                            "displaced"    : True,
                            "displaced_by" : session_id
                        }
                    )
                except Exception as ws_err:
                    # Bridge write succeeded; broadcast is best-effort
                    print( f"[CONVERSATION-MODE] ⚠️ Displace-notify push failed for {other_sid}: {ws_err}" )

                # Action push: nudge the displaced session's listener to
                # inject the conversation-mode-exit system-reminder into
                # tmux. This corrects the model's in-context assumption
                # that conversation mode is still active — the bridge
                # flip alone is silent to the model. The listener filters
                # by 8-char job_id; cc_notification_listener._handle_action
                # routes title="action:exit_conversation_mode" through
                # _inject_exit_conversation_reminder which calls
                # hook_common.conv_mode_exit_reminder for the body.
                try:
                    notification_queue.push_notification(
                        message            = "",
                        type               = "user_initiated_message",
                        title              = "action:exit_conversation_mode",
                        user_id            = authenticated_user_id,
                        sender_id          = build_sender_id_for_cc( other_sid ),
                        job_id             = other_sid[:8],
                        suppress_ding      = True,
                        response_requested = False,
                    )
                except Exception as action_err:
                    # Listener push is best-effort; if it fails, the next
                    # user prompt will still hydrate correctly via the
                    # UserPromptSubmit hook reading the (now-false) bridge.
                    print( f"[CONVERSATION-MODE] ⚠️ Exit-action push failed for {other_sid}: {action_err}" )

            # Now activate ours inside the same critical section so no parallel
            # request can sneak in between displace and activate.
            ok = set_conversation_mode( session_id, body.active )
            if not ok:
                raise HTTPException( status_code=500, detail=f"Bridge write failed for session_id={session_id}" )
    else:
        ok = set_conversation_mode( session_id, body.active )
        if not ok:
            raise HTTPException( status_code=500, detail=f"Bridge write failed for session_id={session_id}" )

    # Route through the canonical notification subsystem with a custom type value.
    # See: src/rnd/v0.1.7/2026.04.29-ws-event-cleanup-to-custom-notification-types/01-design.md
    broadcast_delivered = False
    try:
        notification_queue.push_notification(
            message            = "",
            type               = "conversation_mode_changed",
            user_id            = authenticated_user_id,
            sender_id          = build_sender_id_for_cc( session_id ),
            suppress_ding      = True,
            response_requested = False,
            payload            = {
                "session_id" : session_id,
                "active"     : body.active
            }
        )
        broadcast_delivered = True
    except Exception as ws_err:
        # Log but do not fail — bridge write succeeded; broadcast is best-effort
        print( f"[CONVERSATION-MODE] ⚠️ Notification push failed for session {session_id}: {ws_err}" )

    return JSONResponse( content={
        "session_id"          : session_id,
        "active"              : body.active,
        "broadcast_delivered" : broadcast_delivered,
        "displaced_sessions"  : displaced_sessions
    } )
