"""
Server-side daemon that tails the `broadcast-acks` topic and pushes
`commons_broadcast_ack` custom notifications to the originating user.

Per AC7 + T9 (Pass 2) + F3 (REUSE) of
src/rnd/v0.1.7/2026.05.09-inter-session-commons/03-phase2-user-broadcast-design.md.

**In-flight broadcast tracker semantics** (T9 + AC7):
- Entries are added by `POST /api/commons/broadcast-to-cc-sessions` via
  `register_broadcast(bid, originating_user_id, expected_recipients)`
- The check-and-register operation is atomic under `self._lock` — prevents
  TOCTOU race between concurrent inserts with the same caller-supplied UUID
- TTL: 5 minutes from registration (matches AC9's UI auto-dismiss window).
  Expired entries are pruned lazily on each `_tick()`
- Lookup uses `is_in_flight(bid)` — returns False once TTL elapses or after
  explicit `unregister_broadcast(bid)`

**Watcher daemon thread** (F3 REUSE template — same shape as
`commons_archival.CommonsArchiver`):
- `threading.Event` stop signal
- `threading.Thread(daemon=True, name="CommonsAckWatcher")`
- `while not stop_event.wait(timeout=interval): try: tick(); except: log + continue`

**Startup `last_seen_ts`**: initialized to the timestamp of the LAST ack
entry already in `broadcast-acks` at watcher-start, so historical acks
don't replay to the UI on every restart.
"""

import threading
import time
from typing import Any, Callable, Dict, Optional

from lupin_mcp.commons_store import CommonsStore


_BROADCAST_ACKS_TOPIC      = "broadcast-acks"
_DEFAULT_TTL_SECONDS       = 300.0
_DEFAULT_POLL_INTERVAL     = 1.0
_READ_LIMIT_PER_TICK       = 10000


class _InFlightEntry:
    """Per-broadcast tracking state. Plain data — no methods."""
    def __init__(
        self,
        originating_user_id : str,
        expected_recipients : int,
        expires_at_monotonic: float,
    ):
        self.originating_user_id  = originating_user_id
        self.expected_recipients  = expected_recipients
        self.expires_at_monotonic = expires_at_monotonic
        self.received_acks        = 0


