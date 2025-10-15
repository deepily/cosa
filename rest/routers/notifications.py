"""
Notification management endpoints.

Provides REST API endpoints for managing user notifications including
sending notifications from Claude Code, retrieving user notifications,
and managing notification lifecycle (played/deleted status).

Generated on: 2025-01-24
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Dict, Any, Optional
import zoneinfo

# Import dependencies and services
from ..notification_fifo_queue import NotificationFifoQueue
from ..websocket_manager import WebSocketManager

router = APIRouter(prefix="/api", tags=["notifications"])

# Global variables that will be injected via dependencies (temporary)
jobs_notification_queue = None
websocket_manager = None

def get_notification_queue():
    """
    Dependency to get notification queue from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has jobs_notification_queue attribute
        
    Ensures:
        - Returns the notification queue instance
        - Provides access to notification management
        
    Raises:
        - ImportError if main module not available
        - AttributeError if notification queue not found
    """
    # This will be properly injected later
    import fastapi_app.main as main_module
    return main_module.jobs_notification_queue

def get_websocket_manager():
    """
    Dependency to get websocket manager from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has websocket_manager attribute
        
    Ensures:
        - Returns the websocket manager instance
        - Provides access to WebSocket communication
        
    Raises:
        - ImportError if main module not available
        - AttributeError if websocket manager not found
    """
    import fastapi_app.main as main_module
    return main_module.websocket_manager

def get_local_timestamp():
    """
    Get timezone-aware timestamp using configured timezone from ConfigurationManager.
    
    Requires:
        - fastapi_app.main module is available
        - config_mgr and app_debug are accessible
        - zoneinfo module is available
        
    Ensures:
        - Returns ISO format timestamp with timezone information
        - Uses configured timezone or defaults to America/New_York
        - Falls back to UTC if timezone configuration is invalid
        - Provides debug output if app_debug is enabled
        
    Raises:
        - None (handles all exceptions with fallback to UTC)
    """
    import fastapi_app.main as main_module
    config_mgr = main_module.config_mgr
    app_debug = main_module.app_debug
    
    # Get timezone from config, default to America/New_York (East Coast)
    timezone_name = config_mgr.get("app_timezone", default="America/New_York")
    
    
    try:
        # Create timezone-aware datetime
        tz = zoneinfo.ZoneInfo(timezone_name)
        local_time = datetime.now(tz)
        result = local_time.isoformat()
        
        
        return result
    except Exception as e:
        # Fallback to UTC if timezone is invalid
        if app_debug: print(f"[TIMEZONE] Warning: Invalid timezone '{timezone_name}', falling back to UTC: {e}")
        return datetime.now().isoformat()

@router.post("/notify")
async def notify_user(
    message: str = Query(..., description="Notification message text"),
    type: str = Query("custom", description="Notification type (task, progress, alert, custom)"),
    priority: str = Query("medium", description="Priority level (low, medium, high, urgent)"),
    target_user: str = Query("ricardo.felipe.ruiz@gmail.com", description="Target user EMAIL ADDRESS (server converts to system ID internally)"),
    api_key: str = Query(..., description="Simple API key for authentication"),
    notification_queue: NotificationFifoQueue = Depends(get_notification_queue),
    ws_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Claude Code notification endpoint for user communication.
    
    This endpoint allows Claude Code and other agents to send notifications
    to users through the Genie-in-the-Box application. Notifications are
    delivered via WebSocket and converted to audio using HybridTTS.
    
    Requires:
        - api_key matches "claude_code_simple_key"
        - message is non-empty after stripping whitespace
        - type is one of: task, progress, alert, custom
        - priority is one of: low, medium, high, urgent
        - target_user is a valid email address
        - WebSocket manager and notification queue are initialized
        
    Ensures:
        - Validates all input parameters against allowed values
        - Converts target email to system ID for routing
        - Adds notification to queue with proper metadata
        - Attempts WebSocket delivery to connected users
        - Returns appropriate status based on delivery success
        - Logs all notification attempts and results
        
    Raises:
        - HTTPException with 401 for invalid API key
        - HTTPException with 400 for invalid parameters
        - HTTPException with 500 for delivery failures
        
    Args:
        message: The notification message text
        type: Type of notification (task, progress, alert, custom)
        priority: Priority level (low, medium, high, urgent)
        api_key: Simple API key for authentication
        
    Returns:
        dict: Success status and notification details
    """
    # Validate API key (Phase 1: Simple hardcoded key)
    if api_key != "claude_code_simple_key":
        print(f"[AUTH] Invalid API key attempt: {api_key}")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Validate notification type
    valid_types = ["task", "progress", "alert", "custom"]
    if type not in valid_types:
        raise HTTPException( 
            status_code=400, 
            detail=f"Invalid notification type: {type}. Valid types: {', '.join(valid_types)}" 
        )
    
    # Validate priority
    valid_priorities = ["low", "medium", "high", "urgent"]
    if priority not in valid_priorities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority: {priority}. Valid priorities: {', '.join(valid_priorities)}"
        )
    
    # Validate message
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Please provide a message to send")
    
    # Create notification payload
    notification = {
        "message": message.strip(),
        "type": type,
        "priority": priority,
        "timestamp": get_local_timestamp(),
        "source": "claude_code"
    }
    
    # Log notification (existing logging system)
    print(f"[NOTIFY] Claude Code notification: {type}/{priority} - {message}")

    try:
        # Look up user in JWT auth database to get their UUID user_id
        # This replaces the old email_to_system_id() which used email-hash format
        from cosa.rest.user_service import get_user_by_email

        user_data = get_user_by_email(target_user)
        if not user_data:
            # User doesn't exist in auth database
            print(f"[NOTIFY] ❌ User not found in auth database: {target_user}")
            raise HTTPException(
                status_code=404,
                detail=f"User not found: {target_user}"
            )

        # Use UUID from auth database (matches WebSocket authentication)
        target_system_id = user_data["id"]
        print(f"[NOTIFY] Resolved user {target_user} → UUID {target_system_id}")

        # Add to notification queue with state tracking and io_tbl logging
        notification_item = notification_queue.push_notification(
            message=message.strip(),
            type=type,
            priority=priority,
            source="claude_code",
            user_id=target_system_id
        )

        # Check if user is available before attempting to send
        is_connected = ws_manager.is_user_connected(target_system_id)
        connection_count = ws_manager.get_user_connection_count(target_system_id)

        print(f"[NOTIFY] WebSocket connection check: is_connected={is_connected}, count={connection_count}")
        
        if not is_connected:
            # User not available - log and return appropriate response
            print(f"[NOTIFY] User {target_user} ({target_system_id}) is not connected to queue UI - notification not delivered")
            return {
                "status": "user_not_available",
                "message": f"User {target_user} is not connected to queue UI",
                "notification": notification,
                "target_user": target_user,
                "target_system_id": target_system_id,
                "connection_count": 0
            }
        
        # Notification automatically queued and will be delivered via notification_queue_update event
        # No immediate WebSocket emission needed - eliminates duplicate notification system
        print(f"[NOTIFY] ✓ Notification queued for {target_user} ({target_system_id}) - {connection_count} connection(s)")
        print(f"[NOTIFY] → Will be delivered via notification_queue_update WebSocket event")
        
        return {
            "status": "queued",
            "message": f"Notification queued for delivery to {target_user}",
            "notification": notification,
            "target_user": target_user,
            "target_system_id": target_system_id,
            "connection_count": connection_count
        }
            
    except Exception as e:
        print(f"[NOTIFY] ❌ Notification error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Notification failed: {str(e)}")

