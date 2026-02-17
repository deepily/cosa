#!/usr/bin/env python3
"""
Voice-First I/O Layer for COSA SWE Team Agent.

Thin wrapper around the consolidated voice_io module in
cosa.agents.utils.voice_io, configured with the SWE Team
cosa_interface for proper sender identity.

Priority Order:
    1. Voice I/O (cosa_interface functions) - PRIMARY
    2. CLI fallback (print/input) - when voice unavailable
    3. --cli-mode flag - forces CLI regardless of voice availability

CONTRACT:
    This module is for standalone/CLI usage when the orchestrator is
    NOT involved. It provides a simplified voice-first interface:
    - notify(), ask_yes_no(), get_input(), choose(), present_choices()
    - Automatic voice availability detection with CLI fallback
    - No role-aware sender IDs (uses the configured cosa_interface internally)

    Use this module when:
    - Building standalone CLI tools or scripts
    - Working outside the orchestrator's execution loop
    - You want automatic voice/CLI mode switching

    Do NOT use this module for:
    - Orchestrator-internal notifications (use cosa_interface.py instead)
    - Anything that needs role-specific sender IDs or job_id routing

    See also: cosa_interface.py — orchestrator notification layer with role-aware routing
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

    Requires:
        - enabled is a boolean

    Ensures:
        - Subsequent calls use appropriate mode

    Args:
        enabled: True to force CLI mode, False for voice-first
    """
    _core_voice_io.set_cli_mode( enabled )


def reset_voice_check() -> None:
    """
    Reset the cached voice availability check.

    Ensures:
        - Next call to is_voice_available() will re-check
    """
    _core_voice_io.reset_voice_check()


async def is_voice_available() -> bool:
    """
    Check if voice service is available (result cached).

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
    job_id: Optional[ str ] = None,
    queue_name: Optional[ str ] = None
) -> None:
    """
    Send a progress notification (voice-first).

    Requires:
        - message is a non-empty string
        - priority is "low", "medium", "high", or "urgent"

    Ensures:
        - Message is communicated via appropriate channel
        - Never raises

    Args:
        message: The message to announce
        priority: Notification priority level
        abstract: Optional supplementary context
        session_name: Optional session name for UI
        job_id: Optional agentic job ID for job cards
        queue_name: Optional queue name
    """
    await _core_voice_io.notify( message, priority, abstract, session_name, job_id, queue_name )


async def ask_yes_no(
    question: str,
    default: str = "no",
    timeout: int = 60,
    abstract: Optional[ str ] = None
) -> bool:
    """
    Ask a yes/no question (voice-first).

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

    Returns:
        str or None: User's response, or None on timeout/error
    """
    return await _core_voice_io.get_input( prompt, allow_empty, timeout )


async def choose(
    question: str,
    options: Union[ List[ str ], List[ dict ] ],
    timeout: int = 120,
    allow_custom: bool = False
) -> str:
    """
    Present multiple-choice options (voice-first).

    Returns:
        str: The selected option label
    """
    return await _core_voice_io.choose( question, options, timeout, allow_custom )


async def present_choices(
    questions: list,
    timeout: int = 120,
    title: Optional[ str ] = None,
    abstract: Optional[ str ] = None
) -> dict:
    """
    Present multiple-choice questions (voice-first).

    Returns:
        dict: {"answers": {...}} with selections
    """
    return await _core_voice_io.present_choices( questions, timeout, title, abstract )


# =============================================================================
# Smoke Test
# =============================================================================

def quick_smoke_test():
    """Quick smoke test for SWE Team voice_io wrapper module."""
    import cosa.utils.util as cu

    cu.print_banner( "SWE Team Voice I/O Wrapper Smoke Test", prepend_nl=True )

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
        assert inspect.iscoroutinefunction( choose )
        assert inspect.iscoroutinefunction( present_choices )
        print( "✓ All async functions have correct signatures" )

        # Test 6: notify has job_id parameter
        print( "Testing notify() has job_id parameter..." )
        sig = inspect.signature( notify )
        assert "job_id" in sig.parameters
        print( "✓ notify() supports job_id parameter" )

        # Reset state
        _core_voice_io._voice_available = None

        print( "\n✓ SWE Team voice_io wrapper smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
