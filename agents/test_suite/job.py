"""
Test Suite background job for queue-based execution.

Runs integration and/or E2E test suites as scheduled AgenticJobs within
the CJ Flow queue system. Delegates to existing shell scripts via
subprocess.Popen for cancellation support.

Example:
    job = TestSuiteJob(
        test_types = [ "integration", "e2e" ],
        user_id    = "user123",
        user_email = "user@example.com",
        session_id = "wise-penguin",
        dry_run    = True
    )
    result = job.do_all()  # Runs test suites and returns summary
"""

import asyncio
import os
import re
import subprocess
import time
from datetime import datetime
from typing import Optional, List, Dict

from cosa.agents.agentic_job_base import AgenticJobBase
from cosa.rest.job_state import JobState
import cosa.utils.util as cu


# Valid suite types and their script paths (relative to project root)
SUITE_SCRIPTS = {
    "unit"         : "src/tests/run-unit-tests.sh",
    "smoke"        : "src/tests/run-smoke-tests.sh",
    "smoke_direct" : "src/tests/run-smoke-direct.sh",
    "websocket"    : "src/scripts/run-websocket-smoke-tests.sh",
    "integration"  : "src/tests/run-integration-tests.sh",
    "e2e"          : "src/scripts/run-e2e-ui-tests.sh",
    "all"          : "src/tests/run-all-tests.sh",
}

# Per-suite max execution timeout (seconds). Process is killed if exceeded.
# Values based on observed worst-case runtimes + 2x buffer. Tunable.
SUITE_TIMEOUTS_SECONDS = {
    "unit"         : 180,    #  3 min (fast, ~915 tests, no server)
    "smoke"        : 600,    # 10 min (server-dependent, ~40 files)
    "smoke_direct" : 1200,   # 20 min (longest: Phase D live ~10 min)
    "websocket"    : 300,    #  5 min (~50 tests, server + WS)
    "integration"  : 1200,   # 20 min (~43 tests, ~5-10 min observed)
    "e2e"          : 2400,   # 40 min (~297 tests, ~17 min observed)
    "all"          : 3600,   # 60 min (sequential pyramid, ~25-35 min observed)
}
SUITE_TIMEOUT_DEFAULT_SECONDS = 600  # 10 min fallback for unknown types

# Regex to parse pytest summary line:
#   "X passed, Y failed, Z skipped, W error in Ns"
# Each component is optional (pytest omits zero-count items)
_PYTEST_SUMMARY_RE = re.compile(
    r"=+\s+"
    r"(?:(\d+)\s+passed)?"
    r"(?:,?\s*(\d+)\s+failed)?"
    r"(?:,?\s*(\d+)\s+skipped)?"
    r"(?:,?\s*(\d+)\s+warnings?)?"
    r"(?:,?\s*(\d+)\s+errors?)?"
    r"(?:,?\s*(\d+)\s+deselected)?"
    r"\s+in\s+[\d.]+s"
    r"\s*=+"
)