class CommonsAckWatcher:
    """
    Daemon thread + in-flight broadcast tracker for ack fanout.

    Requires:
        - `store` is a `CommonsStore` rooted at `<LUPIN_ROOT>/io/commons`
        - `push_notification_fn` is a callable matching `NotificationFifoQueue.push_notification`'s kwargs interface
        - `poll_interval_seconds` is a positive float (default 1.0)
        - `in_flight_ttl_seconds` is a positive float (default 300.0)

    Ensures:
        - `register_broadcast(bid, user_id, expected)` atomically inserts; raises ValueError on collision
        - `_tick()` reads since `last_seen_ts`, fires push for each matching in-flight broadcast, prunes expired entries
        - `start()` / `stop()` spawn / signal the daemon
        - All state mutation is guarded by `self._lock`
    """

    def __init__(
        self,
        store                  : CommonsStore,
        push_notification_fn   : Callable[ ..., Any ],
        poll_interval_seconds  : float = _DEFAULT_POLL_INTERVAL,
        in_flight_ttl_seconds  : float = _DEFAULT_TTL_SECONDS,
        debug                  : bool  = False,
    ):
        self.store                  = store
        self.push_notification_fn   = push_notification_fn
        self.poll_interval_seconds  = float( poll_interval_seconds )
        self.in_flight_ttl_seconds  = float( in_flight_ttl_seconds )
        self.debug                  = debug

        self._in_flight: Dict[ str, _InFlightEntry ] = { }
        self._lock                  = threading.Lock()
        self._last_seen_ts: Optional[ str ] = None
        self._stop_event            = threading.Event()
        self._thread: Optional[ threading.Thread ] = None
        self._initialized_last_seen = False

    # ─── In-flight tracker public API ───────────────────────────────────────

    def register_broadcast( self, broadcast_id: str, originating_user_id: str, expected_recipients: int ) -> None:
        """
        Atomic insert-or-raise (per T9). Raises `ValueError` if `broadcast_id`
        is already in flight — the endpoint translates this to HTTP 409.
        """
        now = time.monotonic()
        with self._lock:
            self._prune_expired_locked( now )
            if broadcast_id in self._in_flight:
                raise ValueError( f"broadcast_id collision: {broadcast_id}" )
            self._in_flight[ broadcast_id ] = _InFlightEntry(
                originating_user_id  = originating_user_id,
                expected_recipients  = expected_recipients,
                expires_at_monotonic = now + self.in_flight_ttl_seconds,
            )

    def unregister_broadcast( self, broadcast_id: str ) -> None:
        """Manual cleanup. Silent on unknown id."""
        with self._lock:
            self._in_flight.pop( broadcast_id, None )

    def is_in_flight( self, broadcast_id: str ) -> bool:
        """True if the broadcast is registered AND not expired."""
        with self._lock:
            self._prune_expired_locked( time.monotonic() )
            return broadcast_id in self._in_flight

    def _prune_expired_locked( self, now_monotonic: float ) -> None:
        """Remove entries past their TTL. Caller MUST hold self._lock."""
        expired = [ bid for bid, entry in self._in_flight.items() if entry.expires_at_monotonic <= now_monotonic ]
        for bid in expired:
            del self._in_flight[ bid ]

    # ─── Daemon lifecycle ───────────────────────────────────────────────────

    def start( self ) -> None:
        """Initialize last_seen_ts (if not yet) and spawn the daemon thread. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return
        if not self._initialized_last_seen:
            self._initialize_last_seen_ts()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target = self._run_loop,
            daemon = True,
            name   = "CommonsAckWatcher",
        )
        self._thread.start()

    def stop( self, join_timeout: Optional[ float ] = 5.0 ) -> None:
        """Signal stop + join. Safe to call on never-started watcher."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join( timeout=join_timeout )

    def _initialize_last_seen_ts( self ) -> None:
        """
        On first start, set `_last_seen_ts` to the timestamp of the LAST existing
        ack entry — so historical acks (from a prior watcher run) don't replay
        when the server restarts. Per AC7 startup-cursor semantics.
        """
        try:
            entries = self.store.read( _BROADCAST_ACKS_TOPIC, limit=1 )
            if entries:
                self._last_seen_ts = entries[ 0 ][ "ts" ]
        except Exception as e:
            if self.debug: print( f"[CommonsAckWatcher] startup _last_seen_ts init failed: {e}" )
        self._initialized_last_seen = True

    def _run_loop( self ) -> None:
        """Daemon body — call _tick() every poll_interval until stop signal."""
        while not self._stop_event.wait( timeout=self.poll_interval_seconds ):
            try:
                self.tick()
            except Exception as e:
                if self.debug: print( f"[CommonsAckWatcher] tick raised: {e}" )

    # ─── Tick (single poll iteration; extracted for unit-testing) ───────────

    def tick( self ) -> int:
        """
        Single poll iteration.

        Reads new ack entries since `_last_seen_ts`, fires push for each
        entry whose `metadata.broadcast_id` is in flight, prunes expired
        in-flight entries.

        Returns the number of acks dispatched (for testability).
        """
        try:
            entries = self.store.read(
                _BROADCAST_ACKS_TOPIC,
                since = self._last_seen_ts,
                limit = _READ_LIMIT_PER_TICK,
            )
        except FileNotFoundError:
            return 0

        dispatched = 0
        latest_ts = self._last_seen_ts
        for entry in entries:
            metadata     = entry.get( "metadata", { } ) or { }
            broadcast_id = metadata.get( "broadcast_id" )
            entry_ts     = entry.get( "ts" )

            if entry_ts is not None and ( latest_ts is None or entry_ts > latest_ts ):
                latest_ts = entry_ts

            if not broadcast_id:
                continue

            with self._lock:
                self._prune_expired_locked( time.monotonic() )
                inflight = self._in_flight.get( broadcast_id )
                if inflight is None:
                    continue
                inflight.received_acks += 1
                user_id  = inflight.originating_user_id

            self._push_ack_event( entry, broadcast_id, user_id, metadata )
            dispatched += 1

        if latest_ts is not None and latest_ts != self._last_seen_ts:
            self._last_seen_ts = latest_ts

        return dispatched

    def _push_ack_event(
        self,
        entry        : Dict[ str, Any ],
        broadcast_id : str,
        user_id      : str,
        metadata     : Dict[ str, Any ],
    ) -> None:
        """Fire the `commons_broadcast_ack` notification for one ack."""
        try:
            self.push_notification_fn(
                message            = "",
                type               = "commons_broadcast_ack",
                user_id            = user_id,
                suppress_ding      = True,
                response_requested = False,
                payload            = {
                    "broadcast_id"  : broadcast_id,
                    "session_id"    : entry.get( "sender_session_id" ),
                    "persona_name"  : entry.get( "persona_name" ),
                    "persona_icon"  : entry.get( "persona_icon" ),
                    "persona_color" : entry.get( "persona_color" ),
                    "status"        : metadata.get( "status" ),
                    "body_summary"  : metadata.get( "body_summary", "" ),
                },
            )
        except Exception as e:
            if self.debug: print( f"[CommonsAckWatcher] push failed for {broadcast_id}: {e}" )
