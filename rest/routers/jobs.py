"""
Job and snapshot management endpoints.

Provides REST API endpoints for managing job lifecycle including
snapshot deletion and audio answer retrieval. Currently implements
stub functionality for Phase 1 development.

Generated on: 2025-01-24
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime
import os

router = APIRouter(tags=["jobs"])

# Global dependencies (temporary access via main module)
def get_static_dir():
    """
    Dependency to get static directory from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has static_dir attribute
        
    Ensures:
        - Returns the static directory path
        - Provides access to static assets
        
    Raises:
        - ImportError if main module not available
        - AttributeError if static_dir not found
    """
    import fastapi_app.main as main_module
    return main_module.static_dir

@router.get("/api/delete-snapshot/{id}")
async def delete_snapshot(id: str):
    """
    Delete a completed job snapshot.
    
    PHASE 1 STUB: Returns mock success response for testing.
    
    Requires:
        - id is a non-empty string identifier
        - id does not start with "invalid" (for stub validation)
        
    Ensures:
        - Returns success status with job ID and timestamp
        - Raises 404 HTTPException for invalid IDs
        - Provides mock deletion confirmation
        
    Raises:
        - HTTPException with 404 status for invalid or missing IDs
        
    Args:
        id: The job identifier to delete
        
    Returns:
        dict: Deletion status with confirmation details
    """
    print(f"[STUB] /api/delete-snapshot/{id} called")
    
    # Mock deletion logic
    if not id or id.startswith("invalid"):
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {id}")
    
    return {
        "status": "deleted",
        "id": id,
        "message": f"Snapshot {id} deleted successfully (STUB)",
        "timestamp": datetime.now().isoformat()
    }

@router.get("/get-answer/{id}")
async def get_answer(id: str):
    """
    Retrieve audio answer for completed job.
    
    PHASE 1 STUB: Returns a placeholder audio file for testing.
    
    Requires:
        - id is a non-empty string identifier
        - fastapi_app.main module is accessible
        - static_dir contains audio/gentle-gong.mp3 file
        - Placeholder audio file exists in static directory
        
    Ensures:
        - Returns FileResponse with audio/mpeg media type
        - Uses placeholder gentle-gong.mp3 for all requests
        - Sets appropriate filename with job ID
        - Raises 404 if placeholder audio file missing
        
    Raises:
        - HTTPException with 404 status if audio file not found
        - ImportError if main module not accessible
        
    Args:
        id: The job identifier to get audio for
        
    Returns:
        FileResponse: Audio file stream for playback
    """
    print(f"[STUB] /get-answer/{id} called")
    
    # Get static directory from main module
    import fastapi_app.main as main_module
    static_dir = main_module.static_dir
    
    # For now, return the gentle gong as placeholder audio
    audio_file_path = os.path.join(static_dir, "audio", "gentle-gong.mp3")
    
    if not os.path.exists(audio_file_path):
        raise HTTPException(status_code=404, detail=f"Audio file not found for job: {id}")
    
    return FileResponse(
        path=audio_file_path,
        media_type="audio/mpeg",
        filename=f"answer-{id}.mp3"
    )