@router.get("/notifications/{user_id}")
async def get_user_notifications(
    user_id: str,
    include_played: bool = Query(True, description="Include played notifications"),
    limit: int = Query(50, description="Maximum number of notifications to return"),
    notification_queue: NotificationFifoQueue = Depends(get_notification_queue)
):
    """
    Get notifications for a specific user.
    
    Requires:
        - user_id is a non-empty valid system user ID
        - notification_queue is initialized and accessible
        - include_played is a boolean value
        - limit is a positive integer or None
        
    Ensures:
        - Retrieves all notifications for the specified user
        - Applies include_played filter as requested
        - Limits results to specified number if provided
        - Returns notifications sorted by timestamp (newest first)
        - Includes metadata about query parameters and results
        
    Raises:
        - HTTPException with 500 for query failures
        
    Args:
        user_id: The system user ID (not email)
        include_played: Whether to include already played notifications
        limit: Maximum number of notifications to return
        
    Returns:
        dict: User notifications with metadata
    """
    try:
        notifications = notification_queue.get_user_notifications(
            user_id=user_id,
            include_played=include_played
        )
        
        # Apply limit manually if specified
        if limit and limit < len(notifications):
            notifications = notifications[:limit]
        
        return {
            "status": "success",
            "user_id": user_id,
            "notification_count": len(notifications),
            "include_played": include_played,
            "limit": limit,
            "notifications": notifications,
            "timestamp": get_local_timestamp()
        }
        
    except Exception as e:
        print(f"[NOTIFY] Error getting notifications for {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get notifications: {str(e)}")

