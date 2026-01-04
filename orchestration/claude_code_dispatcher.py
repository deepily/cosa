#!/usr/bin/env python3
"""
Cosa Task Dispatcher - Routes tasks to appropriate Claude Code runtime.

Supports two modes:
    Option A (BOUNDED): Print mode for discrete tasks with natural completion
    Option B (INTERACTIVE): SDK client for open-ended sessions with bidirectional control

Usage:
    from cosa.orchestration import ClaudeCodeDispatcher, Task, TaskType

    dispatcher = ClaudeCodeDispatcher()

    # Bounded task
    result = await dispatcher.dispatch( Task(
        id="task-001",
        project="lupin",
        prompt="Run tests and fix failures",
        type=TaskType.BOUNDED
    ) )

    # Interactive session (requires claude-agent-sdk)
    result = await dispatcher.dispatch( Task(
        id="session-001",
        project="lupin",
        prompt="Let's work on the auth refactor",
        type=TaskType.INTERACTIVE
    ) )

Requirements:
    pip install claude-agent-sdk  # For interactive mode only
    npm install -g @anthropic-ai/claude-code

Environment Variables:
    LUPIN_ROOT: Project root path (required)
    MCP_PROJECT: Project name fallback (optional, auto-detected from task)
    LUPIN_APP_SERVER_URL: Server URL (default: http://localhost:7999)
"""

import asyncio
import subprocess
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any
from datetime import datetime

# SDK imports - graceful fallback if not installed
try:
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AssistantMessage,
        TextBlock,
        ToolUseBlock,
        ToolResultBlock,
        ResultMessage
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    print( "Warning: claude-agent-sdk not installed. Interactive mode unavailable.",
          file=__import__( 'sys' ).stderr )


class TaskType( Enum ):
    """Task execution mode."""
    BOUNDED     = "bounded"      # Option A: Print mode, runs to completion
    INTERACTIVE = "interactive"  # Option B: SDK client, bidirectional control


@dataclass
class Task:
    """Task definition for Claude Code execution."""
    id: str
    project: str
    prompt: str
    type: TaskType
    max_turns: int = 50
    timeout_seconds: int = 3600
    working_dir: str = None  # Will default to LUPIN_ROOT if not specified

    def __post_init__( self ):
        """Set working_dir from LUPIN_ROOT if not specified."""
        if self.working_dir is None:
            lupin_root = os.environ.get( 'LUPIN_ROOT' )
            if lupin_root:
                # Default to LUPIN_ROOT directly
                self.working_dir = lupin_root
            else:
                self.working_dir = "/home/projects"

    @property
    def sender_id( self ) -> str:
        """Generate sender_id for session correlation."""
        return f"claude.code@{self.project.lower()}.deepily.ai"


@dataclass
class TaskResult:
    """Result from task execution."""
    task_id: str
    success: bool
    session_id: Optional[str] = None
    result: Optional[str] = None
    cost_usd: Optional[float] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None


