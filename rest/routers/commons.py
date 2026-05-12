"""
Commons broadcast endpoints.

Per AC1 + AC2 + AC3 + AC4 + AC5 + AC14 of
src/rnd/v0.1.7/2026.05.09-inter-session-commons/03-phase2-user-broadcast-design.md.

**Template**: `src/cosa/rest/routers/conversation_mode.py` (per F4 REUSE).

Two endpoints:
- `GET /api/commons/active-sessions` — recipient-preview chip-row data
- `POST /api/commons/broadcast-to-cc-sessions` — fanout to active CC sessions

Design split:
- **Pure-logic helpers** (this module's `_*` and `*` non-route functions) are in
  the 100% coverage gate. All take dependencies explicitly — no module-level
  side effects, no FastAPI plumbing.
- **Route handlers** are thin dispatchers — they pull singletons from the module
  state and delegate to the helpers. Route bodies are `# pragma: no cover`'d to
  keep the gate enforceable from unit tests alone (per AC12: "endpoint
  integration tests do NOT contribute to the gate").
"""

import hashlib
import json
import re
import time
import uuid
from typing import Annotated, Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cosa.rest.commons_ack_watcher import CommonsAckWatcher
from cosa.rest.commons_rate_limiter import CommonsBroadcastRateLimiter
from cosa.rest.middleware.api_key_auth import require_api_key_or_jwt
from lupin_cli.claude_code.hooks.lib.session_bridge import (
    build_sender_id_for_cc,
    find_active_voice_persona_sessions,
)
from lupin_mcp.commons_store import CommonsStore

router = APIRouter( prefix="/api/commons", tags=[ "commons" ] )


# ─── Module-level state — initialized at FastAPI startup (step 8) ───────────

_commons_store        : Optional[ CommonsStore ]                  = None
_commons_rate_limiter : Optional[ CommonsBroadcastRateLimiter ]   = None
_commons_ack_watcher  : Optional[ CommonsAckWatcher ]             = None
# Threshold for "active enough to receive a broadcast" — set at startup from INI.
_active_session_threshold_seconds : float = 600.0


def init_commons_state(
    store                              : CommonsStore,
    rate_limiter                       : CommonsBroadcastRateLimiter,
    ack_watcher                        : CommonsAckWatcher,
    active_session_threshold_seconds   : float,
) -> None:
    """Wire singletons at FastAPI startup. Idempotent for testing."""
    global _commons_store, _commons_rate_limiter, _commons_ack_watcher, _active_session_threshold_seconds
    _commons_store                    = store
    _commons_rate_limiter             = rate_limiter
    _commons_ack_watcher              = ack_watcher
    _active_session_threshold_seconds = float( active_session_threshold_seconds )


# ─── Pydantic models ────────────────────────────────────────────────────────


class BroadcastRequestBody( BaseModel ):
    """POST /broadcast-to-cc-sessions request body."""
    message            : str
    broadcast_id       : Optional[ str ] = None
    require_ack        : bool            = True
    include_originator : bool            = True


# ─── Pure-logic helpers (in 100% coverage gate) ─────────────────────────────


_UUIDV4_RE = re.compile( r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE )

_SYSTEM_REMINDER_OPEN_LC  = "<system-reminder>"
_SYSTEM_REMINDER_CLOSE_LC = "</system-reminder>"


def _body_contains_reminder_framing( body: str ) -> bool:
    """True if body has literal `<system-reminder>` / `</system-reminder>` (case-insensitive) — per T1."""
    lowered = body.lower()
    return _SYSTEM_REMINDER_OPEN_LC in lowered or _SYSTEM_REMINDER_CLOSE_LC in lowered


def validate_broadcast_body( message: Optional[ str ] ) -> Tuple[ bool, Optional[ str ] ]:
    """
    Validate the broadcast `message` field. Returns (valid, error_detail).
    Per AC1: empty/whitespace → 400; system-reminder substring → 400.
    """
    if not isinstance( message, str ) or not message.strip():
        return ( False, "message body is required" )
    if _body_contains_reminder_framing( message ):
        return ( False, "message must not contain system-reminder framing tags" )
    return ( True, None )


