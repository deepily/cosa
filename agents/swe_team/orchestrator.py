#!/usr/bin/env python3
"""
Core Orchestrator for COSA SWE Team Agent.

Phase 2: Lead + Coder delegation loop with real Claude Agent SDK.
Lead decomposes tasks into TaskSpec[], delegates each to a Coder
subagent via ClaudeSDKClient, and collects DelegationResults.

Supports dry-run mode via MockAgentSDKSession (Phase 1 preserved).
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Optional

import cosa.utils.util as cu

from .config import SweTeamConfig
from .state import (
    OrchestratorState,
    SweTeamState,
    TaskSpec,
    DelegationResult,
    VerificationResult,
    create_initial_state,
)
from .safety_limits import SafetyGuard, SafetyLimitError
from .agent_definitions import (
    get_agent_roles,
    get_active_roles,
    get_model_for_role,
    get_sender_id,
    LEAD_SYSTEM_PROMPT,
    CODER_SYSTEM_PROMPT,
    TESTER_SYSTEM_PROMPT,
)
from .test_runner import run_pytest, TestRunResult
from .mock_clients import MockAgentSDKSession
from .hooks import build_can_use_tool, post_tool_hook
from .state_files import FeatureList, ProgressLog

# SDK imports — graceful fallback
try:
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AssistantMessage,
        TextBlock,
        ToolUseBlock,
        ResultMessage,
        query as sdk_query,
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

logger = logging.getLogger( __name__ )

MAX_VERIFICATION_ITERATIONS = 3


class SweTeamOrchestrator:
    """
    Orchestrator for the SWE Team multi-agent engineering system.

    Phase 3 implementation:
    - Lead decomposes task into TaskSpec[] via SDK
    - Coder executes each TaskSpec via SDK delegation
    - Tester verifies coder output with tests (coder-tester loop)
    - Safety guard enforced at every delegation step
    - Dry-run mode preserved from Phase 1

    Future phases will add:
    - Phase 5: Reviewer, Debugger, full CJ Flow

    Requires:
        - task_description is a non-empty string
        - config is a valid SweTeamConfig

    Ensures:
        - run() executes the task within safety limits
        - Notifications flow through cosa_interface
        - Dry-run mode simulates without API calls
        - Live mode decomposes, delegates, and verifies via SDK
    """

    def __init__(
        self,
        task_description : str,
        config           : SweTeamConfig = None,
        session_id       : str = None,
        debug            : bool = False,
        verbose          : bool = False,
    ):
        self.task_description = task_description
        self.config           = config or SweTeamConfig()
        self.session_id       = session_id or f"st-{uuid.uuid4().hex[ :8 ]}"
        self.debug            = debug
        self.verbose          = verbose

        # State
        self.state          = create_initial_state( task_description )
        self.current_state  = OrchestratorState.INITIALIZING
        self._stop_requested = False

        # Safety
        self.guard = SafetyGuard(
            max_iterations = self.config.max_iterations_per_task,
            max_failures   = self.config.max_consecutive_failures,
            timeout_secs   = self.config.wall_clock_timeout_secs,
        )

        # Metrics
        self.start_time   = None
        self.end_time     = None
        self.tokens_used  = 0

    async def run( self ) -> Optional[ str ]:
        """
        Execute the SWE Team task.

        Phase 2: Decomposes task, delegates to coder, or runs dry-run.

        Requires:
            - task_description is non-empty

        Ensures:
            - Returns final summary string on success
            - Returns None on failure
            - Notifications sent at each phase boundary
            - Safety limits enforced throughout

        Returns:
            str or None: Final task summary
        """
        self.start_time = time.time()

        try:
            # Import here to avoid circular imports at module load
            from . import cosa_interface as team_io

            # Set session context for notifications
            team_io.SESSION_ID = self.session_id

            self.current_state = OrchestratorState.INITIALIZING

            await team_io.notify_progress(
                message  = f"Starting SWE Team task: {self.task_description[ :100 ]}",
                role     = "lead",
                priority = "medium",
                abstract = self.task_description,
            )

            if self.config.dry_run:
                result = await self._execute_dry_run( team_io )
            else:
                result = await self._execute_live( team_io )

            self.end_time = time.time()
            self.current_state = OrchestratorState.COMPLETED

            elapsed = self.end_time - self.start_time
            await team_io.notify_progress(
                message  = f"SWE Team task complete ({elapsed:.1f}s)",
                role     = "lead",
                priority = "medium",
                abstract = f"**Task**: {self.task_description[ :80 ]}\n**Duration**: {elapsed:.1f}s",
            )

            return result

        except SafetyLimitError as e:
            self.current_state = OrchestratorState.FAILED
            self.end_time = time.time()

            from . import cosa_interface as team_io
            await team_io.notify_progress(
                message  = f"SWE Team task stopped: {e}",
                role     = "lead",
                priority = "urgent",
            )

            logger.error( f"Safety limit reached: {e}" )
            return None

        except Exception as e:
            self.current_state = OrchestratorState.FAILED
            self.end_time = time.time()

            from . import cosa_interface as team_io
            await team_io.notify_progress(
                message  = f"SWE Team task failed: {str( e )[ :200 ]}",
                role     = "lead",
                priority = "urgent",
            )

            logger.exception( f"Orchestrator failed: {e}" )
            return None

    async def _execute_dry_run( self, team_io ) -> str:
        """
        Execute task in dry-run mode using mock client.

        Sends breadcrumb notifications at each phase.

        Returns:
            str: Dry-run summary
        """
        if self.debug: print( "[Orchestrator] Entering dry-run mode" )

        mock_session = MockAgentSDKSession(
            task_description = self.task_description,
            debug            = self.debug,
        )

        # Override our session_id with the mock's
        self.session_id = mock_session.session_id

        self.current_state = OrchestratorState.DELEGATING

        async for msg in mock_session.query():
            # Send each phase as a notification
            await team_io.notify_progress(
                message  = f"[{msg.agent_name}] {msg.content[ :200 ]}",
                role     = msg.agent_name,
                priority = "low",
            )

            self.guard.check_timeout()

            if self._stop_requested:
                break

        summary = mock_session.get_session_summary()
        self.state[ "final_summary" ] = f"Dry-run complete: {summary[ 'messages_sent' ]} phases simulated"

        return self.state[ "final_summary" ]

    async def _execute_live( self, team_io ) -> str:
        """
        Execute task with real Agent SDK delegation.

        Phase 3: Lead decomposes task into TaskSpec[], asks user
        confirmation, delegates each to a Coder subagent, then
        verifies with a Tester subagent in a retry loop.

        Requires:
            - SDK_AVAILABLE is True (claude-agent-sdk installed)
            - team_io is the cosa_interface module

        Ensures:
            - Returns final summary string
            - state["task_specs"] populated with decomposition
            - state["delegation_results"] populated per task
            - state["verification_results"] populated per verification
            - Safety guard checked at each delegation and verification
            - Coder-tester loop capped at MAX_VERIFICATION_ITERATIONS

        Returns:
            str: Task execution summary
        """
        if not SDK_AVAILABLE:
            self.state[ "final_summary" ] = (
                "claude-agent-sdk not installed. Cannot run live mode.\n"
                "Install with: pip install claude-agent-sdk"
            )
            return self.state[ "final_summary" ]

        if self.debug: print( "[Orchestrator] Entering live execution mode" )

        # --- Phase: DECOMPOSING ---
        self.current_state = OrchestratorState.DECOMPOSING

        await team_io.notify_progress(
            message  = "Decomposing task into subtasks...",
            role     = "lead",
            priority = "medium",
        )

        task_specs = await self._decompose_task( team_io )
        self.state[ "task_specs" ] = task_specs

        if self.debug: print( f"[Orchestrator] Decomposed into {len( task_specs )} tasks" )

        # --- Confirmation ---
        self.current_state = OrchestratorState.WAITING_CONFIRMATION

        task_summary = "\n".join(
            f"  {i + 1}. {spec.title} → {spec.assigned_role}"
            for i, spec in enumerate( task_specs )
        )

        approved = await team_io.ask_confirmation(
            question = f"SWE Team decomposed the task into {len( task_specs )} subtasks. Proceed?",
            role     = "lead",
            default  = "yes",
            timeout  = 120,
            abstract = f"**Task**: {self.task_description[ :100 ]}\n\n**Subtasks**:\n{task_summary}",
        )

        if not approved:
            self.state[ "final_summary" ] = "Task cancelled by user after decomposition."
            return self.state[ "final_summary" ]

        # --- Phase: DELEGATING ---
        self.current_state = OrchestratorState.DELEGATING
        results = []

        # Initialize state files for progress tracking
        storage_dir = os.path.join( cu.get_project_root(), "io", "swe_team", self.session_id )
        progress_log = ProgressLog( storage_dir=storage_dir )
        feature_list = FeatureList( storage_dir=storage_dir )

        for spec in task_specs:
            feature_list.add_task( spec )

        for i, spec in enumerate( task_specs ):
            if self._stop_requested:
                break

            self.guard.check_timeout()
            self.state[ "current_task_index" ] = i

            await team_io.notify_progress(
                message  = f"Delegating task {i + 1}/{len( task_specs )}: {spec.title}",
                role     = "lead",
                priority = "low",
            )

            progress_log.log( f"Starting task {i + 1}: {spec.title}", role="lead" )

            try:
                result = await self._delegate_task( spec, i, team_io )
                results.append( result )
                self.state[ "delegation_results" ].append( result )

                if result.status == "success" and self.config.require_test_pass:
                    # --- Coder-Tester Verification Loop ---
                    verification_iteration = 0
                    while verification_iteration < MAX_VERIFICATION_ITERATIONS:
                        verification_iteration += 1
                        self.state[ "total_verification_iterations" ] += 1

                        verification = await self._verify_result( spec, result, i, team_io )
                        self.state[ "verification_results" ].append( verification )

                        if verification.passed:
                            result.test_results = verification.tester_output[ :1000 ]
                            self.guard.record_success()
                            feature_list.mark_complete( i )
                            progress_log.log(
                                f"Task {i + 1} verified (iteration {verification_iteration}): {spec.title}",
                                role="tester",
                            )
                            break  # Tests pass — done

                        if verification_iteration >= MAX_VERIFICATION_ITERATIONS:
                            # Max retries exhausted — mark task failed
                            self.guard.record_failure( "verification failed after max iterations" )
                            result = DelegationResult(
                                task_index    = i,
                                task_title    = spec.title,
                                status        = "failure",
                                output        = result.output,
                                errors        = [ "Verification failed after max iterations" ],
                                test_results  = verification.tester_output[ :1000 ],
                                confidence    = 0.0,
                            )
                            self.state[ "delegation_results" ][ -1 ] = result
                            progress_log.log(
                                f"Task {i + 1} verification exhausted: {spec.title}",
                                role="lead",
                            )
                            break

                        # Re-delegate to coder with tester feedback
                        result = await self._redelegate_with_feedback(
                            spec, i, result, verification.tester_output,
                            verification_iteration + 1, team_io,
                        )
                        self.state[ "delegation_results" ][ -1 ] = result

                        if result.status != "success":
                            self.guard.record_failure( "coder re-implementation failed" )
                            progress_log.log(
                                f"Task {i + 1} re-implementation failed: {spec.title}",
                                role="coder",
                            )
                            break

                elif result.status == "success":
                    # require_test_pass=False — skip verification
                    self.guard.record_success()
                    feature_list.mark_complete( i )
                    progress_log.log( f"Task {i + 1} completed (no verification): {spec.title}", role="coder" )

                else:
                    self.guard.record_failure( f"Task {i + 1} failed: {result.errors}" )
                    progress_log.log( f"Task {i + 1} failed: {spec.title}", role="coder" )

                # Track changed files
                for f in result.files_changed:
                    if f not in self.state[ "files_changed" ]:
                        self.state[ "files_changed" ].append( f )

            except SafetyLimitError:
                raise  # Let outer handler catch

            except Exception as e:
                logger.error( f"Delegation failed for task {i + 1}: {e}" )
                self.guard.record_failure( str( e ) )

                results.append( DelegationResult(
                    task_index    = i,
                    task_title    = spec.title,
                    status        = "failure",
                    output        = "",
                    errors        = [ str( e ) ],
                    confidence    = 0.0,
                ) )
                progress_log.log( f"Task {i + 1} exception: {e}", role="lead" )

        # --- Summary ---
        success_count        = sum( 1 for r in results if r.status == "success" )
        total_files          = len( self.state[ "files_changed" ] )
        verification_count   = len( self.state[ "verification_results" ] )
        verification_passed  = sum( 1 for v in self.state[ "verification_results" ] if v.passed )
        total_v_iterations   = self.state[ "total_verification_iterations" ]

        self.state[ "final_summary" ] = (
            f"SWE Team completed {success_count}/{len( task_specs )} tasks.\n"
            f"Files changed: {total_files}\n"
            f"Verifications: {verification_passed}/{verification_count} passed"
            f" ({total_v_iterations} total iterations)\n"
            f"Session: {self.session_id}"
        )

        progress_log.log( self.state[ "final_summary" ], role="lead" )

        return self.state[ "final_summary" ]

    async def _decompose_task( self, team_io ):
        """
        Lead agent decomposes task into TaskSpec[].

        Uses ClaudeSDKClient with lead model and read-only tools
        to produce a structured JSON decomposition.

        Requires:
            - SDK_AVAILABLE is True
            - team_io is the cosa_interface module

        Ensures:
            - Returns list[TaskSpec] with at least 1 item
            - Falls back to single TaskSpec if parse fails

        Args:
            team_io: cosa_interface module

        Returns:
            list[TaskSpec]: Decomposed task specifications
        """
        decomposition_prompt = f"""Decompose the following task into 1-5 subtasks.

