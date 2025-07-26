"""
WebSocket and authentication endpoints
Generated on: 2025-01-24
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from datetime import datetime
import json
import asyncio
import re

# Import dependencies
from cosa.rest.auth import get_current_user
from cosa.rest.websocket_manager import WebSocketManager

router = APIRouter(tags=["websocket"])

# Global dependencies (temporary access via main module)
def get_websocket_manager():
    """Dependency to get WebSocket manager"""
    import fastapi_app.main as main_module
    return main_module.websocket_manager

def get_active_tasks():
    """Dependency to get active tasks"""
    import fastapi_app.main as main_module
    return main_module.active_tasks

def get_app_debug():
    """Dependency to get debug settings"""
    import fastapi_app.main as main_module
    return main_module.app_debug, main_module.app_verbose

def is_valid_session_id(session_id: str) -> bool:
    """
    Validate session ID format.
    
    Session IDs should be in the format: adjective noun (e.g., 'wise penguin')
    
    Args:
        session_id: The session ID to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    # Check it's not empty or just whitespace
    if not session_id or not session_id.strip():
        return False
    
    # Check format: word word (with a single space)
    pattern = r'^[a-z]+\s[a-z]+$'
    return bool(re.match(pattern, session_id.lower()))

@router.get("/api/auth-test")
async def auth_test(current_user: dict = Depends(get_current_user)):
    """
    Test endpoint to verify authentication is working.
    
    Example usage:
    curl -H "Authorization: Bearer mock_token_alice" http://localhost:8000/api/auth-test
    
    Returns:
        dict: Current user information
    """
    return {
        "message": "Authentication successful",
        "user_id": current_user["uid"],
        "email": current_user["email"],
        "name": current_user["name"],
        "timestamp": datetime.now().isoformat()
    }

