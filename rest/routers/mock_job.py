"""
Mock job endpoints for testing queue UI without inference costs.

Provides endpoints for:
- Submitting mock jobs with configurable behavior
- Testing queue system (todo → run → done/dead flow)
- Zero-cost UI development and stress testing

Generated on: 2026-01-20
"""

from typing import Optional, Tuple
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from cosa.rest.auth import get_current_user
from cosa.rest.queue_extensions import user_job_tracker

router = APIRouter( prefix="/api/mock-job", tags=[ "testing" ] )


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════════

class MockJobSubmitRequest( BaseModel ):
    """Request body for submitting a mock job."""
    # Randomization ranges
    iterations_min: int = Field( 3, ge=1, le=20, description="Minimum iterations" )
    iterations_max: int = Field( 8, ge=1, le=20, description="Maximum iterations" )
    sleep_min: float = Field( 1.0, ge=0.1, le=30.0, description="Minimum sleep seconds" )
    sleep_max: float = Field( 5.0, ge=0.1, le=30.0, description="Maximum sleep seconds" )
    failure_probability: float = Field( 0.0, ge=0.0, le=1.0, description="Probability of failure (0-1)" )
    # Fixed overrides (optional)
    fixed_iterations: Optional[ int ] = Field( None, ge=1, le=20, description="Override random iterations" )
    fixed_sleep: Optional[ float ] = Field( None, ge=0.1, le=30.0, description="Override random sleep" )
    # Optional metadata
    description: Optional[ str ] = Field( None, max_length=100, description="Custom description for queue display" )
    websocket_id: Optional[ str ] = Field( None, description="WebSocket session ID for notifications" )


class MockJobSubmitResponse( BaseModel ):
    """Response body for mock job submission."""
    status: str = Field( ..., description="Job status (queued)" )
    job_id: str = Field( ..., description="Unique job identifier (mock-{uuid8})" )
    queue_position: int = Field( ..., description="Position in the todo queue" )
    config: dict = Field( ..., description="Resolved job configuration" )
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


# ═══════════════════════════════════════════════════════════════════════════════
# Job Submission Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

@router.post( "/submit", response_model=MockJobSubmitResponse )
async def submit_mock_job(
    request_body: MockJobSubmitRequest = MockJobSubmitRequest(),
    current_user: dict = Depends( get_current_user ),
    todo_queue = Depends( get_todo_queue )
):
    """
    Submit a mock job for testing queue UI.

    Creates a MockAgenticJob and pushes it to the todo queue for
    asynchronous execution. The job just sleeps and emits notifications,
    incurring zero inference costs.

    Use cases:
    - Testing queue visualization without waiting for real jobs
    - Testing failure paths (dead queue) with failure_probability
    - Testing notification routing to job cards
    - Stress testing queue system with multiple concurrent jobs

    Requires:
        - Authenticated user (current_user from token)

    Ensures:
        - MockAgenticJob created with unique ID
        - Job pushed to todo queue
        - Returns job_id and configuration for tracking

    Args:
        request_body: Mock job parameters (all optional with defaults)
        current_user: Authenticated user from token
        todo_queue: Todo queue instance

    Returns:
        MockJobSubmitResponse: Job submission confirmation

    Raises:
        HTTPException 400: Invalid request parameters
        HTTPException 500: Queue push failed
    """
    from cosa.agents.test_harness.mock_job import MockAgenticJob

    # Validate ranges
    if request_body.iterations_min > request_body.iterations_max:
        raise HTTPException(
            status_code=400,
            detail="iterations_min cannot be greater than iterations_max"
        )
    if request_body.sleep_min > request_body.sleep_max:
        raise HTTPException(
            status_code=400,
            detail="sleep_min cannot be greater than sleep_max"
        )

    # Get user info from token
    user_id = current_user.get( "uid" )
    user_email = current_user.get( "email" )

    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="User ID not found in authentication token"
        )

    # Use provided websocket_id or fall back to a default
    session_id = request_body.websocket_id or f"api-{user_id[ :8 ]}"

    try:
        # Create the MockAgenticJob
        job = MockAgenticJob(
            user_id             = user_id,
            user_email          = user_email or "mock@test.com",
            session_id          = session_id,
            iterations_range    = ( request_body.iterations_min, request_body.iterations_max ),
            sleep_range         = ( request_body.sleep_min, request_body.sleep_max ),
            failure_probability = request_body.failure_probability,
            fixed_iterations    = request_body.fixed_iterations,
            fixed_sleep         = request_body.fixed_sleep,
            description         = request_body.description,
            debug               = False,
            verbose             = False
        )

        # Session 108: Associate BEFORE push to prevent race condition
        # The consumer thread may grab the job immediately after push(), so user mapping must exist first
        user_job_tracker.associate_job_with_user( job.id_hash, user_id )
        user_job_tracker.associate_job_with_session( job.id_hash, session_id )

        # Push to todo queue
        todo_queue.push( job )

        # Get queue position (approximate - queue length after push)
        queue_position = todo_queue.size()

        # Build config summary for response
        estimated_duration = job.iterations * job.sleep_seconds
        config = {
            "iterations"          : job.iterations,
            "sleep_seconds"       : round( job.sleep_seconds, 2 ),
            "will_fail"           : job.will_fail,
            "fail_at_iteration"   : job.fail_at_iteration if job.will_fail else None,
            "estimated_duration"  : f"{estimated_duration:.1f}s"
        }

        return MockJobSubmitResponse(
            status         = "queued",
            job_id         = job.id_hash,
            queue_position = queue_position,
            config         = config,
            message        = f"Mock job queued: {job.last_question_asked}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit mock job: {str( e )}"
        )


@router.get( "/health" )
async def mock_job_health():
    """
    Health check for mock job endpoint.

    Returns availability status.
    """
    return {
        "status"    : "ok",
        "available" : True,
        "description": "Mock job endpoint for testing queue UI without inference costs"
    }
