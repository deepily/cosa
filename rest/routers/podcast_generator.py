"""
Podcast Generator API router for queue-based podcast generation.

Provides smart input parsing that handles both direct file paths and
natural language descriptions with LLM-powered fuzzy matching.

Endpoints:
    POST /api/podcast-generator/submit - Submit podcast generation job

Example:
    # Direct path mode (immediate job creation)
    POST /api/podcast-generator/submit
    {"research_source": "/io/deep-research/user@email/2026.01.26-topic.md"}

    # Description mode (fuzzy matching with notification confirmation)
    POST /api/podcast-generator/submit
    {"research_source": "my Claude Code research"}
"""

import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cosa.rest.auth import get_current_user
from cosa.agents.podcast_generator.job import PodcastGeneratorJob
import cosa.utils.util as cu


router = APIRouter(
    prefix="/api/podcast-generator",
    tags=[ "podcast-generator" ]
)


class PodcastSubmitRequest( BaseModel ):
    """
    Request body for podcast generation submission.

    The research_source field is overloaded:
    - If it looks like a path → direct mode (immediate job creation)
    - If it looks like text → description mode (fuzzy match + confirmation)
    """
    research_source   : str
    target_languages  : Optional[ List[ str ] ] = None
    max_segments      : Optional[ int ]         = None


class PodcastSubmitResponse( BaseModel ):
    """Response for successful job submission."""
    job_id         : str
    queue_position : int
    status         : str = "queued"


class PodcastMatchingResponse( BaseModel ):
    """Response when fuzzy matching is triggered."""
    status  : str
    message : str


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
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════════

def is_research_path( input_text: str, user_email: str ) -> bool:
    """
    Detect if input is a research path (direct mode) or description (fuzzy match mode).

    Path patterns detected:
    - /io/deep-research/{user_email}/filename.md
    - io/deep-research/{user_email}/filename.md
    - Contains user_email AND ends with .md

    Requires:
        - input_text is a non-empty string
        - user_email is a valid email address

    Ensures:
        - Returns True if input looks like a file path
        - Returns False if input looks like a natural language description

    Args:
        input_text: The user's input (path or description)
        user_email: The authenticated user's email

    Returns:
        bool: True if input is a path, False if description
    """
    from cosa.config.configuration_manager import ConfigurationManager

    config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
    research_root = config_mgr.get( "deep research output directory", default="/io/deep-research" )
    expected_prefix = f"{research_root}/{user_email}/"

    input_clean = input_text.strip()

    # Check for path patterns
    return (
        input_clean.startswith( expected_prefix ) or
        input_clean.startswith( expected_prefix.lstrip( "/" ) ) or
        ( user_email in input_clean and input_clean.endswith( ".md" ) )
    )


async def match_research_docs( user_email: str, description: str, debug: bool = False ) -> List[ str ]:
    """
    List user's research docs and fuzzy match against description using LLM.

    Requires:
        - user_email is a valid email address
        - description is a non-empty string

    Ensures:
        - Returns list of 0-5 matching filenames, ordered by relevance
        - Returns empty list if no research documents found

    Args:
        user_email: The user's email (determines research directory)
        description: Natural language description of desired research
        debug: Enable debug output

    Returns:
        List[ str ]: Matching document filenames
    """
    from cosa.memory.gister import Gister

    # Get research directory
    research_dir = f"{cu.get_project_root()}/io/deep-research/{user_email}"

    if not os.path.exists( research_dir ):
        if debug:
            print( f"[match_research_docs] Research directory not found: {research_dir}" )
        return []

    # List markdown files
    docs = [ f for f in os.listdir( research_dir ) if f.endswith( '.md' ) ]

    if not docs:
        if debug:
            print( f"[match_research_docs] No markdown files found in {research_dir}" )
        return []

    if debug:
        print( f"[match_research_docs] Found {len( docs )} research documents" )
        print( f"[match_research_docs] Description: {description}" )

    # Use Gister for LLM fuzzy matching
    gister = Gister( debug=debug )

    prompt = f"""Given this user description: "{description}"

Match against these research document filenames:
{chr( 10 ).join( f'- {doc}' for doc in docs )}

Return ONLY a JSON array of the top 3-5 best matching filenames, ordered by relevance.
Only include filenames that reasonably match the description.
If no good matches exist, return an empty array: []

Example response: ["2026.01.15-claude-code-analysis.md", "2026.01.10-ai-tools-comparison.md"]"""

    try:
        response = gister.get_gist( prompt, prompt_key="fuzzy_match_research" )

        # Parse JSON response
        import json
        if isinstance( response, str ):
            # Clean up response - extract JSON array if wrapped in other text
            response = response.strip()
            if response.startswith( "[" ):
                matches = json.loads( response )
            else:
                # Try to extract JSON array from response
                import re
                match = re.search( r'\[.*\]', response, re.DOTALL )
                if match:
                    matches = json.loads( match.group() )
                else:
                    matches = []
        else:
            matches = response if isinstance( response, list ) else []

        # Validate matches exist in docs
        valid_matches = [ m for m in matches if m in docs ]

        if debug:
            print( f"[match_research_docs] Matches: {valid_matches}" )

        return valid_matches

    except Exception as e:
        if debug:
            print( f"[match_research_docs] Error during fuzzy matching: {e}" )
        return []


