#!/usr/bin/env python3
"""
Voice-First I/O Layer for COSA Podcast Generator Agent.

This module provides a unified interface for user interaction that:
1. PRIMARILY uses voice I/O via cosa_interface (TTS + voice input)
2. Automatically falls back to CLI text when voice is unavailable
3. Allows explicit --cli-mode override to force text interaction

This is a thin wrapper around the consolidated voice_io module in
cosa.agents.utils.voice_io, configured with the Podcast Generator
cosa_interface for proper sender identity.

Priority Order:
    1. Voice I/O (cosa_interface functions) - PRIMARY
    2. CLI fallback (print/input) - when voice unavailable
    3. --cli-mode flag - forces CLI regardless of voice availability
"""

import asyncio
import logging
from typing import Optional, List, Union

# Import the consolidated voice_io module
from cosa.agents.utils import voice_io as _core_voice_io

# Import this agent's cosa_interface for configuration
from . import cosa_interface as _cosa_interface

logger = logging.getLogger( __name__ )


# =============================================================================
# Module Initialization
# =============================================================================

# Configure the core voice_io with our cosa_interface
_core_voice_io.configure( _cosa_interface )


# =============================================================================
# Re-export Configuration Functions
# =============================================================================

def set_cli_mode( enabled: bool ) -> None:
    """
    Enable or disable forced CLI mode.

    When enabled, all interactions use CLI text (print/input)
    even if voice service is available.

    Requires:
        - enabled is a boolean

    Ensures:
        - Module state updated
        - Subsequent calls use appropriate mode

    Args:
        enabled: True to force CLI mode, False for voice-first
    """
    _core_voice_io.set_cli_mode( enabled )


def reset_voice_check() -> None:
    """
    Reset the cached voice availability check.

    Call this if the voice service status may have changed
    and you want to re-check availability.

    Ensures:
        - Next call to is_voice_available() will re-check
    """
    _core_voice_io.reset_voice_check()


async def is_voice_available() -> bool:
    """
    Check if voice service is available (result cached).

    Ensures:
        - Returns True if voice service responds
        - Returns False if voice service unavailable/fails
        - Result is cached for subsequent calls

    Returns:
        bool: True if voice service is available
    """
    return await _core_voice_io.is_voice_available()


def get_mode_description() -> str:
    """
    Get a human-readable description of the current I/O mode.

    Returns:
        str: Description of current mode
    """
    return _core_voice_io.get_mode_description()


# =============================================================================
# Re-export Voice-First I/O Functions
# =============================================================================

async def notify(
    message: str,
    priority: str = "medium",
    abstract: Optional[ str ] = None,
    session_name: Optional[ str ] = None,
    job_id: Optional[ str ] = None
) -> None:
    """
    Send a progress notification (voice-first).

    In voice mode: Plays TTS announcement
    In CLI mode: Prints to console

    Requires:
        - message is a non-empty string
        - priority is "low", "medium", "high", or "urgent"

    Ensures:
        - Message is communicated to user via appropriate channel
        - Never raises (logs warnings on failure)

    Args:
        message: The message to announce
        priority: Notification priority level
        abstract: Optional supplementary context (markdown, URLs, details)
        session_name: Optional human-readable session name for UI display
        job_id: Optional agentic job ID for routing to job cards (e.g., "pg-a1b2c3d4")
    """
    await _core_voice_io.notify( message, priority, abstract, session_name, job_id )


async def ask_yes_no(
    question: str,
    default: str = "no",
    timeout: int = 60,
    abstract: Optional[ str ] = None
) -> bool:
    """
    Ask a yes/no question (voice-first).

    In voice mode: Speaks question via TTS, waits for voice response
    In CLI mode: Prints question, waits for keyboard input

    Requires:
        - question is a non-empty string
        - default is "yes" or "no"
        - timeout is positive integer (1-600)

    Ensures:
        - Returns True if user said yes
        - Returns False if user said no
        - Returns default value on timeout or error

    Args:
        question: The yes/no question to ask
        default: Default answer if timeout ("yes" or "no")
        timeout: Seconds to wait for response
        abstract: Optional supplementary context (plan details, URLs, markdown)

    Returns:
        bool: True if user approved, False otherwise
    """
    return await _core_voice_io.ask_yes_no( question, default, timeout, abstract )


