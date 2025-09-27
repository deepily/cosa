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
from ..auth import get_current_user
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
        - HTTPException with 403 status if authentication fails
        - HTTPException with 401 status if token is invalid/missing
        
    Args:
        current_user: Authenticated user information from JWT token
        
    Returns:
        dict: Success message, user details, and timestamp
        
    Note:
        REFACTORING CHANGE: This endpoint maintains 403 (Forbidden) status
        when called without auth token, same as original Flask implementation.
        Authentication behavior is preserved. Documented in refactoring plan 2025.01.24.
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