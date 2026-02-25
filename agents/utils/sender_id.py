#!/usr/bin/env python3
"""
Shared Sender ID Construction for COSA Agent Notifications.

Provides project detection from the current working directory and
sender_id string construction. Used by all agent cosa_interface/
notification_profile modules and the MCP server.

The sender_id format is: {agent_type}@{project}.deepily.ai[#{suffix}]

Examples:
    deep.research@lupin.deepily.ai
    podcast.gen@lupin.deepily.ai#cli
    swe.lead@lupin.deepily.ai#abc123
    claude.code@lupin.deepily.ai#a1b2c3d4
"""

import os


def detect_project() -> str:
    """
    Detect project name from current working directory.

    Requires:
        - Current working directory is accessible

    Ensures:
        - Returns lowercase project name
        - Checks more specific paths first (cosa before lupin)
        - Falls back to basename of cwd if no known project pattern

    Known project patterns (checked in order):
        - /cosa (standalone, not nested in lupin) -> "cosa"
        - /planning-is-prompting -> "plan"
        - /lupin -> "lupin"
        - anything else -> basename of cwd

    Returns:
        str: Detected project name
    """
    cwd = os.getcwd().lower()

    # CoSA detection (standalone only — not nested inside lupin)
    if "/cosa" in cwd and "/lupin" not in cwd:
        return "cosa"

    # Planning-is-Prompting detection
    if "/planning-is-prompting" in cwd:
        return "plan"

    # Lupin project (includes nested cosa subdirectory)
    if "/lupin" in cwd:
        return "lupin"

    return os.path.basename( os.getcwd() ).lower()


def build_sender_id( agent_type: str, project: str = None, suffix: str = None ) -> str:
    """
    Construct a sender_id string for notification routing.

    Requires:
        - agent_type is a non-empty string (e.g., "deep.research", "swe.lead")

    Ensures:
        - Returns sender_id in format: {agent_type}@{project}.deepily.ai[#{suffix}]
        - If project is None, auto-detects from cwd
        - If suffix is provided, appends #{suffix}

    Args:
        agent_type: The agent identifier prefix (e.g., "deep.research", "podcast.gen")
        project: Project name override (None = auto-detect from cwd)
        suffix: Optional suffix after # (e.g., session hash, "cli")

    Returns:
        str: Fully-qualified sender_id string

    Examples:
        build_sender_id( "deep.research" )
            -> "deep.research@lupin.deepily.ai"

        build_sender_id( "podcast.gen", suffix="cli" )
            -> "podcast.gen@lupin.deepily.ai#cli"

        build_sender_id( "swe.lead", project="lupin", suffix="abc123" )
            -> "swe.lead@lupin.deepily.ai#abc123"
    """
    if project is None:
        project = detect_project()

    base = f"{agent_type}@{project}.deepily.ai"

    if suffix:
        return f"{base}#{suffix}"

    return base


def quick_smoke_test():
    """Quick smoke test for sender_id module."""
    import cosa.utils.util as cu

    cu.print_banner( "Sender ID Utilities Smoke Test", prepend_nl=True )

    try:
        # Test 1: detect_project returns a string
        print( "Testing detect_project..." )
        project = detect_project()
        assert isinstance( project, str )
        assert len( project ) > 0
        print( f"  Detected project: {project}" )

        # Test 2: build_sender_id basic
        print( "Testing build_sender_id (basic)..." )
        sid = build_sender_id( "deep.research" )
        assert "deep.research@" in sid
        assert ".deepily.ai" in sid
        print( f"  Basic: {sid}" )

        # Test 3: build_sender_id with suffix
        print( "Testing build_sender_id (with suffix)..." )
        sid = build_sender_id( "podcast.gen", suffix="cli" )
        assert sid.endswith( "#cli" )
        print( f"  With suffix: {sid}" )

        # Test 4: build_sender_id with explicit project
        print( "Testing build_sender_id (explicit project)..." )
        sid = build_sender_id( "swe.lead", project="testproject", suffix="abc123" )
        assert "swe.lead@testproject.deepily.ai#abc123" == sid
        print( f"  Explicit: {sid}" )

        # Test 5: build_sender_id without suffix
        print( "Testing build_sender_id (no suffix)..." )
        sid = build_sender_id( "claude.code.job", project="lupin" )
        assert sid == "claude.code.job@lupin.deepily.ai"
        assert "#" not in sid
        print( f"  No suffix: {sid}" )

        print( "\n  Sender ID utilities smoke test completed successfully" )

    except Exception as e:
        print( f"\n  Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