TASK: {self.task_description}

OUTPUT FORMAT: Respond with a JSON array of task objects. Each object must have:
- "title": Short title (string)
- "objective": What must be accomplished (string)
- "output_format": Expected output structure (string)
- "tool_guidance": Which tools to use (string, optional)
- "scope_boundary": What NOT to touch (string, optional)
- "assigned_role": "coder" (string)
- "priority": 1-5 integer

IMPORTANT: Output ONLY the JSON array, no markdown fences, no explanation.

Example:
[
  {{
    "title": "Add health check endpoint",
    "objective": "Create GET /health that returns {{'status': 'ok'}}",
    "output_format": "Modified main.py with new endpoint",
    "tool_guidance": "Use Edit to modify existing router file",
    "scope_boundary": "Do not modify authentication code",
    "assigned_role": "coder",
    "priority": 1
  }}
]"""

        try:
            options = self._build_agent_options( "lead" )
            collected_text = []

            async for message in sdk_query( prompt=decomposition_prompt, options=options ):
                if isinstance( message, AssistantMessage ):
                    for block in message.content:
                        if isinstance( block, TextBlock ):
                            collected_text.append( block.text )
                elif isinstance( message, TextBlock ):
                    collected_text.append( message.text )

            raw_response = "".join( collected_text ).strip()

            if self.debug: print( f"[Orchestrator] Lead response: {raw_response[ :500 ]}" )

            return self._parse_task_specs( raw_response )

        except Exception as e:
            logger.warning( f"Decomposition failed, using single-task fallback: {e}" )
            return self._fallback_single_task()

    def _parse_task_specs( self, raw_response ):
        """
        Parse lead's JSON response into list[TaskSpec].

        Requires:
            - raw_response is a string (possibly with markdown fences)

        Ensures:
            - Returns list[TaskSpec] with validated entries
            - Falls back to single TaskSpec on parse failure

        Args:
            raw_response: Raw text from lead agent

        Returns:
            list[TaskSpec]: Parsed task specifications
        """
        # Strip markdown code fences if present
        text = raw_response.strip()
        if text.startswith( "```" ):
            lines = text.split( "\n" )
            # Remove first and last lines (fences)
            lines = [ l for l in lines if not l.strip().startswith( "```" ) ]
            text = "\n".join( lines ).strip()

        try:
            data = json.loads( text )

            if not isinstance( data, list ):
                data = [ data ]

            specs = []
            for item in data:
                spec = TaskSpec( **item )
                specs.append( spec )

            if not specs:
                return self._fallback_single_task()

            return specs

        except ( json.JSONDecodeError, TypeError, ValueError ) as e:
            logger.warning( f"Failed to parse task specs: {e}" )
            return self._fallback_single_task()

    def _fallback_single_task( self ):
        """
        Create a single TaskSpec fallback from the original task.

        Ensures:
            - Returns list with one TaskSpec
            - Uses original task_description as objective

        Returns:
            list[TaskSpec]: Single-item list
        """
        return [ TaskSpec(
            title          = self.task_description[ :80 ],
            objective      = self.task_description,
            output_format  = "Modified source files",
            tool_guidance  = "Use Read, Edit, and Bash as needed",
            scope_boundary = "Stay within the project directory",
            assigned_role  = "coder",
            priority       = 1,
        ) ]

    async def _delegate_task( self, task_spec, task_index, team_io ):
        """
        Delegate a single TaskSpec to a coder subagent via SDK.

        Requires:
            - task_spec is a valid TaskSpec
            - task_index is a non-negative integer
            - team_io is the cosa_interface module

        Ensures:
            - Returns DelegationResult with status, output, files_changed
            - Safety guard checked during execution
            - Notifications sent for progress

        Args:
            task_spec: The task to delegate
            task_index: Index of this task in the decomposition
            team_io: cosa_interface module

        Returns:
            DelegationResult: Execution result
        """
        delegation_prompt = f"""TASK: {task_spec.title}
