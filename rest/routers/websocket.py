"""
WebSocket and authentication endpoints
Generated on: 2025-01-24
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from datetime import datetime
import json
import asyncio

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

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
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
    
    await websocket.accept()
    websocket_manager.connect(websocket, session_id)
    
    print(f"[WS] WebSocket connected for session: {session_id}")
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "status",
            "text": f"WebSocket connected for session {session_id}",
            "status": "success"
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client (optional - for bidirectional communication)
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if app_debug and app_verbose: 
                    print(f"[WS] Received message from {session_id}: {message}")
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                if app_debug: 
                    print(f"[WS] Error handling message from {session_id}: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        # Cancel any active streaming tasks for this session
        if session_id in active_tasks:
            print(f"[WS] Cancelling active streaming task for session: {session_id}")
            active_tasks[session_id].cancel()
            try:
                await active_tasks[session_id]
            except asyncio.CancelledError:
                pass
            del active_tasks[session_id]
        
        # Clean up connection
        websocket_manager.disconnect(session_id)
        print(f"[WS] WebSocket disconnected for session: {session_id}")

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
    
    await websocket.accept()
    print(f"[WS-QUEUE] Queue WebSocket connected for session: {session_id}")
    
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
            
            # Connect with user association
            websocket_manager.connect(websocket, session_id, user_id)
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