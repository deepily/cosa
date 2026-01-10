"""
Claude Code Dispatcher API Router.

Provides REST endpoints for dispatching Claude Code tasks from the UI.
Supports both Option A (bounded) and Option B (interactive) execution modes.

This router enables the Claude Code UI Card in the Notifications interface
to submit tasks and receive streaming responses via WebSocket.

Generated on: 2026-01-08
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime
import asyncio
import json

from cosa.orchestration import ClaudeCodeDispatcher, Task, TaskType, TaskResult
import cosa.utils.util as cu

router = APIRouter( prefix="/api/claude-code", tags=[ "claude-code" ] )

# Store active dispatchers for Option B session management
active_sessions: Dict[ str, Dict[ str, Any ] ] = {}

# WebSocket connections for streaming responses
websocket_connections: Dict[ str, WebSocket ] = {}


class TaskTypeEnum( str, Enum ):
    """Task type selection for dispatch."""
    BOUNDED     = "BOUNDED"
    INTERACTIVE = "INTERACTIVE"


class DispatchRequest( BaseModel ):
    """
    Request model for task dispatch.

    Attributes:
        project: Target project name (e.g., "lupin", "cosa")
        prompt: Task description/prompt for Claude Code
        task_type: BOUNDED (Option A) or INTERACTIVE (Option B)
    """
    project   : str
    prompt    : str
    task_type : TaskTypeEnum = TaskTypeEnum.BOUNDED


class DispatchResponse( BaseModel ):
    """
    Response model for task dispatch.

    Attributes:
        task_id: Unique identifier for the dispatched task
        status: Current status ("dispatched", "running", etc.)
        websocket_url: WebSocket URL for streaming responses
    """
    task_id       : str
    status        : str
    websocket_url : str


class InjectRequest( BaseModel ):
    """Request model for injecting messages into Option B sessions."""
    message : str


@router.post( "/dispatch", response_model=DispatchResponse )
async def dispatch_task( request: DispatchRequest, background_tasks: BackgroundTasks ):
    """
    Dispatch a new Claude Code task.

    Requires:
        - request.project is a non-empty string
        - request.prompt is a non-empty string
        - request.task_type is BOUNDED or INTERACTIVE

    Ensures:
        - Creates unique task_id
        - Initializes dispatcher and session tracking
        - Starts background dispatch task
        - Returns task_id for WebSocket subscription

    Raises:
        - HTTPException 400 if prompt is empty
    """
    print( f"[DEBUG] dispatch_task called: project={request.project}, task_type={request.task_type}" )

    if not request.prompt.strip():
        raise HTTPException( status_code=400, detail="Prompt cannot be empty" )

    task_id = f"claude-code-{datetime.now().strftime( '%Y%m%d-%H%M%S' )}"

    task = Task(
        id        = task_id,
        project   = request.project,
        prompt    = request.prompt,
        type      = TaskType.BOUNDED if request.task_type == TaskTypeEnum.BOUNDED else TaskType.INTERACTIVE,
        max_turns = 50 if request.task_type == TaskTypeEnum.BOUNDED else 200
    )

    # Create message callback that sends to WebSocket
    def on_message( tid: str, message ):
        asyncio.create_task( _send_websocket_message( tid, message ) )

    # Create dispatcher and store for session management
    dispatcher = ClaudeCodeDispatcher( on_message=on_message )
    active_sessions[ task_id ] = {
        "dispatcher" : dispatcher,
        "task"       : task,
        "status"     : "pending",
        "result"     : None,
        "error"      : None
    }

    # Dispatch in background - use asyncio.create_task for async function
    print( f"[DEBUG] Creating async task for _run_dispatch({task_id})" )
    asyncio.create_task( _run_dispatch( task_id ) )
    print( f"[DEBUG] Async task created, returning response" )

    return DispatchResponse(
        task_id       = task_id,
        status        = "dispatched",
        websocket_url = f"/ws/claude-code/{task_id}"
    )


async def _send_websocket_message( task_id: str, message ):
    """
    Send a message to the WebSocket connection for a task.

    Requires:
        - task_id is a valid string
        - message is either a dict (from stream-json) or SDK object (from interactive mode)

    Ensures:
        - Formats message as JSON
        - Sends to WebSocket if connected
        - Handles both stream-json dicts and SDK message objects
    """
    ws = websocket_connections.get( task_id )
    if not ws:
        return

    try:
        # Handle dict messages from stream-json format (Option A bounded mode)
        if isinstance( message, dict ):
            msg_type = message.get( "type", "unknown" )

            if msg_type == "assistant":
                # Assistant message with content
                content = message.get( "message", {} )
                if isinstance( content, dict ):
                    text_content = content.get( "content", [] )
                    for block in text_content if isinstance( text_content, list ) else []:
                        if isinstance( block, dict ) and block.get( "type" ) == "text":
                            await ws.send_json( { "type": "text", "content": block.get( "text", "" ) } )
                else:
                    await ws.send_json( { "type": "text", "content": str( content ) } )

            elif msg_type == "user":
                # User message (tool results)
                content = message.get( "message", {} )
                if isinstance( content, dict ):
                    text_content = content.get( "content", [] )
                    for block in text_content if isinstance( text_content, list ) else []:
                        if isinstance( block, dict ) and block.get( "type" ) == "tool_result":
                            await ws.send_json( { "type": "tool_result", "content": str( block.get( "content", "" ) )[ :500 ] } )

            elif msg_type == "result":
                # Final result
                await ws.send_json( {
                    "type"        : "complete",
                    "success"     : True,
                    "cost_usd"    : message.get( "cost_usd" ) or message.get( "total_cost_usd" ),
                    "duration_ms" : message.get( "duration_ms" ),
                    "session_id"  : message.get( "session_id" )
                } )

            elif msg_type == "text":
                # Plain text wrapped by dispatcher
                await ws.send_json( { "type": "text", "content": message.get( "content", "" ) } )

            elif msg_type == "system":
                await ws.send_json( { "type": "status", "state": "system_loaded" } )

            else:
                # Pass through other stream-json types
                await ws.send_json( message )

            return

        # Handle SDK message objects (Option B interactive mode)
        msg_type = type( message ).__name__

        if msg_type == "TextBlock":
            text = getattr( message, "text", str( message ) )
            await ws.send_json( { "type": "text", "content": text } )

        elif msg_type == "ToolUseBlock":
            tool_name = getattr( message, "name", "unknown" )
            await ws.send_json( { "type": "tool_use", "name": tool_name } )

        elif msg_type == "ToolResultBlock":
            content = getattr( message, "content", str( message ) )
            await ws.send_json( { "type": "tool_result", "content": content } )

        elif msg_type == "ResultMessage":
            cost = getattr( message, "cost_usd", None )
            await ws.send_json( {
                "type"     : "complete",
                "success"  : True,
                "cost_usd" : cost
            } )

        elif msg_type == "AssistantMessage":
            # Handle AssistantMessage content blocks
            content = getattr( message, "content", [] )
            for block in content:
                block_type = type( block ).__name__
                if block_type == "TextBlock":
                    text = getattr( block, "text", str( block ) )
                    await ws.send_json( { "type": "text", "content": text } )
                elif block_type == "ToolUseBlock":
                    tool_name = getattr( block, "name", "unknown" )
                    await ws.send_json( { "type": "tool_use", "name": tool_name } )

        elif msg_type == "UserMessage":
            # Tool results from UserMessage
            content = getattr( message, "content", [] )
            for block in content:
                block_type = type( block ).__name__
                if block_type == "ToolResultBlock":
                    result = getattr( block, "content", str( block ) )
                    await ws.send_json( { "type": "tool_result", "content": result } )

        elif msg_type == "SystemMessage":
            await ws.send_json( { "type": "status", "state": "system_loaded" } )

        else:
            # Generic fallback
            await ws.send_json( { "type": "info", "content": str( message )[ :200 ] } )

    except Exception as e:
        print( f"Error sending WebSocket message: {e}" )


async def _run_dispatch( task_id: str ):
    """
    Background task to run the dispatch.

    Requires:
        - task_id exists in active_sessions

    Ensures:
        - Updates session status to "running"
        - Calls dispatcher.dispatch( task )
        - Updates session with result or error
        - Sends final status to WebSocket
    """
    print( f"[DEBUG] _run_dispatch starting for task_id={task_id}" )

    session = active_sessions.get( task_id )
    if not session:
        print( f"[DEBUG] No session found for task_id={task_id}" )
        return

    session[ "status" ] = "running"
    dispatcher = session[ "dispatcher" ]
    task = session[ "task" ]

    print( f"[DEBUG] Dispatching task: project={task.project}, prompt={task.prompt[:50]}..." )

    # Send running status to WebSocket
    ws = websocket_connections.get( task_id )
    if ws:
        try:
            await ws.send_json( { "type": "status", "state": "running" } )
            print( f"[DEBUG] Sent 'running' status to WebSocket" )
        except Exception as e:
            print( f"[DEBUG] Failed to send running status: {e}" )

    try:
        print( f"[DEBUG] Calling dispatcher.dispatch()..." )
        result = await dispatcher.dispatch( task )
        print( f"[DEBUG] Dispatch returned: success={result.success}, error={result.error}" )

        session[ "status" ] = "complete" if result.success else "failed"
        session[ "result" ] = result

        # Send final status
        if ws:
            try:
                await ws.send_json( {
                    "type"     : "complete",
                    "success"  : result.success,
                    "cost_usd" : result.cost_usd,
                    "error"    : result.error
                } )
                print( f"[DEBUG] Sent 'complete' status to WebSocket" )
            except Exception as e:
                print( f"[DEBUG] Failed to send complete status: {e}" )

    except Exception as e:
        print( f"[DEBUG] Exception in dispatch: {type(e).__name__}: {e}" )
        import traceback
        traceback.print_exc()

        session[ "status" ] = "error"
        session[ "error" ] = str( e )

        # Send error status
        if ws:
            try:
                await ws.send_json( { "type": "error", "message": str( e ) } )
            except Exception:
                pass


@router.post( "/{task_id}/inject" )
async def inject_message( task_id: str, request: InjectRequest ):
    """
    Inject a follow-up message into an Option B session.

    Requires:
        - task_id exists in active_sessions
        - Session is an INTERACTIVE task type
        - request.message is non-empty

    Ensures:
        - Calls dispatcher.inject() with the message
        - Returns success status

    Raises:
        - HTTPException 404 if session not found
        - HTTPException 400 if inject fails
    """
    session = active_sessions.get( task_id )
    if not session:
        raise HTTPException( status_code=404, detail="Session not found" )

    if not request.message.strip():
        raise HTTPException( status_code=400, detail="Message cannot be empty" )

    dispatcher = session[ "dispatcher" ]

    try:
        success = await dispatcher.inject( task_id, request.message )

        if not success:
            raise HTTPException( status_code=400, detail="Inject failed - session may not be active" )

        return { "status": "injected", "task_id": task_id }

    except Exception as e:
        raise HTTPException( status_code=500, detail=f"Inject error: {str( e )}" )


@router.post( "/{task_id}/interrupt" )
async def interrupt_session( task_id: str ):
    """
    Interrupt the current response in an Option B session.

    Requires:
        - task_id exists in active_sessions
        - Session is currently running

    Ensures:
        - Calls dispatcher.interrupt()
        - Returns success status

    Raises:
        - HTTPException 404 if session not found
    """
    session = active_sessions.get( task_id )
    if not session:
        raise HTTPException( status_code=404, detail="Session not found" )

    dispatcher = session[ "dispatcher" ]

    try:
        # Note: interrupt() may not exist yet on dispatcher - will need implementation
        if hasattr( dispatcher, "interrupt" ):
            await dispatcher.interrupt( task_id )

        return { "status": "interrupted", "task_id": task_id }

    except Exception as e:
        raise HTTPException( status_code=500, detail=f"Interrupt error: {str( e )}" )


@router.post( "/{task_id}/end" )
async def end_session( task_id: str ):
    """
    End an Option B session gracefully.

    Requires:
        - task_id exists in active_sessions

    Ensures:
        - Calls dispatcher.end_session() if available
        - Removes session from active_sessions
        - Closes WebSocket connection

    Raises:
        - HTTPException 404 if session not found
    """
    session = active_sessions.get( task_id )
    if not session:
        raise HTTPException( status_code=404, detail="Session not found" )

    dispatcher = session[ "dispatcher" ]

    try:
        # Note: end_session() may not exist yet on dispatcher - will need implementation
        if hasattr( dispatcher, "end_session" ):
            await dispatcher.end_session( task_id )

        # Clean up
        del active_sessions[ task_id ]

        # Close WebSocket if connected
        ws = websocket_connections.get( task_id )
        if ws:
            await ws.close()
            del websocket_connections[ task_id ]

        return { "status": "ended", "task_id": task_id }

    except Exception as e:
        raise HTTPException( status_code=500, detail=f"End session error: {str( e )}" )


@router.get( "/{task_id}/status" )
async def get_session_status( task_id: str ):
    """
    Get the current status of a task/session.

    Requires:
        - task_id is a valid string

    Ensures:
        - Returns current status and metadata

    Raises:
        - HTTPException 404 if session not found
    """
    session = active_sessions.get( task_id )
    if not session:
        raise HTTPException( status_code=404, detail="Session not found" )

    result = session.get( "result" )

    return {
        "task_id"  : task_id,
        "status"   : session[ "status" ],
        "cost_usd" : result.cost_usd if result else None,
        "error"    : session.get( "error" ) or ( result.error if result else None )
    }


# ============================================================================
# WebSocket Endpoint for Streaming
# ============================================================================

@router.websocket( "/ws/{task_id}" )
async def websocket_endpoint( websocket: WebSocket, task_id: str ):
    """
    WebSocket endpoint for streaming Claude Code responses.

    Requires:
        - task_id is a valid string
        - Client connects via WebSocket

    Ensures:
        - Accepts WebSocket connection
        - Stores connection for message routing
        - Keeps connection alive until task completes or client disconnects
        - Cleans up connection on disconnect
    """
    await websocket.accept()
    websocket_connections[ task_id ] = websocket

    try:
        # Send initial connection confirmation
        await websocket.send_json( {
            "type"    : "connected",
            "task_id" : task_id
        } )

        # Keep connection alive - messages sent via _send_websocket_message
        while True:
            try:
                # Listen for client messages (e.g., ping/pong)
                data = await asyncio.wait_for( websocket.receive_text(), timeout=60.0 )

                # Handle client messages if needed
                if data == "ping":
                    await websocket.send_text( "pong" )

            except asyncio.TimeoutError:
                # Send keepalive
                try:
                    await websocket.send_json( { "type": "keepalive" } )
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print( f"WebSocket error for task {task_id}: {e}" )
    finally:
        # Clean up
        if task_id in websocket_connections:
            del websocket_connections[ task_id ]


# ============================================================================
# Smoke Test
# ============================================================================

def quick_smoke_test():
    """
    Quick smoke test for Claude Code router - validates basic functionality.

    Requires:
        - Module imports successfully
        - Router is configured correctly

    Ensures:
        - Router object exists
        - Has expected endpoints
        - DispatchRequest/Response models work
    """
    cu.print_banner( "Claude Code Router Smoke Test", prepend_nl=True )

    try:
        # Test 1: Router exists
        print( "Testing router configuration..." )
        assert router is not None
        assert router.prefix == "/api/claude-code"
        print( "✓ Router configured correctly" )

        # Test 2: Models work
        print( "Testing Pydantic models..." )
        req = DispatchRequest(
            project   = "lupin",
            prompt    = "Test prompt",
            task_type = TaskTypeEnum.BOUNDED
        )
        assert req.project == "lupin"
        assert req.task_type == TaskTypeEnum.BOUNDED
        print( "✓ DispatchRequest model works" )

        resp = DispatchResponse(
            task_id       = "test-123",
            status        = "dispatched",
            websocket_url = "/ws/claude-code/test-123"
        )
        assert resp.task_id == "test-123"
        print( "✓ DispatchResponse model works" )

        # Test 3: TaskTypeEnum
        print( "Testing TaskTypeEnum..." )
        assert TaskTypeEnum.BOUNDED.value == "BOUNDED"
        assert TaskTypeEnum.INTERACTIVE.value == "INTERACTIVE"
        print( "✓ TaskTypeEnum works" )

        print( "\n✓ Smoke test completed successfully" )
        return True

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    quick_smoke_test()