OBJECTIVE: {task_spec.objective}
EXPECTED OUTPUT: {task_spec.output_format}
TOOL GUIDANCE: {task_spec.tool_guidance}
SCOPE BOUNDARY: {task_spec.scope_boundary}

Complete this task. When done, summarize what you did and list all files changed."""

        try:
            options = self._build_agent_options( "coder", team_io )
            collected_text  = []
            files_changed   = []

            self.current_state = OrchestratorState.CODING

            async for message in sdk_query( prompt=delegation_prompt, options=options ):
                self.guard.check_timeout()

                if isinstance( message, AssistantMessage ):
                    for block in message.content:
                        if isinstance( block, TextBlock ):
                            collected_text.append( block.text )
                        elif isinstance( block, ToolUseBlock ):
                            # Track file changes from Edit/Write tool uses
                            if block.name in ( "Edit", "Write" ):
                                file_path = block.input.get( "file_path", "" )
                                if file_path and file_path not in files_changed:
                                    files_changed.append( file_path )
                                await post_tool_hook( block.name, block.input, self.guard )

                elif isinstance( message, TextBlock ):
                    collected_text.append( message.text )

                if self._stop_requested:
                    break

            self.guard.check_iteration()

            output = "".join( collected_text ).strip()

            return DelegationResult(
                task_index    = task_index,
                task_title    = task_spec.title,
                status        = "success",
                output        = output[ :2000 ],
                files_changed = files_changed,
                confidence    = 0.8,
            )

        except SafetyLimitError:
            raise  # Propagate to outer handler

        except Exception as e:
            logger.error( f"Delegation error for '{task_spec.title}': {e}" )
            return DelegationResult(
                task_index    = task_index,
                task_title    = task_spec.title,
                status        = "failure",
                output        = "",
                errors        = [ str( e ) ],
                confidence    = 0.0,
            )

    async def _verify_result( self, task_spec, coder_result, task_index, team_io ):
        """
        Verify coder's implementation by delegating to the tester agent.

        Builds a tester prompt with the original task spec and coder's output,
        delegates to the tester via sdk_query(), and optionally runs independent
        pytest validation on any test files created.

        Requires:
            - task_spec is a valid TaskSpec
            - coder_result is a DelegationResult with status "success"
            - task_index is a non-negative integer
            - team_io is the cosa_interface module

        Ensures:
            - Sets self.current_state to OrchestratorState.TESTING
            - Returns VerificationResult with pass/fail status
            - Tracks test files created by the tester
            - Never raises — returns failed VerificationResult on error

        Args:
            task_spec: The original task specification
            coder_result: The coder's delegation result
            task_index: Index of the task in decomposition
            team_io: cosa_interface module

        Returns:
            VerificationResult: Test verification outcome
        """
        self.current_state = OrchestratorState.TESTING

        await team_io.notify_progress(
            message  = f"Verifying task {task_index + 1}: {task_spec.title}",
            role     = "tester",
            priority = "low",
        )

        verification_prompt = f"""VERIFY THE FOLLOWING IMPLEMENTATION:

