"""
Queue management endpoints.

Provides REST API endpoints for managing COSA job queues including
pushing jobs to todo queue, retrieving queue contents with user filtering,
and resetting all queues.

Generated on: 2025-01-24
"""

import asyncio

from fastapi import APIRouter, Query, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Dict, Any, Optional

import cosa.utils.util as cu

# Import dependencies
from cosa.rest.auth import get_current_user
from cosa.rest.queue_auth import authorize_queue_filter
from cosa.rest.auth_middleware import is_admin
from cosa.agents.agentic_job_base import AgenticJobBase
from cosa.rest.job_state import JobState
from cosa.rest.queue_util import emit_job_state_transition

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

@router.post(
    "/push",
    summary     = "Push job to queue",
    description = "Submit a new job to the todo queue. Requires question and websocket_id in request body."
)
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
    
    user_id    = current_user["uid"]
    user_email = current_user["email"]
    print( f"[API] /api/push called - question: '{question}', websocket_id: {websocket_id}, user_id: {user_id}, user_email: {user_email}" )

    # Push to queue with websocket_id, user_id, and user_email for TTS routing
    try:
        result = await asyncio.to_thread( todo_queue.push_job, question, websocket_id, user_id, user_email )
        print(f"[API] /api/push successful - result: {result}")
    except Exception as e:
        print(f"[API] /api/push failed - error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to push job to queue: {str(e)}")

    return {
        "status"       : "queued",
        "websocket_id" : websocket_id,
        "user_id"      : user_id,
        "job_id"       : result.get( "job_id" ) if isinstance( result, dict ) else None,
        "result"       : result.get( "message", str( result ) ) if isinstance( result, dict ) else str( result )
    }