async def send_document_selection_notification(
    user_email: str,
    session_id: str,
    matches: List[ str ],
    debug: bool = False
) -> None:
    """
    Send a multiple choice notification for document selection.

    Requires:
        - user_email is a valid email
        - session_id is a valid WebSocket session
        - matches is a non-empty list of filenames

    Ensures:
        - Notification sent to user via cosa-voice
        - User can select from matches or cancel

    Args:
        user_email: The user's email for notification routing
        session_id: WebSocket session ID
        matches: List of matching document filenames
        debug: Enable debug output
    """
    from cosa.agents.deep_research import voice_io

    options = [
        { "label": m[ :35 ] + "..." if len( m ) > 35 else m, "description": m }
        for m in matches
    ]
    options.append( { "label": "Cancel", "description": "Don't create podcast" } )

    if debug:
        print( f"[send_document_selection_notification] Sending notification with {len( options )} options" )

    await voice_io.ask_multiple_choice(
        questions=[ {
            "question"    : "Which research document should I use for the podcast?",
            "header"      : "Research",
            "multiSelect" : False,
            "options"     : options
        } ],
        title="Select Research Document",
        priority="high"
    )


@router.post(
    "/submit",
    response_model=PodcastSubmitResponse | PodcastMatchingResponse,
    summary="Submit podcast generation job",
    description="Submit a podcast generation job. Accepts either a direct file path or a natural language description."
)
async def submit_podcast_job(
    request: PodcastSubmitRequest,
    current_user: dict = Depends( get_current_user ),
    todo_queue = Depends( get_todo_queue )
):
    """
    Submit a podcast generation job with smart input parsing.

    Flow A (Direct Path):
        - Input looks like a file path
        - Validate path exists
        - Create job immediately
        - Return job_id and queue_position

    Flow B (Description):
        - Input looks like natural language
        - Fuzzy match against user's research documents
        - Send multiple choice notification for selection
        - Return status="matching" with instructions

    Requires:
        - Valid authentication token
        - research_source is non-empty

    Ensures:
        - Returns PodcastSubmitResponse if direct path mode
        - Returns PodcastMatchingResponse if description mode
        - Raises 404 if path not found (direct mode)
        - Raises 404 if no research documents match (description mode)
    """
    user_email = current_user.get( "email" )
    user_id    = current_user.get( "user_id", user_email )
    session_id = current_user.get( "session_id", "unknown" )
    debug      = current_user.get( "debug", False )

    research_source = request.research_source.strip()

    if not research_source:
        raise HTTPException( status_code=400, detail="research_source cannot be empty" )

    # Smart input detection
    if is_research_path( research_source, user_email ):
        # Flow A: Direct path mode
        if debug:
            print( f"[submit_podcast_job] Direct path mode: {research_source}" )

        # Normalize path
        if research_source.startswith( "/" ):
            full_path = cu.get_project_root() + research_source
        else:
            full_path = cu.get_project_root() + "/" + research_source

        # Validate path exists
        if not os.path.exists( full_path ):
            raise HTTPException(
                status_code=404,
                detail=f"Research file not found: {research_source}"
            )

        # Create job
        job = PodcastGeneratorJob(
            research_path    = full_path,
            user_id          = user_id,
            user_email       = user_email,
            session_id       = session_id,
            target_languages = request.target_languages,
            max_segments     = request.max_segments,
            debug            = debug
        )

        # Add to queue
        todo_queue.push_job( job, user_id, session_id )

        return PodcastSubmitResponse(
            job_id         = job.id_hash,
            queue_position = todo_queue.get_position( job.id_hash ),
            status         = "queued"
        )

    else:
        # Flow B: Description mode (fuzzy matching)
        if debug:
            print( f"[submit_podcast_job] Description mode: {research_source}" )

        # Find matching documents
        matches = await match_research_docs( user_email, research_source, debug=debug )

        if not matches:
            raise HTTPException(
                status_code=404,
                detail="No matching research documents found. Please check your research library or provide a direct file path."
            )

        # Send notification for user to select
        await send_document_selection_notification(
            user_email = user_email,
            session_id = session_id,
            matches    = matches,
            debug      = debug
        )

        return PodcastMatchingResponse(
            status  = "matching",
            message = f"Found {len( matches )} matching documents. Check notifications to select one."
        )


def quick_smoke_test():
    """
    Quick smoke test for podcast_generator router.
    """
    cu.print_banner( "Podcast Generator Router Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import
        print( "Testing module import..." )
        from cosa.rest.routers.podcast_generator import router, is_research_path
        print( "✓ Module imported successfully" )

        # Test 2: Router configuration
        print( "Testing router configuration..." )
        assert router.prefix == "/api/podcast-generator"
        assert "podcast-generator" in router.tags
        print( f"✓ Router prefix: {router.prefix}" )

        # Test 3: is_research_path function - path detection
        print( "Testing is_research_path() with paths..." )
        test_email = "test@example.com"

        # Should detect as path
        assert is_research_path( "/io/deep-research/test@example.com/report.md", test_email ) == True
        assert is_research_path( "io/deep-research/test@example.com/report.md", test_email ) == True
        print( "✓ Path patterns detected correctly" )

        # Test 4: is_research_path function - description detection
        print( "Testing is_research_path() with descriptions..." )

        # Should detect as description
        assert is_research_path( "my latest Claude Code research", test_email ) == False
        assert is_research_path( "research about AI safety", test_email ) == False
        print( "✓ Description patterns detected correctly" )

        # Test 5: Request/Response models
        print( "Testing request/response models..." )
        req = PodcastSubmitRequest(
            research_source  = "test description",
            target_languages = [ "en" ],
            max_segments     = 5
        )
        assert req.research_source == "test description"
        assert req.target_languages == [ "en" ]
        assert req.max_segments == 5
        print( "✓ Request model works correctly" )

        resp = PodcastSubmitResponse(
            job_id         = "pg-abc123",
            queue_position = 1,
            status         = "queued"
        )
        assert resp.job_id == "pg-abc123"
        print( "✓ Response model works correctly" )

        print( "\n✓ Smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
