"""
Deep Research to Podcast API router for queue-based chained workflows.

Submits research queries that automatically generate a podcast after
research completion. Combines Deep Research → Podcast Generation pipeline.

Endpoints:
    POST /api/deep-research-to-podcast/submit - Submit chained research→podcast job

Example:
    POST /api/deep-research-to-podcast/submit
    {
        "query": "State of AI safety in 2026",
        "budget": 3.00,
        "target_languages": ["en"],
        "max_segments": null
    }
"""

import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cosa.rest.auth import get_current_user
from cosa.agents.deep_research_to_podcast.job import DeepResearchToPodcastJob
import cosa.utils.util as cu


router = APIRouter(
    prefix="/api/deep-research-to-podcast",
    tags=[ "deep-research-to-podcast" ]
)


# ═══════════════════════════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════════════════════════

class ResearchToPodcastSubmitRequest( BaseModel ):
    """
    Request body for research→podcast submission.

    Mirrors DeepResearchSubmitRequest with additional podcast parameters.
    """
    query            : str = Field( ..., description="Research topic/question to investigate" )
    budget           : Optional[ float ]       = Field( None, description="Maximum budget in USD for Deep Research" )
    target_languages : Optional[ List[ str ] ] = Field( None, description="ISO language codes for audio generation" )
    max_segments     : Optional[ int ]         = Field( None, description="Limit TTS to first N segments" )


class ResearchToPodcastSubmitResponse( BaseModel ):
    """Response for successful job submission."""
    job_id         : str = Field( ..., description="Unique job identifier (rp-xxxxx format)" )
    queue_position : int = Field( ..., description="Position in the todo queue" )
    message        : str = Field( ..., description="Human-readable confirmation message" )


# ═══════════════════════════════════════════════════════════════════════════════
# Dependencies
# ═══════════════════════════════════════════════════════════════════════════════

def get_todo_queue():
    """
    Dependency to get todo queue from main module.

    Returns:
        RunningFifoQueue: The todo queue instance
    """
    import fastapi_app.main as main_module
    return main_module.jobs_todo_queue


# ═══════════════════════════════════════════════════════════════════════════════
# Job Submission Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/submit",
    response_model=ResearchToPodcastSubmitResponse,
    summary="Submit research→podcast chained job",
    description="Submit a deep research job that automatically generates a podcast upon completion."
)
async def submit_research_to_podcast(
    request: ResearchToPodcastSubmitRequest,
    current_user: dict = Depends( get_current_user ),
    todo_queue = Depends( get_todo_queue )
):
    """
    Submit a deep research→podcast chained job.

    Creates a DeepResearchToPodcastJob and pushes it to the todo queue.
    The job runs the full pipeline:
    1. Deep Research: Web search, synthesis, report generation
    2. Podcast Generation: Script creation, TTS, audio stitching

    Requires:
        - Authenticated user (current_user from token)
        - Valid research query (non-empty)
        - Valid user email for artifact storage

    Ensures:
        - Job created with rp- prefix
        - Job added to queue with user/session context
        - Returns job_id and queue_position

    Args:
        request: ResearchToPodcastSubmitRequest with query and options
        current_user: Authenticated user from JWT token
        todo_queue: Todo queue instance for job submission

    Returns:
        ResearchToPodcastSubmitResponse with job_id and queue_position

    Raises:
        HTTPException 400: If query is empty
        HTTPException 401: If not authenticated
    """
    user_email = current_user.get( "email" )
    user_id    = current_user.get( "user_id", user_email )
    session_id = current_user.get( "session_id", "unknown" )
    debug      = current_user.get( "debug", False )

    # Validate query
    query = request.query.strip()
    if not query:
        raise HTTPException( status_code=400, detail="Query cannot be empty" )

    if debug:
        print( f"[submit_research_to_podcast] Query: {query[ :60 ]}..." )
        print( f"[submit_research_to_podcast] Budget: ${request.budget}" if request.budget else "[submit_research_to_podcast] Budget: unlimited" )
        print( f"[submit_research_to_podcast] Target languages: {request.target_languages}" )

    # Create the chained job
    job = DeepResearchToPodcastJob(
        query            = query,
        user_id          = user_id,
        user_email       = user_email,
        session_id       = session_id,
        budget           = request.budget,
        target_languages = request.target_languages,
        max_segments     = request.max_segments,
        debug            = debug
    )

    # Add to queue
    todo_queue.push_job( job, user_id, session_id )

    # Get queue position
    position = todo_queue.get_position( job.id_hash )

    return ResearchToPodcastSubmitResponse(
        job_id         = job.id_hash,
        queue_position = position,
        message        = f"Research→Podcast job '{query[ :40 ]}...' added to queue at position {position}"
    )


def quick_smoke_test():
    """
    Quick smoke test for deep_research_to_podcast router.
    """
    cu.print_banner( "Deep Research to Podcast Router Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import
        print( "Testing module import..." )
        from cosa.rest.routers.deep_research_to_podcast import router
        print( "✓ Module imported successfully" )

        # Test 2: Router configuration
        print( "Testing router configuration..." )
        assert router.prefix == "/api/deep-research-to-podcast"
        assert "deep-research-to-podcast" in router.tags
        print( f"✓ Router prefix: {router.prefix}" )

        # Test 3: Request model
        print( "Testing request model..." )
        req = ResearchToPodcastSubmitRequest(
            query            = "test research topic",
            budget           = 3.00,
            target_languages = [ "en" ],
            max_segments     = 5
        )
        assert req.query == "test research topic"
        assert req.budget == 3.00
        assert req.target_languages == [ "en" ]
        assert req.max_segments == 5
        print( "✓ Request model works correctly" )

        # Test 4: Response model
        print( "Testing response model..." )
        resp = ResearchToPodcastSubmitResponse(
            job_id         = "rp-abc123",
            queue_position = 1,
            message        = "Job added to queue"
        )
        assert resp.job_id == "rp-abc123"
        assert resp.queue_position == 1
        print( "✓ Response model works correctly" )

        # Test 5: Route exists
        print( "Testing route registration..." )
        routes = [ r.path for r in router.routes ]
        assert any( "/submit" in route for route in routes )
        print( f"✓ Routes: {routes}" )

        print( "\n✓ Smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