@router.get(
    "/get-queue/{queue_name}",
    summary     = "Get queue contents",
    description = "Retrieve jobs from a named queue (todo/run/done/dead) with role-based user filtering."
)
async def get_queue(
    queue_name: str,
    current_user: dict = Depends(get_current_user),
    user_filter: Optional[str] = Query(
        None,
        description="User filter: omit for self, '*' for all (admin), or specific user_id (admin)",
        example="ricardo_felipe_ruiz_6bdc"
    ),
    todo_queue = Depends(get_todo_queue),
    running_queue = Depends(get_running_queue),
    done_queue = Depends(get_done_queue),
    dead_queue = Depends(get_dead_queue)
):
    """
    Retrieve jobs from queue with role-based user filtering.

    **PHASE 1 IMPLEMENTATION:** User-filtered queue views with role-based access control

    Authorization Rules:
    - Regular users: Can ONLY query their own jobs (user_filter ignored or must match self)
    - Admin users: Can query own, specific user's, or all users' jobs

    Query Parameters:
        - user_filter: Optional[str]
            - None (omit): Current user's jobs (default for all users)
            - "*": ALL users' jobs (admin only)
            - "user_id_xyz": Specific user's jobs (admin only)

    Requires:
        - queue_name is one of: 'todo', 'run', 'done', 'dead'
        - current_user is authenticated with valid token containing uid
        - All queue objects (todo, running, done, dead) are initialized

    Ensures:
        - Retrieves jobs from specified queue filtered by user
        - Applies appropriate sorting (descending for todo/done/dead, ascending for run)
        - Returns queue-specific job arrays in expected format
        - Raises 400 for invalid queue names
        - Raises 403 if regular user attempts admin operations

    Raises:
        - HTTPException 400: Invalid queue_name parameter
        - HTTPException 403: Unauthorized user filter access
        - HTTPException 401: Authentication fails

    Args:
        queue_name: The queue to retrieve ('todo'|'run'|'done'|'dead')
        current_user: Authenticated user info from token
        user_filter: Optional filter (None=self, "*"=all, or user_id)
        todo_queue: Todo queue dependency
        running_queue: Running queue dependency
        done_queue: Done queue dependency
        dead_queue: Dead queue dependency

    Returns:
        dict: Queue data with job arrays, metadata, and filtering info
    """

    # Step 1: Authorize the filter request
    try:
        authorized_filter = authorize_queue_filter(
            current_user=current_user,
            filter_user_id=user_filter
        )
    except HTTPException:
        raise  # Re-raise authorization failures

    # Step 2: Map queue name to queue object
    queue_map = {
        "todo": todo_queue,
        "run": running_queue,
        "done": done_queue,
        "dead": dead_queue
    }

    if queue_name not in queue_map:
        raise HTTPException(status_code=400, detail=f"Invalid queue name: {queue_name}")

    queue = queue_map[queue_name]

    # Step 3: Retrieve jobs based on authorized filter
    if authorized_filter == "*":
        # Admin requesting ALL users' jobs
        jobs = queue.get_all_jobs()
    elif authorized_filter.startswith( "!" ):
        # Admin requesting all jobs EXCEPT their own ("!user_id" sentinel)
        jobs = queue.get_jobs_excluding_user( authorized_filter[ 1: ] )
    else:
        # Specific user's jobs (could be self or other for admin)
        jobs = queue.get_jobs_for_user( authorized_filter )

    # Step 4: Apply queue-specific sorting
    descending = queue_name in ["todo", "done", "dead"]
    if descending:
        jobs.reverse()

    # Step 5: Handle done queue special case (metadata + HTML)
    if queue_name == "done":
        # Extract structured job data from SolutionSnapshot or AgenticJobBase objects
        structured_jobs = []
        for job in jobs:
            # Phase 3: Explicit type check replaces duck typing hasattr() checks
            is_agentic_job = isinstance( job, AgenticJobBase )

            # Generate job metadata using unified interface properties
            # All job types now have: job_type, question, last_question_asked, answer,
            # answer_conversational, run_date, created_date, session_id
            job_data = {
                "job_id"          : job.id_hash,
                "question_text"   : job.last_question_asked,
                "response_text"   : job.answer_conversational or job.answer,
                "timestamp"       : job.run_date or job.created_date,
                "user_id"         : authorized_filter,
                "user_email"      : job.user_email,
                "session_id"      : job.session_id,  # For job-notification correlation
                "agent_type"      : job.job_type,  # Unified property replaces getattr() chain
                "has_interactions": bool( job.session_id ),  # True if can query notifications
                "has_audio_cache" : False,  # Will be determined by frontend cache check
                "is_cache_hit"    : job.is_cache_hit,  # For Time Saved Dashboard
                # Phase 7: Agentic job artifacts for enhanced done cards
                "report_path"               : job.artifacts.get( 'report_path' ) if is_agentic_job else None,
                "remediation_snapshot_path" : job.artifacts.get( 'remediation_snapshot_path' ) if is_agentic_job else None,
                "yaml_path"                : job.artifacts.get( 'yaml_path' ) if is_agentic_job else None,
                "abstract"        : job.artifacts.get( 'abstract' ) if is_agentic_job else None,
                "cost_summary"    : job.cost_summary if is_agentic_job else None,
                "started_at"      : job.started_at,
                "completed_at"    : job.completed_at,
                "status"          : job.state.value if hasattr( job.state, 'value' ) else str( job.state ),
                "error"           : job.error,
                "scheduled_at"    : getattr( job, 'scheduled_at', None ),
                "monopolize"      : getattr( job, 'monopolize', False ),
                "paused"          : job.state == JobState.PAUSED,
            }

            # Calculate duration for agentic jobs
            if is_agentic_job and job_data[ "started_at" ] and job_data[ "completed_at" ]:
                try:
                    start = datetime.fromisoformat( job_data[ "started_at" ] )
                    end   = datetime.fromisoformat( job_data[ "completed_at" ] )
                    job_data[ "duration_seconds" ] = ( end - start ).total_seconds()
                except Exception:
                    job_data[ "duration_seconds" ] = None
            else:
                job_data[ "duration_seconds" ] = None

            structured_jobs.append( job_data )

        # Return structured metadata (HTML field deprecated - frontend uses metadata exclusively)
        return {
            f"{queue_name}_jobs_metadata": structured_jobs,
            "filtered_by": authorized_filter,
            "is_admin_view": is_admin( current_user ) and ( user_filter is not None ),
            "total_jobs": len( structured_jobs )
        }

    # Step 5b: Handle dead queue — surface partial artifacts from failed-
    # before-completion runs so users can recover diagnoses/plans that the
    # job computed before dying. Previously fell through to the generic
    # todo/run branch which only returned basic fields; dead TFE/BFE jobs
    # that wrote a Phase 2 plan had no way to surface it to the UI.
    # See: src/rnd/v0.1.6/2026.04.11-tfe-forensics-capture-plan.md (Fix 8b)
    if queue_name == "dead":
        structured_jobs = []
        for job in jobs:
            is_agentic_job = isinstance( job, AgenticJobBase )
            job_data = {
                "job_id"          : job.id_hash,
                "question_text"   : job.last_question_asked,
                "timestamp"       : job.run_date or job.created_date,
                "user_id"         : authorized_filter,
                "user_email"      : job.user_email,
                "session_id"      : job.session_id,
                "agent_type"      : job.job_type,
                "status"          : job.state.value if hasattr( job.state, 'value' ) else str( job.state ),
                "started_at"      : job.started_at,
                "completed_at"    : job.completed_at,
                "error"           : job.error,
                "is_cache_hit"    : False,
                "has_interactions": bool( job.session_id ),
                "scheduled_at"    : getattr( job, 'scheduled_at', None ),
                "monopolize"      : getattr( job, 'monopolize', False ),
                "paused"          : job.state == JobState.PAUSED,
                # Partial artifacts from failed-before-completion runs.
                # Agents that died mid-pipeline may have populated any of these.
                "plan_path"                : job.artifacts.get( 'plan_path' )                if is_agentic_job else None,
                "remediation_snapshot_path": job.artifacts.get( 'remediation_snapshot_path' ) if is_agentic_job else None,
                "report_path"              : job.artifacts.get( 'report_path' )              if is_agentic_job else None,
                "yaml_path"                : job.artifacts.get( 'yaml_path' )                if is_agentic_job else None,
                "cost_summary"             : job.cost_summary                                 if is_agentic_job else None,
            }
            # Calculate duration for agentic jobs when both timestamps exist
            if is_agentic_job and job_data[ "started_at" ] and job_data[ "completed_at" ]:
                try:
                    start = datetime.fromisoformat( job_data[ "started_at" ] )
                    end   = datetime.fromisoformat( job_data[ "completed_at" ] )
                    job_data[ "duration_seconds" ] = ( end - start ).total_seconds()
                except Exception:
                    job_data[ "duration_seconds" ] = None
            else:
                job_data[ "duration_seconds" ] = None

            structured_jobs.append( job_data )

        return {
            f"{queue_name}_jobs_metadata": structured_jobs,
            "filtered_by" : authorized_filter,
            "is_admin_view": is_admin( current_user ) and ( user_filter is not None ),
            "total_jobs"  : len( structured_jobs ),
        }

    # Step 6: Handle todo/run queues with metadata (Phase 7)
    # Using unified interface properties - all job types now have consistent attributes
    structured_jobs = []
    for job in jobs:
        job_data = {
            "job_id"       : job.id_hash,
            "question_text": job.last_question_asked,
            "timestamp"    : job.run_date or job.created_date,
            "user_id"      : authorized_filter,
            "user_email"   : job.user_email,
            "session_id"   : job.session_id,
            "agent_type"   : job.job_type,  # Unified property replaces getattr() chain
            "status"       : job.state.value if hasattr( job.state, 'value' ) else str( job.state ),
            "started_at"   : job.started_at,
            "error"        : job.error,
            "scheduled_at" : getattr( job, 'scheduled_at', None ),
            "monopolize"   : getattr( job, 'monopolize', False ),
            "paused"       : job.state == JobState.PAUSED,
        }
        structured_jobs.append( job_data )

    # Return structured metadata (HTML field deprecated - frontend uses metadata exclusively)
    is_admin_override = is_admin( current_user ) and ( user_filter is not None )

    return {
        f"{queue_name}_jobs_metadata": structured_jobs,
        "filtered_by": authorized_filter,
        "is_admin_view": is_admin_override,
        "total_jobs": len( structured_jobs )
    }

