#!/usr/bin/env python3
"""
Shared factory for creating agentic jobs in CJ Flow (COSA Jobs Flow).

Extracted from TodoFifoQueue to enable both voice routing and REST endpoints
to create jobs identically. This eliminates duplicated job creation code.

Used by:
    - todo_fifo_queue.py (voice path via expeditor)
    - routers/deep_research.py (REST form submission)
    - routers/podcast_generator.py (REST form submission)
    - routers/deep_research_to_podcast.py (REST form submission)
    - routers/mock_job.py (expeditor test mode)
"""

from typing import Optional

_SEMANTIC_NONE = { "default", "no limit", "none", "skip", "no", "" }


def _parse_optional_int( value, default=None ):
    """
    Safely parse a value to int, treating semantic strings as None.

    Requires:
        - value is a string, int, None, or other type

    Ensures:
        - Returns int if value is a valid numeric string or int
        - Returns default if value is None, empty, a semantic skip word, or unparseable
    """
    if not value or str( value ).strip().lower() in _SEMANTIC_NONE:
        return default
    try:
        return int( value )
    except ( ValueError, TypeError ):
        return default


def _parse_optional_float( value, default=None ):
    """
    Safely parse a value to float, treating semantic strings as None.

    Requires:
        - value is a string, float, int, None, or other type

    Ensures:
        - Returns float if value is a valid numeric string or number
        - Returns default if value is None, empty, a semantic skip word, or unparseable
    """
    if not value or str( value ).strip().lower() in _SEMANTIC_NONE:
        return default
    try:
        return float( value )
    except ( ValueError, TypeError ):
        return default


def create_agentic_job( command, args_dict, user_id, user_email, session_id, debug=False, verbose=False ):
    """
    Factory function to create the correct agentic job based on command.

    Requires:
        - command is a recognized agentic routing command string
        - args_dict contains the required arguments for the target job
        - user_id, user_email, session_id are non-empty strings

    Ensures:
        - Returns appropriate Job instance for the command
        - Returns None if command is unrecognized

    Args:
        command: Routing command key (e.g., "agent router go to deep research")
        args_dict: Complete argument dictionary
        user_id: System user ID
        user_email: User's email address
        session_id: WebSocket session ID
        debug: Enable debug output
        verbose: Enable verbose output

    Returns:
        AgenticJobBase subclass instance, or None
    """
    from cosa.agents.deep_research.job import DeepResearchJob
    from cosa.agents.podcast_generator.job import PodcastGeneratorJob
    from cosa.agents.deep_research_to_podcast.job import DeepResearchToPodcastJob
    from cosa.agents.claude_code.job import ClaudeCodeJob

    if command == "agent router go to deep research":
        return DeepResearchJob(
            query            = args_dict.get( "query", "" ),
            user_id          = user_id,
            user_email       = user_email,
            session_id       = session_id,
            budget           = _parse_optional_float( args_dict.get( "budget" ) ),
            no_confirm       = True,
            dry_run          = args_dict.get( "dry_run", False ),
            audience         = args_dict.get( "audience" ),
            audience_context = args_dict.get( "audience_context" ),
            debug            = debug,
            verbose          = verbose
        )

    elif command == "agent router go to podcast generator":
        # Parse target_languages if provided as string
        languages = None
        if args_dict.get( "languages" ):
            if isinstance( args_dict[ "languages" ], list ):
                languages = args_dict[ "languages" ]
            else:
                languages = [ lang.strip() for lang in args_dict[ "languages" ].split( "," ) ]

        return PodcastGeneratorJob(
            research_path    = args_dict.get( "research", "" ),
            user_id          = user_id,
            user_email       = user_email,
            session_id       = session_id,
            target_languages = languages,
            dry_run          = args_dict.get( "dry_run", False ),
            audience         = args_dict.get( "audience" ),
            audience_context = args_dict.get( "audience_context" ),
            debug            = debug,
            verbose          = verbose
        )

    elif command == "agent router go to research to podcast":
        # Parse target_languages if provided as string
        languages = None
        if args_dict.get( "languages" ):
            if isinstance( args_dict[ "languages" ], list ):
                languages = args_dict[ "languages" ]
            else:
                languages = [ lang.strip() for lang in args_dict[ "languages" ].split( "," ) ]

        return DeepResearchToPodcastJob(
            query            = args_dict.get( "query", "" ),
            user_id          = user_id,
            user_email       = user_email,
            session_id       = session_id,
            budget           = _parse_optional_float( args_dict.get( "budget" ) ),
            target_languages = languages,
            dry_run          = args_dict.get( "dry_run", False ),
            audience         = args_dict.get( "audience" ),
            audience_context = args_dict.get( "audience_context" ),
            debug            = debug,
            verbose          = verbose
        )

    elif command == "agent router go to claude code":
        return ClaudeCodeJob(
            prompt          = args_dict.get( "prompt", "" ),
            project         = args_dict.get( "project", "lupin" ),
            user_id         = user_id,
            user_email      = user_email,
            session_id      = session_id,
            task_type       = args_dict.get( "task_type", "BOUNDED" ),
            max_turns       = _parse_optional_int( args_dict.get( "max_turns" ) ),
            timeout_seconds = _parse_optional_int( args_dict.get( "timeout_seconds" ) ),
            dry_run         = args_dict.get( "dry_run", False ),
            debug           = debug,
            verbose         = verbose
        )

    elif command == "agent router go to swe team":
        from cosa.agents.swe_team.job import SweTeamJob
        return SweTeamJob(
            task         = args_dict.get( "task", args_dict.get( "prompt", "" ) ),
            user_id      = user_id,
            user_email   = user_email,
            session_id   = session_id,
            dry_run      = args_dict.get( "dry_run", False ),
            lead_model   = args_dict.get( "lead_model" ),
            worker_model = args_dict.get( "worker_model" ),
            budget       = _parse_optional_float( args_dict.get( "budget" ) ),
            timeout      = _parse_optional_int( args_dict.get( "timeout" ) ),
            debug        = debug,
            verbose      = verbose
        )

    else:
        print( f"[agentic_job_factory] Unknown command: {command}" )
        return None
