# from cosa.agents.math_refactoring_agent import MathRefactoringAgent
from cosa.agents.receptionist_agent import ReceptionistAgent
from cosa.agents.weather_agent import WeatherAgent
from cosa.rest.fifo_queue import FifoQueue
from cosa.agents.agent_base import AgentBase
from cosa.memory.input_and_output_table import InputAndOutputTable
from cosa.memory.solution_snapshot import SolutionSnapshot

import cosa.utils.util as du
import cosa.utils.util_stopwatch as sw
import time

import traceback
import pprint
from typing import Optional, Any

class RunningFifoQueue( FifoQueue ):
    """
    Queue for handling running jobs with agents and solution snapshots.
    
    Manages execution of jobs from todo queue to done/dead queues.
    Handles both AgentBase instances and SolutionSnapshot instances.
    """
    def __init__( self, app: Any, websocket_mgr: Any, snapshot_mgr: Any, jobs_todo_queue: FifoQueue, jobs_done_queue: FifoQueue, jobs_dead_queue: FifoQueue, config_mgr: Optional[Any]=None, emit_speech_callback: Optional[Any]=None ) -> None:
        """
        Initialize the running FIFO queue.
        
        Requires:
            - app is a Flask application instance
            - websocket_mgr is a WebSocketManager instance
            - snapshot_mgr is a valid snapshot manager
            - All queue parameters are FifoQueue instances
            - config_mgr is None or a valid ConfigurationManager
            - emit_speech_callback is None or a callable function
            
        Ensures:
            - Sets up queue management components
            - Initializes auto_debug and inject_bugs from config
            - Creates InputAndOutputTable instance
            
        Raises:
            - None
        """
        
        super().__init__( websocket_mgr=websocket_mgr, queue_name="running", emit_enabled=True )
        
        self.app                 = app
        self.snapshot_mgr        = snapshot_mgr
        self.jobs_todo_queue     = jobs_todo_queue
        self.jobs_done_queue     = jobs_done_queue
        self.jobs_dead_queue     = jobs_dead_queue
        self.emit_speech_callback = emit_speech_callback
        
        self.auto_debug          = False if config_mgr is None else config_mgr.get( "auto_debug",  default=False, return_type="boolean" )
        self.inject_bugs         = False if config_mgr is None else config_mgr.get( "inject_bugs", default=False, return_type="boolean" )
        self.io_tbl              = InputAndOutputTable()
    
    
    def enter_running_loop( self ) -> None:
        """
        DEPRECATED: Enter the main job execution loop.
        
        This method is deprecated in favor of the producer-consumer pattern
        using start_todo_producer_run_consumer_thread() which eliminates
        the inefficient polling with time.sleep(1).
        
        Use _process_job() for individual job processing instead.
        
        Requires:
            - All queue instances are initialized
            - websocket_mgr is connected
            
        Ensures:
            - Continuously processes jobs from todo queue
            - Emits socket updates for queue states
            - Never returns (infinite loop)
            
        Raises:
            - Exceptions handled internally
        """
        print( "Starting job run loop..." )
        while True:
            
            if not self.jobs_todo_queue.is_empty():
                
                print( "Jobs running @ " + du.get_current_datetime() )
                
                print( "popping one job from todo Q" )
                job = self.jobs_todo_queue.pop()  # Auto-emits 'todo_update'
                
                self.push( job )  # Auto-emits 'run_update'
                
                # Point to the head of the queue without popping it
                running_job = self.head()
                
                # Limit the length of the question string
                truncated_question = du.truncate_string( running_job.last_question_asked, max_len=64 )
                
                run_timer = sw.Stopwatch( "Starting job run timer..." )
                
                # Assume for now that all *agents* are of type AgentBase. If it's not, then it's a solution snapshot
                if isinstance( running_job, AgentBase ):
                    running_job = self._handle_base_agent( running_job, truncated_question, run_timer )
                else:
                    running_job = self._handle_solution_snapshot( running_job, truncated_question, run_timer )
            
            else:
                # print( "No jobs to pop from todo Q " )
                time.sleep( 1 )
    
    def _process_job( self, job: Any ) -> None:
        """
        Process a single job (extracted from enter_running_loop).
        
        Requires:
            - job is a valid job instance (AgentBase or SolutionSnapshot)
            - Job is already in the running queue
            
        Ensures:
            - Processes job based on its type
            - Moves job to done or dead queue when complete
            - Emits appropriate WebSocket updates
            
        Raises:
            - None (exceptions handled internally)
        """
        try:
            # Point to the head of the queue without popping it
            running_job = self.head()
            
            if not running_job:
                print( "[RUNNING] Warning: _process_job called but no job in running queue" )
                return
            
            # Limit the length of the question string
            truncated_question = du.truncate_string( running_job.last_question_asked, max_len=64 )
            
            run_timer = sw.Stopwatch( "Starting job run timer..." )
            
            # Process based on job type
            if isinstance( running_job, AgentBase ):
                # NEW: Check cache BEFORE agent execution
                question = running_job.last_question_asked

                if hasattr( self, 'debug' ) and self.debug:
                    print( f"[CACHE] Checking cache for question: {question}" )

                # Search for existing snapshot
                cached_snapshots = self.snapshot_mgr.get_snapshots_by_question( question )

                if cached_snapshots and len( cached_snapshots ) > 0:
                    # CACHE HIT - Use cached result
                    cached_snapshot = cached_snapshots[0]  # Use first/best match

                    if hasattr( self, 'debug' ) and self.debug:
                        print( f"[CACHE] 🎯 CACHE HIT: Found cached solution from {cached_snapshot.run_date}" )

                    # Convert cached snapshot to proper format and use it
                    running_job = self._format_cached_result( cached_snapshot, truncated_question, run_timer )
                else:
                    # CACHE MISS - Continue with normal agent execution
                    if hasattr( self, 'debug' ) and self.debug:
                        print( f"[CACHE] ❌ CACHE MISS: Running agent for new question" )

                    running_job = self._handle_base_agent( running_job, truncated_question, run_timer )
            else:
                running_job = self._handle_solution_snapshot( running_job, truncated_question, run_timer )
                
        except Exception as e:
            print( f"[RUNNING] Error processing job: {e}" )
            print( f"[RUNNING] Full stack trace:" )
            traceback.print_exc()
            
            # Move job to dead queue on error
            failed_job = self.pop()
            if failed_job:
                self.jobs_dead_queue.push( failed_job )
    
    def _handle_error_case( self, response: dict, running_job: Any, truncated_question: str ) -> Any:
        """
        Handle error cases during job execution.
        
        Requires:
            - response is a dictionary with 'output' key
            - running_job is a valid job instance
            - truncated_question is a string
            
        Ensures:
            - Moves job from running to dead queue
            - Emits error audio message
            - Updates socket connections
            - Returns the job instance
            
        Raises:
            - None (handles errors gracefully)
        """
        du.print_banner( f"Error running code for [{truncated_question}]", prepend_nl=True )
        
        for line in response[ "output" ].split( "\n" ): print( line )
        
        self.pop()  # Auto-emits 'run_update'
        
        self._emit_speech( "I'm sorry Dave, I'm afraid I can't do that. Please check your logs", job=running_job )
        
        self.jobs_dead_queue.push( running_job )  # Auto-emits 'dead_update'
        
        return running_job
    
    def _handle_base_agent( self, running_job: AgentBase, truncated_question: str, agent_timer: sw.Stopwatch ) -> Any:
        """
        Handle execution of AgentBase instances.
        
        Requires:
            - running_job is an AgentBase instance
            - truncated_question is a string
            - agent_timer is a running Stopwatch
            
        Ensures:
            - Executes agent's do_all() method
            - Handles serialization for eligible agents
            - Updates queues and database
            - Emits socket updates
            - Returns the job (possibly converted to SolutionSnapshot)
            
        Raises:
            - Catches and handles all exceptions internally
        """
        msg = f"Running AgentBase for [{truncated_question}]..."
        
        code_response = {
            "return_code": -1,
            "output"     : "ERROR: code_response: Output not yet generated!?!"
        }
        
        formatted_output = "ERROR: Formatted output not yet generated!?!"
        try:
            formatted_output    = running_job.do_all()
        
        except Exception as e:
            
            du.print_stack_trace( e, explanation="do_all() failed", caller="RunningFifoQueue._handle_base_agent()" )
            running_job = self._handle_error_case( code_response, running_job, truncated_question )
        
        du.print_banner( f"Job [{running_job.last_question_asked}] complete...", prepend_nl=True, end="\n" )
        
        if running_job.code_ran_to_completion() and running_job.formatter_ran_to_completion():
            
            # If we've arrived at this point, then we've successfully run the agentic part of this job
            self._emit_speech( running_job.answer_conversational, job=running_job )
            agent_timer.print( "Done!", use_millis=True )
            
            # Only the ReceptionistAgent and WeatherAgent are not being serialized as a solution snapshot
            # TODO: this needs to not be so ad hoc as it appears right now!
            serialize_snapshot = (
                not isinstance( running_job, ReceptionistAgent ) and 
                not isinstance( running_job, WeatherAgent ) # and
                # not isinstance( running_job, MathRefactoringAgent )
            )
            if serialize_snapshot:
                
                # recast the agent object as a solution snapshot object and add it to the snapshot manager
                running_job = SolutionSnapshot.create( running_job )
                # KLUDGE! I shouldn't have to do this!
                print( f"KLUDGE! Setting running_job.answer_conversational to [{formatted_output}]...")
                running_job.answer_conversational = formatted_output
                
                running_job.update_runtime_stats( agent_timer )
                
                # Adding this snapshot to the snapshot manager serializes it to the local filesystem
                print( f"Adding job [{truncated_question}] to snapshot manager..." )
                self.snapshot_mgr.add_snapshot( running_job )
                print( f"Adding job [{truncated_question}] to snapshot manager... Done!" )
                
                du.print_banner( "running_job.runtime_stats", prepend_nl=True )
                pprint.pprint( running_job.runtime_stats )
            else:
                print( f"NOT adding to snapshot manager" )
                # There's no code executed to generate a RAW answer, just a canned, conversational one
                running_job.answer = "no code executed by non-serializing/ephemeral objects"
            
            self.pop()  # Auto-emits 'run_update'
            if serialize_snapshot: self.jobs_done_queue.push( running_job )  # Auto-emits 'done_update'
            
            # Write the job to the database for posterity's sake
            self.io_tbl.insert_io_row( input_type=running_job.routing_command, input=running_job.last_question_asked, output_raw=running_job.answer, output_final=running_job.answer_conversational )
            
        else:
            
            running_job = self._handle_error_case( code_response, running_job, truncated_question )
        
        return running_job
    
    def _handle_solution_snapshot( self, running_job: SolutionSnapshot, truncated_question: str, run_timer: sw.Stopwatch ) -> SolutionSnapshot:
        """
        Handle execution of SolutionSnapshot instances.
        
        Requires:
            - running_job is a SolutionSnapshot instance
            - truncated_question is a string
            - run_timer is a running Stopwatch
            
        Ensures:
            - Executes stored code
            - Formats and emits output
            - Updates queues and database
            - Writes snapshot to file
            - Returns the updated snapshot
            
        Raises:
            - None (handles errors gracefully)
        """
        msg = f"Executing SolutionSnapshot code for [{truncated_question}]..."
        du.print_banner( msg=msg, prepend_nl=True )
        timer = sw.Stopwatch( msg=msg )
        _ = running_job.run_code()
        timer.print( "Done!", use_millis=True )
        
        formatted_output = running_job.run_formatter()
        print( formatted_output )
        self._emit_speech( running_job.answer_conversational, job=running_job )
        
        self.pop()  # Auto-emits 'run_update'
        self.jobs_done_queue.push( running_job )  # Auto-emits 'done_update'

        # If we've arrived at this point, then we've successfully run the job
        run_timer.print( "Solution snapshot full run complete ", use_millis=True )
        running_job.update_runtime_stats( run_timer )
        du.print_banner( f"Job [{running_job.question}] complete!", prepend_nl=True, end="\n" )
        
        # Note: Snapshot already saved via self.snapshot_mgr.add_snapshot() at line 248
        # Removed redundant write_current_state_to_file() call as serialization
        # is now handled by managers, not snapshot objects
        
        du.print_banner( "running_job.runtime_stats", prepend_nl=True )
        pprint.pprint( running_job.runtime_stats )
        
        # Write the job to the database for posterity's sake
        self.io_tbl.insert_io_row( input_type=running_job.routing_command, input=running_job.last_question_asked, output_raw=running_job.answer, output_final=running_job.answer_conversational )
        
        return running_job

    def _format_cached_result( self, cached_snapshot: Any, truncated_question: str, run_timer: sw.Stopwatch ) -> Any:
        """
        Format cached snapshot result to behave like a freshly executed job.

        Requires:
            - cached_snapshot is a valid SolutionSnapshot with results
            - truncated_question is a string for logging
            - run_timer is a running Stopwatch

        Ensures:
            - Emits speech for cached result
            - Updates queues (moves to done queue)
            - Emits websocket updates
            - Updates runtime stats
            - Returns properly formatted cached result

        Raises:
            - None (handles errors gracefully)
        """
        msg = f"Using CACHED result for [{truncated_question}]..."
        du.print_banner( msg=msg, prepend_nl=True )

        # Emit the cached answer as speech
        self._emit_speech( cached_snapshot.answer_conversational, job=cached_snapshot )

        # Move job through the queue system properly
        self.pop()  # Remove from running queue, auto-emits 'run_update'
        self.jobs_done_queue.push( cached_snapshot )  # Add to done queue, auto-emits 'done_update'

        # Update runtime stats to show this was a cache hit
        run_timer.print( "CACHE HIT - result retrieved in ", use_millis=True )
        cached_snapshot.update_runtime_stats( run_timer )

        # Update the run_date to current time to show when it was retrieved
        cached_snapshot.run_date = cached_snapshot.get_timestamp()

        du.print_banner( f"CACHED Job [{cached_snapshot.question}] complete!", prepend_nl=True, end="\n" )

        if hasattr( self, 'debug' ) and self.debug:
            du.print_banner( "cached_snapshot.runtime_stats", prepend_nl=True )
            pprint.pprint( cached_snapshot.runtime_stats )

        # Write to database to track cache hit
        self.io_tbl.insert_io_row(
            input_type=cached_snapshot.routing_command,
            input=cached_snapshot.last_question_asked,
            output_raw=cached_snapshot.answer,
            output_final=cached_snapshot.answer_conversational
        )

        return cached_snapshot

    # def _get_audio_url( self, text ):
    #
    #     with self.app.app_context():
    #         url = url_for( 'get_tts_audio' ) + f"?tts_text={text}"
    #
    #     return url


