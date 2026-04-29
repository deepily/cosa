"""
Per-session voice persona endpoints.

Each new Claude Code session is uniformly randomly assigned a voice/persona
at SessionStart from a 6-voice allocatable pool so the user can audibly
distinguish parallel sessions in the notifications UI accordion. Sam (the
global ElevenLabs default) is reserved as the system-wide TTS default voice
and is NOT in the allocatable pool.

The bridge file at ~/.claude/sessions/cc-{PPID}.json is the canonical state.
This module mirrors `conversation_mode.py` structurally:
    - module-level asyncio.Lock for atomic scan→pick→write
    - dependency-injected ConfigurationManager + WebSocketManager
    - bridge file is ground truth, WS broadcast is best-effort confirmation
    - dead-PID bridges are filtered on every read (implicit sweeper)

Endpoints:
    GET  /api/cosa-voice/voice-persona/{session_id}            — read current persona
    POST /api/cosa-voice/voice-persona/{session_id}/allocate   — atomic claim
    POST /api/cosa-voice/voice-persona/{session_id}/release    — clear bridge field
    GET  /api/cosa-voice/voice-persona/pool                    — diagnostics snapshot

Orthogonal to conversation mode v1.1: a session can have a persona
regardless of conversation_mode_active state, and conversation mode's
mutex-1 displacement does NOT touch the voice_persona field.

See: src/rnd/v0.1.7/2026.04.28-per-session-voice-personas/01-design.md
"""

import asyncio
from typing import Annotated

from fastapi          import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..middleware.api_key_auth import require_api_key_or_jwt
from ..websocket_manager       import WebSocketManager

from lupin_cli.claude_code.hooks.lib.session_bridge import (
    get_voice_persona, set_voice_persona, find_active_voice_persona_sessions,
    find_session_path_by_id
)

from ..voice_persona_helpers import (
    load_persona_pool_from_config, allocate_persona_for_session
)


router = APIRouter( prefix="/api/cosa-voice", tags=[ "cosa-voice" ] )

# Module-level lock serializes scan→pick→write so two parallel /allocate
# calls can't both pick the same persona. Single-process uvicorn assumed
# (same caveat as conversation_mode addendum §11). On /release there is
# nothing to coordinate, so we skip the lock for that path.
_voice_persona_lock = asyncio.Lock()


# ── Dependency injection ─────────────────────────────────────────────────────

def get_websocket_manager():
    """Dependency to get the global WebSocketManager from main module."""
    import fastapi_app.main as main_module
    return main_module.websocket_manager


def get_config_manager():
    """Dependency to get a ConfigurationManager with the standard env var."""
    from cosa.config.configuration_manager import ConfigurationManager
    return ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/voice-persona/pool",
    summary     = "Pool snapshot — allocatable pool, occupied names, free slots",
    description = "Returns the configured pool plus current occupancy. Diagnostics endpoint; does not allocate."
)
async def get_voice_persona_pool(
    authenticated_user_id: Annotated[ str, Depends( require_api_key_or_jwt ) ],
    config_mgr = Depends( get_config_manager )
) -> JSONResponse:
    """
    Return the configured pool, the set of currently-occupied persona names,
    and the names that are free for allocation right now.

    Live-PID dead-bridge filter applies (so a stale persona on a dead-PID
    bridge counts as free).
    """
    pool   = load_persona_pool_from_config( config_mgr )
    active = find_active_voice_persona_sessions()

    occupied_names = sorted( {
        p[ "name" ] for _path, _sid, p in active
        if isinstance( p, dict ) and p.get( "name" )
    } )
    free_names = [ p[ "name" ] for p in pool if p[ "name" ] not in occupied_names ]

    return JSONResponse( content={
        "pool"           : pool,
        "occupied_names" : occupied_names,
        "free_names"     : free_names,
        "active_sessions": [
            { "session_id": sid, "persona_name": p.get( "name" ), "borrowed": p.get( "borrowed", False ) }
            for _path, sid, p in active
            if isinstance( p, dict )
        ]
    } )


@router.get(
    "/voice-persona/{session_id}",
    summary     = "Read voice persona for a session",
    description = "Returns the voice_persona dict from the cosa-voice session bridge file, or null when none is set."
)
async def get_voice_persona_endpoint(
    session_id           : str,
    authenticated_user_id: Annotated[ str, Depends( require_api_key_or_jwt ) ]
) -> JSONResponse:
    """
    Read voice_persona from the bridge for the given session_id.
    """
    if not find_session_path_by_id( session_id ):
        raise HTTPException( status_code=404, detail=f"No active session bridge found for session_id={session_id}" )

    persona = get_voice_persona( session_id )
    return JSONResponse( content={ "session_id": session_id, "voice_persona": persona } )


