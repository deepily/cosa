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
from typing import Annotated, Optional

import httpx
from fastapi          import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic         import BaseModel

import cosa.utils.util as du

from ..middleware.api_key_auth import require_api_key_or_jwt
from ..notification_fifo_queue import NotificationFifoQueue

from lupin_cli.claude_code.hooks.lib.session_bridge import (
    get_voice_persona, set_voice_persona, find_active_voice_persona_sessions,
    find_session_path_by_id, build_sender_id_for_cc
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

def get_notification_queue():
    """Dependency to get the singleton NotificationFifoQueue from main module."""
    import fastapi_app.main as main_module
    return main_module.jobs_notification_queue


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
    previous_persona_name: Optional[ str ] = None,
    notification_queue   : NotificationFifoQueue = Depends( get_notification_queue ),
    config_mgr           = Depends( get_config_manager )
) -> JSONResponse:
    """
    Atomically allocate a persona for the given session.

    Idempotency: if the bridge already has a non-null voice_persona, return
    it as-is (no re-allocation, no broadcast). This is the SessionStart hook
    contract — calling /allocate is safe to repeat across hook invocations.

    When `previous_persona_name` is supplied AND a new persona is actually
    allocated (newly_allocated=True), an additional "Voice re-assigned: X → Y"
    notification is pushed so the user hears the handoff spoken in the new
    voice. Used by the SessionStart hook on /clear-with-overwrite to make
    voice changes audible rather than silent.
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

    # Route through the canonical notification subsystem with a custom type value
    # rather than inventing a new top-level WS event. The notification arrives at
    # the client as `notification_queue_update` carrying notification.type =
    # "voice_persona_assigned"; the client dispatches inside handleNotificationUpdate.
    # See: src/rnd/v0.1.7/2026.04.29-ws-event-cleanup-to-custom-notification-types/01-design.md
    broadcast_delivered = False
    try:
        notification_queue.push_notification(
            message            = "",
            type               = "voice_persona_assigned",
            user_id            = authenticated_user_id,
            sender_id          = build_sender_id_for_cc( session_id ),
            voice_persona      = persona,
            suppress_ding      = True,
            response_requested = False,
            payload            = { "session_id": session_id }
        )
        broadcast_delivered = True
    except Exception as ws_err:
        # Log but do not fail — bridge write succeeded; broadcast is best-effort
        print( f"[VOICE-PERSONA] ⚠️ Notification push failed for session {session_id}: {ws_err}" )

    # When the SessionStart hook detected an unpreserved persona handoff, push
    # a user-facing announcement so the voice change is audible — pre-empts
    # the "wait, why does this sound different?" confusion. Best-effort.
    if previous_persona_name:
        try:
            notification_queue.push_notification(
                message            = f"Voice re-assigned: {previous_persona_name} → {persona[ 'display_name' ]}",
                type               = "task",
                priority           = "medium",
                user_id            = authenticated_user_id,
                sender_id          = build_sender_id_for_cc( session_id ),
                voice_persona      = persona,
                suppress_ding      = False,
                response_requested = False
            )
        except Exception as ws_err:
            print( f"[VOICE-PERSONA] ⚠️ Re-assigned announcement push failed for session {session_id}: {ws_err}" )

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
    notification_queue   : NotificationFifoQueue = Depends( get_notification_queue )
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

    # Route through the canonical notification subsystem with a custom type value.
    # See: src/rnd/v0.1.7/2026.04.29-ws-event-cleanup-to-custom-notification-types/01-design.md
    broadcast_delivered = False
    try:
        notification_queue.push_notification(
            message            = "",
            type               = "voice_persona_released",
            user_id            = authenticated_user_id,
            sender_id          = build_sender_id_for_cc( session_id ),
            voice_persona      = { "name": existing.get( "name" ), "released": True },
            suppress_ding      = True,
            response_requested = False,
            payload            = { "session_id": session_id }
        )
        broadcast_delivered = True
    except Exception as ws_err:
        print( f"[VOICE-PERSONA] ⚠️ Notification push failed for session {session_id}: {ws_err}" )

    return JSONResponse( content={
        "session_id"          : session_id,
        "released"            : True,
        "released_persona"    : existing,
        "broadcast_delivered" : broadcast_delivered
    } )


# ── Voice sample endpoint (reference page) ───────────────────────────────────

class VoicePersonaSampleRequest( BaseModel ):
    voice_id: str
    text    : str


@router.post(
    "/voice-persona/sample",
    summary     = "Synthesize a voice sample for the persona-reference page",
    description = "Returns audio/mpeg bytes inline. The voice_id MUST belong to the configured persona pool — arbitrary voice_ids are rejected so this endpoint cannot be used as a general-purpose TTS oracle.",
    responses   = {
        200: { "content": { "audio/mpeg": {} } },
        400: { "description": "voice_id is not in the configured persona pool" },
        503: { "description": "ElevenLabs API unavailable or returned an error" }
    }
)
async def voice_persona_sample(
    authenticated_user_id: Annotated[ str, Depends( require_api_key_or_jwt ) ],
    body                 : VoicePersonaSampleRequest = Body( ... ),
    config_mgr           = Depends( get_config_manager )
) -> Response:
    """
    Synthesize a short voice sample for the dev-tools persona-reference page.

    Why a separate endpoint (vs. /api/get-speech-elevenlabs): the existing
    streaming TTS path delivers PCM chunks over WebSocket and requires an
    open audio session — appropriate for the live notification UI but heavy
    for a static reference page that just needs to play six sample clips.
    This endpoint calls the ElevenLabs HTTP TTS API and returns the audio
    as a single response body, so the page can `<audio>.src = blobURL` it.

    Pool-membership check: the voice_id must match an entry in the
    configured persona pool (`cc session voice persona pool` in
    lupin-app.ini). This prevents the endpoint from being used to burn
    ElevenLabs quota on arbitrary voice_ids.

    Requires:
        - body.voice_id is a non-empty string
        - body.text is a non-empty string
        - voice_id matches an entry in load_persona_pool_from_config(config_mgr)
        - ElevenLabs API key is reachable via du.get_api_key("eleven11")

    Ensures:
        - Returns 200 + audio/mpeg bytes on success
        - Returns 400 if voice_id is not in pool
        - Returns 503 if ElevenLabs upstream fails
        - Never raises (all paths return Response or JSONResponse)
    """
    if not body.voice_id or not body.text:
        raise HTTPException( status_code=400, detail="voice_id and text are both required" )

    pool      = load_persona_pool_from_config( config_mgr )
    pool_ids  = { p[ "voice_id" ] for p in pool if p.get( "voice_id" ) }
    if body.voice_id not in pool_ids:
        raise HTTPException(
            status_code=400,
            detail=f"voice_id {body.voice_id!r} is not in the configured persona pool. Allowed: {sorted( pool_ids )}"
        )

    api_key = du.get_api_key( "eleven11" )
    if not api_key:
        raise HTTPException( status_code=503, detail="ElevenLabs API key not available on server" )

    # Match the streaming path's defaults so the reference samples sound
    # representative of what the live notification UI plays. Profile keys
    # mirror the "balanced" profile from speech.py:846-855.
    model_id          = config_mgr.get( "elevenlabs tts default model",          default="eleven_turbo_v2_5", silent=True )
    stability         = config_mgr.get( "elevenlabs tts profile balanced stability",         default=0.5, return_type="float", silent=True )
    similarity_boost  = config_mgr.get( "elevenlabs tts profile balanced similarity boost",  default=0.8, return_type="float", silent=True )

    url     = f"https://api.elevenlabs.io/v1/text-to-speech/{body.voice_id}"
    headers = {
        "xi-api-key"   : api_key,
        "accept"       : "audio/mpeg",
        "Content-Type" : "application/json"
    }
    payload = {
        "text"           : body.text,
        "model_id"       : model_id,
        "voice_settings" : {
            "stability"        : stability,
            "similarity_boost" : similarity_boost
        }
    }

    try:
        async with httpx.AsyncClient( timeout=30.0 ) as client:
            r = await client.post( url, headers=headers, json=payload )
    except httpx.HTTPError as e:
        raise HTTPException( status_code=503, detail=f"ElevenLabs request failed: {e}" )

    if r.status_code != 200:
        # Surface a redacted snippet of the upstream body so the user can
        # diagnose (e.g., quota exceeded, voice not found) without exposing
        # internal headers.
        snippet = r.text[ :200 ] if r.text else "(empty)"
        raise HTTPException(
            status_code=503,
            detail=f"ElevenLabs returned {r.status_code}: {snippet}"
        )

    return Response(
        content    = r.content,
        media_type = "audio/mpeg",
        headers    = { "Cache-Control": "no-store" }
    )
