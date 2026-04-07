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


def _parse_boolean( value, default=False ):
    """
    Safely parse a value to bool, treating semantic strings appropriately.

    Requires:
        - value is a string, bool, None, or other type

    Ensures:
        - Returns True for "yes", "true", "1", "enable", "enabled"
        - Returns False for all other strings including "no", "false", "0"
        - Returns default if value is None
        - Passes through bool values unchanged
    """
    if value is None: return default
    if isinstance( value, bool ): return value
    s = str( value ).lower().strip()
    return s in ( "yes", "true", "1", "enable", "enabled" )


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
    from cosa.agents.bug_fix_expediter.job              import BugFixExpediterJob
    from cosa.agents.claude_code.job                     import ClaudeCodeJob
    from cosa.agents.deep_research.job                   import DeepResearchJob
    from cosa.agents.deep_research_to_podcast.job        import DeepResearchToPodcastJob
    from cosa.agents.deep_research_to_presentation.job   import DeepResearchToPresentationJob
    from cosa.agents.podcast_generator.job               import PodcastGeneratorJob
    from cosa.agents.presentation_generator.job          import PresentationGeneratorJob
    from cosa.agents.swe_team.job                        import SweTeamJob
    from cosa.agents.test_suite.job                      import TestSuiteJob

    if command == "agent router go to deep research":
        return DeepResearchJob(
            query            = args_dict.get( "query", "" ),
            user_id          = user_id,
            user_email       = user_email,
            session_id       = session_id,
            budget           = _parse_optional_float( args_dict.get( "budget" ) ),
            no_confirm       = True,
            dry_run          = _parse_boolean( args_dict.get( "dry_run" ) ),
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
            dry_run          = _parse_boolean( args_dict.get( "dry_run" ) ),
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
            dry_run          = _parse_boolean( args_dict.get( "dry_run" ) ),
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
            dry_run         = _parse_boolean( args_dict.get( "dry_run" ) ),
            debug           = debug,
            verbose         = verbose
        )

    elif command == "agent router go to presentation generator":
        return PresentationGeneratorJob(
            source_path             = args_dict.get( "source", "" ),
            user_id                 = user_id,
            user_email              = user_email,
            session_id              = session_id,
            target_duration_minutes = _parse_optional_int( args_dict.get( "target_duration_minutes" ) ),
            audience                = args_dict.get( "audience" ),
            audience_context        = args_dict.get( "audience_context" ),
            theme                   = args_dict.get( "theme" ),
            content_model           = args_dict.get( "content_model" ),
            dry_run                 = _parse_boolean( args_dict.get( "dry_run" ) ),
            debug                   = debug,
            verbose                 = verbose
        )

    elif command == "agent router go to research to presentation":
        return DeepResearchToPresentationJob(
            query                   = args_dict.get( "query", "" ),
            user_id                 = user_id,
            user_email              = user_email,
            session_id              = session_id,
            budget                  = _parse_optional_float( args_dict.get( "budget" ) ),
            target_duration_minutes = _parse_optional_int( args_dict.get( "target_duration_minutes" ) ),
            theme                   = args_dict.get( "theme" ),
            dry_run                 = _parse_boolean( args_dict.get( "dry_run" ) ),
            audience                = args_dict.get( "audience" ),
            audience_context        = args_dict.get( "audience_context" ),
            debug                   = debug,
            verbose                 = verbose,
        )

    elif command == "agent router go to swe team":
        return SweTeamJob(
            task           = args_dict.get( "task", args_dict.get( "prompt", "" ) ),
            user_id        = user_id,
            user_email     = user_email,
            session_id     = session_id,
            dry_run        = _parse_boolean( args_dict.get( "dry_run" ) ),
            dry_run_phases = _parse_optional_int( args_dict.get( "dry_run_phases" ) ) or 10,
            dry_run_delay  = _parse_optional_float( args_dict.get( "dry_run_delay" ) ) or 1.5,
            lead_model     = args_dict.get( "lead_model" ),
            worker_model   = args_dict.get( "worker_model" ),
            budget         = _parse_optional_float( args_dict.get( "budget" ) ),
            timeout        = _parse_optional_int( args_dict.get( "timeout" ) ),
            trust_mode     = args_dict.get( "trust_mode" ),
            debug          = debug,
            verbose        = verbose
        )

    elif command == "agent router go to test suite":
        # Parse test_types: comma-separated string → list
        test_types_raw = args_dict.get( "test_types", "integration,e2e" )
        if isinstance( test_types_raw, str ):
            test_types = [ t.strip() for t in test_types_raw.split( "," ) if t.strip() ]
        else:
            test_types = test_types_raw

        # Parse pytest_args: JSON list or space-separated string → list
        pytest_args_raw = args_dict.get( "pytest_args", "" )
        if isinstance( pytest_args_raw, list ):
            pytest_args = pytest_args_raw
        elif pytest_args_raw and pytest_args_raw.lower() not in _SEMANTIC_NONE:
            pytest_args = pytest_args_raw.split()
        else:
            pytest_args = []

        return TestSuiteJob(
            test_types  = test_types,
            user_id     = user_id,
            user_email  = user_email,
            session_id  = session_id,
            pytest_args = pytest_args,
            dry_run     = _parse_boolean( args_dict.get( "dry_run" ) ),
            debug       = debug,
            verbose     = verbose
        )

    elif command == "agent router go to bug fix expediter":
        return BugFixExpediterJob(
            dead_job_id   = args_dict.get( "dead_job_id", "" ),
            user_id       = user_id,
            user_email    = user_email,
            session_id    = session_id,
            extra_context = args_dict.get( "extra_context", "" ),
            dry_run       = _parse_boolean( args_dict.get( "dry_run" ) ),
            debug         = debug,
            verbose       = verbose
        )

    else:
        print( f"[agentic_job_factory] Unknown command: {command}" )
        return None
