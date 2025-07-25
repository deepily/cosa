import random
import threading
from typing import Any, Optional

from cosa.agents.v010.confirmation_dialog import ConfirmationDialogue
from cosa.rest.fifo_queue import FifoQueue

from cosa.agents.v010.date_and_time_agent import DateAndTimeAgent
from cosa.agents.v010.receptionist_agent import ReceptionistAgent
from cosa.agents.v010.weather_agent import WeatherAgent
from cosa.agents.v010.todo_list_agent import TodoListAgent
from cosa.agents.v010.calendaring_agent import CalendaringAgent
from cosa.agents.v010.math_agent import MathAgent
from cosa.agents.v010.llm_client_factory import LlmClientFactory
from cosa.agents.v010.gister import Gister
from cosa.tools.search_lupin_v010 import LupinSearch

# from app       import emit_audio
from cosa.utils import util     as du
from cosa.utils import util_xml as dux


from cosa.memory.solution_snapshot import SolutionSnapshot
from cosa.rest.queue_extensions import user_job_tracker

class TodoFifoQueue( FifoQueue ):
    """
    Queue for managing todo items with agent routing capabilities.
    
    Handles question parsing, agent routing, and snapshot management for
    conversational AI tasks.
    """
    def __init__( self, websocket_mgr: Any, snapshot_mgr: Any, app: Any, config_mgr: Optional[Any]=None, emit_speech_callback: Optional[Any]=None, debug: bool=False, verbose: bool=False, silent: bool=False ) -> None:
        """
        Initialize the todo FIFO queue.
        
        Requires:
            - websocket_mgr is a valid WebSocketManager instance or None for testing
            - snapshot_mgr is a valid snapshot manager or None for testing
            - app is a Flask application instance or None for testing
            - config_mgr is None or a valid ConfigurationManager
            - emit_speech_callback is None or a callable function
            
        Ensures:
            - Sets up queue management components
            - Initializes salutations and filler phrase lists
            - Configures debug settings from config_mgr
            
        Raises:
            - None
        """
        
        super().__init__( websocket_mgr=websocket_mgr, queue_name="todo", emit_enabled=True )
        self.debug               = debug
        self.verbose             = verbose
        self.silent              = silent
        
        self.snapshot_mgr        = snapshot_mgr
        self.app                 = app
        self.push_counter        = 0
        self.config_mgr          = config_mgr
        self.emit_speech_callback = emit_speech_callback
        
        self.auto_debug   = False if config_mgr is None else config_mgr.get( "auto_debug",  default=False, return_type="boolean" )
        self.inject_bugs  = False if config_mgr is None else config_mgr.get( "inject_bugs", default=False, return_type="boolean" )
        
        # Initialize LLM client factory for v010 compatibility
        self.llm_factory = LlmClientFactory( debug=debug, verbose=verbose )
        
        # Initialize Gister for extracting question gists
        self.gister = Gister( debug=debug, verbose=verbose )
        
        # Salutations to be stripped by a brute force method until the router parses them off for us
        self.salutations = [ "computer", "little", "buddy", "pal", "ai", "jarvis", "alexa", "siri", "hal", "einstein",
            "jeeves", "alfred", "watson", "samwise", "sam", "hawkeye", "oye", "hey", "there", "you", "yo",
            "hi", "hello", "hola", "good", "morning", "afternoon", "evening", "night", "buenas", "buenos", "buen", "tardes",
            "noches", "dias", "día", "tarde", "greetings", "my", "dear", "dearest", "esteemed", "assistant", "receptionist", "friend"
        ]
        self.hemming_and_hawing = [
            "", "", "", "umm...", "hmm...", "hmm...", "well...", "ahem..."
        ]
        self.thinking = [
            "interesting...", "thinking...", "let me see...", "let me think...", "let's see...",
            "let me think about that...", "let me think about it...", "let me check...", "checking..."
        ]
        
        # Producer-consumer coordination
        self.condition = threading.Condition()
        self.consumer_running = False
        
    def parse_salutations( self, transcription: str ) -> tuple[str, str]:
        """
        Parse salutations from the beginning of a transcription.
        
        Requires:
            - transcription is a string
            - self.salutations list is initialized
            
        Ensures:
            - Returns tuple of (salutations, remaining_text)
            - Salutations are extracted based on self.salutations list
            - Punctuation is handled properly
            
        Raises:
            - None
        """
        # Normalize the transcription by removing extra spaces after punctuation
        # From: https://chat.openai.com/share/5783e1d5-c9ce-4503-9338-270a4c9095b2
        words = transcription.split()
        prefix_holder = [ ]
        
        # Find the index where salutations stop
        index = 0
        for word in words:
            if word.strip( ',.:;!?' ).lower() in self.salutations:
                prefix_holder.append( word )
                index += 1
            else:
                break
        
        # Get the remaining string after salutations
        remaining_string = ' '.join( words[ index: ] )
        
        return ' '.join( prefix_holder ), remaining_string
    
    def _is_fit( self, question: str ) -> bool:
        """
        Validate if job is suitable for processing.
        
        Requires:
            - question is a string
            
        Ensures:
            - Returns True if job meets processing criteria
            - Returns False if job should be rejected
            
        Raises:
            - None
        """
        if not question or not question.strip():
            return False
        if len( question ) > 1000:  # Example length limit
            return False
        if question.lower().startswith( "invalid" ):  # Example content filter
            return False
        return True
    
    def _notify_rejection( self, question: str, websocket_id: str, reason: str ) -> None:
        """
        Send rejection notification via WebSocket.
        
        Requires:
            - question is the rejected question
            - websocket_id is a valid websocket identifier  
            - reason is a descriptive rejection reason
            
        Ensures:
            - Sends job_rejected event to specific websocket session
            - Includes question, reason, and timestamp
            
        Raises:
            - None (handles errors gracefully)
        """
        if self.websocket_mgr:
            rejection_data = {
                "type": "job_rejected",
                "question": question,
                "reason": reason,
                "timestamp": du.get_current_time()
            }
            try:
                # Use emit_to_session if available, fallback to general emit
                if hasattr( self.websocket_mgr, 'emit_to_session_sync' ):
                    self.websocket_mgr.emit_to_session_sync( websocket_id, "job_rejected", rejection_data )
                else:
                    self.websocket_mgr.emit( "job_rejected", rejection_data )
                    
                if self.debug:
                    print( f"[TODO-QUEUE] Sent rejection notification for: {question[:50]}..." )
            except Exception as e:
                if self.debug:
                    print( f"[TODO-QUEUE] Failed to send rejection notification: {e}" )
    
    def push_job( self, question: str, websocket_id: str, user_id: str = "ricardo_felipe_ruiz_6bdc" ) -> str:
        """
        Push a new job onto the queue based on the question.
        
        Requires:
            - question is a non-empty string
            - websocket_id is a non-empty string
            - user_id is a valid system ID
            - Queue and snapshot manager are initialized
            
        Ensures:
            - Handles blocking objects for confirmation
            - Searches for similar snapshots if applicable
            - Routes to appropriate agent or snapshot
            - Returns status message
            - Associates websocket_id and user_id with the job
            - Passes user_id to agent creation for event routing
            
        Raises:
            - None (exceptions handled internally)
        """
        run_previous_best_snapshot = False
        similar_snapshots = [ ]
        
        # NEW: Pre-processing and validation
        if not self._is_fit( question ):
            reason = "Question does not meet processing criteria"
            if not question or not question.strip():
                reason = "Question cannot be empty"
            elif len( question ) > 1000:
                reason = "Question too long (max 1000 characters)"
            elif question.lower().startswith( "invalid" ):
                reason = "Question contains invalid content"
                
            self._notify_rejection( question, websocket_id, reason )
            return f"Job rejected: {reason}"
        
        # check to see if the queue isn't accepting jobs (because it's waiting for response to a previous request)
        if not self.is_accepting_jobs():
            
            msg = f"The human responded '{question}'"
            du.print_banner( msg )
            confirmation_llm_spec      = self.config_mgr.get( "llm spec key for confirmation dialog" )
            run_previous_best_snapshot = ConfirmationDialogue( confirmation_llm_spec, debug=self.debug, verbose=self.verbose ).confirmed( question )
            
        if run_previous_best_snapshot:
                
            blocking_object = self.pop_blocking_object()
            
            # unpack the blocking object, setting best score to 100 because the user has confirmed that it is an exact semantic match
            best_score          = 100.0
            best_snapshot       = blocking_object[ "best_snapshot" ]
            last_question_asked = blocking_object[ "question" ]
            
            # update last question asked before we throw it on the queue
            best_snapshot.last_question_asked = last_question_asked
            
            self._dump_code( best_snapshot )
            return self._queue_best_snapshot( best_snapshot, best_score )
                
        # if we're not running the previous best snapshot, then we need to find a similar one before queuing the job
        else:
            
            # make sure to remove a possible blocking object
            self.pop_blocking_object()
            
            salutations, question = self.parse_salutations( question )
            question_gist = self.gister.get_gist( question )
            # DEMO KLUDGE: if the question doesn't start with "refactor", then we're going to search for similar snapshots
            if not question.lower().strip().startswith( "refactor " ):
                
                # salutations, question = self.parse_salutations( question )
                # question_gist = self.get_gist( question )
                
                du.print_banner( f"push_job( '{( salutations + ' ' + question ).strip()}' )", prepend_nl=True )
                threshold_question = self.config_mgr.get( "similarity_threshold_question",      default=98.0, return_type="float" )
                threshold_gist     = self.config_mgr.get( "similarity_threshold_question_gist", default=95.0, return_type="float" )
                print( f"push_job(): Using snapshot similarity threshold of [{threshold_question}] and gist similarity threshold of [{threshold_gist}]" )
                
                # We're searching for similar snapshots without any salutations prepended to the question.
                similar_snapshots = self.snapshot_mgr.get_snapshots_by_question( question, question_gist=question_gist, threshold_question=threshold_question, threshold_gist=threshold_gist )
                print()
            else:
                print( "push_job(): Skipping snapshot search..." )
                similar_snapshots = [ ]
        
        # if we've got a set of similar snapshot candidates, then check its score before pushing it onto the queue
        if len( similar_snapshots ) > 0:
        
            best_score    = similar_snapshots[ 0 ][ 0 ]
            best_snapshot = similar_snapshots[ 0 ][ 1 ]
            
            # verify that this is what they were looking for, according to the similarity threshold for confirmation
            if best_score < self.config_mgr.get( "similarity_threshold_confirmation", default=98.0, return_type="float" ):
                
                blocking_object = {
                    "best_score": best_score,
                    "best_snapshot": best_snapshot,
                    "question": question
                }
                self.push_blocking_object( blocking_object )
                msg = f"Is that the same as: {best_snapshot.question}?"
                du.print_banner( msg )
                print( "Blocking object pushed onto queue, waiting for response..." )
                self._emit_speech( msg, websocket_id )
                return msg
            
            # This is an exact match, so queue it up
            else:
                
                # update last question asked before we throw it on the queue
                best_snapshot.last_question_asked = ( salutations + ' ' + question ).strip()
                self._dump_code( best_snapshot )
                return self._queue_best_snapshot( best_snapshot, best_score )
            
        else:
            
            print( "No similar snapshots found, calling routing LLM..." )
            
            # Note the distinction between salutation and the question: all agents except the receptionist get the question only.
            # The receptionist gets the salutation plus the question to help it decide how it will respond.
            salutation_plus_question = ( salutations + " " + question ).strip()

            # We're going to give the routing function maximum information, hence including the salutation with the question
            # ¡OJO! I know this is a tad adhoc-ish, but it's what we want... for the moment at least
            command, args = self._get_routing_command( salutation_plus_question )
            
            starting_a_new_job = "New {agent_type} job..."
            ding_for_new_job   = False
            agent              = None
            self.push_counter += 1
            
            # TODO: implement search and summarize training and routing
            if question.lower().strip().startswith( "search and summarize" ):
                
                msg = du.print_banner( f"TO DO: train and implement 'agent router go to search and summary' command {command}" )
                print( msg )
                self._emit_speech( f"{self.hemming_and_hawing[ random.randint( 0, len( self.hemming_and_hawing ) - 1 ) ]} I'm gonna ask our research librarian about that", None )
                search = LupinSearch( query=question_gist )
                search.search_and_summarize_the_web()
                msg = search.get_results( scope="summary" )
            
            elif command == "agent router go to calendar":
                calendar_llm_spec = self.config_mgr.get( "llm spec key for calendar agent" )
                calendar_client = self.llm_factory.get_client( calendar_llm_spec, debug=self.debug, verbose=self.verbose )
                agent = CalendaringAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, llm_client=calendar_client, user_id=user_id, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                msg = starting_a_new_job.format( agent_type="calendaring" )
                ding_for_new_job = True
            elif command == "agent router go to math":
                if question.lower().strip().startswith( "refactor " ):
                    # raise a not implemented exception
                    raise NotImplementedError( "Refactoring agent not implemented yet!" )
                    # agent = self._get_math_refactoring_agent( question, question_gist, salutation_plus_question, self.push_counter )
                    # msg = starting_a_new_job.format( agent_type="math refactoring" )
                else:
                    math_llm_spec = self.config_mgr.get( "llm spec key for math agent" )
                    math_client = self.llm_factory.get_client( math_llm_spec, debug=self.debug, verbose=self.verbose )
                    agent = MathAgent( question=salutation_plus_question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, llm_client=math_client, user_id=user_id, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                    msg = starting_a_new_job.format( agent_type="math" )
                ding_for_new_job = True
            elif command == "agent router go to todo list":
                todo_llm_spec = self.config_mgr.get( "llm spec key for todo list agent" )
                todo_client = self.llm_factory.get_client( todo_llm_spec, debug=self.debug, verbose=self.verbose )
                agent = TodoListAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, llm_client=todo_client, user_id=user_id, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                msg = starting_a_new_job.format( agent_type="todo list" )
                ding_for_new_job = True
            elif command == "agent router go to date and time":
                datetime_llm_spec = self.config_mgr.get( "llm spec key for date and time agent" )
                datetime_client = self.llm_factory.get_client( datetime_llm_spec, debug=self.debug, verbose=self.verbose )
                agent = DateAndTimeAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, llm_client=datetime_client, user_id=user_id, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                msg = starting_a_new_job.format( agent_type="date and time" )
                ding_for_new_job = True
            elif command == "agent router go to weather":
                weather_llm_spec = self.config_mgr.get( "llm spec key for weather agent" )
                weather_client = self.llm_factory.get_client( weather_llm_spec, debug=self.debug, verbose=self.verbose )
                agent = WeatherAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, llm_client=weather_client, user_id=user_id, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                msg = starting_a_new_job.format( agent_type="weather" )
                # ding_for_new_job = False
            elif command == "agent router go to receptionist" or command == "none":
                print( f"Routing '{command}' to receptionist..." )
                receptionist_llm_spec = self.config_mgr.get( "llm spec key for receptionist agent" )
                receptionist_client = self.llm_factory.get_client( receptionist_llm_spec, debug=self.debug, verbose=self.verbose )
                agent = ReceptionistAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, llm_client=receptionist_client, user_id=user_id, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                # Randomly grab hemming and hawing string and prepend it to a randomly chosen thinking string
                msg = f"{self.hemming_and_hawing[ random.randint( 0, len( self.hemming_and_hawing ) - 1 ) ]} {self.thinking[ random.randint( 0, len( self.thinking ) - 1 ) ]}".strip()
                # ding_for_new_job = False
            else:
                msg = du.print_banner( f"TO DO: Implement else case command {command}" )
                print( msg )
                if self.emit_speech_callback:
                    self.emit_speech_callback( f"{self.hemming_and_hawing[ random.randint( 0, len( self.hemming_and_hawing ) - 1 ) ]} {self.thinking[ random.randint( 0, len( self.thinking ) - 1 ) ]}" )
                search = LupinSearch( query=question_gist )
                search.search_and_summarize_the_web()
                msg = search.get_results( scope="summary" )
                
            if ding_for_new_job:
                self.websocket_mgr.emit( 'notification_sound_update', { 'soundFile': '/static/gentle-gong.mp3' } )
            if agent is not None:
                self.push( agent )
            
            if self.emit_speech_callback:
                self.emit_speech_callback( msg )
            
            return msg
            
            # agent = FunctionMappingAgent( question=question, push_counter=self.push_counter, debug=True, verbose=True )
            # self.push( agent )
            # Auto-emission via parent class handles todo_update
            #
            # return f'No similar snapshots found, adding NEW FunctionMappingAgent to TODO queue. Queue size [{self.size()}]'

    # TODO: implement math refactoring agent?
    # def _get_math_refactoring_agent( self, question: str, question_gist: str, last_question_asked: str, push_counter: int ) -> MathRefactoringAgent:
    #     """
    #     Create a math refactoring agent for the given question.
    #
    #     Requires:
    #         - question is the refactoring request
    #         - question_gist is the extracted gist
    #         - last_question_asked includes salutations
    #         - push_counter is a valid integer
    #
    #     Ensures:
    #         - Finds similar snapshots for refactoring
    #         - Creates MathRefactoringAgent with examples
    #         - Returns configured agent instance
    #
    #     Raises:
    #         - None
    #     """
    #     # DEMO KLUDGE: if the question doesn't start with "refactor", then we're going to search for similar snapshots
    #     threshold = 85.0
    #     path_to_snapshots = du.get_project_root() + "/src/conf/long-term-memory/solutions/"
    #     exemplar_snapshot = self.snapshot_mgr.get_snapshots_by_question( question, question_gist=question_gist, threshold_question=95.0, threshold_gist=92.5 )[ 0 ][ 1 ]
    #     similar_snapshots = self.snapshot_mgr.get_snapshots_by_code_similarity( exemplar_snapshot, threshold=threshold )
    #
    #     agent = MathRefactoringAgent( similar_snapshots=similar_snapshots, path_to_solutions=path_to_snapshots, debug=True, verbose=False )
    #     return agent
    
    def _dump_code( self, best_snapshot: SolutionSnapshot ) -> None:
        """
        Debug helper to print snapshot code.
        
        Requires:
            - best_snapshot is a valid SolutionSnapshot
            - best_snapshot.code exists
            
        Ensures:
            - Prints code if debug and verbose are True
            - Formats output with banner
            
        Raises:
            - None
        """
        if self.debug and self.verbose:
            lines_of_code = best_snapshot.code
            if len( lines_of_code ) > 0:
                du.print_banner( f"Code for [{best_snapshot.question}]:" )
            else:
                du.print_banner( "Code: NONE found?" )
            for line in lines_of_code:
                print( line )
            if len( lines_of_code ) > 0:
                print()
                
    def _queue_best_snapshot( self, best_snapshot: SolutionSnapshot, best_score: float=100.0 ) -> str:
        """
        Queue the best matching snapshot for execution.
        
        Requires:
            - best_snapshot is a valid SolutionSnapshot
            - best_score is between 0 and 100
            - Queue is initialized
            
        Ensures:
            - Creates a copy of the snapshot
            - Configures job with current settings
            - Pushes job to queue
            - Emits socket updates
            - Returns status message
            
        Raises:
            - None
        """
        job = best_snapshot.get_copy()
        print( "Python object ID for copied job: " + str( id( job ) ) )
        job.debug   = self.debug
        job.verbose = self.verbose
        job.add_synonymous_question( best_snapshot.last_question_asked, score=best_score )
        
        job.run_date     = du.get_current_datetime()
        job.push_counter = self.push_counter + 1
        job.id_hash      = SolutionSnapshot.generate_id_hash( job.push_counter, job.run_date )
        
        print()
        
        if self.size() != 0:
            suffix = "s" if self.size() > 1 else ""
            if self.emit_speech_callback:
                self.emit_speech_callback( f"{self.size()} job{suffix} ahead of this one" )
        else:
            print( "No jobs ahead of this one in the todo Q" )
        
        self.push( job )  # Auto-emits 'todo_update' via parent class
        
        return f'Job added to queue. Queue size [{self.size()}]'
    
    def _get_routing_command( self, question: str ) -> tuple[str, str]:
        """
        Determine the routing command for a question.
        
        Requires:
            - question is a non-empty string
            - Config has agent router prompt path
            - LLM configuration is available
            
        Ensures:
            - Returns tuple of (command, args)
            - Uses LLM to determine the appropriate agent
            - Parses XML response for command and args
            
        Raises:
            - FileNotFoundError if prompt template missing
            - LLM errors propagated
        """
        router_prompt_template_path = self.config_mgr.get( "prompt template for agent router" )
        router_prompt_template = du.get_file_as_string( du.get_project_root() + router_prompt_template_path )
        
        prompt = router_prompt_template.format( voice_command=question )
        
        llm_spec_key = self.config_mgr.get( "llm spec key for agent router" )
        llm_client = self.llm_factory.get_client( llm_spec_key, debug=self.debug, verbose=self.verbose )
        response = llm_client.run( prompt )
        if self.debug: print( f"LLM response: [{response}]" )
        # Parse results
        command = dux.get_value_by_xml_tag_name( response, "command" )
        args    = dux.get_value_by_xml_tag_name( response, "args" )
        
        return command, args
    
    def push( self, item: Any ) -> None:
        """
        Override parent's push to add producer-consumer coordination.
        
        Requires:
            - item must have an 'id_hash' attribute
            
        Ensures:
            - Item is added to queue via parent method
            - Consumer thread is notified of new work
            
        Raises:
            - AttributeError if item doesn't have id_hash
        """
        # Use condition variable for producer-consumer coordination
        with self.condition:
            # Call parent's push method
            super().push( item )
            # Notify consumer thread that work is available
            self.condition.notify()
            
        if self.debug:
            print( f"[TODO-QUEUE] Added job and notified consumer: {item.id_hash}" )
    
# Add me
def quick_smoke_test():
    """Quick smoke test to validate TodoFifoQueue functionality."""
    import cosa.utils.util as du
    
    du.print_banner( "TodoFifoQueue Smoke Test", prepend_nl=True )
    
    # Test salutation parsing functionality
    test_cases = [
        "Good morning, my dearest receptionist. How are you feeling today?",
        "Greetings little buddy! What's your name?",
        "Hello there! Can you help me with my schedule?",
        "What's the weather like today?"  # No salutation case
    ]
    
    try:
        queue = TodoFifoQueue( None, None, None )
        print( "✓ TodoFifoQueue instantiated successfully" )
        
        for i, input_string in enumerate( test_cases, 1 ):
            print( f"\nTest {i}: '{input_string}'" )
            salutations, question = queue.parse_salutations( input_string )
            print( f"  Salutations: '{salutations}'" )
            print( f"  Question: '{question}'" )
        
    except Exception as e:
        print( f"✗ Error testing TodoFifoQueue: {e}" )
    
    print( "\n✓ TodoFifoQueue smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()