@router.post(
    "/reset-queues",
    summary     = "Reset all queues",
    description = "Clear all five queues (todo, run, done, dead, notification) and return items-cleared summary."
)
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
            "timestamp": cu.get_current_datetime_iso(),
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


@router.get(
    "/get-job-interactions/{job_id}",
    summary     = "Get job interactions",
    description = "Retrieve notification interaction history for a job with progress deduplication."
)
async def get_job_interactions(
    job_id: str,
    current_user: dict = Depends( get_current_user ),
    todo_queue    = Depends( get_todo_queue ),
    running_queue = Depends( get_running_queue ),
    done_queue    = Depends( get_done_queue )
):
    """
    Get notification interaction history for a completed job.

    Requires:
        - job_id is a valid job identifier
        - current_user is authenticated
        - Job belongs to current user OR user is admin

    Ensures:
        - Returns job metadata + interaction history
        - Interactions ordered newest-first
        - Returns empty interactions list if job has no session_id

    Returns:
        dict: {job_id, session_id, job_metadata, interactions: [...]}
    """
    from datetime import timezone, timedelta
    from cosa.rest.db.database import get_db
    from cosa.rest.db.repositories.notification_repository import NotificationRepository
    from cosa.rest.db.repositories.user_repository import UserRepository
    from cosa.rest.postgres_models import Notification

    print( f"[API] /api/get-job-interactions/{job_id} called by user: {current_user['uid']}" )

    # Find job across all queues (running, done, todo) by compound ID
    job = None
    for queue in [ running_queue, done_queue, todo_queue ]:
        for snapshot in queue.get_all_jobs():
            if snapshot.id_hash == job_id:
                job = snapshot
                break
        if job:
            break

    # DB fallback when job not found in in-memory queues
    db_job = None
    if not job:
        from cosa.rest.job_persistence import get_job_by_id_hash
        db_job = get_job_by_id_hash( job_id )
        if not db_job:
            print( f"[API] Job not found in any queue or DB: {job_id}" )
            raise HTTPException( status_code=404, detail=f"Job not found: {job_id}" )
        print( f"[API] Job {job_id} found in DB (not in memory)" )

    # Authorization check — db_job is a dict, job is an object
    if job:
        job_owner = job.user_id
    else:
        job_owner = db_job.get( "user_id" )
    if job_owner and job_owner != current_user["uid"] and not is_admin( current_user ):
        print( f"[API] Unauthorized access to job {job_id} by {current_user['uid']}" )
        raise HTTPException( status_code=403, detail="Not authorized to view this job" )

    # Build response from in-memory job or DB fallback
    if job:
        response = {
            "job_id"       : job_id,
            "session_id"   : job.session_id,
            "job_metadata" : {
                "question"    : job.last_question_asked,
                "answer"      : job.answer_conversational or job.answer,
                "agent_type"  : job.job_type,
                "run_date"    : job.run_date,
                "created_date": job.created_date
            },
            "interactions"      : [],
            "interaction_count" : 0
        }
    else:
        metadata   = db_job.get( "metadata_json" ) or {}
        created_at = db_job.get( "created_at" )
        response = {
            "job_id"       : job_id,
            "session_id"   : db_job.get( "session_id" ),
            "job_metadata" : {
                "question"    : db_job.get( "question_text" ),
                "answer"      : metadata.get( "answer_conversational" ) or metadata.get( "response_text" ),
                "agent_type"  : db_job.get( "job_type" ),
                "run_date"    : created_at.isoformat() if hasattr( created_at, "isoformat" ) else created_at,
                "created_date": created_at.isoformat() if hasattr( created_at, "isoformat" ) else created_at
            },
            "interactions"      : [],
            "interaction_count" : 0
        }

    # Query notifications by job_id (direct lookup - much simpler than time-window)
    try:
        with get_db() as db:
            print( f"[API] Querying notifications for job_id={job_id}" )

            notifications = db.query( Notification ).filter(
                Notification.job_id == job_id
            ).order_by( Notification.created_at.desc() ).all()

            # Deduplicate progress groups: keep only latest per progress_group_id
            # Notifications are ordered newest-first, so first occurrence is latest
            seen_groups = set()
            deduped     = []
            for n in notifications:
                if n.progress_group_id:
                    if n.progress_group_id in seen_groups:
                        continue
                    seen_groups.add( n.progress_group_id )
                deduped.append( n )

            response["interactions"] = [
                {
                    "id"                 : str( n.id ),
                    "type"               : n.type,
                    "message"            : n.message,
                    "timestamp"          : n.created_at.isoformat(),
                    "response_requested" : n.response_requested,
                    "response_value"     : n.response_value,
                    "priority"           : n.priority,
                    "abstract"           : n.abstract
                }
                for n in deduped
            ]
            response["interaction_count"] = len( deduped )

            print( f"[API] Found {len( notifications )} interactions for job {job_id}" )

    except Exception as e:
        print( f"[API] Error querying notifications: {e}" )
        # Return empty interactions rather than failing
        pass

    return response


