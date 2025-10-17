"""
System administration and health monitoring endpoints.

Provides essential system management capabilities including health checks,
configuration refresh, session ID generation, authentication testing,
and WebSocket session management with cleanup functionality.

Generated on: 2025-01-24
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Dict, Any

# Import dependencies
from ..auth import get_current_user, get_current_user_id
from ..dependencies.config import get_config_manager, get_snapshot_manager, get_id_generator
from cosa.config.configuration_manager import ConfigurationManager
from cosa.memory.solution_snapshot_mgr import SolutionSnapshotManager
from cosa.agents.two_word_id_generator import TwoWordIdGenerator
import cosa.utils.util as du

router = APIRouter(tags=["system"])

@router.get("/", response_class=JSONResponse)
async def health_check():
    """
    Basic health check endpoint for service status monitoring.
    
    Requires:
        - FastAPI application is running and responsive
        
    Ensures:
        - Returns healthy status with service identification
        - Includes current timestamp in ISO format
        - Provides version information for monitoring systems
        - Response is consistently formatted for health checks
        
    Raises:
        - None (endpoint is designed to always succeed)
        
    Returns:
        dict: Health status with service name, timestamp, and version
    """
    return {
        "status": "healthy",
        "service": "lupin-fastapi",
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0"
    }

@router.get("/health", response_class=JSONResponse)
async def health():
    """
    Simplified health endpoint for lightweight monitoring checks.
    
    Requires:
        - FastAPI application is running and responsive
        
    Ensures:
        - Returns "ok" status for monitoring systems
        - Includes current timestamp in ISO format
        - Provides minimal response for high-frequency health checks
        
    Raises:
        - None (endpoint is designed to always succeed)
        
    Returns:
        dict: Simple status and timestamp for monitoring
    """
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }

@router.get("/api/init", response_class=JSONResponse)
async def init():
    """
    Refresh configuration and reload application resources without restart.
    
    Requires:
        - FastAPI application is running with initialized components
        - Configuration files exist at specified paths (lupin-app.ini)
        - LUPIN_CONFIG_MGR_CLI_ARGS environment variable is set
        - fastapi_app.main module is accessible with global components
        
    Ensures:
        - Creates new ConfigurationManager instance with fresh settings
        - Prints current configuration with bracket formatting
        - Reloads solution snapshots from disk if snapshot_mgr exists
        - Returns success status with confirmation message
        - STT model remains loaded (managed by lifespan context)
        - Handles exceptions gracefully with error status
        
    Raises:
        - None (catches all exceptions and returns error status)
        
    Returns:
        dict: Success/error status with message and timestamp
        
    Note:
        Unlike Flask version, STT model is not reloaded as it's 
        already managed by the lifespan context manager
    """
    try:
        # Import global variables from main (temporary solution)
        import fastapi_app.main as main_module
        
        # Refresh configuration manager
        config_mgr = ConfigurationManager(env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS")
        config_mgr.print_configuration(brackets=True)
        
        # Reload snapshots using the global snapshot manager
        if hasattr(main_module, 'snapshot_mgr') and main_module.snapshot_mgr:
            print("Reloading solution snapshots...")
            main_module.snapshot_mgr.reload()
        
        return {
            "status": "success",
            "message": "Configuration refreshed and snapshots reloaded",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Init failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@router.get("/api/get-session-id")
async def get_session_id(
    id_gen: TwoWordIdGenerator = Depends(get_id_generator)
):
    """
    Generate and return a unique session ID for WebSocket communication routing.
    
    Requires:
        - id_gen dependency is properly initialized TwoWordIdGenerator
        - TwoWordIdGenerator has loaded word lists and is functional
        
    Ensures:
        - Generates a unique two-word hyphenated ID string
        - Logs the generated session ID for debugging
        - Returns session ID with current timestamp
        - ID is suitable for WebSocket message routing
        
    Raises:
        - None (TwoWordIdGenerator handles internal errors gracefully)
        
    Args:
        id_gen: Injected TwoWordIdGenerator dependency
        
    Returns:
        dict: Contains generated session_id and timestamp
        
    Note:
        This ID will be used to route asynchronous WebSocket messages
        to the correct client in future implementations
    """
    session_id = id_gen.get_id()
    print(f"[API] Generated new session ID: {session_id}")
    
    return {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/api/auth-test")
async def auth_test(current_user: dict = Depends(get_current_user)):
    """
    Test endpoint to verify authentication system functionality.
    
    Requires:
        - Valid JWT authentication token in Authorization header
        - get_current_user dependency is properly configured
        - Firebase authentication system is accessible
        
    Ensures:
        - Returns success status with authenticated user information
        - Confirms authentication system is working correctly
        - Includes user details from JWT token payload
        - Provides timestamp for testing verification
        
    Raises:
        - HTTPException with 401 status if authentication fails
        - HTTPException with 401 status if token is invalid/missing
        
    Args:
        current_user: Authenticated user information from JWT token
        
    Returns:
        dict: Success message, user details, and timestamp
        
    Note:
        REFACTORING CHANGE: This endpoint now returns 401 (Unauthorized) status
        when called without auth token, fixing test expectations.
        Changed from 403 to 401 on 2025.09.28.
    """
    return {
        "status": "success",
        "message": "Authentication is working",
        "user": current_user,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/api/websocket-sessions")
async def get_websocket_sessions(
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive information about all active WebSocket sessions with metrics.
    
    Requires:
        - Valid JWT authentication token in Authorization header
        - fastapi_app.main module is accessible
        - WebSocketManager is initialized in main module
        - WebSocketManager has get_all_sessions_info() method
        
    Ensures:
        - Retrieves all active WebSocket session information
        - Calculates session metrics including total and unique users
        - Identifies users with multiple concurrent sessions
        - Returns single session policy configuration status
        - Includes comprehensive session details and statistics
        
    Raises:
        - HTTPException with 403 status if authentication fails
        - AttributeError if WebSocketManager not properly initialized
        
    Args:
        current_user: Authenticated user information from JWT token
        
    Returns:
        dict: Session metrics, policy info, session list, and timestamp
    """
    # Get WebSocketManager from main module
    import fastapi_app.main as main_module
    websocket_manager = main_module.websocket_manager
    
    sessions = websocket_manager.get_all_sessions_info()
    
    # Calculate metrics
    total_sessions = len(sessions)
    user_sessions = {}
    for session in sessions:
        user_id = session.get('user_id')
        if user_id:
            if user_id not in user_sessions:
                user_sessions[user_id] = 0
            user_sessions[user_id] += 1
    
    return {
        "total_sessions": total_sessions,
        "unique_users": len(user_sessions),
        "users_with_multiple_sessions": sum(1 for count in user_sessions.values() if count > 1),
        "single_session_policy": websocket_manager.single_session_per_user,
        "sessions": sessions,
        "timestamp": datetime.now().isoformat()
    }