def validate_broadcast_id( broadcast_id: Optional[ str ] ) -> Tuple[ bool, Optional[ str ] ]:
    """
    Validate caller-supplied `broadcast_id`. None is allowed (server generates).
    Per AC1: invalid UUIDv4 shape → 400.
    """
    if broadcast_id is None:
        return ( True, None )
    if not isinstance( broadcast_id, str ) or not _UUIDV4_RE.match( broadcast_id ):
        return ( False, "broadcast_id must be a UUIDv4" )
    return ( True, None )


def build_pseudo_sender_id( user_id: str ) -> str:
    """
    Build the server-pseudo-sender-id used for `broadcasts` topic posts.
    Per AC4 + F8: `broadcast-<8-hex-of-sha256(user_id)>`. Hyphen, NEVER `@`
    (would fail `commons_store._HEADER_RE` round-trip).
    """
    digest = hashlib.sha256( user_id.encode( "utf-8" ) ).hexdigest()[ :8 ]
    return f"broadcast-{digest}"


def _load_bridge_fields( bridge_path: Any ) -> Optional[ Dict[ str, Any ] ]:
    """
    Open a bridge file and return its content as dict, or None on failure.
    Extracted so unit tests can mock at the source.
    """
    try:
        with open( bridge_path ) as f:
            return json.load( f )
    except ( json.JSONDecodeError, OSError ):
        return None


def _bridge_last_activity_epoch( bridge: Dict[ str, Any ] ) -> Optional[ float ]:
    """
    Extract the bridge's last-activity epoch seconds. Tries common field names;
    returns None if unparseable. Defensive against schema drift.
    """
    for field in ( "last_activity_epoch", "last_activity", "updated_at" ):
        val = bridge.get( field )
        if isinstance( val, ( int, float ) ):
            return float( val )
    return None


def project_session_response(
    session_id   : str,
    persona      : Dict[ str, Any ],
    bridge       : Dict[ str, Any ],
) -> Dict[ str, Any ]:
    """
    Build the response dict for one session per AC2 + T8.

    **NEVER includes the bridge Path or any filesystem-derived field.**
    Only these fields are exposed: session_id, persona_name, persona_icon,
    persona_color, last_seen_iso, conversation_mode_active.
    """
    last_seen_iso = bridge.get( "last_activity_iso" ) or bridge.get( "updated_at_iso" )
    return {
        "session_id"               : session_id,
        "persona_name"             : persona.get( "name" ),
        "persona_icon"             : persona.get( "icon" ),
        "persona_color"            : persona.get( "color" ),
        "last_seen_iso"            : last_seen_iso,
        "conversation_mode_active" : bool( bridge.get( "conversation_mode_active", False ) ),
    }


def filter_and_project_sessions(
    raw_sessions                      : List[ Tuple[ Any, str, Dict[ str, Any ] ] ],
    authenticated_user_id             : str,
    active_session_threshold_seconds  : float,
    now_epoch                         : float,
    bridge_loader                     : Callable[ [ Any ], Optional[ Dict[ str, Any ] ] ],
    originator_session_id             : Optional[ str ] = None,
    include_originator                : bool            = True,
) -> List[ Dict[ str, Any ] ]:
    """
    Apply all AC2 filters + T7 + T8 projection to the raw 3-tuple list.

    1. Open each bridge via `bridge_loader` — skip on parse fail
    2. Filter by `user_id == authenticated_user_id` (T7 + Q9 same-user scoping)
    3. Filter by last-activity age (newer than threshold)
    4. Optionally exclude originator's session (when `include_originator=False`)
    5. Project to response shape via `project_session_response` (T8 — no Path leak)
    """
    out: List[ Dict[ str, Any ] ] = [ ]
    for path, sid, persona in raw_sessions:
        bridge = bridge_loader( path )
        if bridge is None:
            continue
        if bridge.get( "user_id" ) != authenticated_user_id:
            continue
        last_epoch = _bridge_last_activity_epoch( bridge )
        if last_epoch is not None and ( now_epoch - last_epoch ) > active_session_threshold_seconds:
            continue
        if not include_originator and originator_session_id is not None and sid == originator_session_id:
            continue
        out.append( project_session_response( sid, persona, bridge ) )
    return out