@router.get("/notifications/{user_id}/next")
async def get_next_notification(
    user_id: str,
    notification_queue: NotificationFifoQueue = Depends(get_notification_queue)
):
    """
    Get the next unplayed notification for a user.
    
    Requires:
        - user_id is a non-empty valid system user ID
        - notification_queue is initialized and accessible
        
    Ensures:
        - Retrieves the next unplayed notification if available
        - Does not modify notification played status
        - Returns appropriate status indicating found/not found
        - Includes timestamp for response tracking
        
    Raises:
        - HTTPException with 500 for query failures
        
    Args:
        user_id: The system user ID (not email)
        
    Returns:
        dict: Next notification or null if none available
    """
    try:
        next_notification = notification_queue.get_next_unplayed(user_id)
        
        if next_notification:
            return {
                "status": "found",
                "user_id": user_id,
                "notification": next_notification,
                "timestamp": get_local_timestamp()
            }
        else:
            return {
                "status": "none_available",
                "user_id": user_id,
                "notification": None,
                "timestamp": get_local_timestamp()
            }
            
    except Exception as e:
        print(f"[NOTIFY] Error getting next notification for {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get next notification: {str(e)}")

@router.post("/notifications/{notification_id}/played")
async def mark_notification_played(
    notification_id: str,
    notification_queue: NotificationFifoQueue = Depends(get_notification_queue)
):
    """
    Mark a notification as played.
    
    Requires:
        - notification_id is a non-empty valid notification ID
        - notification_queue is initialized and accessible
        - notification with given ID exists in the queue
        
    Ensures:
        - Updates notification played status with timestamp
        - Persists played status to io_tbl database
        - Returns success confirmation with notification details
        - Raises 404 if notification not found
        
    Raises:
        - HTTPException with 404 if notification not found
        - HTTPException with 500 for update failures
        
    Args:
        notification_id: The unique notification ID
        
    Returns:
        dict: Success status and updated notification info
    """
    try:
        success = notification_queue.mark_played(notification_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Notification {notification_id} marked as played",
                "notification_id": notification_id,
                "timestamp": get_local_timestamp()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Notification {notification_id} not found")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[NOTIFY] Error marking notification {notification_id} as played: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to mark notification as played: {str(e)}")

@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    notification_queue: NotificationFifoQueue = Depends(get_notification_queue)
):
    """
    Delete a notification.
    
    Requires:
        - notification_id is a non-empty valid notification ID
        - notification_queue is initialized and accessible
        - notification with given ID exists in the queue
        
    Ensures:
        - Removes notification from queue and io_tbl database
        - Returns success confirmation with deletion details
        - Raises 404 if notification not found
        
    Raises:
        - HTTPException with 404 if notification not found
        - HTTPException with 500 for deletion failures
        
    Args:
        notification_id: The unique notification ID
        
    Returns:
        dict: Success status and deletion info
    """
    try:
        success = notification_queue.delete_by_id_hash(notification_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Notification {notification_id} deleted",
                "notification_id": notification_id,
                "timestamp": get_local_timestamp()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Notification {notification_id} not found")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[NOTIFY] Error deleting notification {notification_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete notification: {str(e)}")