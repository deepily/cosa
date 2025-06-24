"""
Job and snapshot management endpoints
Generated on: 2025-01-24
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime
import os

router = APIRouter(tags=["jobs"])

# Global dependencies (temporary access via main module)
def get_static_dir():
    """Dependency to get static directory"""
    import fastapi_app.main as main_module
    return main_module.static_dir

@router.get("/api/delete-snapshot/{id}")
async def delete_snapshot(id: str):
    """
    Delete a completed job snapshot.
    
    PHASE 1 STUB: Returns mock success response for testing.
    
    Preconditions:
        - id must be a valid job identifier
        
    Postconditions:
        - Returns success confirmation (stubbed)
        
    Args:
        id: The job identifier to delete
        
    Returns:
        dict: Deletion status
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
    
    Preconditions:
        - id must be a valid job identifier
        - Audio file should exist for the job
        
    Postconditions:
        - Returns audio file stream (stubbed with placeholder)
        
    Args:
        id: The job identifier to get audio for
        
    Returns:
        FileResponse: Audio file for playback
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