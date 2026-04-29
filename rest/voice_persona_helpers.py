"""
Pure-function helpers for per-session voice persona allocation.

This module composes (a) ConfigurationManager reads of the [Voice Personas]
INI block and (b) bridge-file scans from session_bridge.find_active_voice_persona_sessions
into the higher-level allocation primitives used by the voice_persona router:

    - load_persona_pool_from_config()  → list of persona dicts (Sam excluded)
    - pick_unallocated_persona()       → uniform random draw, falls back to borrow
    - borrowed_persona_for_sid()       → deterministic hash-modulo fallback
    - allocate_persona_for_session()   → end-to-end composition (config → scan → pick → return)

The router holds the asyncio.Lock; this module is purely functional and
synchronous. The bridge file is the single source of truth — no in-memory
registry, no separate sweeper. Pool occupancy is freshly computed per call by
scanning live-PID bridge files.

Sam is intentionally NOT in the pool. He is the system-wide TTS default
voice (see `elevenlabs tts default voice id` in lupin-app.ini), used by the
speech router for any request lacking a voice_id. Treat him as permanently
allocated to the server itself.

See: src/rnd/v0.1.7/2026.04.28-per-session-voice-personas/01-design.md
"""

import hashlib
import random
from datetime  import datetime, timezone
from typing    import List, Optional, Set, Dict, Any


PoolPersona = Dict[ str, Any ]


def load_persona_pool_from_config( config_mgr ) -> List[ PoolPersona ]:
    """
    Read the [Voice Personas] INI block and return the allocatable pool.

    Reads `cc session voice persona pool` (comma-separated names) and for each
    name reads the four required keys: voice id, icon, color, profile.

    Requires:
        - config_mgr is an initialized ConfigurationManager instance

    Ensures:
        - Returns a list of persona dicts in the order specified by the pool key
        - Each dict has keys: name, voice_id, icon, color, profile
        - Personas with missing or empty voice_id are skipped (logged via
          ConfigurationManager's silent=False default)
        - Returns an empty list if the pool key is missing or empty
        - Never raises on a single bad entry — skips it and continues

    Args:
        config_mgr: ConfigurationManager (already constructed by caller)

    Returns:
        list[dict]: Allocatable pool, ordered as in INI
    """
    pool_csv = config_mgr.get( "cc session voice persona pool", default="", silent=True )
    if not pool_csv:
        return []

    names = [ n.strip() for n in pool_csv.split( "," ) if n.strip() ]
    pool  = []

    for name in names:
        prefix   = f"cc session voice persona {name}"
        voice_id = config_mgr.get( f"{prefix} voice id", default="", silent=True )
        icon     = config_mgr.get( f"{prefix} icon",     default="🎙️", silent=True )
        color    = config_mgr.get( f"{prefix} color",    default="#888888", silent=True )
        profile  = config_mgr.get( f"{prefix} profile",  default="", silent=True )

        if not voice_id:
            # Pool entry has no voice_id — skip silently rather than poison allocation
            continue

        pool.append( {
            "name"     : name,
            "voice_id" : voice_id,
            "icon"     : icon,
            "color"    : color,
            "profile"  : profile
        } )

    return pool