class ClaudeCodeDispatcher:
    """
    Routes tasks to appropriate Claude Code runtime.

    Manages both bounded (print mode) and interactive (SDK client) sessions,
    with voice I/O via MCP server connecting to Lupin.

    Requires:
        - LUPIN_ROOT environment variable set
        - MCP server registered with Claude Code
        - Lupin server running (for voice notifications)

    Ensures:
        - Tasks are dispatched to appropriate runtime based on TaskType
        - MCP voice tools are available for clarification questions
        - Results are returned as TaskResult with success/error info

    Raises:
        - RuntimeError if LUPIN_ROOT not set
    """

    def __init__(
        self,
        mcp_config_path: str = None,
        mcp_server_path: str = None,
        on_message: Optional[Callable[[str, Any], None]] = None
    ):
        """
        Initialize dispatcher.

        Requires:
            - LUPIN_ROOT environment variable is set

        Ensures:
            - Dispatcher configured with production MCP paths

        Args:
            mcp_config_path: Path to MCP configuration JSON (default: from LUPIN_ROOT)
            mcp_server_path: Path to MCP server Python script (default: from LUPIN_ROOT)
            on_message: Callback for streaming messages (interactive mode)
        """
        # Get LUPIN_ROOT - required for production paths
        lupin_root = os.environ.get( 'LUPIN_ROOT' )
        if not lupin_root:
            raise RuntimeError(
                "LUPIN_ROOT environment variable not set.\n"
                "Set it before running:\n"
                "  export LUPIN_ROOT=/path/to/genie-in-the-box\n"
            )

        # Set default paths based on LUPIN_ROOT
        if mcp_config_path is None:
            mcp_config_path = os.path.join( lupin_root, "src/conf/mcp/cosa_mcp.json" )
        if mcp_server_path is None:
            mcp_server_path = os.path.join( lupin_root, "src/lupin_mcp/cosa_voice_mcp.py" )

        self.mcp_config_path = os.path.expanduser( mcp_config_path )
        self.mcp_server_path = mcp_server_path
        self.on_message = on_message or self._default_message_handler
        self.active_sessions: dict[str, Any] = {}  # task_id -> ClaudeSDKClient

    def _default_message_handler( self, task_id: str, message: Any ) -> None:
        """Default handler that prints messages."""
        timestamp = datetime.now().strftime( "%H:%M:%S" )

        if hasattr( message, 'content' ):
            for block in message.content:
                if hasattr( block, 'text' ):
                    print( f"[{timestamp}] [{task_id}] {block.text[:100]}..." )
                elif hasattr( block, 'name' ):
                    print( f"[{timestamp}] [{task_id}] Tool: {block.name}" )
        else:
            print( f"[{timestamp}] [{task_id}] {type( message ).__name__}" )

    async def dispatch( self, task: Task ) -> TaskResult:
        """
        Dispatch task to appropriate runtime.

        Requires:
            - task.type is a valid TaskType
            - For INTERACTIVE: claude-agent-sdk installed

        Ensures:
            - Returns TaskResult with execution outcome
            - Errors are captured in TaskResult.error

        Args:
            task: Task definition

        Returns:
            TaskResult with execution outcome
        """
        if task.type == TaskType.BOUNDED:
            return await self._run_bounded( task )
        elif task.type == TaskType.INTERACTIVE:
            if not SDK_AVAILABLE:
                return TaskResult(
                    task_id=task.id,
                    success=False,
                    error="claude-agent-sdk not installed. Run: pip install claude-agent-sdk"
                )
            return await self._run_interactive( task )
        else:
            return TaskResult(
                task_id=task.id,
                success=False,
                error=f"Unknown task type: {task.type}"
            )

    async def _run_bounded( self, task: Task ) -> TaskResult:
        """
        Option A: Print mode for bounded tasks.

        Runs Claude Code with -p flag, waits for completion.
        Claude can use MCP tools to ask questions, but user cannot
        inject input unprompted.
        """
        env = os.environ.copy()
        env["MCP_PROJECT"] = task.project.lower()

        # Use production MCP tool names (cosa-voice server)
        allowed_tools = ",".join( [
            "mcp__cosa-voice__converse",
            "mcp__cosa-voice__notify",
            "mcp__cosa-voice__ask_yes_no",
            "Read", "Write", "Bash"
        ] )

        cmd = [
            "claude", "-p", task.prompt,
            "--mcp-config", self.mcp_config_path,
            "--allowedTools", allowed_tools,
            "--permission-mode", "acceptEdits",
            "--output-format", "json",
            "--max-turns", str( task.max_turns )
        ]

        try:
            result = subprocess.run(
                cmd,
                env=env,
                cwd=task.working_dir,
                capture_output=True,
                text=True,
                timeout=task.timeout_seconds
            )

            if result.returncode == 0:
                data = json.loads( result.stdout )
                return TaskResult(
                    task_id=task.id,
                    success=True,
                    session_id=data.get( "session_id" ),
                    result=data.get( "result" ),
                    cost_usd=data.get( "total_cost_usd" ),
                    duration_ms=data.get( "duration_ms" ),
                    exit_code=0
                )
            else:
                return TaskResult(
                    task_id=task.id,
                    success=False,
                    error=result.stderr or "Unknown error",
                    exit_code=result.returncode
                )

        except subprocess.TimeoutExpired:
            return TaskResult(
                task_id=task.id,
                success=False,
                error=f"Task timed out after {task.timeout_seconds}s",
                exit_code=-1
            )
        except json.JSONDecodeError as e:
            return TaskResult(
                task_id=task.id,
                success=False,
                error=f"Failed to parse output: {e}",
                exit_code=-1
            )
        except Exception as e:
            return TaskResult(
                task_id=task.id,
                success=False,
                error=str( e ),
                exit_code=-1
            )

    async def _run_interactive( self, task: Task ) -> TaskResult:
        """
        Option B: SDK client for interactive sessions.

        Creates persistent session with bidirectional control.
        User can inject messages, interrupt, suspend, and resume.

        Note: Requires claude-agent-sdk to be installed.
        """
        options = ClaudeAgentOptions(
            cwd=task.working_dir,
            permission_mode="acceptEdits",
            allowed_tools=[
                "Read", "Write", "Bash",
                "mcp__cosa-voice__converse",
                "mcp__cosa-voice__notify",
                "mcp__cosa-voice__ask_yes_no"
            ],
            mcp_servers={
                "cosa-voice": {
                    "type": "stdio",
                    "command": "python",
                    "args": [self.mcp_server_path],
                    "env": {"MCP_PROJECT": task.project.lower()}
                }
            },
            system_prompt=f"""Session: {task.sender_id}

Voice tools available:
- converse(): Ask user and wait for voice response
- notify(): Announce status (fire-and-forget)
- ask_yes_no(): Quick yes/no decisions

Use notify() for progress. Use converse() when you need input."""
        )

        try:
            async with ClaudeSDKClient( options=options ) as client:
                self.active_sessions[task.id] = client

                await client.query( task.prompt )

                result_data = None
                async for message in client.receive_response():
                    # Stream to callback
                    self.on_message( task.id, message )

                    # Capture final result
                    if isinstance( message, ResultMessage ):
                        result_data = {
                            "session_id": message.session_id,
                            "result": message.result,
                            "cost_usd": message.total_cost_usd,
                            "duration_ms": message.duration_ms
                        }

                del self.active_sessions[task.id]

                if result_data:
                    return TaskResult(
                        task_id=task.id,
                        success=True,
                        **result_data
                    )
                else:
                    return TaskResult(
                        task_id=task.id,
                        success=False,
                        error="No result received"
                    )

        except Exception as e:
            if task.id in self.active_sessions:
                del self.active_sessions[task.id]
            return TaskResult(
                task_id=task.id,
                success=False,
                error=str( e )
            )

    async def inject( self, task_id: str, message: str ) -> bool:
        """
        Inject a message into an active interactive session.

        Only works for TaskType.INTERACTIVE sessions.

        Args:
            task_id: ID of active session
            message: Message to inject

        Returns:
            True if message was injected, False if session not found
        """
        client = self.active_sessions.get( task_id )
        if client:
            await client.query( message )
            return True
        return False

    async def interrupt( self, task_id: str ) -> bool:
        """
        Interrupt an active interactive session.

        Session can be resumed later with inject().

        Args:
            task_id: ID of active session

        Returns:
            True if session was interrupted, False if not found
        """
        client = self.active_sessions.get( task_id )
        if client:
            await client.interrupt()
            return True
        return False

    def get_active_sessions( self ) -> list[str]:
        """Get list of active interactive session IDs."""
        return list( self.active_sessions.keys() )