@router.websocket("/ws/audio/{session_id}")
async def websocket_audio_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time TTS audio streaming.
    
    Preconditions:
        - session_id must be a valid session identifier
        - WebSocket connection must be established
        
    Postconditions:
        - Manages WebSocket connection lifecycle
        - Stores connection in websocket_manager for audio streaming
        - Handles disconnection cleanup
        
    Args:
        websocket: WebSocket connection object
        session_id: Unique session identifier for this client
    """
    # Get dependencies from main module
    import fastapi_app.main as main_module
    websocket_manager = main_module.websocket_manager
    active_tasks = main_module.active_tasks
    app_debug = main_module.app_debug
    app_verbose = main_module.app_verbose
    
    # Validate session ID format
    if not is_valid_session_id(session_id):
        await websocket.close(code=1008, reason="Invalid session ID format")
        print(f"[WS-AUDIO] Rejected connection with invalid session ID: {session_id}")
        return
    
    await websocket.accept()
    
    # Check if this session has been pre-registered with a user (from TTS request)
    user_id = websocket_manager.session_to_user.get(session_id)
    
    # Audio WebSocket should only receive audio-related events
    audio_events = ["audio_status", "audio_complete", "ping"]
    
    if not user_id:
        # If no pre-registration, audio WebSocket connections don't require immediate auth
        # The user association will be established when TTS request comes in
        print(f"[WS-AUDIO] No pre-registered user for session {session_id}, connecting without user association")
        websocket_manager.connect(websocket, session_id, subscribed_events=audio_events)
    else:
        print(f"[WS-AUDIO] Found pre-registered user {user_id} for session {session_id}")
        websocket_manager.connect(websocket, session_id, user_id, subscribed_events=audio_events)
    
    if app_debug:
        user_info = user_id if user_id else "no-user-yet"
        print( f"[WEBSOCKET] New connection on /ws/audio/{session_id} endpoint (audio streaming WebSocket) for user {user_info}" )
    
    print(f"[WS-AUDIO] Audio WebSocket connected for session: {session_id}")
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "audio_status",
            "text": f"Audio WebSocket connected for session {session_id}",
            "status": "success"
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client (optional - for bidirectional communication)
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if app_debug and app_verbose: 
                    print(f"[WS-AUDIO] Received message from {session_id}: {message}")
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                if app_debug: 
                    print(f"[WS-AUDIO] Error handling message from {session_id}: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        # Cancel any active streaming tasks for this session
        if session_id in active_tasks:
            print(f"[WS-AUDIO] Cancelling active streaming task for session: {session_id}")
            active_tasks[session_id].cancel()
            try:
                await active_tasks[session_id]
            except asyncio.CancelledError:
                pass
            del active_tasks[session_id]
        
        # Clean up connection
        websocket_manager.disconnect(session_id)
        print(f"[WS-AUDIO] Audio WebSocket disconnected for session: {session_id}")

@router.websocket("/ws/queue/{session_id}")
async def websocket_queue_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time queue updates and events.
    
    PHASE 2: WebSocket with authentication for user-specific updates.
    
    Preconditions:
        - session_id must be a valid session identifier
        - WebSocket connection must be established
        - First message must contain authentication token
        
    Postconditions:
        - Manages WebSocket connection for queue updates
        - Associates connection with authenticated user
        - Handles disconnection cleanup
        
    Args:
        websocket: WebSocket connection object
        session_id: Unique session identifier for this client
    """
    # Get dependencies from main module
    import fastapi_app.main as main_module
    websocket_manager = main_module.websocket_manager
    app_debug = main_module.app_debug
    
    # Validate session ID format
    if not is_valid_session_id(session_id):
        await websocket.close(code=1008, reason="Invalid session ID format")
        print(f"[WS-QUEUE] Rejected connection with invalid session ID: {session_id}")
        return
    
    await websocket.accept()
    print(f"[WS-QUEUE] Queue WebSocket connected for session: {session_id}")
    
    if app_debug:
        print( f"[WEBSOCKET] New connection on /ws/queue/{session_id} endpoint (authenticated queue WebSocket)" )
    
    # Wait for authentication message
    try:
        auth_message = await websocket.receive_json()
        if auth_message.get("type") != "auth" or "token" not in auth_message:
            await websocket.send_json({
                "type": "error",
                "message": "First message must be auth with token"
            })
            await websocket.close()
            return
            
        # Verify token
        from cosa.rest.auth import verify_firebase_token
        try:
            user_info = await verify_firebase_token(auth_message["token"])
            user_id = user_info["uid"]
            
            # Extract subscribed events from auth message
            subscribed_events = auth_message.get("subscribed_events", ["*"])
            
            # Connect with user association and subscriptions
            websocket_manager.connect(websocket, session_id, user_id, subscribed_events)
            print(f"[WS-QUEUE] Authenticated session [{session_id}] for user [{user_id}]")
            
            # Send auth success
            await websocket.send_json({
                "type": "auth_success",
                "user_id": user_id,
                "session_id": session_id
            })
            
        except Exception as e:
            await websocket.send_json({
                "type": "auth_error",
                "message": str(e)
            })
            await websocket.close()
            return
            
    except Exception as e:
        print(f"[WS-QUEUE] Auth error: {e}")
        await websocket.close()
        return
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connect",
            "message": f"Queue WebSocket connected for session {session_id}",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        })
        
        # PHASE 2: Real queue updates now come from COSA queues via websocket_manager
        # Keep connection alive and listen for incoming messages
        while True:
            try:
                # Listen for any incoming messages (for future bidirectional communication)
                data = await websocket.receive_text()
                message = json.loads(data)
                print(f"[WS-QUEUE] Received message from {session_id}: {message}")
                
                # Handle specific message types if needed
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })
                elif message.get("type") == "update_subscriptions":
                    # Handle subscription updates
                    events = message.get("events", [])
                    action = message.get("action", "replace")
                    success = websocket_manager.update_subscriptions(session_id, events, action)
                    await websocket.send_json({
                        "type": "subscription_update",
                        "success": success,
                        "subscriptions": websocket_manager.session_subscriptions.get(session_id, [])
                    })
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"[WS-QUEUE] Error in queue WebSocket for {session_id}: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        websocket_manager.disconnect(session_id)
        print(f"[WS-QUEUE] Queue WebSocket disconnected for session: {session_id}")