@router.post("/api/websocket-sessions/cleanup")
async def cleanup_stale_sessions(
    max_age_hours: int = 24,
    current_user: dict = Depends(get_current_user)
):
    """
    Clean up stale WebSocket sessions older than specified age limit.
    
    Requires:
        - Valid JWT authentication token in Authorization header
        - fastapi_app.main module is accessible
        - WebSocketManager is initialized in main module
        - max_age_hours is a positive integer value
        - WebSocketManager has cleanup_stale_sessions() method
        
    Ensures:
        - Identifies and removes WebSocket sessions older than max_age_hours
        - Returns count of sessions that were cleaned up
        - Logs cleanup operation for monitoring purposes
        - Includes cleanup parameters in response for verification
        
    Raises:
        - HTTPException with 403 status if authentication fails
        - AttributeError if WebSocketManager not properly initialized
        - ValueError if max_age_hours is invalid
        
    Args:
        max_age_hours: Maximum age in hours before session is stale (default: 24)
        current_user: Authenticated user information from JWT token
        
    Returns:
        dict: Number of sessions cleaned, age limit, and timestamp
    """
    # Get WebSocketManager from main module
    import fastapi_app.main as main_module
    websocket_manager = main_module.websocket_manager
    
    cleaned = websocket_manager.cleanup_stale_sessions(max_age_hours)
    
    return {
        "sessions_cleaned": cleaned,
        "max_age_hours": max_age_hours,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/api/debug/websocket-state")
async def get_websocket_state():
    """
    Get complete internal state of WebSocket manager for debugging.

    **DEBUG ENDPOINT**: This endpoint exposes internal WebSocket manager state
    for troubleshooting connection and authentication issues. Should be removed
    or protected in production environments.

    Requires:
        - fastapi_app.main module is accessible
        - WebSocketManager is initialized in main module

    Ensures:
        - Returns all active_connections (session IDs)
        - Returns session_to_user mapping (session → user ID)
        - Returns user_sessions mapping (user ID → list of sessions)
        - Returns session_subscriptions mapping (session → subscribed events)
        - Returns session_timestamps for age calculation
        - Includes helper analysis for quick diagnostics

    Raises:
        - AttributeError if WebSocketManager not properly initialized

    Returns:
        dict: Complete internal state with mappings and diagnostics

    Example Response:
        {
            "active_connections": ["faithful zebra", "wise penguin"],
            "session_to_user": {"wise penguin": "ricardo_felipe_ruiz_6bdc"},
            "user_sessions": {"ricardo_felipe_ruiz_6bdc": ["wise penguin"]},
            "session_subscriptions": {"wise penguin": ["*"]},
            "diagnostics": {
                "unmapped_sessions": ["faithful zebra"],
                "total_active": 2,
                "authenticated": 1,
                "unauthenticated": 1
            }
        }
    """
    # Get WebSocketManager from main module
    import fastapi_app.main as main_module
    websocket_manager = main_module.websocket_manager

    # Extract internal state
    active_sessions = list(websocket_manager.active_connections.keys())
    session_to_user_map = dict(websocket_manager.session_to_user)
    user_sessions_map = {k: list(v) for k, v in websocket_manager.user_sessions.items()}
    session_subscriptions = {k: list(v) for k, v in websocket_manager.session_subscriptions.items()}

    # Build session timestamps (convert to ISO format)
    session_timestamps = {}
    for session_id, timestamp in websocket_manager.session_timestamps.items():
        session_timestamps[session_id] = timestamp.isoformat()

    # Diagnostic analysis
    unmapped_sessions = [sid for sid in active_sessions if sid not in session_to_user_map]
    authenticated_count = len(session_to_user_map)
    unauthenticated_count = len(unmapped_sessions)

    # Check for orphaned user mappings (user has sessions but none are active)
    orphaned_users = []
    for user_id, sessions in user_sessions_map.items():
        active_user_sessions = [s for s in sessions if s in active_sessions]
        if not active_user_sessions:
            orphaned_users.append(user_id)

    return {
        "active_connections": active_sessions,
        "session_to_user": session_to_user_map,
        "user_sessions": user_sessions_map,
        "session_subscriptions": session_subscriptions,
        "session_timestamps": session_timestamps,
        "diagnostics": {
            "total_active_connections": len(active_sessions),
            "authenticated_sessions": authenticated_count,
            "unauthenticated_sessions": unauthenticated_count,
            "unmapped_sessions": unmapped_sessions,
            "unique_users_connected": len(user_sessions_map),
            "orphaned_user_mappings": orphaned_users,
            "single_session_policy_enabled": websocket_manager.single_session_per_user
        },
        "timestamp": datetime.now().isoformat()
    }

@router.get("/api/config/client")
async def get_client_config( user_id: str = Depends( get_current_user_id ) ):
    """
    Return client-side configuration parameters for authenticated users.

    **Authentication**: REQUIRED - JWT token validated via dependency injection

    Requires:
        - Valid JWT token in Authorization header
        - ConfigurationManager initialized
        - lupin-app.ini contains timing settings (or uses defaults)

    Ensures:
        - Returns JSON with all client timing parameters
        - Only accessible to authenticated users (401 if unauthenticated)
        - Units converted appropriately for client use
        - Fallback defaults provided for missing config values

    Args:
        user_id: Authenticated user ID (injected by dependency, ensures JWT valid)

    Returns:
        JSON response with timing parameters:
        {
            "token_refresh_check_interval_ms": 600000,    # 10 mins in milliseconds
            "token_expiry_threshold_secs": 300,           # 5 mins in seconds
            "token_refresh_dedup_window_ms": 60000,       # 60 secs in milliseconds
            "websocket_heartbeat_interval_secs": 30       # Reference value (secs)
        }

    Example:
        GET /api/config/client
        Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

        Response 200:
        {
            "token_refresh_check_interval_ms": 600000,
            "token_expiry_threshold_secs": 300,
            "token_refresh_dedup_window_ms": 60000,
            "websocket_heartbeat_interval_secs": 30
        }
    """
    # Note: user_id parameter required by Depends() - validates JWT token
    # We don't use the actual user_id value, but it ensures authentication

    config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )

    # Fetch from config with fallback defaults
    refresh_check_interval_mins = config_mgr.get(
        "jwt_token_refresh_check_interval_mins",
        default=10
    )
    expiry_threshold_mins = config_mgr.get(
        "jwt_token_refresh_expiry_threshold_mins",
        default=5
    )
    dedup_window_secs = config_mgr.get(
        "jwt_token_refresh_dedup_window_secs",
        default=60
    )
    heartbeat_interval_secs = config_mgr.get(
        "websocket_heartbeat_interval_seconds",
        default=30
    )

    return {
        # Convert minutes → milliseconds (for setInterval)
        "token_refresh_check_interval_ms": int( refresh_check_interval_mins * 60 * 1000 ),

        # Convert minutes → seconds (for JWT exp comparison)
        "token_expiry_threshold_secs": int( expiry_threshold_mins * 60 ),

        # Convert seconds → milliseconds (for Date.now() comparison)
        "token_refresh_dedup_window_ms": int( dedup_window_secs * 1000 ),

        # Already in seconds (reference value for logging/debugging)
        "websocket_heartbeat_interval_secs": int( heartbeat_interval_secs )
    }