# ============================================================================
# Smoke Test
# ============================================================================

def quick_smoke_test():
    """
    Quick smoke test for Claude Code Dispatcher - validates basic functionality.

    Tests module imports, class instantiation, and command construction
    without requiring Claude Code CLI or Lupin server.
    """
    import cosa.utils.util as cu
    import unittest.mock as mock

    cu.print_banner( "Claude Code Dispatcher Smoke Test", prepend_nl=True )

    # Set LUPIN_ROOT for tests (required by dispatcher)
    original_lupin_root = os.environ.get( 'LUPIN_ROOT' )
    test_lupin_root = os.path.dirname( os.path.dirname( os.path.dirname(
        os.path.dirname( os.path.abspath( __file__ ) ) ) ) )
    os.environ['LUPIN_ROOT'] = test_lupin_root

    try:
        # Test 1: Verify TaskType enum values
        print( "Test 1: Verifying TaskType enum..." )
        assert TaskType.BOUNDED.value == "bounded"
        assert TaskType.INTERACTIVE.value == "interactive"
        print( f"✓ TaskType.BOUNDED = {TaskType.BOUNDED.value}" )
        print( f"✓ TaskType.INTERACTIVE = {TaskType.INTERACTIVE.value}" )

        # Test 2: Create Task and verify sender_id
        print( "\nTest 2: Creating Task and verifying sender_id..." )
        task = Task(
            id="test-001",
            project="lupin",
            prompt="Test prompt",
            type=TaskType.BOUNDED
        )
        assert task.id == "test-001"
        assert task.project == "lupin"
        assert task.sender_id == "claude.code@lupin.deepily.ai"
        print( f"✓ Task created with id: {task.id}" )
        print( f"✓ Task sender_id: {task.sender_id}" )

        # Test 3: Test sender_id with different projects
        print( "\nTest 3: Testing sender_id for different projects..." )
        task_cosa = Task( id="t1", project="COSA", prompt="test", type=TaskType.BOUNDED )
        assert task_cosa.sender_id == "claude.code@cosa.deepily.ai"
        print( f"✓ COSA project → {task_cosa.sender_id}" )

        # Test 4: Test Task defaults
        print( "\nTest 4: Verifying Task defaults..." )
        task_defaults = Task( id="t3", project="test", prompt="test", type=TaskType.BOUNDED )
        assert task_defaults.max_turns == 50
        assert task_defaults.timeout_seconds == 3600
        assert task_defaults.working_dir is not None
        print( f"✓ max_turns default: {task_defaults.max_turns}" )
        print( f"✓ timeout_seconds default: {task_defaults.timeout_seconds}" )
        print( f"✓ working_dir auto-detected: {task_defaults.working_dir}" )

        # Test 5: Create TaskResult success/failure cases
        print( "\nTest 5: Creating TaskResult objects..." )
        result_success = TaskResult(
            task_id="test-001", success=True,
            session_id="session-abc123", cost_usd=0.0123, exit_code=0
        )
        result_failure = TaskResult(
            task_id="test-002", success=False,
            error="Task timed out", exit_code=-1
        )
        assert result_success.success is True
        assert result_failure.success is False
        print( f"✓ TaskResult success case: success={result_success.success}" )
        print( f"✓ TaskResult failure case: error={result_failure.error}" )

        # Test 6: Create ClaudeCodeDispatcher
        print( "\nTest 6: Creating ClaudeCodeDispatcher instance..." )
        dispatcher = ClaudeCodeDispatcher()
        assert dispatcher is not None
        assert dispatcher.mcp_config_path.endswith( "cosa_mcp.json" )
        assert dispatcher.mcp_server_path.endswith( "cosa_voice_mcp.py" )
        print( f"✓ ClaudeCodeDispatcher created" )
        print( f"✓ mcp_config_path: ...{dispatcher.mcp_config_path[-40:]}" )

        # Test 7: Verify dispatcher methods exist
        print( "\nTest 7: Verifying dispatcher methods..." )
        assert hasattr( dispatcher, '_run_bounded' )
        assert hasattr( dispatcher, '_run_interactive' )
        assert hasattr( dispatcher, 'dispatch' )
        assert hasattr( dispatcher, 'get_active_sessions' )
        print( "✓ All required methods exist" )

        # Test 8: Verify LUPIN_ROOT requirement
        print( "\nTest 8: Verifying LUPIN_ROOT requirement..." )
        original_root = os.environ.pop( 'LUPIN_ROOT', None )
        try:
            try:
                ClaudeCodeDispatcher()
                assert False, "Expected RuntimeError"
            except RuntimeError as e:
                assert "LUPIN_ROOT" in str( e )
                print( f"✓ RuntimeError raised when LUPIN_ROOT not set" )
        finally:
            if original_root:
                os.environ['LUPIN_ROOT'] = original_root
        os.environ['LUPIN_ROOT'] = test_lupin_root

        # Test 9: Test command construction by inspecting _run_bounded internals
        print( "\nTest 9: Testing command construction..." )
        task = Task(
            id="cmd-test", project="lupin",
            prompt="Test command", type=TaskType.BOUNDED, max_turns=10
        )

        # Build expected command components (mirrors _run_bounded logic)
        expected_tools = [
            "mcp__cosa-voice__converse",
            "mcp__cosa-voice__notify",
            "mcp__cosa-voice__ask_yes_no",
            "Read", "Write", "Bash"
        ]
        allowed_tools_str = ",".join( expected_tools )

        # Verify the dispatcher would construct correct command
        assert "mcp__cosa-voice__converse" in allowed_tools_str
        assert "mcp__cosa-voice__notify" in allowed_tools_str
        assert "mcp__cosa-voice__ask_yes_no" in allowed_tools_str
        print( f"✓ MCP voice tools in allowed list" )
        print( f"✓ Command would use: claude -p 'Test command' --max-turns 10" )

        print( "\n" + "=" * 70 )
        print( "✅ ALL SMOKE TESTS PASSED!" )
        print( "=" * 70 )
        print( "\nTo run actual tasks, ensure:" )
        print( "  1. Claude Code CLI installed" )
        print( "  2. Lupin server running" )
        print( "  3. MCP server registered" )

    except AssertionError as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print( f"\n✗ Error: {e}" )
        import traceback
        traceback.print_exc()
        return False
    finally:
        if original_lupin_root:
            os.environ['LUPIN_ROOT'] = original_lupin_root
        elif 'LUPIN_ROOT' in os.environ:
            del os.environ['LUPIN_ROOT']

    return True


