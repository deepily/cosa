"""
Claude Code Queue Submission Router.

Provides endpoint for submitting Claude Code tasks to CJ Flow (COSA Job Flow)
for background execution. Unlike the direct /api/claude-code/dispatch endpoint,
queued tasks run asynchronously through the queue system with full job tracking.

Endpoints:
    POST /api/claude-code/queue/submit - Submit task to CJF queue

Generated on: 2026-01-27
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from cosa.rest.auth import get_current_user
from cosa.rest.agentic_job_factory import create_agentic_job

router = APIRouter( tags=[ "claude-code-queue" ] )


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════════

class ClaudeCodeQueueRequest( BaseModel ):
    """Request body for submitting a Claude Code task to the queue."""
    prompt: str = Field( ..., min_length=1, description="The task prompt for Claude Code" )
    project: str = Field( "lupin", description="Target project name (e.g., lupin, cosa)" )
    task_type: str = Field( "BOUNDED", description="Task type: BOUNDED or INTERACTIVE" )
    max_turns: int = Field( 50, ge=1, le=500, description="Maximum agentic turns" )
    websocket_id: Optional[ str ] = Field( None, description="WebSocket session ID for notifications" )
    dry_run: bool = Field( False, description="If True, simulate execution without running Claude Code" )


class ClaudeCodeQueueResponse( BaseModel ):
    """Response body for Claude Code queue submission."""
    status: str = Field( ..., description="Job status (queued)" )
    job_id: str = Field( ..., description="Unique job identifier (cc-{uuid8})" )
    queue_position: int = Field( ..., description="Position in the todo queue" )
    message: str = Field( ..., description="Human-readable confirmation message" )


# ═══════════════════════════════════════════════════════════════════════════════
# Dependencies
# ═══════════════════════════════════════════════════════════════════════════════

def get_todo_queue():
    """
    Dependency to get todo queue from main module.

    Returns:
        TodoFifoQueue: The todo queue instance
    """
    import fastapi_app.main as main_module
    return main_module.jobs_todo_queue


def get_user_job_tracker():
    """
    Dependency to get user job tracker from main module.

    Returns:
        UserJobTracker: The user job tracker instance
    """
    from cosa.rest.queue_extensions import user_job_tracker
    return user_job_tracker


# ═══════════════════════════════════════════════════════════════════════════════
# Queue Submission Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

@router.post( "/api/claude-code/queue/submit", response_model=ClaudeCodeQueueResponse )
async def submit_claude_code_to_queue(
    request_body: ClaudeCodeQueueRequest,
    current_user: dict = Depends( get_current_user ),
    todo_queue = Depends( get_todo_queue ),
    user_job_tracker = Depends( get_user_job_tracker )
):
    """
    Submit a Claude Code task to CJ Flow queue for background execution.

    Unlike /api/claude-code/dispatch (direct execution with WebSocket streaming),
    this endpoint queues the task for background processing through the CJF system.
    The job will:
    - Appear in the CJF Todo queue
    - Transition to Running queue when executed
    - Move to Done/Dead queue on completion/failure
    - Send notifications via cosa-voice with job_id for job card routing

    Requires:
        - Authenticated user (current_user from token)
        - Valid task prompt
        - Valid task type (BOUNDED or INTERACTIVE)

    Ensures:
        - ClaudeCodeJob created with unique cc-{uuid8} ID
        - Job pushed to todo queue
        - Job associated with user for filtering
        - Returns job_id for tracking

    Args:
        request_body: Task parameters (prompt, project, task_type, etc.)
        current_user: Authenticated user from token
        todo_queue: Todo queue instance
        user_job_tracker: User-job association tracker

    Returns:
        ClaudeCodeQueueResponse: Job submission confirmation with job_id

    Raises:
        HTTPException 400: Invalid request parameters
        HTTPException 500: Queue push failed
    """
    # Get user ID and email from token (canonical source - don't trust client)
    user_id    = current_user.get( "uid" )
    user_email = current_user.get( "email" )

    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="User ID not found in authentication token"
        )

    if not user_email:
        raise HTTPException(
            status_code=400,
            detail="User email not found in authentication token"
        )

    # Validate task_type
    task_type = request_body.task_type.upper()
    if task_type not in [ "BOUNDED", "INTERACTIVE" ]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_type: {task_type}. Must be BOUNDED or INTERACTIVE"
        )

    # Use provided websocket_id or fall back to a default
    session_id = request_body.websocket_id or f"api-{user_id[ :8 ]}"

    try:
        # Create the ClaudeCodeJob via shared factory (same as voice path)
        job = create_agentic_job(
            command    = "agent router go to claude code",
            args_dict  = {
                "prompt"    : request_body.prompt,
                "project"   : request_body.project,
                "task_type" : task_type,
                "max_turns" : request_body.max_turns,
                "dry_run"   : request_body.dry_run
            },
            user_id    = user_id,
            user_email = user_email,
            session_id = session_id
        )

        # Session 108: Associate BEFORE push to prevent race condition
        # The consumer thread may grab the job immediately after push(), so user mapping must exist first
        user_job_tracker.associate_job_with_user( job.id_hash, user_id )
        user_job_tracker.associate_job_with_session( job.id_hash, session_id )

        # Push to todo queue
        # The todo queue's push method handles WebSocket notifications
        todo_queue.push( job )

        # Get queue position (approximate - queue length after push)
        queue_position = todo_queue.size()

        return ClaudeCodeQueueResponse(
            status         = "queued",
            job_id         = job.id_hash,
            queue_position = queue_position,
            message        = f"Claude Code job queued: {job.last_question_asked}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit Claude Code job: {str( e )}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Smoke Test
# ═══════════════════════════════════════════════════════════════════════════════

def quick_smoke_test():
    """
    Quick smoke test for Claude Code Queue Router - validates basic functionality.
    """
    import cosa.utils.util as cu

    cu.print_banner( "Claude Code Queue Router Smoke Test", prepend_nl=True )

    try:
        # Test 1: Router exists
        print( "Testing router configuration..." )
        assert router is not None
        assert "claude-code-queue" in router.tags
        print( "✓ Router configured correctly" )

        # Test 2: Models work
        print( "Testing Pydantic models..." )
        req = ClaudeCodeQueueRequest(
            prompt    = "Run the tests",
            project   = "lupin",
            task_type = "BOUNDED",
            max_turns = 50
        )
        assert req.prompt == "Run the tests"
        assert req.project == "lupin"
        assert req.task_type == "BOUNDED"
        print( "✓ ClaudeCodeQueueRequest model works" )

        resp = ClaudeCodeQueueResponse(
            status         = "queued",
            job_id         = "cc-a1b2c3d4",
            queue_position = 1,
            message        = "Job queued"
        )
        assert resp.job_id == "cc-a1b2c3d4"
        assert resp.status == "queued"
        print( "✓ ClaudeCodeQueueResponse model works" )

        # Test 3: Test INTERACTIVE task type
        print( "Testing INTERACTIVE task type..." )
        req_interactive = ClaudeCodeQueueRequest(
            prompt    = "Let's refactor the auth",
            project   = "cosa",
            task_type = "INTERACTIVE",
            max_turns = 200
        )
        assert req_interactive.task_type == "INTERACTIVE"
        print( "✓ INTERACTIVE task type works" )

        # Test 4: Test default values
        print( "Testing default values..." )
        req_defaults = ClaudeCodeQueueRequest( prompt="Test prompt" )
        assert req_defaults.project == "lupin"
        assert req_defaults.task_type == "BOUNDED"
        assert req_defaults.max_turns == 50
        assert req_defaults.dry_run == False
        print( "✓ Default values work correctly" )

        # Test 5: Test dry_run flag
        print( "Testing dry_run flag..." )
        req_dry_run = ClaudeCodeQueueRequest(
            prompt  = "Test prompt",
            dry_run = True
        )
        assert req_dry_run.dry_run == True
        print( "✓ dry_run flag works correctly" )

        print( "\n✓ Smoke test completed successfully" )
        return True

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    quick_smoke_test()