@router.post(
    "/jobs/{job_id}/message",
    summary     = "Send message to job",
    description = "Send a user-initiated message to a running agentic job via WebSocket notification."
)
async def send_job_message(
    job_id: str,
    request: Request,
    current_user: dict = Depends( get_current_user ),
    running_queue = Depends( get_running_queue ),
):
    """
    Send a user message to a running SWE Team job.

    Creates a notification with type="user_initiated_message" targeting the
    specified job_id. The job's orchestrator notification client receives this
    via WebSocket and queues it for consumption at the next check-in point.

    Requires:
        - job_id identifies a currently running job
        - request body contains {"message": str, "priority": "normal"|"urgent"}
        - current_user is authenticated

    Ensures:
        - Notification created in database with user_initiated_message type
        - WebSocket event emitted to job owner for delivery
        - Returns notification_id on success

    Raises:
        - HTTPException 400: Missing or invalid request body
        - HTTPException 404: Job not found in running queue
        - HTTPException 403: User does not own this job

    Args:
        job_id: Target running job ID
        request: FastAPI request with JSON body
        current_user: Authenticated user info
        running_queue: Running queue dependency

    Returns:
        dict: {status, notification_id, job_id}
    """
    # Parse request body
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException( status_code=400, detail=f"Invalid JSON: {e}" )

    message_text = body.get( "message", "" ).strip()
    priority     = body.get( "priority", "normal" )

    if not message_text:
        raise HTTPException( status_code=400, detail="Message cannot be empty" )

    if priority not in ( "normal", "urgent" ):
        raise HTTPException( status_code=400, detail="Priority must be 'normal' or 'urgent'" )

    user_id = current_user[ "uid" ]

    print( f"[API] POST /api/jobs/{job_id}/message - user: {user_id}, priority: {priority}" )

    # Validate job exists and is running
    try:
        job = running_queue.get_by_id_hash( job_id )
    except KeyError:
        raise HTTPException( status_code=404, detail=f"Job not found or not running: {job_id}" )

    # Validate user owns this job
    if job.user_id != user_id and not is_admin( current_user ):
        raise HTTPException( status_code=403, detail="Not authorized to message this job" )

    # Create notification record
    try:
        from cosa.rest.db.database import get_db
        from cosa.rest.db.repositories.notification_repository import NotificationRepository
        from cosa.rest.db.repositories.user_repository import UserRepository

        with get_db() as db:
            user_repo = UserRepository( db )
            user = user_repo.get_by_email( current_user[ "email" ] )

            if not user:
                raise HTTPException( status_code=404, detail="User not found" )

            notif_repo = NotificationRepository( db )
            notification = notif_repo.create_notification(
                sender_id          = f"user@{current_user[ 'email' ]}",
                recipient_id       = user.id,
                message            = message_text,
                type               = "user_initiated_message",
                priority           = priority,
                response_requested = False,
                job_id             = job_id,
            )
            db.commit()

            notification_id = str( notification.id )
            user_id_db      = user.id

    except HTTPException:
        raise
    except Exception as e:
        print( f"[API] Error creating notification: {e}" )
        raise HTTPException( status_code=500, detail=f"Failed to create notification: {e}" )

    # Emit WebSocket event to deliver to orchestrator's notification client
    try:
        import fastapi_app.main as main_module
        ws_manager = main_module.websocket_manager

        ws_manager.emit_to_user_sync(
            user_id = user_id,
            event   = "notification_queue_update",
            data    = {
                "notification": {
                    "id"                : notification_id,
                    "id_hash"           : notification_id,
                    "type"              : "user_initiated_message",
                    "notification_type" : "user_initiated_message",
                    "message"           : message_text,
                    "priority"          : priority,
                    "job_id"            : job_id,
                    "sender_id"         : f"user@{current_user[ 'email' ]}",
                    "timestamp"         : cu.get_current_datetime_iso(),
                },
            },
        )

        # Cross-user delivery: CC listeners authenticate as a service account
        # (different user_id), so emit_to_user_sync won't reach them.
        if job_id:
            listener_sid = f"cc-listener-{job_id}"
            ws_manager.emit_to_session_sync(
                session_id = listener_sid,
                event      = "notification_queue_update",
                data       = {
                    "notification": {
                        "id"                : notification_id,
                        "id_hash"           : notification_id,
                        "type"              : "user_initiated_message",
                        "notification_type" : "user_initiated_message",
                        "message"           : message_text,
                        "priority"          : priority,
                        "job_id"            : job_id,
                        "sender_id"         : f"user@{current_user[ 'email' ]}",
                        "timestamp"         : cu.get_current_datetime_iso(),
                    },
                },
            )

        # Echo acknowledgment back to user as a progress notification
        # Persist to database so it appears in job interaction history
        echo_message = "📨 Your message has been queued"

        try:
            with get_db() as db2:
                notif_repo2 = NotificationRepository( db2 )
                echo_notif  = notif_repo2.create_notification(
                    sender_id          = f"swe.lead@lupin",
                    recipient_id       = user_id_db,
                    message            = echo_message,
                    type               = "progress",
                    priority           = "low",
                    response_requested = False,
                    job_id             = job_id,
                )
                db2.commit()
                echo_id = str( echo_notif.id )
        except Exception as echo_err:
            print( f"[API] Warning: Echo persistence failed (non-fatal): {echo_err}" )
            echo_id = f"echo-{notification_id}"

        echo_data = {
            "notification": {
                "id"                : echo_id,
                "id_hash"           : echo_id,
                "type"              : "progress",
                "notification_type" : "progress",
                "message"           : echo_message,
                "priority"          : "low",
                "job_id"            : job_id,
                "sender_id"         : f"swe.lead@lupin",
                "timestamp"         : cu.get_current_datetime_iso(),
            },
        }
        ws_manager.emit_to_user_sync( user_id=user_id, event="notification_queue_update", data=echo_data )

    except Exception as e:
        print( f"[API] Warning: WebSocket emission failed (message still persisted): {e}" )

    print( f"[API] User message delivered to job {job_id}: {message_text[ :80 ]}" )

    return {
        "status"          : "delivered",
        "notification_id" : notification_id,
        "job_id"          : job_id,
    }


