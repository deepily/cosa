"""
Podcast Generator API router for CJ Flow queue-based podcast generation.

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
from cosa.rest.queue_extensions import user_job_tracker
from cosa.rest.agentic_job_factory import create_agentic_job
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
    dry_run           : bool                    = False
    audience          : Optional[ str ]         = None
    audience_context  : Optional[ str ]         = None


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
    research_root = config_mgr.get( "deep research output path" )
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
    Match user description against research docs using LLM (kaitchup/phi_4_14b).

    Uses the CoSA XML I/O pattern with PromptTemplateProcessor.
    Response is parsed via FuzzyFileMatchResponse.from_xml() - proper Pydantic XML I/O.

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
    from cosa.agents.llm_client_factory import LlmClientFactory
    from cosa.config.configuration_manager import ConfigurationManager
    from cosa.agents.io_models.utils.prompt_template_processor import PromptTemplateProcessor
    from cosa.agents.io_models.xml_models import FuzzyFileMatchResponse

    # Get research directory
    research_dir = f"{cu.get_project_root()}/io/deep-research/{user_email}"

    if not os.path.exists( research_dir ):
        if debug: print( f"[match_research_docs] Research directory not found: {research_dir}" )
        return []

    # List markdown files
    docs = [ f for f in os.listdir( research_dir ) if f.endswith( '.md' ) ]

    if not docs:
        if debug: print( f"[match_research_docs] No markdown files found in {research_dir}" )
        return []

    if debug:
        print( f"[match_research_docs] Found {len( docs )} research documents" )
        print( f"[match_research_docs] Description: {description}" )

    # Load config and prompt template
    config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
    template_path = config_mgr.get( "prompt template for fuzzy file matching" )
    template = cu.get_file_as_string( cu.get_project_root() + template_path )

    # Process template to inject XML example
    processor = PromptTemplateProcessor( debug=debug )
    template = processor.process_template( template, 'fuzzy file matching' )

    # Format with description and file list
    file_list = "\n".join( f"- {doc}" for doc in docs )
    prompt = template.format( description=description, file_list=file_list )

    # Call LLM
    llm_factory = LlmClientFactory()
    llm_spec_key = config_mgr.get( "llm spec key for fuzzy file matching" )
    llm_client = llm_factory.get_client( llm_spec_key, debug=debug, verbose=False )

    try:
        response = llm_client.run( prompt )

        if debug: print( f"[match_research_docs] LLM response: {response[ :200 ]}..." )

        # Parse XML response using proper Pydantic XML I/O (NOT deprecated util_xml)
        parsed_response = FuzzyFileMatchResponse.from_xml( response )
        matches = parsed_response.get_matches_list()

        # Validate matches exist in docs
        valid_matches = [ m for m in matches if m in docs ]

        if debug: print( f"[match_research_docs] Matches: {valid_matches}" )

        return valid_matches

    except Exception as e:
        if debug: print( f"[match_research_docs] Error during fuzzy matching: {e}" )
        return []


async def get_user_document_selection(
    user_email: str,
    session_id: str,
    matches: List[ str ],
    debug: bool = False
) -> Optional[ str ]:
    """
    Present document options to user and wait for selection (BLOCKING).

    Uses voice_io.present_choices() which blocks until user responds.

    Requires:
        - user_email is a valid email
        - session_id is a valid WebSocket session
        - matches is a non-empty list of filenames

    Ensures:
        - Returns selected filename string
        - Returns None if user cancels or times out

    Args:
        user_email: The user's email for notification routing
        session_id: WebSocket session ID
        matches: List of matching document filenames
        debug: Enable debug output

    Returns:
        str: Selected filename, or None if cancelled
    """
    from cosa.agents.deep_research import voice_io

    options = [
        { "label": m[ :35 ] + "..." if len( m ) > 35 else m, "description": m }
        for m in matches
    ]
    options.append( { "label": "Cancel", "description": "Don't create podcast" } )

    if debug:
        print( f"[get_user_document_selection] Presenting {len( options )} options" )

    # Use present_choices() which BLOCKS until user responds
    questions = [ {
        "question"    : "Which research document should I use for the podcast?",
        "header"      : "Research",
        "multiSelect" : False,
        "options"     : options
    } ]

    result = await voice_io.present_choices(
        questions = questions,
        timeout   = 120,
        title     = "Select Research Document"
    )

    selection = result.get( "answers", {} ).get( "Research" )

    if debug:
        print( f"[get_user_document_selection] User selected: {selection}" )

    # User cancelled
    if selection == "Cancel" or not selection:
        return None

    # Find full filename from truncated label
    for m in matches:
        label = m[ :35 ] + "..." if len( m ) > 35 else m
        if label == selection or m == selection:
            return m

    return None


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

        # Create job using shared factory
        args_dict = { "research": full_path }
        if request.target_languages:
            args_dict[ "languages" ] = ",".join( request.target_languages )
        if request.dry_run:
            args_dict[ "dry_run" ] = True
        if request.audience:
            args_dict[ "audience" ] = request.audience
        if request.audience_context:
            args_dict[ "audience_context" ] = request.audience_context

        job = create_agentic_job(
            command    = "agent router go to podcast generator",
            args_dict  = args_dict,
            user_id    = user_id,
            user_email = user_email,
            session_id = session_id,
            debug      = debug
        )

        if job is None:
            raise HTTPException( status_code=500, detail="Failed to create podcast job" )

        # Apply max_segments if specified (factory doesn't handle this)
        if request.max_segments:
            job.max_segments = request.max_segments

        # Associate BEFORE push to prevent race condition
        # The consumer thread may grab the job immediately after push(), so user mapping must exist first
        user_job_tracker.associate_job_with_user( job.id_hash, user_id )
        user_job_tracker.associate_job_with_session( job.id_hash, session_id )

        # Push to todo queue
        todo_queue.push( job )

        # Get queue position (approximate - queue length after push)
        queue_position = todo_queue.size()

        return PodcastSubmitResponse(
            job_id         = job.id_hash,
            queue_position = queue_position,
            status         = "queued"
        )

    else:
        # Flow B: Description mode (fuzzy matching with blocking selection)
        if debug:
            print( f"[submit_podcast_job] Description mode: {research_source}" )

        # Step 1: Find matching documents via LLM
        matches = await match_research_docs( user_email, research_source, debug=debug )

        if not matches:
            raise HTTPException(
                status_code=404,
                detail="No matching research documents found. Please check your research library or provide a direct file path."
            )

        # Step 2: Present options to user and wait for selection (BLOCKING)
        selected_filename = await get_user_document_selection(
            user_email = user_email,
            session_id = session_id,
            matches    = matches,
            debug      = debug
        )

        if not selected_filename:
            # User cancelled
            return PodcastMatchingResponse(
                status  = "cancelled",
                message = "Podcast generation cancelled by user."
            )

        # Step 3: Build full path and create job (same as Flow A)
        from cosa.config.configuration_manager import ConfigurationManager
        config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
        research_root = config_mgr.get( "deep research output path" )

        full_path = f"{cu.get_project_root()}{research_root}/{user_email}/{selected_filename}"

        if not os.path.exists( full_path ):
            raise HTTPException(
                status_code=404,
                detail=f"Selected research file not found: {selected_filename}"
            )

        # Create job using shared factory
        args_dict = { "research": full_path }
        if request.target_languages:
            args_dict[ "languages" ] = ",".join( request.target_languages )
        if request.dry_run:
            args_dict[ "dry_run" ] = True
        if request.audience:
            args_dict[ "audience" ] = request.audience
        if request.audience_context:
            args_dict[ "audience_context" ] = request.audience_context

        job = create_agentic_job(
            command    = "agent router go to podcast generator",
            args_dict  = args_dict,
            user_id    = user_id,
            user_email = user_email,
            session_id = session_id,
            debug      = debug
        )

        if job is None:
            raise HTTPException( status_code=500, detail="Failed to create podcast job" )

        # Apply max_segments if specified
        if request.max_segments:
            job.max_segments = request.max_segments

        # Associate BEFORE push to prevent race condition
        user_job_tracker.associate_job_with_user( job.id_hash, user_id )
        user_job_tracker.associate_job_with_session( job.id_hash, session_id )

        # Push to todo queue
        todo_queue.push( job )

        # Get queue position
        queue_position = todo_queue.size()

        return PodcastSubmitResponse(
            job_id         = job.id_hash,
            queue_position = queue_position,
            status         = "queued"
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