def perform_fanout(
    broadcast_id          : str,
    message               : str,
    sessions              : List[ Dict[ str, Any ] ],
    sender_user_id        : str,
    store                 : CommonsStore,
    notification_queue    : Any,
    build_sender_id       : Callable[ [ str ], Optional[ str ] ],
) -> Tuple[ int, List[ str ] ]:
    """
    Per-recipient fanout: post to `broadcasts` topic + push `action:broadcast_received` notification.

    Per AC4 + AC5 + F10 (per-recipient failure isolation): if `push_notification`
    fails for recipient K, log + continue. Returns `(successful_count, failed_recipient_sids)`.
    """
    pseudo_sid = build_pseudo_sender_id( sender_user_id )
    successful = 0
    failed: List[ str ] = [ ]
    for s in sessions:
        target_sid = s[ "session_id" ]
        # AC4: per-recipient broadcasts entry
        try:
            store.post(
                topic             = "broadcasts",
                body              = message,
                sender_session_id = pseudo_sid,
                persona_name      = "System Broadcast",
                persona_icon      = "📢",
                persona_color     = "#FFC107",
                metadata          = {
                    "broadcast_id"     : broadcast_id,
                    "target_session_id": target_sid,
                    "sender_user_id"   : sender_user_id,
                },
            )
        except Exception:
            failed.append( target_sid )
            continue
        # AC5: per-session listener notification
        try:
            notification_queue.push_notification(
                message            = "",
                type               = "user_initiated_message",
                title              = "action:broadcast_received",
                sender_id          = build_sender_id( target_sid ),
                job_id             = target_sid[ :8 ],
                user_id            = sender_user_id,
                suppress_ding      = True,
                response_requested = False,
                payload            = {
                    "broadcast_id"   : broadcast_id,
                    "body"           : message,
                    "sender_user_id" : sender_user_id,
                },
            )
            successful += 1
        except Exception:
            failed.append( target_sid )
    return ( successful, failed )


def execute_broadcast(
    *,
    authenticated_user_id              : str,
    body                               : BroadcastRequestBody,
    store                              : CommonsStore,
    rate_limiter                       : CommonsBroadcastRateLimiter,
    ack_watcher                        : CommonsAckWatcher,
    notification_queue                 : Any,
    active_session_threshold_seconds   : float,
    raw_sessions_fn                    : Callable[ [ ], List[ Tuple[ Any, str, Dict[ str, Any ] ] ] ],
    bridge_loader                      : Callable[ [ Any ], Optional[ Dict[ str, Any ] ] ],
    build_sender_id                    : Callable[ [ str ], Optional[ str ] ],
    now_epoch_fn                       : Callable[ [ ], float ] = time.time,
) -> Dict[ str, Any ]:
    """
    Full broadcast execution pipeline — pure-logic core of the POST endpoint.

    Returns a dict with one of these shapes:
      {"http_status": 400, "detail": "..."}
      {"http_status": 429, "retry_after": float}
      {"http_status": 409, "detail": "broadcast_id collision"}
      {"http_status": 200, "broadcast_id": "...", "recipients": int, "failed_recipients": [...], "status": "..."}

    Raises nothing — all error states are returned as dicts for the route
    handler to translate into FastAPI responses.
    """
    # AC1: body validation
    ok, err = validate_broadcast_body( body.message )
    if not ok:
        return { "http_status": 400, "detail": err }
    ok, err = validate_broadcast_id( body.broadcast_id )
    if not ok:
        return { "http_status": 400, "detail": err }

    # AC3: rate limit
    allowed, retry_after = rate_limiter.check_and_record( authenticated_user_id )
    if not allowed:
        return { "http_status": 429, "retry_after": retry_after }

    # AC1 + T9: atomic register (collision → 409)
    broadcast_id = body.broadcast_id or str( uuid.uuid4() )
    if body.require_ack:
        try:
            ack_watcher.register_broadcast( broadcast_id, authenticated_user_id, expected_recipients=0 )
        except ValueError:
            return { "http_status": 409, "detail": "broadcast_id collision" }

    # AC2: enumerate + filter recipients
    sessions = filter_and_project_sessions(
        raw_sessions                     = raw_sessions_fn(),
        authenticated_user_id            = authenticated_user_id,
        active_session_threshold_seconds = active_session_threshold_seconds,
        now_epoch                        = now_epoch_fn(),
        bridge_loader                    = bridge_loader,
        originator_session_id            = None,
        include_originator               = body.include_originator,
    )

    # AC2 / Q14: zero recipients
    if not sessions:
        if body.require_ack:
            ack_watcher.unregister_broadcast( broadcast_id )
        return {
            "http_status"       : 200,
            "broadcast_id"      : broadcast_id,
            "recipients"        : 0,
            "failed_recipients" : [ ],
            "status"            : "no-active-sessions",
        }

    # AC4 + AC5: fanout
    successful, failed_recipients = perform_fanout(
        broadcast_id       = broadcast_id,
        message            = body.message,
        sessions           = sessions,
        sender_user_id     = authenticated_user_id,
        store              = store,
        notification_queue = notification_queue,
        build_sender_id    = build_sender_id,
    )

    # Update expected_recipients on in-flight entry now that we know N
    if body.require_ack:
        entry = ack_watcher._in_flight.get( broadcast_id )
        if entry is not None:
            entry.expected_recipients = len( sessions )

    return {
        "http_status"       : 200,
        "broadcast_id"      : broadcast_id,
        "recipients"        : successful,
        "failed_recipients" : failed_recipients,
        "status"            : "queued",
    }