@router.post(
    "/jobs/{job_id}/cancel",
    summary     = "Cancel running job",
    description = "Request graceful cancellation of a running agentic job at its next phase boundary."
)
async def cancel_job(
    job_id: str,
    current_user: dict = Depends( get_current_user ),
    running_queue = Depends( get_running_queue ),
):
    """
    Request graceful cancellation of a running agentic job.

    Sets the job's cancel flag so it stops at the next phase-boundary checkpoint.
    Only agentic jobs (deep research, podcast generator) support cancellation.

    Requires:
        - job_id identifies a currently running job
        - current_user is authenticated
        - Job belongs to current user OR user is admin

    Ensures:
        - Job's _cancel_requested flag is set to True
        - Orchestrator's _stop_requested flag is set (if available)
        - Job will stop at next checkpoint (0-60 seconds latency)
        - Returns confirmation of cancel request

    Raises:
        - HTTPException 404: Job not found in running queue
        - HTTPException 403: User does not own this job
        - HTTPException 400: Job type does not support cancellation

    Args:
        job_id: Target running job ID
        current_user: Authenticated user info
        running_queue: Running queue dependency

    Returns:
        dict: {status, job_id, message}
    """
    user_id = current_user[ "uid" ]

    print( f"[API] POST /api/jobs/{job_id}/cancel - user: {user_id}" )

    # Validate job exists and is running
    try:
        job = running_queue.get_by_id_hash( job_id )
    except KeyError:
        raise HTTPException( status_code=404, detail=f"Job not found or not running: {job_id}" )

    # Validate ownership (user or admin)
    if job.user_id != user_id and not is_admin( current_user ):
        raise HTTPException( status_code=403, detail="Not authorized to cancel this job" )

    # Check if it's an agentic job (only agentic jobs support cancellation)
    if not isinstance( job, AgenticJobBase ):
        raise HTTPException( status_code=400, detail="Only agentic jobs support cancellation" )

    # Request graceful cancellation
    job.request_cancel()

    print( f"[API] Cancel requested for job {job_id} by user {user_id}" )

    return {
        "status"  : "cancel_requested",
        "job_id"  : job_id,
        "message" : "Cancellation requested. Job will stop at next checkpoint.",
    }


