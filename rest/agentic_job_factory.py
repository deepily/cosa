#!/usr/bin/env python3
"""
Shared factory for creating agentic jobs.

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

    if command == "agent router go to deep research":
        return DeepResearchJob(
            query      = args_dict.get( "query", "" ),
            user_id    = user_id,
            user_email = user_email,
            session_id = session_id,
            budget     = float( args_dict[ "budget" ] ) if args_dict.get( "budget" ) else None,
            no_confirm = True,
            dry_run    = args_dict.get( "dry_run", False ),
            debug      = debug,
            verbose    = verbose
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
            budget           = float( args_dict[ "budget" ] ) if args_dict.get( "budget" ) else None,
            target_languages = languages,
            dry_run          = args_dict.get( "dry_run", False ),
            debug            = debug,
            verbose          = verbose
        )

    else:
        print( f"[agentic_job_factory] Unknown command: {command}" )
        return None