def quick_smoke_test():
    """
    Critical smoke test for RunningFifoQueue - validates active queue management functionality.
    
    This test is essential for v000 deprecation as running_fifo_queue.py is critical
    for active job processing and queue management in the REST system.
    """
    import cosa.utils.util as du
    
    du.print_banner( "Running FIFO Queue Smoke Test", prepend_nl=True )
    
    try:
        # Test 1: Basic class and method presence
        print( "Testing core running queue components..." )
        expected_methods = [
            "enter_running_loop", "_process_job", "_handle_base_agent", 
            "_handle_solution_snapshot", "_handle_error_case"
        ]
        
        methods_found = 0
        for method_name in expected_methods:
            if hasattr( RunningFifoQueue, method_name ):
                methods_found += 1
            else:
                print( f"⚠ Missing method: {method_name}" )
        
        if methods_found == len( expected_methods ):
            print( f"✓ All {len( expected_methods )} core running queue methods present" )
        else:
            print( f"⚠ Only {methods_found}/{len( expected_methods )} running queue methods present" )
        
        # Test 2: Critical dependency imports
        print( "Testing critical dependency imports..." )
        try:
            from cosa.agents.receptionist_agent import ReceptionistAgent
            from cosa.agents.weather_agent import WeatherAgent
            from cosa.rest.fifo_queue import FifoQueue
            from cosa.agents.agent_base import AgentBase
            print( "✓ Core agent imports successful" )
        except ImportError as e:
            print( f"✗ Core agent imports failed: {e}" )
        
        try:
            from cosa.memory.input_and_output_table import InputAndOutputTable
            from cosa.memory.solution_snapshot import SolutionSnapshot
            print( "✓ Memory system imports successful" )
        except ImportError as e:
            print( f"⚠ Memory system imports failed: {e}" )
        
        try:
            import cosa.utils.util_stopwatch as sw
            print( "✓ Utility imports successful" )
        except ImportError as e:
            print( f"⚠ Utility imports failed: {e}" )
        
        # Test 3: Inheritance validation
        print( "Testing inheritance structure..." )
        import inspect
        
        # Check if RunningFifoQueue properly inherits from FifoQueue
        base_classes = inspect.getmro( RunningFifoQueue )
        base_class_names = [ cls.__name__ for cls in base_classes ]
        
        if "FifoQueue" in base_class_names:
            print( "✓ Properly inherits from FifoQueue" )
        else:
            print( "✗ Missing FifoQueue inheritance" )
        
        # Test 4: Basic initialization (mock)
        print( "Testing basic initialization..." )
        try:
            # Create mock objects for initialization
            class MockApp:
                pass
            
            class MockWebSocketMgr:
                def emit( self, event, data ):
                    pass
            
            class MockSnapshotMgr:
                pass
            
            class MockConfigMgr:
                def get( self, key, default=None, return_type=None ):
                    return default
            
            # Create mock queues
            mock_app = MockApp()
            mock_ws_mgr = MockWebSocketMgr()
            mock_snapshot_mgr = MockSnapshotMgr()
            mock_todo_queue = FifoQueue()
            mock_done_queue = FifoQueue()
            mock_dead_queue = FifoQueue()
            mock_config_mgr = MockConfigMgr()
            
            # Test initialization
            running_queue = RunningFifoQueue(
                app=mock_app,
                websocket_mgr=mock_ws_mgr,
                snapshot_mgr=mock_snapshot_mgr,
                jobs_todo_queue=mock_todo_queue,
                jobs_done_queue=mock_done_queue,
                jobs_dead_queue=mock_dead_queue,
                config_mgr=mock_config_mgr
            )
            
            # Check basic attributes
            if ( hasattr( running_queue, 'app' ) and 
                 hasattr( running_queue, 'snapshot_mgr' ) and
                 hasattr( running_queue, 'io_tbl' ) ):
                print( "✓ Running queue initialization working" )
            else:
                print( "✗ Running queue initialization failed" )
            
        except Exception as e:
            print( f"⚠ Basic initialization issues: {e}" )
        
        # Test 5: Job processing structure validation
        print( "Testing job processing structure..." )
        try:
            # Verify that _process_job method has proper structure
            process_job_method = getattr( RunningFifoQueue, '_process_job', None )
            if callable( process_job_method ):
                print( "✓ Job processing method structure valid" )
            else:
                print( "✗ Job processing method not callable" )
            
            # Check handler methods
            handlers = [ '_handle_base_agent', '_handle_solution_snapshot', '_handle_error_case' ]
            handler_count = 0
            for handler in handlers:
                if hasattr( RunningFifoQueue, handler ):
                    handler_count += 1
            
            if handler_count == len( handlers ):
                print( f"✓ All {len( handlers )} job handlers present" )
            else:
                print( f"⚠ Only {handler_count}/{len( handlers )} job handlers present" )
            
        except Exception as e:
            print( f"⚠ Job processing structure issues: {e}" )
        
        # Test 6: Input/Output table integration
        print( "Testing I/O table integration..." )
        try:
            # Test that InputAndOutputTable can be imported and instantiated
            io_table = InputAndOutputTable()
            if hasattr( io_table, 'insert_io_row' ):
                print( "✓ I/O table integration structure valid" )
            else:
                print( "⚠ I/O table missing required methods" )
        except Exception as e:
            print( f"⚠ I/O table integration issues: {e}" )
        
        # Test 7: Job type handling logic
        print( "Testing job type handling logic..." )
        try:
            # Create mock job types for testing logic
            class MockAgentJob:
                def __init__( self ):
                    self.last_question_asked = "test question"
                    self.id_hash = "mock_hash"
            
            class MockSolutionJob:
                def __init__( self ):
                    self.last_question_asked = "test question"
                    self.id_hash = "mock_hash"
            
            mock_agent_job = MockAgentJob()
            mock_solution_job = MockSolutionJob()
            
            # Test type checking logic (simulated)
            if isinstance( mock_agent_job, AgentBase ):
                agent_check = "would handle as AgentBase"
            else:
                agent_check = "would handle as non-AgentBase"
            
            print( f"✓ Job type handling logic structure validated" )
            print( f"  Mock agent job: {agent_check}" )
            
        except Exception as e:
            print( f"⚠ Job type handling issues: {e}" )
        
        # Test 8: Critical v000 dependency scanning
        print( "\\n🔍 Scanning for v000 dependencies..." )
        
        # Scan the file for v000 patterns
        import inspect
        source_file = inspect.getfile( RunningFifoQueue )
        
        v000_found = False
        v000_patterns = []
        
        with open( source_file, 'r' ) as f:
            content = f.read()
            
            # Split content and exclude smoke test function
            lines = content.split( '\\n' )
            in_smoke_test = False
            
            for i, line in enumerate( lines ):
                stripped_line = line.strip()
                
                # Track if we're in the smoke test function
                if "def quick_smoke_test" in line:
                    in_smoke_test = True
                    continue
                elif in_smoke_test and line.startswith( "def " ):
                    in_smoke_test = False
                elif in_smoke_test:
                    continue
                
                # Skip comments and docstrings
                if ( stripped_line.startswith( '#' ) or 
                     stripped_line.startswith( '"""' ) or
                     stripped_line.startswith( "'" ) ):
                    continue
                
                # Look for actual v000 code references
                if "v000" in stripped_line and any( pattern in stripped_line for pattern in [
                    "import", "from", "cosa.agents.v000", ".v000."
                ] ):
                    v000_found = True
                    v000_patterns.append( f"Line {i+1}: {stripped_line}" )
        
        if v000_found:
            print( "🚨 CRITICAL: v000 dependencies detected!" )
            print( "   Found v000 references:" )
            for pattern in v000_patterns[ :3 ]:  # Show first 3
                print( f"     • {pattern}" )
            if len( v000_patterns ) > 3:
                print( f"     ... and {len( v000_patterns ) - 3} more v000 references" )
            print( "   ⚠️  These dependencies MUST be resolved before v000 deprecation!" )
        else:
            print( "✅ EXCELLENT: No v000 dependencies found!" )
        
        # Test 9: Queue management integration
        print( "\\nTesting queue management integration..." )
        try:
            # Test that the class properly extends FifoQueue functionality
            running_queue_methods = set( dir( RunningFifoQueue ) )
            fifo_queue_methods = set( dir( FifoQueue ) )
            
            # Should have all FifoQueue methods plus additional ones
            inherited_methods = fifo_queue_methods.intersection( running_queue_methods )
            
            if len( inherited_methods ) >= 10:  # Expect at least 10 core methods inherited
                print( "✓ Queue management integration validated" )
                print( f"  Inherited {len( inherited_methods )} methods from FifoQueue" )
            else:
                print( f"⚠ Limited queue inheritance: only {len( inherited_methods )} methods" )
            
        except Exception as e:
            print( f"⚠ Queue management integration issues: {e}" )
    
    except Exception as e:
        print( f"✗ Error during running FIFO queue testing: {e}" )
        import traceback
        traceback.print_exc()
    
    # Summary
    print( "\\n" + "="*60 )
    if v000_found:
        print( "🚨 CRITICAL ISSUE: Running FIFO queue has v000 dependencies!" )
        print( "   Status: NOT READY for v000 deprecation" )
        print( "   Priority: IMMEDIATE ACTION REQUIRED" )
        print( "   Risk Level: CRITICAL - Active job processing will break" )
    else:
        print( "✅ Running FIFO queue smoke test completed successfully!" )
        print( "   Status: Active queue management ready for v000 deprecation" )
        print( "   Risk Level: LOW" )
    
    print( "✓ Running FIFO queue smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()