async def get_input(
    prompt: str,
    allow_empty: bool = True,
    timeout: int = 300
) -> Optional[ str ]:
    """
    Get open-ended input from user (voice-first).

    In voice mode: Speaks prompt via TTS, captures voice response
    In CLI mode: Prints prompt, waits for keyboard input

    Requires:
        - prompt is a non-empty string
        - timeout is positive integer (1-600)

    Ensures:
        - Returns user's text response on success
        - Returns None on timeout, error, or empty (if not allowed)

    Args:
        prompt: The prompt to present to user
        allow_empty: If True, empty response returns empty string
        timeout: Seconds to wait for response

    Returns:
        str or None: User's response, or None on timeout/error
    """
    return await _core_voice_io.get_input( prompt, allow_empty, timeout )


async def present_choices(
    questions: list,
    timeout: int = 120,
    title: Optional[ str ] = None,
    abstract: Optional[ str ] = None
) -> dict:
    """
    Present multiple-choice questions (voice-first).

    In voice mode: Uses TTS and voice UI
    In CLI mode: Prints numbered options, waits for number input

    Requires:
        - questions is a list of question objects
        - Each question has: question, header, multiSelect, options

    Ensures:
        - Returns dict with "answers" key containing selections
        - In CLI mode, returns first option on invalid input

    Args:
        questions: List of question objects with options
        timeout: Seconds to wait for response
        title: Optional title for the notification
        abstract: Optional supplementary context

    Returns:
        dict: {"answers": {...}} with selections keyed by header
    """
    return await _core_voice_io.present_choices( questions, timeout, title, abstract )


async def choose(
    question: str,
    options: Union[ List[ str ], List[ dict ] ],
    timeout: int = 120,
    allow_custom: bool = False
) -> str:
    """
    Present multiple-choice options (voice-first).

    In voice mode: Speaks options via TTS, captures voice selection
    In CLI mode: Prints numbered options, waits for number input

    Options can be provided in two formats:
    - List of strings: ["Option 1", "Option 2"]
    - List of dicts: [{"label": "...", "description": "..."}]

    Requires:
        - question is a non-empty string
        - options is a non-empty list of strings or dicts
        - timeout is positive integer (1-600)

    Ensures:
        - Returns one of the provided option labels (or custom input if allowed)
        - Returns first option as default on timeout/error

    Args:
        question: The question introducing the choices
        options: List of option strings or dicts with label/description
        timeout: Seconds to wait for response
        allow_custom: If True, user can provide custom input via "Other"

    Returns:
        str: The selected option label (or custom input)
    """
    return await _core_voice_io.choose( question, options, timeout, allow_custom )


# =============================================================================
# Re-export Progressive Narrowing Functions (now available to PG!)
# =============================================================================

async def select_themes(
    themes: list,
    timeout: int = 180
) -> list:
    """
    Present themes for multi-select and return selected theme indices.

    Requires:
        - themes is a list of {"name": str, "description": str, "subquery_indices": list}
        - At least 2 themes provided

    Ensures:
        - Returns list of selected theme indices (0-based)
        - Returns empty list if user cancels

    Args:
        themes: List of theme dicts from clustering response
        timeout: Seconds to wait for response

    Returns:
        list[int]: Selected theme indices (0-based)
    """
    return await _core_voice_io.select_themes( themes, timeout )


async def select_topics(
    topics: list,
    preselected: bool = True,
    timeout: int = 180
) -> list:
    """
    Present specific topics for refinement.

    Requires:
        - topics is a list of {"topic": str, "objective": str}

    Ensures:
        - Returns list of selected topic indices
        - Returns empty list if user cancels

    Args:
        topics: List of topic dicts (subqueries)
        preselected: Whether topics should be pre-selected (for deselection flow)
        timeout: Seconds to wait for response

    Returns:
        list[int]: Selected topic indices (0-based)
    """
    return await _core_voice_io.select_topics( topics, preselected, timeout )