# ─── Dependency-injection accessors ─────────────────────────────────────────


def get_notification_queue():   # pragma: no cover
    """DI: return the singleton NotificationFifoQueue from main module."""
    import fastapi_app.main as main_module
    return main_module.jobs_notification_queue


def _require_initialized():   # pragma: no cover
    """Raise if commons singletons not yet wired (step 8 wires them at app startup)."""
    if _commons_store is None or _commons_rate_limiter is None or _commons_ack_watcher is None:
        raise HTTPException( status_code=503, detail="commons subsystem not initialized" )


# ─── Route handlers (thin — # pragma: no cover) ─────────────────────────────


@router.get(
    "/active-sessions",
    summary     = "List active CC sessions belonging to the authenticated user",
    description = "Returns same-user-scoped active sessions with persona info for the broadcast recipient preview.",
)
async def get_active_sessions(   # pragma: no cover
    authenticated_user_id: Annotated[ str, Depends( require_api_key_or_jwt ) ],
) -> JSONResponse:
    _require_initialized()
    sessions = filter_and_project_sessions(
        raw_sessions                     = find_active_voice_persona_sessions(),
        authenticated_user_id            = authenticated_user_id,
        active_session_threshold_seconds = _active_session_threshold_seconds,
        now_epoch                        = time.time(),
        bridge_loader                    = _load_bridge_fields,
        originator_session_id            = None,
        include_originator               = True,
    )
    return JSONResponse( content={ "sessions": sessions } )


@router.post(
    "/broadcast-to-cc-sessions",
    summary     = "Fan out a broadcast to active CC sessions belonging to the authenticated user",
    description = "Posts a per-recipient `broadcasts` entry + a per-session listener notification for each active CC session belonging to the caller. Returns the broadcast_id + recipient count + any failed recipients.",
)
async def post_broadcast_to_cc_sessions(   # pragma: no cover
    body: BroadcastRequestBody,
    authenticated_user_id: Annotated[ str, Depends( require_api_key_or_jwt ) ],
    notification_queue=Depends( get_notification_queue ),
) -> JSONResponse:
    _require_initialized()
    result = execute_broadcast(
        authenticated_user_id            = authenticated_user_id,
        body                             = body,
        store                            = _commons_store,
        rate_limiter                     = _commons_rate_limiter,
        ack_watcher                      = _commons_ack_watcher,
        notification_queue               = notification_queue,
        active_session_threshold_seconds = _active_session_threshold_seconds,
        raw_sessions_fn                  = find_active_voice_persona_sessions,
        bridge_loader                    = _load_bridge_fields,
        build_sender_id                  = build_sender_id_for_cc,
    )
    http_status = result.pop( "http_status" )
    if http_status == 429:
        retry_after = result[ "retry_after" ]
        raise HTTPException(
            status_code = 429,
            detail      = "rate limit exceeded",
            headers     = { "Retry-After": str( int( retry_after ) + 1 ) },
        )
    if http_status >= 400:
        raise HTTPException( status_code=http_status, detail=result[ "detail" ] )
    return JSONResponse( status_code=200, content=result )
