"""
WebSocket administration endpoints
Generated on: 2025-01-25
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from typing import Optional

# Import dependencies
from cosa.rest.auth import get_current_user
from cosa.rest.websocket_manager import WebSocketManager

router = APIRouter(prefix="/api", tags=["websocket-admin"])

# Global dependencies (temporary access via main module)
def get_websocket_manager():
    """Dependency to get WebSocket manager"""
    import fastapi_app.main as main_module
    return main_module.websocket_manager

@router.get("/websocket-sessions")
async def get_websocket_sessions(
    current_user: dict = Depends(get_current_user),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Get information about all active WebSocket sessions.
    
    Returns:
        dict: Session information including counts and details
    """
    sessions = websocket_manager.get_all_sessions_info()
    
    # Calculate summary statistics
    total_users = len(websocket_manager.user_sessions)
    
    return {
        "total_sessions": len(sessions),
        "total_users": total_users,
        "sessions": sessions,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/websocket-sessions/stats")
async def get_websocket_stats(
    current_user: dict = Depends(get_current_user),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Get statistics about WebSocket connections and subscriptions.
    
    Returns:
        dict: Statistics including subscription patterns
    """
    subscription_stats = websocket_manager.get_subscription_stats()
    
    return {
        "connection_count": websocket_manager.get_connection_count(),
        "user_count": len(websocket_manager.user_sessions),
        "subscription_stats": subscription_stats,
        "timestamp": datetime.now().isoformat()
    }

@router.post("/websocket-sessions/cleanup")
async def cleanup_websocket_sessions(
    max_age_hours: Optional[int] = 24,
    current_user: dict = Depends(get_current_user),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Manually trigger cleanup of stale WebSocket sessions.
    
    Args:
        max_age_hours: Maximum age in hours before a session is considered stale
        
    Returns:
        dict: Cleanup results
    """
    if max_age_hours < 0:
        raise HTTPException(status_code=400, detail="max_age_hours must be positive")
    
    sessions_cleaned = websocket_manager.cleanup_stale_sessions(max_age_hours)
    
    return {
        "sessions_cleaned": sessions_cleaned,
        "max_age_hours": max_age_hours,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/websocket-sessions/{session_id}")
async def get_websocket_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Get information about a specific WebSocket session.
    
    Args:
        session_id: The session ID to look up
        
    Returns:
        dict: Session information or 404 if not found
    """
    session_info = websocket_manager.get_session_info(session_id)
    
    if not session_info:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session_info

@router.delete("/websocket-sessions/{session_id}")
async def disconnect_websocket_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Forcefully disconnect a WebSocket session.
    
    Args:
        session_id: The session ID to disconnect
        
    Returns:
        dict: Disconnection result
    """
    if not websocket_manager.is_connected(session_id):
        raise HTTPException(status_code=404, detail="Session not found or already disconnected")
    
    websocket_manager.disconnect(session_id)
    
    return {
        "session_id": session_id,
        "status": "disconnected",
        "timestamp": datetime.now().isoformat()
    }

@router.put("/websocket-sessions/single-session-policy")
async def update_single_session_policy(
    enabled: bool,
    current_user: dict = Depends(get_current_user),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Enable or disable the single-session-per-user policy.
    
    Args:
        enabled: True to enable, False to disable
        
    Returns:
        dict: Policy update result
    """
    websocket_manager.set_single_session_policy(enabled)
    
    return {
        "single_session_policy": enabled,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/websocket-events")
async def get_available_events(
    current_user: dict = Depends(get_current_user),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Get list of available WebSocket event types.
    
    Returns:
        dict: Available event types
    """
    return {
        "available_events": sorted(list(websocket_manager.available_events)),
        "total_events": len(websocket_manager.available_events),
        "timestamp": datetime.now().isoformat()
    }