# =============================================================================
# Backward Compatibility: Module-Level State Access
# =============================================================================

# For backward compatibility, expose the module state variables
# These are read-only views; use the functions above to modify state
@property
def _force_cli_mode():
    """Read-only access to CLI mode state."""
    return _core_voice_io._force_cli_mode

@property
def _voice_available():
    """Read-only access to voice availability state."""
    return _core_voice_io._voice_available


# =============================================================================
# Smoke Test
# =============================================================================

def quick_smoke_test():
    """Quick smoke test for Podcast Generator voice_io wrapper module."""
    import cosa.utils.util as cu

    cu.print_banner( "Podcast Generator Voice I/O Wrapper Smoke Test", prepend_nl=True )

    try:
        # Test 1: Module imports and configuration
        print( "Testing module configuration..." )
        assert _core_voice_io._cosa_interface is not None
        print( "✓ Core voice_io configured with cosa_interface" )

        # Test 2: set_cli_mode works
        print( "Testing set_cli_mode..." )
        set_cli_mode( True )
        assert _core_voice_io._force_cli_mode is True
        set_cli_mode( False )
        assert _core_voice_io._force_cli_mode is False
        print( "✓ set_cli_mode works correctly" )

        # Test 3: reset_voice_check works
        print( "Testing reset_voice_check..." )
        _core_voice_io._voice_available = True
        reset_voice_check()
        assert _core_voice_io._voice_available is None
        print( "✓ reset_voice_check works correctly" )

        # Test 4: get_mode_description works
        print( "Testing get_mode_description..." )
        _core_voice_io._voice_available = None
        set_cli_mode( True )
        desc = get_mode_description()
        assert "forced" in desc.lower()
        set_cli_mode( False )
        print( "✓ get_mode_description works correctly" )

        # Test 5: Async function signatures
        print( "Testing async function signatures..." )
        import inspect
        assert inspect.iscoroutinefunction( is_voice_available )
        assert inspect.iscoroutinefunction( notify )
        assert inspect.iscoroutinefunction( ask_yes_no )
        assert inspect.iscoroutinefunction( get_input )
        assert inspect.iscoroutinefunction( present_choices )
        assert inspect.iscoroutinefunction( choose )
        assert inspect.iscoroutinefunction( select_themes )
        assert inspect.iscoroutinefunction( select_topics )
        print( "✓ All async functions have correct signatures" )

        # Test 6: notify now has job_id parameter (NEW!)
        print( "Testing notify() has job_id parameter (NEW!)..." )
        sig = inspect.signature( notify )
        assert "job_id" in sig.parameters
        print( "✓ notify() now supports job_id parameter" )

        # Test 7: choose() is now available (NEW!)
        print( "Testing choose() is now available (NEW!)..." )
        sig = inspect.signature( choose )
        params = list( sig.parameters.keys() )
        assert "options" in params
        assert "allow_custom" in params
        print( "✓ choose() now available with Union[List[str], List[dict]] support" )

        # Test 8: present_choices has title and abstract params
        print( "Testing present_choices() parameters..." )
        sig = inspect.signature( present_choices )
        assert "title" in sig.parameters
        assert "abstract" in sig.parameters
        print( "✓ present_choices() supports title and abstract parameters" )

        # Test 9: select_themes and select_topics now available (NEW!)
        print( "Testing select_themes and select_topics are now available (NEW!)..." )
        assert inspect.iscoroutinefunction( select_themes )
        assert inspect.iscoroutinefunction( select_topics )
        print( "✓ select_themes() and select_topics() now available" )

        # Test 10: CLI mode fallback
        print( "Testing CLI mode fallback..." )
        set_cli_mode( True )

        async def test_cli_fallback():
            mode = get_mode_description()
            assert "forced" in mode.lower()

        asyncio.run( test_cli_fallback() )
        set_cli_mode( False )
        print( "✓ CLI mode fallback configured correctly" )

        # Reset state
        _core_voice_io._voice_available = None

        print( "\n✓ Podcast Generator voice_io wrapper smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
