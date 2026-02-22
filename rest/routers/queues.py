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

# Import dependencies
from cosa.rest.auth import get_current_user
from cosa.rest.queue_auth import authorize_queue_filter
from cosa.rest.auth_middleware import is_admin
from cosa.agents.agentic_job_base import AgenticJobBase

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

@router.get("/get-queue/{queue_name}")
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
                "session_id"      : job.session_id,  # For job-notification correlation
                "agent_type"      : job.job_type,  # Unified property replaces getattr() chain
                "has_interactions": bool( job.session_id ),  # True if can query notifications
                "has_audio_cache" : False,  # Will be determined by frontend cache check
                "is_cache_hit"    : job.is_cache_hit,  # For Time Saved Dashboard
                # Phase 7: Agentic job artifacts for enhanced done cards
                "report_path"     : job.artifacts.get( 'report_path' ) if is_agentic_job else None,
                "abstract"        : job.artifacts.get( 'abstract' ) if is_agentic_job else None,
                "cost_summary"    : job.cost_summary if is_agentic_job else None,
                "started_at"      : job.started_at,
                "completed_at"    : job.completed_at,
                "status"          : job.status,
                "error"           : job.error,
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

    # Step 6: Handle todo/run queues with metadata (Phase 7)
    # Using unified interface properties - all job types now have consistent attributes
    structured_jobs = []
    for job in jobs:
        job_data = {
            "job_id"       : job.id_hash,
            "question_text": job.last_question_asked,
            "timestamp"    : job.run_date or job.created_date,
            "user_id"      : authorized_filter,
            "session_id"   : job.session_id,
            "agent_type"   : job.job_type,  # Unified property replaces getattr() chain
            "status"       : job.status,
            "started_at"   : job.started_at,
            "error"        : job.error,
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


@router.get( "/get-job-interactions/{job_id}" )
async def get_job_interactions(
    job_id: str,
    current_user: dict = Depends( get_current_user ),
    done_queue = Depends( get_done_queue )
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

    # Find job in done queue by compound ID
    job = None
    for snapshot in done_queue.get_all_jobs():
        if snapshot.id_hash == job_id:
            job = snapshot
            break

    if not job:
        print( f"[API] Job not found: {job_id}" )
        raise HTTPException( status_code=404, detail=f"Job not found: {job_id}" )

    # Authorization check — job.user_id is the single source of truth
    job_owner = job.user_id
    if job_owner and job_owner != current_user["uid"] and not is_admin( current_user ):
        print( f"[API] Unauthorized access to job {job_id} by {current_user['uid']}" )
        raise HTTPException( status_code=403, detail="Not authorized to view this job" )

    # Build response using unified interface properties
    # All job types (SolutionSnapshot, AgenticJobBase) now have consistent attributes
    response = {
        "job_id"       : job_id,
        "session_id"   : job.session_id,
        "job_metadata" : {
            "question"    : job.last_question_asked,
            "answer"      : job.answer_conversational or job.answer,
            "agent_type"  : job.job_type,  # Unified property replaces getattr() chain
            "run_date"    : job.run_date,
            "created_date": job.created_date
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
                for n in notifications
            ]
            response["interaction_count"] = len( notifications )

            print( f"[API] Found {len( notifications )} interactions for job {job_id}" )

    except Exception as e:
        print( f"[API] Error querying notifications: {e}" )
        # Return empty interactions rather than failing
        pass

    return response


@router.post( "/jobs/{job_id}/message" )
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
                    "timestamp"         : datetime.now().isoformat(),
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
                    recipient_id       = user.id,
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
                "timestamp"         : datetime.now().isoformat(),
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