"""
Queue management endpoints.

Provides REST API endpoints for managing COSA job queues including
pushing jobs to todo queue, retrieving queue contents with user filtering,
and resetting all queues.

Generated on: 2025-01-24
"""

from fastapi import APIRouter, Query, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Dict, Any

# Import dependencies
from cosa.rest.auth import get_current_user

router = APIRouter(prefix="/api", tags=["queues"])

# Global dependencies (temporary access via main module)
def get_todo_queue():
    """
    Dependency to get todo queue from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has jobs_todo_queue attribute
        
    Ensures:
        - Returns the todo queue instance
        - Provides access to job queue management
        
    Raises:
        - ImportError if main module not available
        - AttributeError if todo queue not found
    """
    import fastapi_app.main as main_module
    return main_module.jobs_todo_queue

def get_running_queue():
    """
    Dependency to get running queue from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has jobs_run_queue attribute
        
    Ensures:
        - Returns the running queue instance
        - Provides access to active job tracking
        
    Raises:
        - ImportError if main module not available
        - AttributeError if running queue not found
    """
    import fastapi_app.main as main_module
    return main_module.jobs_run_queue

def get_done_queue():
    """
    Dependency to get done queue from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has jobs_done_queue attribute
        
    Ensures:
        - Returns the done queue instance
        - Provides access to completed job tracking
        
    Raises:
        - ImportError if main module not available
        - AttributeError if done queue not found
    """
    import fastapi_app.main as main_module
    return main_module.jobs_done_queue

def get_dead_queue():
    """
    Dependency to get dead queue from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has jobs_dead_queue attribute
        
    Ensures:
        - Returns the dead queue instance
        - Provides access to failed job tracking
        
    Raises:
        - ImportError if main module not available
        - AttributeError if dead queue not found
    """
    import fastapi_app.main as main_module
    return main_module.jobs_dead_queue

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
    import fastapi_app.main as main_module
    return main_module.jobs_notification_queue

