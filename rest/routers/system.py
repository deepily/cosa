"""
System and health check endpoints
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
from cosa.agents.v010.two_word_id_generator import TwoWordIdGenerator
import cosa.utils.util as du

router = APIRouter(tags=["system"])

@router.get("/", response_class=JSONResponse)
async def health_check():
    """
    Basic health check endpoint.
    
    Preconditions:
        - Application must be running
    
    Postconditions:
        - Returns current health status with timestamp
    
    Returns:
        dict: Health status including service name, timestamp, and version
    """
    return {
        "status": "healthy",
        "service": "genie-in-the-box-fastapi",
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0"
    }

@router.get("/health", response_class=JSONResponse)
async def health():
    """
    Simple health endpoint for monitoring.
    
    Preconditions:
        - Application must be running
    
    Postconditions:
        - Returns OK status with current timestamp
    
    Returns:
        dict: Status and timestamp
    """
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }

@router.get("/api/init", response_class=JSONResponse)
async def init():
    """
    Refresh configuration and reload application resources.
    
    Preconditions:
        - Application must be running
        - Configuration files must exist at specified paths
        - All global components must be previously initialized
    
    Postconditions:
        - Configuration manager is refreshed with latest values
        - Solution snapshots are reloaded from disk
        - STT model remains loaded (already in memory)
        - Returns success message
    
    Returns:
        dict: Success message and timestamp
    
    Note:
        Unlike Flask version, STT model is not reloaded as it's 
        already managed by the lifespan context manager
    """
    try:
        # Import global variables from main (temporary solution)
        import fastapi_app.main as main_module
        
        # Refresh configuration manager
        config_mgr = ConfigurationManager(env_var_name="GIB_CONFIG_MGR_CLI_ARGS")
        config_mgr.print_configuration(brackets=True)
        
        # Reload snapshots using the global snapshot manager
        if hasattr(main_module, 'snapshot_mgr') and main_module.snapshot_mgr:
            print("Reloading solution snapshots...")
            main_module.snapshot_mgr.load_snapshots()
        
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
    Generate and return a unique session ID for WebSocket communication.
    
    Preconditions:
        - id_generator must be initialized
        
    Postconditions:
        - Generates a unique two-word ID
        - Returns the ID as a string
        
    Returns:
        dict: Contains the generated session_id
        
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
    Test endpoint to verify authentication is working.
    
    Preconditions:
        - Valid authentication token must be provided
        - get_current_user dependency must be working
    
    Postconditions:
        - Returns success message with user information
        - Confirms authentication system is functional
    
    Returns:
        dict: Success message and user details
        
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