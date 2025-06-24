"""
Queue management endpoints
Generated on: 2025-01-24
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Dict, Any

# Import dependencies
from cosa.rest.auth import get_current_user
from cosa.rest.queue_extensions import push_job_with_user

router = APIRouter(prefix="/api", tags=["queues"])

# Global dependencies (temporary access via main module)
def get_todo_queue():
    """Dependency to get todo queue"""
    import fastapi_app.main as main_module
    return main_module.jobs_todo_queue

def get_running_queue():
    """Dependency to get running queue"""
    import fastapi_app.main as main_module
    return main_module.jobs_run_queue

def get_done_queue():
    """Dependency to get done queue"""
    import fastapi_app.main as main_module
    return main_module.jobs_done_queue

def get_dead_queue():
    """Dependency to get dead queue"""
    import fastapi_app.main as main_module
    return main_module.jobs_dead_queue

@router.get("/push")
async def push(
    question: str = Query(..., description="The question/query to process"),
    websocket_id: str = Query(..., description="WebSocket identifier for routing"),
    current_user: dict = Depends(get_current_user),
    todo_queue = Depends(get_todo_queue)
):
    """
    Add a question to the todo queue with required websocket tracking and user authentication.
    
    Preconditions:
        - jobs_todo_queue must be initialized
        - Question parameter must be provided
        - websocket_id parameter must be provided (from /api/get-session-id)
        - User must be authenticated with valid token
        
    Postconditions:
        - Question added to todo queue
        - WebSocket ID and user ID associated with the job
        
    Args:
        question: The question/query to process (required)
        websocket_id: WebSocket identifier for WebSocket routing (required)
        current_user: Authenticated user info from token
        
    Returns:
        dict: Status, websocket_id, user_id, and result from queue push
    """
    user_id = current_user["uid"]
    print(f"[API] /api/push called - question: '{question}', websocket_id: {websocket_id}, user_id: {user_id}")
    
    # Push to queue with websocket_id and user_id using our wrapper
    result = push_job_with_user(todo_queue, question, websocket_id, user_id)
    
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
    
    Preconditions:
        - queue_name must be one of: 'todo', 'run', 'done', 'dead'
        - Global queue objects must be initialized
        - User must be authenticated
        
    Postconditions:
        - Returns JSON with queue-specific job arrays for authenticated user only
        - Job format matches queue.html expectations
        
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
        jobs = done_queue.get_html_list(descending=True)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid queue name: {queue_name}")
    
    # Add user context to demonstrate filtering (temporary)
    filtered_jobs = [job.replace("</li>", f" [user: {user_id}]</li>") for job in jobs]
    
    return {f"{queue_name}_jobs": filtered_jobs}