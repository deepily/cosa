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

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..middleware.api_key_auth import require_api_key_or_jwt
from ..websocket_manager import WebSocketManager

# Bridge helpers live in the parent Lupin tree, but importing them is fine
# (only git ops on src/cosa/ are restricted from parent context — imports are not).
from lupin_cli.claude_code.hooks.lib.session_bridge import (
    get_conversation_mode, set_conversation_mode, find_session_path_by_id
)


router = APIRouter( prefix="/api/cosa-voice", tags=[ "cosa-voice" ] )


# ── Dependency injection (mirrors notifications.router pattern) ──────────────

def get_websocket_manager():
    """
    Dependency to get the global WebSocketManager from main module.

    Ensures:
        - Returns the singleton WebSocketManager instance
        - Raises ImportError if main module not yet initialized
    """
    import fastapi_app.main as main_module
    return main_module.websocket_manager


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
    ws_manager: WebSocketManager = Depends( get_websocket_manager )
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

    ok = set_conversation_mode( session_id, body.active )
    if not ok:
        raise HTTPException( status_code=500, detail=f"Bridge write failed for session_id={session_id}" )

    broadcast_delivered = False
    try:
        broadcast_delivered = await ws_manager.emit_to_user(
            authenticated_user_id,
            "conversation_mode_changed",
            {
                "session_id"               : session_id,
                "conversation_mode_active" : body.active
            }
        )
    except Exception as ws_err:
        # Log but do not fail — bridge write succeeded; broadcast is best-effort
        print( f"[CONVERSATION-MODE] ⚠️ WS broadcast failed for session {session_id}: {ws_err}" )

    return JSONResponse( content={
        "session_id"          : session_id,
        "active"              : body.active,
        "broadcast_delivered" : broadcast_delivered
    } )