ORIGINAL TASK: {task_spec.title}
OBJECTIVE: {task_spec.objective}
EXPECTED OUTPUT: {task_spec.output_format}

CODER OUTPUT SUMMARY:
{coder_result.output[ :1500 ]}

FILES CHANGED BY CODER:
{chr( 10 ).join( coder_result.files_changed ) if coder_result.files_changed else "None reported"}

YOUR INSTRUCTIONS:
1. Read the changed files to understand what was implemented
2. Write appropriate tests (unit tests preferred, in src/tests/unit/)
3. Run the tests with pytest
4. Report whether the implementation passes all tests

IMPORTANT:
- Focus on testing the ACTUAL changes made by the coder
- Follow existing test patterns in the project
- Report a clear PASS or FAIL verdict at the end of your output
- If tests FAIL, explain what failed and why"""

        try:
            options         = self._build_agent_options( "tester", team_io )
            collected_text  = []
            test_files      = []

            async for message in sdk_query( prompt=verification_prompt, options=options ):
                self.guard.check_timeout()

                if isinstance( message, AssistantMessage ):
                    for block in message.content:
                        if isinstance( block, TextBlock ):
                            collected_text.append( block.text )
                        elif isinstance( block, ToolUseBlock ):
                            # Track test files created by the tester
                            if block.name in ( "Edit", "Write" ):
                                file_path = block.input.get( "file_path", "" )
                                if file_path and file_path not in test_files:
                                    test_files.append( file_path )
                                await post_tool_hook( block.name, block.input, self.guard )

                elif isinstance( message, TextBlock ):
                    collected_text.append( message.text )

                if self._stop_requested:
                    break

            tester_output = "".join( collected_text ).strip()

            # Determine pass/fail from tester output
            output_lower = tester_output.lower()
            passed = (
                "pass" in output_lower
                and "fail" not in output_lower
            ) or "all tests pass" in output_lower

            # Optionally run independent pytest validation on test files
            test_run_dict = None
            if test_files:
                for tf in test_files:
                    if tf.endswith( ".py" ) and "test" in tf.lower():
                        run_result = await run_pytest( tf, timeout_secs=60 )
                        test_run_dict = {
                            "passed"       : run_result.passed,
                            "total_tests"  : run_result.total_tests,
                            "passed_count" : run_result.passed_count,
                            "failed_count" : run_result.failed_count,
                            "error_count"  : run_result.error_count,
                            "timed_out"    : run_result.timed_out,
                        }
                        # Independent validation overrides tester's self-report
                        if not run_result.passed:
                            passed = False
                        break  # Only validate first test file found

            status = "passed" if passed else "failed"

            return VerificationResult(
                task_index         = task_index,
                task_title         = task_spec.title,
                passed             = passed,
                tester_output      = tester_output[ :2000 ],
                test_run_result    = test_run_dict,
                test_files_created = test_files,
                status             = status,
            )

        except SafetyLimitError:
            raise  # Propagate to outer handler

        except Exception as e:
            logger.error( f"Verification error for '{task_spec.title}': {e}" )
            return VerificationResult(
                task_index    = task_index,
                task_title    = task_spec.title,
                passed        = False,
                tester_output = f"Verification error: {e}",
                status        = "failed",
            )

    async def _redelegate_with_feedback( self, task_spec, task_index, coder_result, test_feedback, iteration, team_io ):
        """
        Re-delegate a task to the coder with tester failure feedback.

        Builds an augmented prompt including the prior coder output,
        tester failure feedback, and current iteration number to help
        the coder address the specific test failures.

        Requires:
            - task_spec is a valid TaskSpec
            - task_index is a non-negative integer
            - coder_result is the previous DelegationResult
            - test_feedback is a string with tester output
            - iteration is a positive integer (current retry number)
            - team_io is the cosa_interface module

        Ensures:
            - Returns a new DelegationResult from the coder
            - Prompt includes prior output and failure feedback
            - Sets current_state to CODING

        Args:
            task_spec: The original task specification
            task_index: Index of the task in decomposition
            coder_result: Previous coder result
            test_feedback: Tester output describing failures
            iteration: Current iteration number (2, 3, etc.)
            team_io: cosa_interface module

        Returns:
            DelegationResult: New coder execution result
        """
        await team_io.notify_progress(
            message  = f"Re-delegating task {task_index + 1} (iteration {iteration}): {task_spec.title}",
            role     = "lead",
            priority = "low",
        )

        redelegation_prompt = f"""FIX THE FOLLOWING IMPLEMENTATION (Iteration {iteration}/{MAX_VERIFICATION_ITERATIONS}):