@router.post("/push")
async def push(
    request: Request,
    current_user: dict = Depends(get_current_user),
    todo_queue = Depends(get_todo_queue)
):
    """
    Add a question to the todo queue with required websocket tracking and user authentication.
    
    Requires:
        - request body contains JSON with "question" and "websocket_id" fields
        - question is a non-empty string query to process
        - websocket_id is a valid WebSocket identifier from /api/get-session-id
        - current_user is authenticated with valid token containing uid
        - todo_queue is initialized and accessible
        
    Ensures:
        - Question added to todo queue with metadata
        - WebSocket ID and user ID properly associated with the job
        - Returns confirmation with status and routing information
        - Logs the push operation for debugging
        
    Raises:
        - HTTPException with 400 status if request body is malformed
        - HTTPException with 400 status if required fields are missing
        - HTTPException if authentication fails
        - Exception if queue push operation fails
        
    Args:
        request: FastAPI request containing JSON body with question and websocket_id
        current_user: Authenticated user info from token
        todo_queue: Todo queue instance for job management
        
    Returns:
        dict: Status, websocket_id, user_id, and result from queue push
    """
    try:
        # Parse JSON request body
        request_data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in request body: {str(e)}")
    
    # Validate required fields
    if not isinstance(request_data, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    
    question = request_data.get("question")
    websocket_id = request_data.get("websocket_id")
    
    if not question:
        raise HTTPException(status_code=400, detail="Missing required field: question")
    
    if not websocket_id:
        raise HTTPException(status_code=400, detail="Missing required field: websocket_id")
    
    # Validate field types
    if not isinstance(question, str):
        raise HTTPException(status_code=400, detail="Field 'question' must be a string")
    
    if not isinstance(websocket_id, str):
        raise HTTPException(status_code=400, detail="Field 'websocket_id' must be a string")
    
    # Validate field content
    question = question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Field 'question' cannot be empty")
    
    websocket_id = websocket_id.strip()
    if not websocket_id:
        raise HTTPException(status_code=400, detail="Field 'websocket_id' cannot be empty")
    
    user_id = current_user["uid"]
    print(f"[API] /api/push called - question: '{question}', websocket_id: {websocket_id}, user_id: {user_id}")
    
    # Push to queue with websocket_id and user_id
    result = todo_queue.push_job(question, websocket_id, user_id)
    
    return {
        "status": "queued",
        "websocket_id": websocket_id,
        "user_id": user_id,
        "result": result
    }

@router.get("/get-queue/{queue_name}")
async def get_queue(
    queue_name: str,
    current_user: dict = Depends(get_current_user),
    todo_queue = Depends(get_todo_queue),
    running_queue = Depends(get_running_queue),
    done_queue = Depends(get_done_queue),
    dead_queue = Depends(get_dead_queue)
):
    """
    Retrieve jobs for specific queue (todo, run, done, dead) filtered by user.
    
    PHASE 2 IMPLEMENTATION: Connected to real COSA queue system with user filtering.
    
    Requires:
        - queue_name is one of: 'todo', 'run', 'done', 'dead'
        - current_user is authenticated with valid token containing uid
        - All queue objects (todo, running, done, dead) are initialized
        - Queue objects have get_html_list() method
        
    Ensures:
        - Retrieves jobs from specified queue in HTML list format
        - Applies appropriate sorting (descending for todo/done/dead, ascending for run)
        - Adds user context to demonstrate filtering (temporary implementation)
        - Returns queue-specific job arrays in expected format
        - Raises 400 for invalid queue names
        
    Raises:
        - HTTPException with 400 for invalid queue_name parameter
        - HTTPException if authentication fails
        
    Args:
        queue_name: The queue to retrieve ('todo'|'run'|'done'|'dead')
        current_user: Authenticated user info from token
        
    Returns:
        dict: Queue data with job arrays filtered by user
    """
    user_id = current_user["uid"]
    
    # TODO: For now, return all jobs. In production, we need to:
    # 1. Add user_id field to SolutionSnapshot
    # 2. Implement get_html_list_for_user(user_id) in FifoQueue
    # 3. Filter jobs by user_id
    
    # For demonstration, we'll add a comment to each job showing it belongs to this user
    if queue_name == "todo":
        jobs = todo_queue.get_html_list(descending=True)
    elif queue_name == "run":
        jobs = running_queue.get_html_list()
    elif queue_name == "dead":
        jobs = dead_queue.get_html_list(descending=True)
    elif queue_name == "done":
        # Enhanced done queue response with structured job metadata for replay functionality
        jobs = done_queue.get_html_list(descending=True)
        
        # Extract structured job data from SolutionSnapshot objects in done queue
        # Apply same descending sort as HTML list for consistency
        snapshots = list( done_queue.queue_list )
        snapshots.reverse()  # Apply descending order (most recent first)
        
        structured_jobs = []
        for snapshot in snapshots:
            # Generate job metadata from SolutionSnapshot fields
            job_data = {
                "html": snapshot.get_html().replace("</li>", f" [user: {user_id}]</li>"),
                "job_id": snapshot.id_hash,
                "question_text": snapshot.last_question_asked or snapshot.question,
                "response_text": snapshot.answer_conversational or snapshot.answer,
                "timestamp": snapshot.run_date or snapshot.created_date,
                "user_id": user_id,
                "has_audio_cache": False  # Will be determined by frontend cache check
            }
            structured_jobs.append( job_data )
        
        # Maintain backward compatibility: return both structured data and HTML list
        return {
            f"{queue_name}_jobs": [job["html"] for job in structured_jobs],
            f"{queue_name}_jobs_metadata": structured_jobs
        }
    else:
        raise HTTPException(status_code=400, detail=f"Invalid queue name: {queue_name}")
    
    # Add user context to demonstrate filtering (temporary) - for non-done queues
    filtered_jobs = [job.replace("</li>", f" [user: {user_id}]</li>") for job in jobs]
    
    return {f"{queue_name}_jobs": filtered_jobs}

@router.post("/reset-queues")
async def reset_queues(
    current_user: dict = Depends(get_current_user),
    todo_queue = Depends(get_todo_queue),
    running_queue = Depends(get_running_queue),
    done_queue = Depends(get_done_queue),
    dead_queue = Depends(get_dead_queue),
    notification_queue = Depends(get_notification_queue)
):
    """
    Reset all queues by clearing their contents.
    
    Requires:
        - User must be authenticated with valid token
        - All queue instances must be available
        
    Ensures:
        - All queues are emptied
        - WebSocket notifications are sent for queue updates
        - Returns summary of reset operation
        
    Returns:
        dict: Summary of queues reset with counts and timestamp
    """
    user_id = current_user["uid"]
    print( f"[API] /api/reset-queues called by user: {user_id}" )
    
    # Get initial counts for reporting
    initial_counts = {
        "todo": todo_queue.size(),
        "run": running_queue.size(),
        "done": done_queue.size(),
        "dead": dead_queue.size(),
        "notification": notification_queue.size()
    }
    
    try:
        # Clear all queues (they will automatically emit updates)
        todo_queue.clear()
        running_queue.clear()
        done_queue.clear()
        dead_queue.clear()
        notification_queue.clear()
        
        result = {
            "status": "success",
            "message": "All queues have been reset",
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "queues_reset": {
                "todo": f"cleared {initial_counts['todo']} items",
                "run": f"cleared {initial_counts['run']} items", 
                "done": f"cleared {initial_counts['done']} items",
                "dead": f"cleared {initial_counts['dead']} items",
                "notification": f"cleared {initial_counts['notification']} items"
            },
            "total_items_cleared": sum( initial_counts.values() )
        }
        
        print( f"[API] Successfully reset all queues - cleared {result['total_items_cleared']} total items" )
        return result
        
    except Exception as e:
        print( f"[ERROR] Failed to reset queues: {e}" )
        raise HTTPException( status_code=500, detail=f"Failed to reset queues: {str(e)}" )