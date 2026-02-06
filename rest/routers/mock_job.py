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
    # Expeditor test mode
    voice_command: Optional[ str ] = Field( None, description="Test expeditor: provide a voice command to route through RuntimeArgumentExpeditor" )


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

    # Expeditor test mode: route voice_command through expeditor pipeline
    if request_body.voice_command:
        return await _handle_expeditor_test(
            voice_command = request_body.voice_command,
            current_user  = current_user,
            todo_queue    = todo_queue
        )

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


async def _handle_expeditor_test( voice_command, current_user, todo_queue ):
    """
    Test the RuntimeArgumentExpeditor pipeline with a voice command.

    Routes the command through expeditor gap analysis and creates a dry-run job.
    Returns the disambiguation results for debugging without inference costs.

    Requires:
        - voice_command is a non-empty string
        - current_user has uid and email

    Ensures:
        - Returns MockJobSubmitResponse with expeditor results in config
        - Creates job with dry_run=True

    Args:
        voice_command: Voice command to test (e.g., "make me a podcast")
        current_user: Authenticated user from token
        todo_queue: Todo queue instance

    Returns:
        MockJobSubmitResponse with expeditor results
    """
    from cosa.agents.runtime_argument_expeditor.agent_registry import AGENTIC_AGENTS
    from cosa.agents.runtime_argument_expeditor.expeditor import RuntimeArgumentExpeditor
    from cosa.rest.agentic_job_factory import create_agentic_job
    from cosa.config.configuration_manager import ConfigurationManager

    user_id    = current_user.get( "uid" )
    user_email = current_user.get( "email" )
    session_id = f"expeditor-test-{user_id[ :8 ]}" if user_id else "expeditor-test"

    # Simple keyword matching to find the command
    matched_command = None
    for cmd_key in AGENTIC_AGENTS.keys():
        # Extract keywords from command (e.g., "deep research", "podcast", "research to podcast")
        keywords = cmd_key.replace( "agent router go to ", "" ).split()
        if all( kw in voice_command.lower() for kw in keywords ):
            matched_command = cmd_key
            break

    if not matched_command:
        # Try partial matching
        if "podcast" in voice_command.lower() and "research" in voice_command.lower():
            matched_command = "agent router go to research to podcast"
        elif "podcast" in voice_command.lower():
            matched_command = "agent router go to podcast generator"
        elif "research" in voice_command.lower():
            matched_command = "agent router go to deep research"

    if not matched_command:
        raise HTTPException(
            status_code=400,
            detail=f"Could not match voice command to any agentic agent. Available: {list( AGENTIC_AGENTS.keys() )}"
        )

    # Run through expeditor
    config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
    expeditor = RuntimeArgumentExpeditor(
        config_mgr = config_mgr,
        debug      = True,
        verbose    = False
    )

    args_dict = expeditor.expedite(
        command           = matched_command,
        raw_args          = "",
        user_email        = user_email or "test@test.com",
        session_id        = session_id,
        user_id           = user_id or "test-user",
        original_question = voice_command
    )

    if args_dict is None:
        return MockJobSubmitResponse(
            status         = "cancelled",
            job_id         = "expeditor-test-cancelled",
            queue_position = 0,
            config         = {
                "command"       : matched_command,
                "voice_command" : voice_command,
                "result"        : "cancelled_or_timeout",
                "args_found"    : None
            },
            message        = "Expeditor test: user cancelled or timed out"
        )

    # Create dry-run job
    args_dict[ "dry_run" ] = True
    job = create_agentic_job(
        command    = matched_command,
        args_dict  = args_dict,
        user_id    = user_id or "test-user",
        user_email = user_email or "test@test.com",
        session_id = session_id,
        debug      = True
    )

    job_id = job.id_hash if job else "factory-failed"

    # Associate and push if job was created
    if job:
        user_job_tracker.associate_job_with_user( job.id_hash, user_id or "test-user" )
        user_job_tracker.associate_job_with_session( job.id_hash, session_id )
        todo_queue.push( job )

    return MockJobSubmitResponse(
        status         = "queued" if job else "error",
        job_id         = job_id,
        queue_position = todo_queue.size() if job else 0,
        config         = {
            "command"       : matched_command,
            "voice_command" : voice_command,
            "args_resolved" : { k: str( v ) for k, v in args_dict.items() if k not in ( "user_email", "session_id", "user_id", "no_confirm" ) },
            "dry_run"       : True
        },
        message        = f"Expeditor test: {matched_command} (dry_run=True)"
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