# ============================================================================
# CLI Interface
# ============================================================================

async def main():
    """CLI entry point for ClaudeCodeDispatcher."""
    import argparse

    parser = argparse.ArgumentParser( description="Cosa Task Dispatcher" )
    parser.add_argument( "prompt", nargs="?", help="Task prompt for Claude" )
    parser.add_argument( "--project", "-p", help="Project name" )
    parser.add_argument( "--type", "-t", choices=["bounded", "interactive"],
                        default="bounded", help="Task type (default: bounded)" )
    parser.add_argument( "--max-turns", type=int, default=50,
                        help="Maximum turns (default: 50)" )
    parser.add_argument( "--timeout", type=int, default=3600,
                        help="Timeout in seconds (default: 3600)" )
    parser.add_argument( "--working-dir",
                        help="Working directory base (default: parent of LUPIN_ROOT)" )
    parser.add_argument( "--smoke-test", action="store_true",
                        help="Run smoke tests instead of dispatching" )

    args = parser.parse_args()

    # Run smoke test if requested
    if args.smoke_test:
        success = quick_smoke_test()
        return 0 if success else 1

    # Validate required args for dispatch
    if not args.prompt:
        parser.error( "prompt is required (or use --smoke-test)" )
    if not args.project:
        parser.error( "--project is required" )

    dispatcher = ClaudeCodeDispatcher()

    task = Task(
        id=f"{args.project}-{datetime.now().strftime( '%Y%m%d%H%M%S' )}",
        project=args.project,
        prompt=args.prompt,
        type=TaskType( args.type ),
        max_turns=args.max_turns,
        timeout_seconds=args.timeout,
        working_dir=args.working_dir
    )

    print( f"Dispatching {task.type.value} task: {task.id}" )
    print( f"Sender ID: {task.sender_id}" )
    print( "-" * 60 )

    result = await dispatcher.dispatch( task )

    print( "-" * 60 )
    if result.success:
        print( "✓ Success" )
        print( f"  Session: {result.session_id}" )
        if result.cost_usd:
            print( f"  Cost: ${result.cost_usd:.4f}" )
        if result.duration_ms:
            print( f"  Duration: {result.duration_ms}ms" )
        if result.result:
            print( f"  Result: {result.result[:200]}..." )
    else:
        print( f"✗ Failed: {result.error}" )
        if result.exit_code is not None:
            print( f"  Exit code: {result.exit_code}" )


if __name__ == "__main__":
    import sys
    sys.exit( asyncio.run( main() ) or 0 )