@router.delete(
    "/queue/{queue_name}/{job_id}",
    summary     = "Remove job from queue",
    description = "Forcefully remove a job from todo, run, done, or dead queue."
)
async def delete_queue_job(
    queue_name: str,
    job_id: str,
    current_user: dict = Depends( get_current_user ),
    running_queue = Depends( get_running_queue ),
    done_queue    = Depends( get_done_queue ),
    dead_queue    = Depends( get_dead_queue ),
    todo_queue    = Depends( get_todo_queue ),
):
    """
    Forcefully remove a job from an in-memory queue.

    For running jobs, also signals cancellation so the execution thread stops.
    For todo jobs, the underlying TodoFifoQueue.delete_by_id_hash wakes the
    consumer via condition.notify so it recalculates eligibility.
    Emits a job_removed WebSocket event so other connected clients update.

    Requires:
        - queue_name is one of: 'todo', 'run', 'done', 'dead'
        - job_id identifies an existing job in the specified queue
        - current_user is authenticated
        - Job belongs to current user OR user is admin

    Ensures:
        - Job is removed from the specified queue
        - Running jobs receive cancel signal before removal
        - WebSocket event emitted for UI synchronization
        - Returns confirmation with job_id and queue name

    Raises:
        - HTTPException 400: Invalid queue name
        - HTTPException 404: Job not found in specified queue
        - HTTPException 403: User does not own this job and is not admin

    Args:
        queue_name: Target queue ('todo', 'run', 'done', 'dead')
        job_id: Target job ID
        current_user: Authenticated user info
        running_queue: Running queue dependency
        done_queue: Done queue dependency
        dead_queue: Dead queue dependency
        todo_queue: Todo queue dependency

    Returns:
        dict: {status, job_id, queue}
    """
    user_id = current_user[ "uid" ]

    # Validate queue name
    queue_map = {
        "todo" : todo_queue,
        "run"  : running_queue,
        "done" : done_queue,
        "dead" : dead_queue
    }
    if queue_name not in queue_map:
        raise HTTPException( status_code=400, detail=f"Invalid queue name for deletion: {queue_name}. Must be 'todo', 'run', 'done', or 'dead'." )

    queue = queue_map[ queue_name ]

    print( f"[API] DELETE /api/queue/{queue_name}/{job_id} - user: {user_id}" )

    # Validate job exists
    try:
        job = queue.get_by_id_hash( job_id )
    except KeyError:
        raise HTTPException( status_code=404, detail=f"Job not found in {queue_name} queue: {job_id}" )

    # Validate ownership (user or admin)
    if job.user_id != user_id and not is_admin( current_user ):
        raise HTTPException( status_code=403, detail="Not authorized to remove this job" )

    # For running jobs: signal cancellation before removal
    if queue_name == "run" and isinstance( job, AgenticJobBase ):
        job.request_cancel()
        print( f"[API] Cancel signaled for running job {job_id} before removal" )

    # Remove from queue
    deleted = queue.delete_by_id_hash( job_id )
    if not deleted:
        raise HTTPException( status_code=404, detail=f"Failed to delete job {job_id} from {queue_name} queue" )

    # Emit WebSocket event for UI synchronization (canonical dual-emit:
    # owner + watching admins, deduplicated). See
    # WebSocketManager.emit_to_user_and_admins_sync for the rationale.
    # NOTE: import path is `fastapi_app.main` not `src.fastapi_app.main` —
    # PYTHONPATH already includes src/, so the `src.` prefix raises
    # ModuleNotFoundError and silently swallowed every job_removed emit
    # before today (Session 248e740e fix).
    try:
        import fastapi_app.main as main_module
        ws_manager = main_module.websocket_manager
        if ws_manager:
            ws_manager.emit_to_user_and_admins_sync( user_id, 'job_removed', {
                'job_id'    : job_id,
                'queue'     : queue_name,
                'timestamp' : cu.get_current_datetime_iso()
            } )
    except Exception as e:
        print( f"[API] Warning: Failed to emit job_removed event: {e}" )

    print( f"[API] Job {job_id} removed from {queue_name} queue by user {user_id}" )

    return {
        "status" : "deleted",
        "job_id" : job_id,
        "queue"  : queue_name
    }


# ===========================================================================
# Job History (CJ Flow Persistence)
# ===========================================================================


@router.get(
    "/job-history",
    summary     = "Query job history",
    description = "Paginated history of agentic jobs from PostgreSQL persistence. "
                  "Admin sees all jobs; regular users see only their own."
)
async def get_job_history(
    current_user: dict      = Depends( get_current_user ),
    status: Optional[str]   = Query( None, description="Filter by status: pending, running, completed, failed, interrupted" ),
    job_type: Optional[str] = Query( None, description="Filter by job type: deep_research, podcast, claude_code, swe_team, research_to_podcast" ),
    limit: int              = Query( 20, ge=1, le=100, description="Results per page (max 100)" ),
    offset: int             = Query( 0, ge=0, description="Pagination offset" ),
    days: Optional[int]     = Query( None, ge=1, le=365, description="Time window in days (e.g. 7, 14, 30). None = all time." ),
    exclude_ids: Optional[str] = Query( None, description="Comma-separated job IDs to exclude (for live queue deduplication)" )
):
    """
    Query paginated job history with optional filters.

    Requires:
        - Authenticated user (Bearer token)

    Ensures:
        - Admin users see all jobs (user_id=None filter)
        - Regular users see only their own jobs
        - Results are paginated and sorted by created_at DESC
        - exclude_ids supports the overlay model: frontend passes live Done/Dead job IDs
          so they are excluded from history results (no duplicates)
        - Returns { jobs: [...], total: N, filtered_by: str, limit: N, offset: N }
    """
    from cosa.rest.job_persistence import query_job_history

    # Admin sees all, regular user sees own only
    user_id = None if is_admin( current_user ) else current_user[ "uid" ]

    # Parse comma-separated exclude_ids into a list
    exclude_list = [ eid.strip() for eid in exclude_ids.split( "," ) if eid.strip() ] if exclude_ids else None

    result = query_job_history(
        user_id     = user_id,
        status      = status,
        job_type    = job_type,
        limit       = limit,
        offset      = offset,
        days        = days,
        exclude_ids = exclude_list
    )

    return {
        "jobs"        : result[ "jobs" ],
        "total"       : result[ "total" ],
        "filtered_by" : user_id or "all",
        "limit"       : limit,
        "offset"      : offset
    }