def borrowed_persona_for_sid(
    pool             : List[ PoolPersona ],
    stable_session_id: str
) -> Optional[ PoolPersona ]:
    """
    Deterministic hash-modulo persona pick for the pool-exhausted case.

    When all personas are allocated to live sessions, fall back to a
    deterministic borrowed slot keyed on stable_session_id. Determinism
    means the same session always borrows the same voice across server
    restarts and across pool-exhaustion events.

    Uses sha256 (not Python's built-in hash()) because the latter is
    non-deterministic across processes by default (PYTHONHASHSEED).

    Requires:
        - pool is a non-empty list
        - stable_session_id is a non-empty string

    Ensures:
        - Returns a NEW dict with keys: name, voice_id, icon, color, profile, borrowed=True
        - Never raises on valid inputs
        - Returns None when pool is empty or stable_session_id is empty

    Args:
        pool: The full pool (NOT pool minus occupied — borrowing intentionally
            reuses an in-use voice)
        stable_session_id: Session id used as deterministic seed

    Returns:
        dict or None: Borrowed persona with borrowed=True, or None if invalid input
    """
    if not pool or not stable_session_id:
        return None

    digest_bytes = hashlib.sha256( stable_session_id.encode( "utf-8" ) ).digest()
    idx          = int.from_bytes( digest_bytes[:8], "big" ) % len( pool )
    base         = pool[ idx ]

    return {
        "name"     : base[ "name" ],
        "voice_id" : base[ "voice_id" ],
        "icon"     : base[ "icon" ],
        "color"    : base[ "color" ],
        "profile"  : base[ "profile" ],
        "borrowed" : True
    }


def pick_unallocated_persona(
    pool             : List[ PoolPersona ],
    occupied_names   : Set[ str ],
    stable_session_id: str
) -> Optional[ PoolPersona ]:
    """
    Uniform random draw from (pool − occupied), falling back to borrow on exhaustion.

    Requires:
        - pool is a list (may be empty)
        - occupied_names is a set of name strings (case-sensitive match against pool entries)
        - stable_session_id is a non-empty string

    Ensures:
        - Returns a fresh dict with borrowed=False when (pool − occupied) is non-empty,
          chosen uniformly at random
        - Returns a borrowed=True dict (via borrowed_persona_for_sid) when all
          personas are occupied
        - Returns None only when pool itself is empty (misconfiguration)
        - Never raises

    Args:
        pool: Full allocatable pool (Sam excluded — he's the system default)
        occupied_names: Names currently allocated to live sessions
        stable_session_id: Used both as anti-collision seed and for borrow determinism

    Returns:
        dict or None: Allocated persona, or None if pool is empty
    """
    if not pool:
        return None

    free = [ p for p in pool if p[ "name" ] not in occupied_names ]

    if not free:
        return borrowed_persona_for_sid( pool, stable_session_id )

    chosen = random.choice( free )

    return {
        "name"     : chosen[ "name" ],
        "voice_id" : chosen[ "voice_id" ],
        "icon"     : chosen[ "icon" ],
        "color"    : chosen[ "color" ],
        "profile"  : chosen[ "profile" ],
        "borrowed" : False
    }


def allocate_persona_for_session(
    config_mgr,
    stable_session_id: str
) -> Optional[ PoolPersona ]:
    """
    End-to-end allocation: read pool, scan occupied, pick free (or borrow).

    This is the function the voice_persona router endpoint calls inside its
    asyncio.Lock critical section. It composes load_persona_pool_from_config
    + find_active_voice_persona_sessions (from session_bridge) + pick.

    The returned persona has an `assigned_at` ISO-8601 UTC timestamp added.

    Requires:
        - config_mgr is an initialized ConfigurationManager
        - stable_session_id is a non-empty string

    Ensures:
        - Returns a complete persona dict ready for bridge write, or None if
          the pool is empty (misconfiguration)
        - Adds an `assigned_at` field with current UTC ISO-8601 timestamp
        - Never raises on bridge-scan failures (the bridge module catches them)

    Args:
        config_mgr: ConfigurationManager
        stable_session_id: Session being allocated

    Returns:
        dict or None: persona with all 7 fields, or None if pool is empty
    """
    # Imported here to keep this module importable even when run from a
    # context where session_bridge isn't yet on PYTHONPATH. The router
    # always has it, so this is just a defensive ergonomic.
    from lupin_cli.claude_code.hooks.lib.session_bridge import find_active_voice_persona_sessions

    pool = load_persona_pool_from_config( config_mgr )
    if not pool:
        return None

    active   = find_active_voice_persona_sessions()
    occupied = { p[ "name" ] for _path, _sid, p in active if isinstance( p, dict ) and p.get( "name" ) }

    persona = pick_unallocated_persona( pool, occupied, stable_session_id )
    if persona is None:
        return None

    persona[ "assigned_at" ] = datetime.now( timezone.utc ).isoformat( timespec="seconds" )

    return persona