ORIGINAL TASK: {task_spec.title}
OBJECTIVE: {task_spec.objective}

YOUR PRIOR OUTPUT:
{coder_result.output[ :1000 ]}

FILES YOU CHANGED:
{chr( 10 ).join( coder_result.files_changed ) if coder_result.files_changed else "None reported"}

TESTER FEEDBACK (TESTS FAILED):
{test_feedback[ :1500 ]}

INSTRUCTIONS:
1. Read the tester's failure feedback carefully
2. Fix the implementation to address the test failures
3. Do NOT modify the test files — fix your implementation code
4. Summarize what you changed and list all files modified"""

        try:
            options = self._build_agent_options( "coder", team_io )
            collected_text  = []
            files_changed   = []

            self.current_state = OrchestratorState.CODING

            async for message in sdk_query( prompt=redelegation_prompt, options=options ):
                self.guard.check_timeout()

                if isinstance( message, AssistantMessage ):
                    for block in message.content:
                        if isinstance( block, TextBlock ):
                            collected_text.append( block.text )
                        elif isinstance( block, ToolUseBlock ):
                            if block.name in ( "Edit", "Write" ):
                                file_path = block.input.get( "file_path", "" )
                                if file_path and file_path not in files_changed:
                                    files_changed.append( file_path )
                                await post_tool_hook( block.name, block.input, self.guard )

                elif isinstance( message, TextBlock ):
                    collected_text.append( message.text )

                if self._stop_requested:
                    break

            self.guard.check_iteration()

            output = "".join( collected_text ).strip()

            return DelegationResult(
                task_index    = task_index,
                task_title    = task_spec.title,
                status        = "success",
                output        = output[ :2000 ],
                files_changed = files_changed,
                confidence    = 0.6,  # Lower confidence on retries
            )

        except SafetyLimitError:
            raise

        except Exception as e:
            logger.error( f"Re-delegation error for '{task_spec.title}': {e}" )
            return DelegationResult(
                task_index    = task_index,
                task_title    = task_spec.title,
                status        = "failure",
                output        = "",
                errors        = [ str( e ) ],
                confidence    = 0.0,
            )

    def _build_agent_options( self, role_name, team_io=None ):
        """
        Build ClaudeAgentOptions for a given role.

        Requires:
            - role_name is "lead", "coder", or "tester"

        Ensures:
            - Returns ClaudeAgentOptions with correct model, tools, permissions
            - Coder and tester get can_use_tool callback for safety gating
            - Lead gets read-only tools

        Args:
            role_name: Agent role name
            team_io: cosa_interface module (required for coder/tester)

        Returns:
            ClaudeAgentOptions: Configured SDK options
        """
        roles  = get_agent_roles( self.config )
        role   = roles[ role_name ]
        model  = get_model_for_role( role, self.config )

        if role_name == "lead":
            system_prompt = LEAD_SYSTEM_PROMPT.format(
                max_failures=self.config.max_consecutive_failures
            )
        elif role_name == "tester":
            system_prompt = TESTER_SYSTEM_PROMPT
        else:
            system_prompt = CODER_SYSTEM_PROMPT

        options_kwargs = {
            "model"           : model,
            "system_prompt"   : system_prompt,
            "tools"           : role.tools,
            "cwd"             : cu.get_project_root(),
            "max_turns"       : self.config.max_iterations_per_task,
            "max_budget_usd"  : self.config.budget_usd,
        }

        # Coder and tester get permission gating and acceptEdits mode
        if role_name in ( "coder", "tester" ) and team_io is not None:
            options_kwargs[ "permission_mode" ] = "acceptEdits"
            options_kwargs[ "can_use_tool" ]    = build_can_use_tool( team_io, self.guard, role_name )
        else:
            options_kwargs[ "permission_mode" ] = "plan"

        return ClaudeAgentOptions( **options_kwargs )

    def get_state( self ) -> dict:
        """
        Get current orchestrator state for external monitoring.

        Returns:
            dict: Current state, progress, and guard status
        """
        return {
            "orchestrator_state" : self.current_state.value,
            "session_id"         : self.session_id,
            "task"               : self.task_description[ :100 ],
            "guard_status"       : self.guard.get_status(),
            "tokens_used"        : self.tokens_used,
            "dry_run"            : self.config.dry_run,
        }

    async def stop( self ) -> dict:
        """
        Request graceful stop of the orchestrator.

        Ensures:
            - Sets stop flag for next iteration check
            - Returns current state

        Returns:
            dict: Final state at time of stop
        """
        self._stop_requested = True
        self.current_state = OrchestratorState.STOPPED
        return self.get_state()

    def _calculate_progress( self ) -> int:
        """
        Calculate approximate progress percentage.

        Returns:
            int: Progress 0-100
        """
        progress_map = {
            OrchestratorState.INITIALIZING         : 5,
            OrchestratorState.DECOMPOSING          : 15,
            OrchestratorState.DELEGATING            : 30,
            OrchestratorState.CODING                : 50,
            OrchestratorState.TESTING               : 70,
            OrchestratorState.REVIEWING             : 85,
            OrchestratorState.DEBUGGING             : 75,
            OrchestratorState.WAITING_CONFIRMATION : 40,
            OrchestratorState.WAITING_DECISION     : 40,
            OrchestratorState.WAITING_FEEDBACK     : 40,
            OrchestratorState.COMPLETED             : 100,
            OrchestratorState.FAILED                : 100,
            OrchestratorState.PAUSED                : 50,
            OrchestratorState.STOPPED               : 100,
        }
        return progress_map.get( self.current_state, 0 )


def quick_smoke_test():
    """Quick smoke test for orchestrator module."""
    import cosa.utils.util as cu

    cu.print_banner( "SWE Team Orchestrator Smoke Test", prepend_nl=True )

    try:
        # Test 1: Orchestrator creation
        print( "Testing orchestrator creation..." )
        config = SweTeamConfig( dry_run=True )
        orch = SweTeamOrchestrator(
            task_description = "Implement a health check endpoint",
            config           = config,
            debug            = False,
        )
        assert orch.task_description == "Implement a health check endpoint"
        assert orch.current_state == OrchestratorState.INITIALIZING
        assert orch.session_id.startswith( "st-" )
        print( f"✓ Orchestrator created: {orch.session_id}" )

        # Test 2: get_state
        print( "Testing get_state..." )
        state = orch.get_state()
        assert state[ "orchestrator_state" ] == "initializing"
        assert state[ "dry_run" ] is True
        assert "guard_status" in state
        print( "✓ get_state returns valid dict" )

        # Test 3: Progress calculation
        print( "Testing progress calculation..." )
        assert orch._calculate_progress() == 5  # INITIALIZING
        orch.current_state = OrchestratorState.COMPLETED
        assert orch._calculate_progress() == 100
        orch.current_state = OrchestratorState.INITIALIZING
        print( "✓ Progress calculation works" )

        # Test 4: Dry-run execution
        print( "Testing dry-run execution..." )
        result = asyncio.run( orch.run() )
        assert result is not None
        assert "Dry-run complete" in result
        assert orch.current_state == OrchestratorState.COMPLETED
        print( f"✓ Dry-run completed: {result[ :60 ]}" )

        # Test 5: Stop request
        print( "Testing stop request..." )
        orch2 = SweTeamOrchestrator(
            task_description = "Another task",
            config           = SweTeamConfig( dry_run=True ),
        )
        stop_state = asyncio.run( orch2.stop() )
        assert orch2._stop_requested is True
        assert stop_state[ "orchestrator_state" ] == "stopped"
        print( "✓ Stop request works" )

        print( "\n✓ Orchestrator smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
