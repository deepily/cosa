#!/usr/bin/env python3
"""
Configuration for the Notification Proxy Agent.

Defines test profiles with pre-configured answers for expediter questions,
agent defaults, and connection parameters.

Test profiles map argument names to auto-answers so the proxy can respond
deterministically to known expediter question patterns.
"""

import os


# ============================================================================
# Connection Defaults
# ============================================================================

DEFAULT_SERVER_HOST = "localhost"
DEFAULT_SERVER_PORT = 7999
DEFAULT_EMAIL       = "mock.tester@lupin.deepily.ai"
DEFAULT_SESSION_ID  = "auto proxy"
DEFAULT_PROFILE     = "deep_research"

# WebSocket subscription events
SUBSCRIBED_EVENTS = [
    "notification_queue_update",
    "job_state_transition",
    "sys_ping"
]


# ============================================================================
# Reconnection Parameters
# ============================================================================

RECONNECT_INITIAL_DELAY = 1.0     # seconds
RECONNECT_MAX_DELAY     = 30.0    # seconds
RECONNECT_MAX_ATTEMPTS  = 10
RECONNECT_BACKOFF_FACTOR = 2.0


# ============================================================================
# LLM Fallback Configuration
# ============================================================================

LLM_FALLBACK_MODEL      = "claude-sonnet-4-5-20250929"
LLM_FALLBACK_MAX_TOKENS = 500


# ============================================================================
# Test Profiles
# ============================================================================

TEST_PROFILES = {
    "deep_research" : {
        "description" : "Auto-answer for deep research agent expediter questions",
        "query"            : "quantum computing breakthroughs 2026",
        "budget"           : "no limit",
        "audience"         : "academic",
        "audience_context" : "none",
    },
    "podcast" : {
        "description" : "Auto-answer for podcast generator expediter questions",
        "research"         : "latest",
        "audience"         : "general",
        "audience_context" : "none",
        "languages"        : "en",
    },
    "research_to_podcast" : {
        "description" : "Auto-answer for research-to-podcast chained workflow",
        "query"            : "artificial intelligence safety research 2026",
        "budget"           : "no limit",
        "audience"         : "academic",
        "audience_context" : "none",
        "languages"        : "en,es-MX",
    },
    "all_agents" : {
        "description"      : "Union profile for automated 9-scenario testing across all agents",
        "query"            : "quantum computing breakthroughs 2026",
        "budget"           : "no limit",
        "audience"         : "academic",
        "audience_context" : "none",
        "research"         : "/tmp/mock-research-document.md",
        "languages"        : "en",
    },
    "minimal" : {
        "description" : "Bare minimum answers — required args only, skip optionals",
        "query"    : "test query for automated proxy",
        "research" : "latest",
    },
}


# ============================================================================
# Known Expediter Sender IDs
# ============================================================================

EXPEDITER_SENDER_ID = "arg.expeditor@lupin.deepily.ai"


# ============================================================================
# Credential Resolution
# ============================================================================

def get_credentials( cli_email=None, cli_password=None ):
    """
    Resolve login credentials with 2-tier priority: CLI > env vars.

    Requires:
        - At least one source provides both email and password

    Ensures:
        - Returns ( email, password ) tuple
        - Raises ValueError if either credential cannot be resolved

    Priority:
        1. CLI flags ( --email / --password )
        2. LUPIN_TEST_INTERACTIVE_MOCK_JOBS_EMAIL / LUPIN_TEST_INTERACTIVE_MOCK_JOBS_PASSWORD

    Raises:
        ValueError: If email or password cannot be resolved from any source
    """
    # --- Email resolution ---
    email = (
        cli_email
        or os.environ.get( "LUPIN_TEST_INTERACTIVE_MOCK_JOBS_EMAIL" )
    )

    if not email:
        raise ValueError(
            "No email found. Set one of:\n"
            "  --email <addr>                                (CLI flag)\n"
            "  LUPIN_TEST_INTERACTIVE_MOCK_JOBS_EMAIL=<addr>  (env var)"
        )

    # --- Password resolution ---
    password = (
        cli_password
        or os.environ.get( "LUPIN_TEST_INTERACTIVE_MOCK_JOBS_PASSWORD" )
    )

    if not password:
        raise ValueError(
            "No password found. Set one of:\n"
            "  --password <pw>                                  (CLI flag)\n"
            "  LUPIN_TEST_INTERACTIVE_MOCK_JOBS_PASSWORD=<pw>   (env var)"
        )

    return email, password


# ============================================================================
# API Key Resolution
# ============================================================================

def get_anthropic_api_key():
    """
    Resolve Anthropic API key using the firewalled pattern.

    Requires:
        - ANTHROPIC_API_KEY_FIREWALLED env var is set, OR
        - src/conf/keys/anthropic-api-key-firewalled file exists

    Ensures:
        - Returns API key string on success
        - Returns None if no key found

    Returns:
        str or None: Anthropic API key
    """
    # Priority 1: Environment variable
    key = os.environ.get( "ANTHROPIC_API_KEY_FIREWALLED" )
    if key:
        return key

    # Priority 2: Local file
    try:
        import cosa.utils.util as cu
        key = cu.get_api_key( "anthropic-api-key-firewalled" )
        if key:
            return key
    except Exception:
        pass

    return None


# ============================================================================
# Smoke Test
# ============================================================================

def quick_smoke_test():
    """Quick smoke test for config module."""
    print( "\n" + "=" * 60 )
    print( "Notification Proxy Config Smoke Test" )
    print( "=" * 60 )

    tests_passed = 0
    tests_failed = 0

    # Test 1: Profiles exist
    print( "\n1. Testing profile structure..." )
    try:
        assert len( TEST_PROFILES ) >= 3, f"Expected >= 3 profiles, got {len( TEST_PROFILES )}"
        for name, profile in TEST_PROFILES.items():
            assert "description" in profile, f"Profile '{name}' missing description"
            print( f"   ✓ Profile '{name}': {profile[ 'description' ]}" )
        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Test 2: Connection defaults
    print( "\n2. Testing connection defaults..." )
    try:
        assert DEFAULT_SERVER_PORT == 7999
        assert DEFAULT_EMAIL == "mock.tester@lupin.deepily.ai"
        assert len( SUBSCRIBED_EVENTS ) >= 3
        print( f"   ✓ Server: {DEFAULT_SERVER_HOST}:{DEFAULT_SERVER_PORT}" )
        print( f"   ✓ Email: {DEFAULT_EMAIL}" )
        print( f"   ✓ Events: {SUBSCRIBED_EVENTS}" )
        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Test 3: API key resolution
    print( "\n3. Testing API key resolution..." )
    try:
        key = get_anthropic_api_key()
        if key:
            print( f"   ✓ API key found ({len( key )} chars, source: env or file)" )
        else:
            print( "   ⚠ No API key found (LLM fallback will be unavailable)" )
        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Summary
    print( f"\n{'=' * 60}" )
    print( f"Config Smoke Test: {tests_passed} passed, {tests_failed} failed" )
    print( "=" * 60 )
    return tests_failed == 0


if __name__ == "__main__":
    success = quick_smoke_test()
    exit( 0 if success else 1 )