class TestSuiteJob( AgenticJobBase ):
    """
    Background job for running test suites in CJ Flow.

    Wraps existing shell scripts (run-integration-tests.sh, run-e2e-ui-tests.sh)
    for execution within the COSA queue system. Supports scheduling, monopolize
    mode, cancellation, and voice notifications.

    Always runs with monopolize=True since test scripts hot-swap the database
    config, which is an exclusive operation.

    Attributes:
        test_types: List of suite types to run (e.g., ["integration", "e2e"])
        pytest_args: Optional extra pytest arguments
        dry_run: Simulate execution without running tests
        suite_results: Dict of per-suite results (populated after execution)
    """

    JOB_TYPE   = "test_suite"
    JOB_PREFIX = "ts"

    def __init__(
        self,
        test_types: List[ str ],
        user_id: str,
        user_email: str,
        session_id: str,
        pytest_args: Optional[ List[ str ] ] = None,
        dry_run: bool = False,
        debug: bool = False,
        verbose: bool = False
    ) -> None:
        """
        Initialize a Test Suite job.

        Requires:
            - test_types is a non-empty list of valid suite names ("integration", "e2e")
            - user_id is a valid system ID
            - user_email is a valid email address
            - session_id is a WebSocket session ID

        Ensures:
            - Job ID generated with "ts-" prefix
            - monopolize=True (DB hot-swap is exclusive)
            - All parameters stored for execution

        Args:
            test_types: List of test suite types to run
            user_id: System ID of the job owner
            user_email: Email address of the user
            session_id: WebSocket session for notifications
            pytest_args: Optional extra pytest arguments (e.g., ["-v", "-k", "test_auth"])
            dry_run: Simulate execution without running tests
            debug: Enable debug output
            verbose: Enable verbose output
        """
        super().__init__(
            user_id    = user_id,
            user_email = user_email,
            session_id = session_id,
            monopolize = True,
            debug      = debug,
            verbose    = verbose
        )

        # Test parameters
        self.test_types   = test_types or [ "integration", "e2e" ]
        self.pytest_args  = pytest_args or []
        self.dry_run      = dry_run

        # Results (populated after execution)
        self.suite_results = {}
        self.cost_summary  = None  # Required by queues.py for unified job interface

    @classmethod
    def from_config( cls, config_mgr, user_id, user_email, session_id, debug=False ):
        """
        Create TestSuiteJob with defaults from configuration.

        Requires:
            - config_mgr is a valid ConfigurationManager instance
            - user_id, user_email, session_id are non-empty strings

        Ensures:
            - Returns TestSuiteJob with config-derived defaults

        Args:
            config_mgr: ConfigurationManager instance
            user_id: System ID of the job owner
            user_email: Email address of the user
            session_id: WebSocket session for notifications
            debug: Enable debug output

        Returns:
            TestSuiteJob: Configured job instance
        """
        default_types = config_mgr.get( "test suite default types", default="integration,e2e" )
        test_types    = [ t.strip() for t in default_types.split( "," ) ]

        default_args  = config_mgr.get( "test suite default pytest args", default="" )
        pytest_args   = [ a.strip() for a in default_args.split() if a.strip() ] if default_args else []

        return cls(
            test_types  = test_types,
            user_id     = user_id,
            user_email  = user_email,
            session_id  = session_id,
            pytest_args = pytest_args,
            debug       = debug
        )

    @property
    def last_question_asked( self ) -> str:
        """
        Display string for queue UI.

        Returns:
            str: Human-readable job description (e.g., "[Tests] integration, e2e")
        """
        suites = ", ".join( self.test_types )
        return f"[Tests] {suites}"

    def do_all( self ) -> str:
        """
        Execute test suites and return conversational answer.

        This is the main entry point called by RunningFifoQueue.
        Bridges to the async _execute() method via asyncio.run().

        Returns:
            str: Conversational answer summarizing test results
        """
        if self.debug: print( f"[TestSuiteJob] Starting do_all() for: {self.test_types}" )

        self.state      = JobState.RUNNING
        self.started_at = datetime.now().isoformat()

        try:
            result = asyncio.run( self._execute() )

            # Check if cancellation was requested during execution
            if self._cancel_requested:
                self.state                 = JobState.CANCELLED
                self.completed_at          = datetime.now().isoformat()
                self.error                 = "Cancelled by user request"
                self.answer_conversational = result or "Test suite run was cancelled by the user."
                if self.debug: print( "[TestSuiteJob] Cancelled by user request" )
                return self.answer_conversational

            self.state        = JobState.COMPLETED
            self.completed_at = datetime.now().isoformat()
            self.result       = result
            self.answer_conversational = result

            if self.debug:
                duration = self.get_execution_duration_seconds()
                print( f"[TestSuiteJob] Completed in {duration:.1f}s" )

            return result

        except Exception as e:
            self.state        = JobState.FAILED
            self.completed_at = datetime.now().isoformat()
            self.error        = str( e )

            if self.debug:
                print( f"[TestSuiteJob] Failed: {e}" )
                import traceback
                traceback.print_exc()

            self.answer_conversational = f"Test suite run failed: {str( e )}"
            return self.answer_conversational

    async def _execute( self ) -> str:
        """
        Internal async test suite execution.

        Runs each suite sequentially, always completing all suites regardless
        of individual failures. Reports progress via voice_io notifications.

        Returns:
            str: Conversational summary of all suite results
        """
        from cosa.agents.test_suite import voice_io, cosa_interface

        # Re-establish core voice_io binding (import-order race)
        voice_io.reconfigure()

        # Handle dry-run mode
        if self.dry_run:
            return await self._execute_dry_run( voice_io, cosa_interface )

        # Set sender_id and target_user for notifications
        cosa_interface.SENDER_ID   = cosa_interface._get_sender_id( suffix=self.base_id )
        cosa_interface.TARGET_USER = self.user_email

        # Set job_id for auto-injection into all notify() calls
        voice_io.set_job_id( self.id_hash )

        project_root = cu.get_project_root()

        if self.debug:
            print( f"[TestSuiteJob] Suites: {self.test_types}" )
            print( f"[TestSuiteJob] Pytest args: {self.pytest_args}" )
            print( f"[TestSuiteJob] Project root: {project_root}" )

        try:
            await voice_io.notify(
                f"Starting test suite run: {', '.join( self.test_types )}",
                priority="medium",
                queue_name="run"
            )

            for suite_type in self.test_types:
                if self._cancel_requested:
                    await voice_io.notify(
                        "Test suite run cancelled by user.",
                        priority="medium",
                        queue_name="run"
                    )
                    break

                await voice_io.notify(
                    f"Starting {suite_type} tests...",
                    priority="low",
                    queue_name="run"
                )

                result = self._run_suite( suite_type, project_root )
                self.suite_results[ suite_type ] = result

                # Report per-suite results
                status = "PASSED" if result[ "exit_code" ] == 0 else "FAILED"
                await voice_io.notify(
                    f"{suite_type}: {status} — {result[ 'passed' ]} passed, "
                    f"{result[ 'failed' ]} failed, {result[ 'skipped' ]} skipped",
                    priority="low",
                    queue_name="run"
                )

            # Build summary
            total_passed  = sum( r[ "passed" ] for r in self.suite_results.values() )
            total_failed  = sum( r[ "failed" ] for r in self.suite_results.values() )
            total_skipped = sum( r[ "skipped" ] for r in self.suite_results.values() )
            all_passed    = all( r[ "exit_code" ] == 0 for r in self.suite_results.values() )

            # Store artifacts + cost_summary (required by queues.py unified interface)
            self.cost_summary = {
                "suites_run"    : len( self.suite_results ),
                "total_passed"  : total_passed,
                "total_failed"  : total_failed,
                "total_skipped" : total_skipped,
                "all_passed"    : all_passed,
            }
            self.artifacts[ "suite_results" ] = self.suite_results
            self.artifacts[ "cost_summary" ]  = self.cost_summary
            for suite_type, result in self.suite_results.items():
                if result.get( "log_path" ):
                    self.artifacts[ f"{suite_type}_log" ] = result[ "log_path" ]

            # Build abstract for completion notification
            suite_lines = []
            for suite_type, result in self.suite_results.items():
                icon = "PASS" if result[ "exit_code" ] == 0 else "FAIL"
                line = ( f"- **{suite_type}**: {icon} — "
                         f"{result[ 'passed' ]} passed, {result[ 'failed' ]} failed, "
                         f"{result[ 'skipped' ]} skipped" )
                crash_output = result.get( "startup_crash_output" )
                if crash_output:
                    line += f"\n  **STARTUP CRASH** (exit={result[ 'exit_code' ]}): `{crash_output[ :200 ]}`"
                suite_lines.append( line )

            overall = "ALL PASSED" if all_passed else "FAILURES DETECTED"
            abstract = f"**Test Suite Results: {overall}**\n\n" + "\n".join( suite_lines )

            await voice_io.notify(
                f"Test suite complete: {overall}",
                priority="medium",
                abstract=abstract,
                queue_name="run"
            )

            # Conversational answer
            summary = f"Test suite run complete. {overall}.\n\n"
            for suite_type, result in self.suite_results.items():
                summary += f"  {suite_type}: {result[ 'passed' ]} passed, {result[ 'failed' ]} failed, {result[ 'skipped' ]} skipped\n"
                # Surface startup crash output when subprocess failed with no test results
                crash_output = result.get( "startup_crash_output" )
                if crash_output:
                    summary += f"\n  ⚠ {suite_type} STARTUP CRASH (exit={result[ 'exit_code' ]}, 0 tests found):\n"
                    summary += f"  {crash_output[ :500 ]}\n\n"
            summary += f"\n  Total: {total_passed} passed, {total_failed} failed, {total_skipped} skipped"

            return summary

        finally:
            voice_io.clear_job_id()

    async def _execute_dry_run( self, voice_io, cosa_interface ) -> str:
        """
        Execute dry-run mode with breadcrumb notifications.

        Simulates the test suite workflow without actually running tests.

        Requires:
            - voice_io is a configured voice I/O module
            - cosa_interface is a configured COSA interface module

        Ensures:
            - Breadcrumb notifications sent for each suite
            - Mock artifacts populated
            - Returns mock conversational summary

        Args:
            voice_io: Voice I/O module for notifications
            cosa_interface: COSA interface module for sender ID

        Returns:
            str: Mock conversational summary
        """
        # Set sender_id and target_user
        cosa_interface.SENDER_ID   = cosa_interface._get_sender_id( suffix=self.base_id )
        cosa_interface.TARGET_USER = self.user_email

        voice_io.set_job_id( self.id_hash )

        if self.debug: print( f"[TestSuiteJob] DRY RUN MODE for: {self.test_types}" )

        try:
            await voice_io.notify(
                f"Dry run: Starting test suite simulation for {', '.join( self.test_types )}",
                priority="low",
                job_id=self.id_hash,
                queue_name="run"
            )
            await asyncio.sleep( 0.5 )

            for suite_type in self.test_types:
                await voice_io.notify(
                    f"[DRY RUN] Would run {suite_type} tests",
                    priority="low",
                    job_id=self.id_hash,
                    queue_name="run"
                )
                await asyncio.sleep( 0.5 )

            # Mock results
            self.suite_results = {
                suite_type: {
                    "passed"    : 0,
                    "failed"    : 0,
                    "skipped"   : 0,
                    "errors"    : 0,
                    "exit_code" : 0,
                    "log_path"  : None,
                    "duration"  : 0.0,
                }
                for suite_type in self.test_types
            }

            self.cost_summary = {
                "mode"       : "dry_run",
                "suites"     : self.test_types,
                "suites_run" : len( self.test_types ),
            }
            self.artifacts[ "suite_results" ] = self.suite_results
            self.artifacts[ "cost_summary" ]  = self.cost_summary

            abstract = (
                f"**Dry Run Complete**\n\n"
                f"- Suites: {', '.join( self.test_types )}\n"
                f"- Pytest args: {self.pytest_args or '(none)'}\n"
                f"- monopolize: True"
            )

            await voice_io.notify(
                "Dry run complete! Test suite simulation finished.",
                priority="medium",
                abstract=abstract,
                job_id=self.id_hash,
                queue_name="run"
            )

            return f"Dry run complete. Would have run: {', '.join( self.test_types )}"

        finally:
            voice_io.clear_job_id()

    def _run_suite( self, suite_type: str, project_root: str ) -> Dict:
        """
        Run a single test suite via subprocess.

        Uses subprocess.Popen with a poll loop to support cancellation.
        Does NOT use --bg flag (the AgenticJob IS the background runner).

        Requires:
            - suite_type is "integration" or "e2e"
            - project_root is a valid directory path

        Ensures:
            - Returns dict with passed/failed/skipped/errors/exit_code/log_path/duration
            - Subprocess is terminated if cancellation requested

        Args:
            suite_type: Type of test suite ("integration" or "e2e")
            project_root: Absolute path to project root

        Returns:
            dict: Test results with keys: passed, failed, skipped, errors, exit_code, log_path, duration
        """
        script_rel = SUITE_SCRIPTS.get( suite_type )
        if not script_rel:
            return {
                "passed"    : 0,
                "failed"    : 0,
                "skipped"   : 0,
                "errors"    : 0,
                "exit_code" : 1,
                "log_path"  : None,
                "duration"  : 0.0,
                "error"     : f"Unknown suite type: {suite_type}",
            }

        script_path = os.path.join( project_root, script_rel )

        if not os.path.exists( script_path ):
            return {
                "passed"    : 0,
                "failed"    : 0,
                "skipped"   : 0,
                "errors"    : 0,
                "exit_code" : 1,
                "log_path"  : None,
                "duration"  : 0.0,
                "error"     : f"Script not found: {script_path}",
            }

        # Build command — pass through extra pytest args, never use --bg
        # Strip --bg: harmful when running as a subprocess (detaches, breaks tracking)
        sanitized_args = [ arg for arg in self.pytest_args if arg != "--bg" ]
        if len( sanitized_args ) < len( self.pytest_args ):
            print( f"[TestSuiteJob] WARNING: Stripped --bg flag from pytest_args (harmful for subprocess-tracked runs)" )
        cmd = [ "bash", script_path ] + sanitized_args

        if self.debug: print( f"[TestSuiteJob] Running: {' '.join( cmd )}" )

        start_time = time.monotonic()

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=project_root,
                text=True,
                env={ **os.environ, "LUPIN_ROOT": project_root }
            )

            # Per-suite timeout (seconds)
            timeout_secs = SUITE_TIMEOUTS_SECONDS.get( suite_type, SUITE_TIMEOUT_DEFAULT_SECONDS )
            if self.debug: print( f"[TestSuiteJob] {suite_type} timeout: {timeout_secs}s" )

            # Poll loop for cancellation support + timeout enforcement
            stdout_lines = []
            while True:
                # Check for cancellation
                if self._cancel_requested:
                    process.terminate()
                    try:
                        process.wait( timeout=10 )
                    except subprocess.TimeoutExpired:
                        process.kill()
                    duration = time.monotonic() - start_time
                    return {
                        "passed"    : 0,
                        "failed"    : 0,
                        "skipped"   : 0,
                        "errors"    : 0,
                        "exit_code" : -1,
                        "log_path"  : None,
                        "duration"  : duration,
                        "error"     : "Cancelled by user",
                    }

                # Check for timeout
                elapsed = time.monotonic() - start_time
                if elapsed > timeout_secs:
                    print( f"[TestSuiteJob] TIMEOUT: {suite_type} exceeded {timeout_secs}s, killing process" )
                    process.terminate()
                    try:
                        process.wait( timeout=10 )
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return {
                        "passed"    : 0,
                        "failed"    : 0,
                        "skipped"   : 0,
                        "errors"    : 1,
                        "exit_code" : -2,
                        "log_path"  : None,
                        "duration"  : elapsed,
                        "error"     : f"Timeout: {suite_type} exceeded {timeout_secs}s",
                    }

                # Read available output
                line = process.stdout.readline()
                if line:
                    stdout_lines.append( line )
                    if self.verbose: print( line, end="" )

                # Check if process has finished
                if line == "" and process.poll() is not None:
                    break

            duration  = time.monotonic() - start_time
            exit_code = process.returncode
            stdout    = "".join( stdout_lines )

            # Determine log path from symlink
            log_symlinks = {
                "unit"         : "/tmp/unit-latest.log",
                "smoke"        : "/tmp/smoke-latest.log",
                "smoke_direct" : "/tmp/smoke-direct-latest.log",
                "websocket"    : "/tmp/websocket-latest.log",
                "integration"  : "/tmp/integration-latest.log",
                "e2e"          : "/tmp/e2e-ui-latest.log",
                "all"          : "/tmp/all-tests-latest.log",
            }
            log_path = log_symlinks.get( suite_type )
            if log_path and not os.path.exists( log_path ):
                log_path = None

            # Parse pytest output
            parsed = self._parse_pytest_output( stdout )
            parsed[ "exit_code" ] = exit_code
            parsed[ "log_path" ]  = log_path
            parsed[ "duration" ]  = duration

            # Capture stdout tail when subprocess crashed with no test output
            total_found = parsed[ "passed" ] + parsed[ "failed" ] + parsed[ "skipped" ] + parsed[ "errors" ]
            if exit_code != 0 and total_found == 0:
                tail_lines  = stdout_lines[ -20: ] if stdout_lines else [ "(no output captured)" ]
                parsed[ "startup_crash_output" ] = "".join( tail_lines ).strip()

            if self.debug:
                print( f"[TestSuiteJob] {suite_type} finished: exit={exit_code}, "
                       f"passed={parsed[ 'passed' ]}, failed={parsed[ 'failed' ]}, "
                       f"duration={duration:.1f}s" )

            return parsed

        except Exception as e:
            duration = time.monotonic() - start_time
            return {
                "passed"    : 0,
                "failed"    : 0,
                "skipped"   : 0,
                "errors"    : 0,
                "exit_code" : 1,
                "log_path"  : None,
                "duration"  : duration,
                "error"     : str( e ),
            }

    @staticmethod
    def _parse_pytest_output( stdout: str ) -> Dict:
        """
        Parse pytest summary output for pass/fail/skip/error counts.

        Handles various pytest summary formats:
            "3 passed in 1.23s"
            "10 passed, 2 failed, 1 skipped in 5.67s"
            "5 passed, 3 failed, 1 error in 2.34s"

        Requires:
            - stdout is a string (may be empty)

        Ensures:
            - Returns dict with passed, failed, skipped, errors keys (all int)
            - Returns zeros if summary line not found

        Args:
            stdout: Full pytest console output

        Returns:
            dict: Parsed counts with keys: passed, failed, skipped, errors
        """
        result = {
            "passed"  : 0,
            "failed"  : 0,
            "skipped" : 0,
            "errors"  : 0,
        }

        match = _PYTEST_SUMMARY_RE.search( stdout )
        if match:
            if match.group( 1 ): result[ "passed" ]  = int( match.group( 1 ) )
            if match.group( 2 ): result[ "failed" ]  = int( match.group( 2 ) )
            if match.group( 3 ): result[ "skipped" ] = int( match.group( 3 ) )
            # group(4) = warnings (not tracked)
            if match.group( 5 ): result[ "errors" ]  = int( match.group( 5 ) )
            # group(6) = deselected (not tracked)

        return result