# ── Quick smoke test ─────────────────────────────────────────────────────────

def quick_smoke_test():
    """
    Self-contained smoke test for the pure functions.

    Tests pick_unallocated_persona and borrowed_persona_for_sid against
    synthetic pools, covering: empty pool, fully-free, partially-occupied,
    fully-occupied (borrow path), borrow determinism.

    Does NOT test allocate_persona_for_session (requires bridge files +
    config_mgr — covered by unit tests with mocks).
    """
    print( "Voice persona helpers smoke test" )
    print( "================================" )

    pool = [
        { "name": "Nora",    "voice_id": "v1", "icon": "🌸", "color": "#E91E63", "profile": "" },
        { "name": "Quentin", "voice_id": "v2", "icon": "🦉", "color": "#FFA000", "profile": "" },
        { "name": "Rachel",  "voice_id": "v3", "icon": "🕊️", "color": "#4CAF50", "profile": "" }
    ]

    # Test 1: empty pool → None
    assert pick_unallocated_persona( [], set(), "sid-1" ) is None, "Empty pool returns None"

    # Test 2: fully free, all picks come from pool with borrowed=False
    random.seed( 42 )
    picks = [ pick_unallocated_persona( pool, set(), f"sid-{i}" ) for i in range( 10 ) ]
    assert all( p is not None for p in picks ), "All picks should succeed"
    assert all( p[ "borrowed" ] is False for p in picks ), "None borrowed when fully free"
    assert all( p[ "name" ] in { "Nora", "Quentin", "Rachel" } for p in picks ), "Picks within pool"

    # Test 3: 2/3 occupied → must pick the remaining one
    free_pick = pick_unallocated_persona( pool, { "Nora", "Quentin" }, "sid-x" )
    assert free_pick is not None and free_pick[ "name" ] == "Rachel" and free_pick[ "borrowed" ] is False
    print( "  ✓ Allocation respects occupied set" )

    # Test 4: fully occupied → borrow path
    borrowed = pick_unallocated_persona( pool, { "Nora", "Quentin", "Rachel" }, "sid-borrow-1" )
    assert borrowed is not None, "Borrow returns a persona, not None"
    assert borrowed[ "borrowed" ] is True, "Borrow flag is True"
    assert borrowed[ "name" ] in { "Nora", "Quentin", "Rachel" }, "Borrow stays in pool"
    print( f"  ✓ Borrow path engaged on exhaustion (got {borrowed[ 'name' ]} borrowed=True)" )

    # Test 5: borrow determinism — same sid → same voice across calls
    b1 = borrowed_persona_for_sid( pool, "deterministic-sid" )
    b2 = borrowed_persona_for_sid( pool, "deterministic-sid" )
    assert b1 == b2, "Borrow is deterministic for same sid"
    b3 = borrowed_persona_for_sid( pool, "different-sid" )
    # Different sid usually picks different voice, but with pool=3 there's a
    # 1/3 collision chance — assert weakly: the function ran and returned valid
    assert b3 is not None and b3[ "borrowed" ] is True
    print( "  ✓ Borrow is deterministic for same stable_session_id" )

    # Test 6: borrowed_persona_for_sid edge cases
    assert borrowed_persona_for_sid( [],   "sid" ) is None, "Empty pool → None"
    assert borrowed_persona_for_sid( pool, ""    ) is None, "Empty sid → None"

    print( "\nAll voice persona helpers smoke tests: ✓ passed" )


if __name__ == "__main__":
    quick_smoke_test()
