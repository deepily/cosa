"""
Notification management endpoints.

Provides REST API endpoints for managing user notifications including
sending notifications from Claude Code, retrieving user notifications,
and managing notification lifecycle (played/deleted status).

Generated on: 2025-01-24
"""

from fastapi import APIRouter, Query, HTTPException, Depends, Body
from fastapi.responses import JSONResponse, StreamingResponse
from datetime import datetime
from typing import Dict, Any, Optional, Annotated
import zoneinfo
import asyncio
import json
import uuid

# Import dependencies and services
from ..notification_fifo_queue import NotificationFifoQueue
from ..websocket_manager import WebSocketManager
from ..notifications_database import NotificationsDatabase
from ..middleware.api_key_auth import require_api_key

router = APIRouter(prefix="/api", tags=["notifications"])

# Global variables that will be injected via dependencies (temporary)
jobs_notification_queue = None
websocket_manager = None

# Global state for pending responses (Phase 2.1 SSE blocking flow)
# {notification_id: {"event": asyncio.Event(), "response_data": None}}
pending_responses = {}

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

def get_notifications_database():
    """
    Dependency to get notifications database instance.

    Requires:
        - NotificationsDatabase class is importable
        - Database file exists at canonical path

    Ensures:
        - Returns NotificationsDatabase instance
        - Uses canonical path for production database
        - Provides access to notifications CRUD operations

    Raises:
        - FileNotFoundError if database file not found
    """
    return NotificationsDatabase( debug=False )

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
    authenticated_user_id: Annotated[str, Depends(require_api_key)],
    message: str = Query(..., description="Notification message text"),
    type: str = Query("custom", description="Notification type (task, progress, alert, custom)"),
    priority: str = Query("medium", description="Priority level (low, medium, high, urgent)"),
    target_user: str = Query("ricardo.felipe.ruiz@gmail.com", description="Target user EMAIL ADDRESS (server converts to system ID internally)"),
    response_requested: bool = Query(False, description="Whether notification requires user response (Phase 2.1)"),
    response_type: Optional[str] = Query(None, description="Response type: yes_no or open_ended (Phase 2.1)"),
    timeout_seconds: int = Query(30, description="Timeout in seconds for response-required notifications (Phase 2.2 - reduced for testing)"),
    response_default: Optional[str] = Query(None, description="Default response value for timeout/offline (Phase 2.1)"),
    title: Optional[str] = Query(None, description="Terse technical title for voice-first UX (Phase 2.1)"),
    notification_queue: NotificationFifoQueue = Depends(get_notification_queue),
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    notification_db: NotificationsDatabase = Depends(get_notifications_database)
):
    """
    Claude Code notification endpoint for user communication.

    Supports both fire-and-forget notifications (Phase 1) and response-required
    notifications with SSE blocking (Phase 2.1).

    **Fire-and-Forget Mode** (response_requested=False):
    - Queues notification for WebSocket delivery
    - Returns immediately without blocking
    - Existing behavior unchanged

    **Response-Required Mode** (response_requested=True):
    - Creates notification in database with expiration
    - Pushes to WebSocket for UI rendering
    - Returns SSE stream that blocks until response/timeout
    - Supports offline detection (immediate default return)

    Requires:
        - Valid API key in X-API-Key header (validated by require_api_key middleware)
        - message is non-empty after stripping whitespace
        - type is one of: task, progress, alert, custom
        - priority is one of: low, medium, high, urgent
        - target_user is a valid email address
        - If response_requested=True: response_type must be "yes_no" or "open_ended"

    Ensures:
        - Validates all input parameters against allowed values
        - Converts target email to system ID for routing
        - Fire-and-forget: Queues notification and returns immediately
        - Response-required: Creates database record, returns SSE stream
        - Offline detection: Returns default immediately if user not connected
        - Logs all notification attempts and results

    Raises:
        - HTTPException with 401 for invalid/missing API key (via middleware)
        - HTTPException with 400 for invalid parameters
        - HTTPException with 503 for offline user without default
        - HTTPException with 500 for delivery failures

    Args:
        authenticated_user_id: Service account user ID (from API key validation)
        message: The notification message text
        type: Type of notification (task, progress, alert, custom)
        priority: Priority level (low, medium, high, urgent)
        target_user: Target user email address
        response_requested: Whether notification requires response (Phase 2.1)
        response_type: Response type (yes_no, open_ended) for Phase 2.1
        timeout_seconds: Timeout for response-required notifications (Phase 2.1)
        response_default: Default value for timeout/offline (Phase 2.1)
        title: Terse technical title for voice-first UX (Phase 2.1)

    Returns:
        dict (fire-and-forget) or StreamingResponse (SSE for response-required)
    """
    # API key validation handled by require_api_key middleware
    # authenticated_user_id contains the validated service account user ID

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

    # Phase 2.1: Validate response-required parameters
    if response_requested:
        if not response_type:
            raise HTTPException(
                status_code=400,
                detail="response_type is required when response_requested=True (yes_no or open_ended)"
            )

        valid_response_types = ["yes_no", "open_ended"]
        if response_type not in valid_response_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid response_type: {response_type}. Valid types: {', '.join(valid_response_types)}"
            )

        if timeout_seconds <= 0:
            raise HTTPException(
                status_code=400,
                detail="timeout_seconds must be positive"
            )
    
    # Log notification (existing logging system)
    mode = "response-required" if response_requested else "fire-and-forget"
    print(f"[NOTIFY] Claude Code notification ({mode}): {type}/{priority} - {message}")

    try:
        # Look up user in JWT auth database to get their UUID user_id
        from cosa.rest.user_service import get_user_by_email

        user_data = get_user_by_email(target_user)
        if not user_data:
            print(f"[NOTIFY] ❌ User not found in auth database: {target_user}")
            raise HTTPException(
                status_code=404,
                detail=f"User not found: {target_user}"
            )

        target_system_id = user_data["id"]
        print(f"[NOTIFY] Resolved user {target_user} → UUID {target_system_id}")

        # Check if user is connected
        is_connected = ws_manager.is_user_connected(target_system_id)
        connection_count = ws_manager.get_user_connection_count(target_system_id)
        print(f"[NOTIFY] WebSocket connection check: is_connected={is_connected}, count={connection_count}")

        # =================================================================================
        # FIRE-AND-FORGET MODE (Phase 1 - existing behavior)
        # =================================================================================
        if not response_requested:
            # Add to notification queue with state tracking and io_tbl logging
            notification_item = notification_queue.push_notification(
                message     = message.strip(),
                type        = type,
                priority    = priority,
                source      = "claude_code",
                user_id     = target_system_id,
                title       = title  # Phase 2.2 - include title for consistency
            )

            if not is_connected:
                print(f"[NOTIFY] User {target_user} ({target_system_id}) is not connected - notification not delivered")
                return {
                    "status"             : "user_not_available",
                    "message"            : f"User {target_user} is not connected to queue UI",
                    "target_user"        : target_user,
                    "target_system_id"   : target_system_id,
                    "connection_count"   : 0
                }

            print(f"[NOTIFY] ✓ Notification queued for {target_user} ({target_system_id}) - {connection_count} connection(s)")
            return {
                "status"             : "queued",
                "message"            : f"Notification queued for delivery to {target_user}",
                "target_user"        : target_user,
                "target_system_id"   : target_system_id,
                "connection_count"   : connection_count
            }

        # =================================================================================
        # RESPONSE-REQUIRED MODE (Phase 2.1 - new SSE blocking behavior)
        # =================================================================================

        # Task 5: Offline Detection - return default immediately if user not connected
        if not is_connected:
            if response_default:
                print(f"[NOTIFY] User offline - returning default immediately: {response_default}")

                # Create notification in database with state='expired'
                notification_id = notification_db.create_notification(
                    sender_id          = "claude.code@deepily.ai",
                    recipient_id       = target_system_id,
                    title              = title or message.strip()[:50],  # Fallback to first 50 chars
                    message            = message.strip(),
                    type               = type,
                    priority           = priority,
                    source_context     = "claude_code",
                    response_requested = True,
                    response_type      = response_type,
                    response_default   = response_default,
                    timeout_seconds    = timeout_seconds
                )
                notification_db.update_state( notification_id, "expired" )

                return JSONResponse({
                    "status"             : "offline",
                    "default_used"       : response_default,
                    "notification_id"    : notification_id,
                    "message"            : "User is offline, returned default value immediately"
                })
            else:
                raise HTTPException(
                    status_code = 503,
                    detail      = "User is offline and no default response provided"
                )

        # User is online - create notification in database
        notification_id = notification_db.create_notification(
            sender_id          = "claude.code@deepily.ai",
            recipient_id       = target_system_id,
            title              = title or message.strip()[:50],
            message            = message.strip(),
            type               = type,
            priority           = priority,
            source_context     = "claude_code",
            response_requested = True,
            response_type      = response_type,
            response_default   = response_default,
            timeout_seconds    = timeout_seconds
        )

        print(f"[NOTIFY] Created response-required notification: {notification_id}")

        # Task 3: Create in-memory event for SSE blocking
        response_event = asyncio.Event()
        pending_responses[notification_id] = {
            "event"         : response_event,
            "response_data" : None
        }

        # DEBUG: Log the response_default value before pushing to queue
        print(f"[DEBUG] Creating notification with response_default: '{response_default}'")
        print(f"[DEBUG] Response type: {response_type}, Timeout: {timeout_seconds}s")

        # Push notification to WebSocket for UI rendering (Phase 2.2 with full fields)
        notification_item = notification_queue.push_notification(
            message            = message.strip(),
            type               = type,
            priority           = priority,
            source             = "claude_code",
            user_id            = target_system_id,
            id                 = notification_id,  # Use database ID for consistency
            title              = title or message.strip()[:50],
            response_requested = True,
            response_type      = response_type,
            response_default   = response_default,
            timeout_seconds    = timeout_seconds
        )

        # DEBUG: Log the notification_item after creation
        print(f"[DEBUG] Notification item created: {notification_item}")
        print(f"[DEBUG] Notification item.response_default: '{notification_item.response_default}'")
        print(f"[DEBUG] Notification item to_dict(): {notification_item.to_dict()}")

        print(f"[NOTIFY] Pushed notification {notification_id} via WebSocket, starting SSE stream...")

        # Task 3 & 4: SSE event generator with timeout handling
        async def event_generator():
            try:
                # Wait for response with timeout
                await asyncio.wait_for(
                    response_event.wait(),
                    timeout = timeout_seconds
                )

                # Response received!
                response = pending_responses[notification_id]["response_data"]
                print(f"[NOTIFY] ✓ Response received for {notification_id}: {response}")

                yield f"data: {json.dumps({'status': 'responded', 'response': response, 'default_used': False})}\n\n"

            except asyncio.TimeoutError:
                # Task 4: Timeout - use default value
                print(f"[NOTIFY] ⏱️ Timeout for notification {notification_id}, using default: {response_default}")

                notification_db.update_state( notification_id, "expired" )

                # Task 7: Broadcast notification_expired WebSocket event
                try:
                    await ws_manager.emit_to_user(
                        target_system_id,
                        "notification_expired",
                        {
                            "notification_id"  : notification_id,
                            "default_used"     : response_default,
                            "timeout"          : True,
                            "timestamp"        : datetime.utcnow().isoformat()
                        }
                    )
                    print(f"[NOTIFY] ✓ Broadcast notification_expired event for {notification_id}")
                except Exception as ws_error:
                    print(f"[NOTIFY] ⚠️ Failed to broadcast notification_expired event: {ws_error}")

                default_response = {
                    "status"       : "expired",
                    "response"     : response_default,
                    "default_used" : True,
                    "timeout"      : True
                }

                yield f"data: {json.dumps(default_response)}\n\n"

            except Exception as e:
                # Unexpected error
                print(f"[NOTIFY] ❌ SSE stream error for {notification_id}: {e}")

                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

            finally:
                # Cleanup
                if notification_id in pending_responses:
                    del pending_responses[notification_id]
                    print(f"[NOTIFY] Cleaned up pending_responses for {notification_id}")

        # Return SSE streaming response
        return StreamingResponse(
            event_generator(),
            media_type = "text/event-stream",
            headers    = {
                "Cache-Control"                : "no-cache",
                "X-Accel-Buffering"            : "no",
                "Connection"                   : "keep-alive",
                "Content-Type"                 : "text/event-stream",
                "Access-Control-Allow-Origin"  : "*"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[NOTIFY] ❌ Notification error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Notification failed: {str(e)}")

@router.post("/notify/response")
async def submit_notification_response(
    request_body: Dict[str, Any] = Body(..., description="Request body with notification_id and response_value"),
    notification_db: NotificationsDatabase = Depends(get_notifications_database),
    ws_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Submit user response to a response-required notification (Phase 2.1).

    This endpoint is called by the client UI when the user responds to a notification
    (clicks Yes/No button, submits text input, etc.). It updates the database,
    signals the waiting SSE stream, and broadcasts WebSocket events.

    Requires:
        - notification_id is a valid UUID of an existing notification
        - response_value is a dict with response data
        - Notification exists in database with state='delivered'

    Ensures:
        - Updates database with response_value and state='responded'
        - Signals waiting SSE stream via asyncio.Event
        - Broadcasts notification_responded WebSocket event
        - Accepts responses within grace period (30s after expiration)
        - Returns success confirmation

    Raises:
        - HTTPException with 404 if notification not found
        - HTTPException with 400 if notification already responded/expired (outside grace period)
        - HTTPException with 500 for update failures

    Args:
        notification_id: UUID of the notification
        response_value: Response data dict (structure depends on response_type)

    Returns:
        dict: Success status and response details
    """
    try:
        # Extract fields from request body
        notification_id = request_body.get( "notification_id" )
        response_value  = request_body.get( "response_value" )

        if not notification_id:
            raise HTTPException(
                status_code = 422,
                detail      = "notification_id is required in request body"
            )

        if response_value is None:
            raise HTTPException(
                status_code = 422,
                detail      = "response_value is required in request body"
            )

        # Phase 2.4: Validate and sanitize response_value for open-ended responses
        if isinstance( response_value, str ):
            # Sanitize: Remove HTML/script tags to prevent XSS
            import re
            response_value = re.sub( r'<[^>]+>', '', response_value )

            # Length validation
            if len( response_value ) > 500:
                raise HTTPException(
                    status_code = 400,
                    detail      = "Response too long (maximum 500 characters)"
                )

            # Empty check (after stripping whitespace)
            if len( response_value.strip() ) == 0:
                raise HTTPException(
                    status_code = 400,
                    detail      = "Response cannot be empty"
                )

        print(f"[NOTIFY] Response submission for {notification_id}: {response_value}")

        # Get notification from database
        notification = notification_db.get_notification( notification_id )

        if not notification:
            raise HTTPException(
                status_code = 404,
                detail      = f"Notification {notification_id} not found"
            )

        # Check state - must be 'delivered' or within grace period
        if notification["state"] == "responded":
            raise HTTPException(
                status_code = 400,
                detail      = "Notification already responded to"
            )

        # Grace period check (30 seconds - from config in Phase 2.2)
        grace_period_seconds = 30

        if notification["state"] == "expired":
            # Check if within grace period
            expires_at    = datetime.fromisoformat( notification["expires_at"] ) if notification["expires_at"] else None
            now           = datetime.utcnow()

            if expires_at and (now - expires_at).total_seconds() > grace_period_seconds:
                raise HTTPException(
                    status_code = 400,
                    detail      = f"Notification expired more than {grace_period_seconds}s ago (grace period exceeded)"
                )

            print(f"[NOTIFY] Accepting late response within grace period ({grace_period_seconds}s)")

        # Update database with response
        success = notification_db.update_response(
            notification_id,
            json.dumps( response_value )
        )

        if not success:
            raise HTTPException(
                status_code = 500,
                detail      = "Failed to update notification response in database"
            )

        print(f"[NOTIFY] ✓ Updated database with response for {notification_id}")

        # Task 2: Signal waiting SSE stream (if it exists)
        if notification_id in pending_responses:
            pending_responses[notification_id]["response_data"] = response_value
            pending_responses[notification_id]["event"].set()  # Wake up SSE stream!
            print(f"[NOTIFY] ✓ Signaled SSE stream for {notification_id}")
        else:
            print(f"[NOTIFY] No SSE stream waiting for {notification_id} (may have already completed)")

        # Task 7: Broadcast WebSocket event (notification_responded)
        try:
            await ws_manager.emit_to_user(
                notification["recipient_id"],
                "notification_responded",
                {
                    "notification_id"  : notification_id,
                    "response_value"   : response_value,
                    "timestamp"        : datetime.utcnow().isoformat()
                }
            )
            print(f"[NOTIFY] ✓ Broadcast notification_responded event for {notification_id}")
        except Exception as e:
            print(f"[NOTIFY] ⚠️ Failed to broadcast WebSocket event: {e}")

        return {
            "status"           : "success",
            "message"          : f"Response recorded for notification {notification_id}",
            "notification_id"  : notification_id,
            "response_value"   : response_value,
            "timestamp"        : datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[NOTIFY] ❌ Response submission error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Response submission failed: {str(e)}")

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