def quick_smoke_test():
    """
    Quick smoke test for TestSuiteJob.
    """
    cu.print_banner( "TestSuiteJob Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import
        print( "Testing module import..." )
        from cosa.agents.test_suite.job import TestSuiteJob
        print( "  Module imported successfully" )

        # Test 2: Instantiation
        print( "Testing job instantiation..." )
        job = TestSuiteJob(
            test_types = [ "integration", "e2e" ],
            user_id    = "user123",
            user_email = "test@test.com",
            session_id = "session456",
            debug      = True
        )
        print( f"  Job created with id: {job.id_hash}" )

        # Test 3: ID format
        print( "Testing ID format..." )
        assert job.id_hash.startswith( "ts-" ), "ID should start with ts-"
        print( f"  ID format correct: {job.id_hash}" )

        # Test 4: last_question_asked
        print( "Testing last_question_asked..." )
        lqa = job.last_question_asked
        assert "[Tests]" in lqa
        print( f"  last_question_asked: {lqa}" )

        # Test 5: monopolize
        print( "Testing monopolize flag..." )
        assert job.monopolize == True
        print( "  monopolize correctly set to True" )

        # Test 6: is_cacheable
        print( "Testing is_cacheable property..." )
        assert job.is_cacheable == False
        print( "  is_cacheable correctly returns False" )

        # Test 7: Attributes
        print( "Testing job attributes..." )
        assert job.test_types == [ "integration", "e2e" ]
        assert job.user_email == "test@test.com"
        assert job.state == JobState.PENDING
        assert job.dry_run == False
        print( "  All attributes set correctly" )

        # Test 8: Class constants
        print( "Testing class constants..." )
        assert TestSuiteJob.JOB_TYPE == "test_suite"
        assert TestSuiteJob.JOB_PREFIX == "ts"
        print( "  Class constants correct" )

        # Test 9: Parse pytest output
        print( "Testing _parse_pytest_output..." )
        parsed = TestSuiteJob._parse_pytest_output(
            "======== 195 passed, 3 failed, 32 skipped in 350.12s ========"
        )
        assert parsed[ "passed" ] == 195
        assert parsed[ "failed" ] == 3
        assert parsed[ "skipped" ] == 32
        print( f"  Parsed: {parsed}" )

        print( "\n  Smoke test completed successfully" )

    except Exception as e:
        print( f"\n  Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