@router.get(
    "/job-history/{job_id}",
    summary     = "Get job detail",
    description = "Retrieve a single job's full history record by ID hash."
)
async def get_job_history_detail(
    job_id: str,
    current_user: dict = Depends( get_current_user )
):
    """
    Get a single job's persistence record.

    Requires:
        - Authenticated user (Bearer token)
        - job_id is a valid id_hash string

    Ensures:
        - Returns full job dict if found and authorized
        - 404 if job not found
        - 403 if regular user accessing another user's job
    """
    from cosa.rest.job_persistence import get_job_by_id_hash

    job = get_job_by_id_hash( job_id )

    if job is None:
        raise HTTPException( status_code=404, detail=f"Job not found: {job_id}" )

    # Authorization: regular users can only see their own jobs
    if not is_admin( current_user ) and job.get( "user_id" ) != current_user[ "uid" ]:
        raise HTTPException( status_code=403, detail="Not authorized to view this job" )

    return job


@router.delete(
    "/job-history/{job_id}",
    summary     = "Delete job from history",
    description = "Hard delete a job history record. Admin or job owner only."
)
async def delete_job_history_endpoint(
    job_id: str,
    current_user: dict = Depends( get_current_user )
):
    """
    Delete a single job from PostgreSQL persistence.

    Requires:
        - Authenticated user (Bearer token)
        - job_id is a valid id_hash string
        - User must be admin or the job's owner

    Ensures:
        - Returns { status: "deleted", job_id: str } on success
        - 404 if job not found
        - 403 if regular user deleting another user's job
    """
    from cosa.rest.job_persistence import get_job_by_id_hash, delete_job_history

    job = get_job_by_id_hash( job_id )

    if job is None:
        raise HTTPException( status_code=404, detail=f"Job not found: {job_id}" )

    # Authorization: regular users can only delete their own jobs
    if not is_admin( current_user ) and job.get( "user_id" ) != current_user[ "uid" ]:
        raise HTTPException( status_code=403, detail="Not authorized to delete this job" )

    deleted = delete_job_history( job_id )

    if not deleted:
        raise HTTPException( status_code=500, detail="Failed to delete job from history" )

    return { "status": "deleted", "job_id": job_id }


@router.post(
    "/job-history/{job_id}/retry",
    summary     = "Retry a failed or interrupted job",
    description = "Re-submit a failed or interrupted job to the todo queue as a new job."
)
async def retry_job_history(
    job_id: str,
    request: Request,
    current_user: dict = Depends( get_current_user ),
    todo_queue         = Depends( get_todo_queue )
):
    """
    Re-submit a failed/interrupted job to the CJ Flow todo queue.

    Requires:
        - Authenticated user (Bearer token)
        - job_id is a valid id_hash of a failed or interrupted job
        - Request body contains JSON with "websocket_id" field
        - User must be admin or the job's owner

    Ensures:
        - Creates a new todo entry with the original question_text
        - Returns { status: "retried", original_job_id: str }
        - 404 if job not found
        - 403 if unauthorized
        - 400 if job status is not failed or interrupted
        - 400 if websocket_id missing from request body
    """
    import asyncio
    from cosa.rest.job_persistence import get_job_by_id_hash

    job = get_job_by_id_hash( job_id )

    if job is None:
        raise HTTPException( status_code=404, detail=f"Job not found: {job_id}" )

    # Authorization: regular users can only retry their own jobs
    if not is_admin( current_user ) and job.get( "user_id" ) != current_user[ "uid" ]:
        raise HTTPException( status_code=403, detail="Not authorized to retry this job" )

    # Only allow retry of terminal failure states
    if job.get( "status" ) not in ( "failed", "interrupted" ):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job with status '{job.get( 'status' )}'. Only failed or interrupted jobs can be retried."
        )

    # Parse request body for websocket_id
    try:
        request_data = await request.json()
    except Exception as e:
        raise HTTPException( status_code=400, detail=f"Invalid JSON in request body: {str( e )}" )

    websocket_id = request_data.get( "websocket_id" )
    if not websocket_id or not isinstance( websocket_id, str ):
        raise HTTPException( status_code=400, detail="Missing required field: websocket_id" )

    question     = job.get( "question_text", "" )
    user_id      = current_user[ "uid" ]
    user_email   = current_user[ "email" ]

    print( f"[API] /api/job-history/{job_id}/retry - re-submitting: '{question[:80]}', user: {user_id}" )

    # Push to todo queue using the same pattern as POST /api/push
    result = await asyncio.to_thread( todo_queue.push_job, question, websocket_id, user_id, user_email )

    return {
        "status"          : "retried",
        "original_job_id" : job_id,
        "result"          : result
    }


