# from cosa.agents.v010.math_refactoring_agent import MathRefactoringAgent
from cosa.agents.v010.receptionist_agent import ReceptionistAgent
from cosa.agents.v010.weather_agent import WeatherAgent
from cosa.app.fifo_queue import FifoQueue
from cosa.agents.v010.agent_base import AgentBase
from cosa.memory.input_and_output_table import InputAndOutputTable
from cosa.memory.solution_snapshot import SolutionSnapshot

import cosa.utils.util as du
import cosa.utils.util_stopwatch as sw

# import traceback
import pprint
from typing import Optional, Any

class RunningFifoQueue( FifoQueue ):
    """
    Queue for handling running jobs with agents and solution snapshots.
    
    Manages execution of jobs from todo queue to done/dead queues.
    Handles both AgentBase instances and SolutionSnapshot instances.
    """
    def __init__( self, app: Any, socketio: Any, snapshot_mgr: Any, jobs_todo_queue: FifoQueue, jobs_done_queue: FifoQueue, jobs_dead_queue: FifoQueue, config_mgr: Optional[Any]=None ) -> None:
        """
        Initialize the running FIFO queue.
        
        Requires:
            - app is a Flask application instance
            - socketio is a SocketIO instance
            - snapshot_mgr is a valid snapshot manager
            - All queue parameters are FifoQueue instances
            - config_mgr is None or a valid ConfigurationManager
            
        Ensures:
            - Sets up queue management components
            - Initializes auto_debug and inject_bugs from config
            - Creates InputAndOutputTable instance
            
        Raises:
            - None
        """
        
        super().__init__()
        
        self.app             = app
        self.socketio        = socketio
        self.snapshot_mgr    = snapshot_mgr
        self.jobs_todo_queue = jobs_todo_queue
        self.jobs_done_queue = jobs_done_queue
        self.jobs_dead_queue = jobs_dead_queue
        
        self.auto_debug      = False if config_mgr is None else config_mgr.get( "auto_debug",  default=False, return_type="boolean" )
        self.inject_bugs     = False if config_mgr is None else config_mgr.get( "inject_bugs", default=False, return_type="boolean" )
        self.io_tbl          = InputAndOutputTable()
    
    def enter_running_loop( self ) -> None:
        """
        Enter the main job execution loop.
        
        Requires:
            - All queue instances are initialized
            - socketio is connected
            
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
                job = self.jobs_todo_queue.pop()
                self.socketio.emit( 'todo_update', { 'value': self.jobs_todo_queue.size() } )
                
                self.push( job )
                self.socketio.emit( 'run_update', { 'value': self.size() } )
                
                # Point to the head of the queue without popping it
                running_job = self.head()
                
                # Limit the length of the question string
                truncated_question = du.truncate_string( running_job.last_question_asked, max_len=64 )
                
                run_timer = sw.Stopwatch( "Starting job run timer..." )
                
                # if type( running_job ) == FunctionMappingAgent:
                #     running_job = self._handle_function_mapping_agent( running_job, truncated_question )
                
                # Assume for now that all *agents* are of type AgentBase. If it's not, then it's a solution snapshot
                if isinstance( running_job, AgentBase ):
                    running_job = self._handle_base_agent( running_job, truncated_question, run_timer )
                else:
                    running_job = self._handle_solution_snapshot( running_job, truncated_question, run_timer )
            
            else:
                # print( "No jobs to pop from todo Q " )
                self.socketio.sleep( 1 )
    
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
        
        self.pop()
        
        from app import emit_audio
        emit_audio( "I'm sorry Dave, I'm afraid I can't do that. Please check your logs" )
        
        self.jobs_dead_queue.push( running_job )
        self.socketio.emit( 'dead_update', { 'value': self.jobs_dead_queue.size() } )
        self.socketio.emit( 'run_update', { 'value': self.size() } )
        
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
            from app import emit_audio
            emit_audio( running_job.answer_conversational )
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
            
            self.pop()
            self.socketio.emit( 'run_update', { 'value': self.size() } )
            if serialize_snapshot: self.jobs_done_queue.push( running_job )
            self.socketio.emit( 'done_update', { 'value': self.jobs_done_queue.size() } )
            
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
        
        formatted_output = running_job.format_output()
        print( formatted_output )
        from app import emit_audio
        emit_audio( running_job.answer_conversational )
        
        self.pop()
        self.jobs_done_queue.push( running_job )
        self.socketio.emit( 'run_update', { 'value': self.size() } )
        self.socketio.emit( 'done_update', { 'value': self.jobs_done_queue.size() } )

        # If we've arrived at this point, then we've successfully run the job
        run_timer.print( "Solution snapshot full run complete ", use_millis=True )
        running_job.update_runtime_stats( run_timer )
        du.print_banner( f"Job [{running_job.question}] complete!", prepend_nl=True, end="\n" )
        
        print( f"Writing job [{running_job.last_question_asked}] to file..." )
        running_job.write_current_state_to_file()
        print( f"Writing job [{running_job.last_question_asked}] to file... Done!" )
        
        du.print_banner( "running_job.runtime_stats", prepend_nl=True )
        pprint.pprint( running_job.runtime_stats )
        
        # Write the job to the database for posterity's sake
        self.io_tbl.insert_io_row( input_type=running_job.routing_command, input=running_job.last_question_asked, output_raw=running_job.answer, output_final=running_job.answer_conversational )
        
        return running_job
    
    # def _get_audio_url( self, text ):
    #
    #     with self.app.app_context():
    #         url = url_for( 'get_tts_audio' ) + f"?tts_text={text}"
    #
    #     return url