@router.post(
    "/voice-persona/{session_id}/allocate",
    summary     = "Allocate a voice persona for a session",
    description = "Idempotent: if a persona is already set on the bridge, returns it without re-allocating. Otherwise atomically picks the first uniform-random unallocated persona and writes it to the bridge."
)
async def allocate_voice_persona_endpoint(
    session_id           : str,
    authenticated_user_id: Annotated[ str, Depends( require_api_key_or_jwt ) ],
    ws_manager           : WebSocketManager = Depends( get_websocket_manager ),
    config_mgr           = Depends( get_config_manager )
) -> JSONResponse:
    """
    Atomically allocate a persona for the given session.

    Idempotency: if the bridge already has a non-null voice_persona, return
    it as-is (no re-allocation, no broadcast). This is the SessionStart hook
    contract — calling /allocate is safe to repeat across hook invocations.
    """
    if not find_session_path_by_id( session_id ):
        raise HTTPException( status_code=404, detail=f"No active session bridge found for session_id={session_id}" )

    # Idempotency check — if already allocated, return existing persona
    existing = get_voice_persona( session_id )
    if existing is not None:
        return JSONResponse( content={
            "session_id"          : session_id,
            "voice_persona"       : existing,
            "newly_allocated"     : False,
            "broadcast_delivered" : False
        } )

    async with _voice_persona_lock:
        # Re-check inside the lock to avoid a race where two requests both
        # passed the outer idempotency check.
        existing = get_voice_persona( session_id )
        if existing is not None:
            return JSONResponse( content={
                "session_id"          : session_id,
                "voice_persona"       : existing,
                "newly_allocated"     : False,
                "broadcast_delivered" : False
            } )

        persona = allocate_persona_for_session( config_mgr, session_id )
        if persona is None:
            raise HTTPException(
                status_code=500,
                detail="Voice persona pool is empty or misconfigured (check `cc session voice persona pool` in lupin-app.ini)"
            )

        ok = set_voice_persona( session_id, persona )
        if not ok:
            raise HTTPException( status_code=500, detail=f"Bridge write failed for session_id={session_id}" )

    broadcast_delivered = False
    try:
        broadcast_delivered = await ws_manager.emit_to_user(
            authenticated_user_id,
            "voice_persona_assigned",
            {
                "session_id"    : session_id,
                "voice_persona" : persona
            }
        )
    except Exception as ws_err:
        # Log but do not fail — bridge write succeeded; broadcast is best-effort
        print( f"[VOICE-PERSONA] ⚠️ WS broadcast failed for session {session_id}: {ws_err}" )

    return JSONResponse( content={
        "session_id"          : session_id,
        "voice_persona"       : persona,
        "newly_allocated"     : True,
        "broadcast_delivered" : broadcast_delivered
    } )


@router.post(
    "/voice-persona/{session_id}/release",
    summary     = "Release the voice persona allocated to a session",
    description = "Clears the voice_persona field on the bridge and broadcasts a voice_persona_released event."
)
async def release_voice_persona_endpoint(
    session_id           : str,
    authenticated_user_id: Annotated[ str, Depends( require_api_key_or_jwt ) ],
    ws_manager           : WebSocketManager = Depends( get_websocket_manager )
) -> JSONResponse:
    """
    Release the persona for the given session (clear bridge field).

    Idempotent: clearing an already-empty slot returns 200 with released=False.
    """
    if not find_session_path_by_id( session_id ):
        raise HTTPException( status_code=404, detail=f"No active session bridge found for session_id={session_id}" )

    existing = get_voice_persona( session_id )
    if existing is None:
        return JSONResponse( content={
            "session_id"          : session_id,
            "released"            : False,
            "broadcast_delivered" : False
        } )

    ok = set_voice_persona( session_id, None )
    if not ok:
        raise HTTPException( status_code=500, detail=f"Bridge write failed for session_id={session_id}" )

    broadcast_delivered = False
    try:
        broadcast_delivered = await ws_manager.emit_to_user(
            authenticated_user_id,
            "voice_persona_released",
            {
                "session_id"             : session_id,
                "released_persona_name"  : existing.get( "name" )
            }
        )
    except Exception as ws_err:
        print( f"[VOICE-PERSONA] ⚠️ WS release-broadcast failed for session {session_id}: {ws_err}" )

    return JSONResponse( content={
        "session_id"          : session_id,
        "released"            : True,
        "released_persona"    : existing,
        "broadcast_delivered" : broadcast_delivered
    } )