# =============================================================================
# CJ Flow: Job Pause/Resume (Todo Queue Only)
# =============================================================================


@router.patch(
    "/queue/todo/{job_id}/pause",
    summary     = "Pause a todo queue job",
    description = "Set paused=True on a todo queue job. Consumer skips it until resumed."
)
async def pause_job(
    job_id: str,
    current_user: dict = Depends( get_current_user ),
    todo_queue         = Depends( get_todo_queue ),
):
    """
    Pause a job in the todo queue.

    A paused job remains in the queue but is skipped by the consumer during
    eligibility checks. Resume the job to make it eligible again.

    Requires:
        - job_id identifies a job currently in the todo queue
        - current_user is authenticated
        - Job belongs to current user OR user is admin

    Ensures:
        - Job's paused flag is set to True
        - Returns confirmation

    Raises:
        - HTTPException 404: Job not found in todo queue
        - HTTPException 403: User does not own this job
    """
    user_id = current_user[ "uid" ]

    print( f"[API] PATCH /api/queue/todo/{job_id}/pause - user: {user_id}" )

    try:
        job = todo_queue.get_by_id_hash( job_id )
    except KeyError:
        raise HTTPException( status_code=404, detail=f"Job not found in todo queue: {job_id}" )

    if job.user_id != user_id and not is_admin( current_user ):
        raise HTTPException( status_code=403, detail="Not authorized to pause this job" )

    job.state = JobState.PAUSED

    # Emit WebSocket event for UI update (state transition: queued/scheduled → paused).
    # Canonical dual-emit so admin viewers also see the pause badge appear.
    try:
        import fastapi_app.main as main_module
        ws_manager = main_module.websocket_manager
        ws_manager.emit_to_user_and_admins_sync(
            user_id = user_id,
            event   = "job_state_transition",
            data    = {
                "job_id"     : job_id,
                "from_state" : JobState.QUEUED.value,
                "to_state"   : JobState.PAUSED.value,
                "timestamp"  : cu.get_current_datetime_iso(),
            },
        )
    except Exception as e:
        print( f"[API] Warning: WebSocket emission failed for pause transition: {e}" )

    print( f"[API] Job paused: {job_id} by user {user_id}" )

    return {
        "status"  : "paused",
        "job_id"  : job_id,
        "message" : "Job paused. Consumer will skip it until resumed."
    }


@router.patch(
    "/queue/todo/{job_id}/resume",
    summary     = "Resume a paused todo queue job",
    description = "Set paused=False and notify consumer to recalculate eligibility."
)
async def resume_job(
    job_id: str,
    current_user: dict = Depends( get_current_user ),
    todo_queue         = Depends( get_todo_queue ),
):
    """
    Resume a paused job in the todo queue.

    Clears the paused flag and notifies the consumer thread to recalculate
    eligibility. If the job's scheduled_at has already passed, it becomes
    immediately eligible.

    Requires:
        - job_id identifies a paused job in the todo queue
        - current_user is authenticated
        - Job belongs to current user OR user is admin

    Ensures:
        - Job's paused flag is set to False
        - Consumer thread is notified to recalculate
        - Returns confirmation

    Raises:
        - HTTPException 404: Job not found in todo queue
        - HTTPException 403: User does not own this job
    """
    user_id = current_user[ "uid" ]

    print( f"[API] PATCH /api/queue/todo/{job_id}/resume - user: {user_id}" )

    try:
        job = todo_queue.get_by_id_hash( job_id )
    except KeyError:
        raise HTTPException( status_code=404, detail=f"Job not found in todo queue: {job_id}" )

    if job.user_id != user_id and not is_admin( current_user ):
        raise HTTPException( status_code=403, detail="Not authorized to resume this job" )

    job.state = JobState.QUEUED

    # Emit WebSocket event for UI update (state transition: paused → queued).
    # Canonical dual-emit so admin viewers also see the pause badge clear.
    try:
        import fastapi_app.main as main_module
        ws_manager = main_module.websocket_manager
        ws_manager.emit_to_user_and_admins_sync(
            user_id = user_id,
            event   = "job_state_transition",
            data    = {
                "job_id"     : job_id,
                "from_state" : JobState.PAUSED.value,
                "to_state"   : JobState.QUEUED.value,
                "timestamp"  : cu.get_current_datetime_iso(),
            },
        )
    except Exception as e:
        print( f"[API] Warning: WebSocket emission failed for resume transition: {e}" )

    # Notify consumer to recalculate eligibility (may wake from timed sleep)
    with todo_queue.condition:
        todo_queue.condition.notify()

    print( f"[API] Job resumed: {job_id} by user {user_id}" )

    return {
        "status"  : "resumed",
        "job_id"  : job_id,
        "message" : "Job resumed. Consumer will process it when eligible."
    }