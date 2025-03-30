import random

from cosa.agents.confirmation_dialog import ConfirmationDialogue
from cosa.agents.math_refactoring_agent import MathRefactoringAgent
from cosa.app.fifo_queue import FifoQueue

from cosa.agents.date_and_time_agent import DateAndTimeAgent
from cosa.agents.receptionist_agent import ReceptionistAgent
from cosa.agents.weather_agent import WeatherAgent
from cosa.agents.todo_list_agent import TodoListAgent
from cosa.agents.calendaring_agent import CalendaringAgent
from cosa.agents.math_agent import MathAgent
from cosa.agents.llm import Llm
from cosa.tools.search_gib import GibSearch

# from lib.agents.agent_function_mapping        import FunctionMappingAgent

# from app       import emit_audio
from cosa.utils import util     as du
from cosa.utils import util_xml as dux

import cosa.app.util_llm_client  as llm_client

from cosa.memory.solution_snapshot import SolutionSnapshot

class TodoFifoQueue( FifoQueue ):
    def __init__( self, socketio, snapshot_mgr, app, config_mgr=None, debug=False, verbose=False, silent=False ):
        
        super().__init__()
        self.debug        = debug
        self.verbose      = verbose
        self.silent       = silent
        
        self.socketio     = socketio
        self.snapshot_mgr = snapshot_mgr
        self.app          = app
        self.push_counter = 0
        self.config_mgr   = config_mgr
        
        self.auto_debug   = False if config_mgr is None else config_mgr.get( "auto_debug",  default=False, return_type="boolean" )
        self.inject_bugs  = False if config_mgr is None else config_mgr.get( "inject_bugs", default=False, return_type="boolean" )
        
        # # Set by set_llm() below
        # self.cmd_llm_in_memory = None
        # self.cmd_llm_tokenizer = None
        
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
        
    # def set_llm( self, cmd_llm_in_memory, cmd_llm_tokenizer ):
    #
    #     self.cmd_llm_in_memory = cmd_llm_in_memory
    #     self.cmd_llm_tokenizer = cmd_llm_tokenizer
    
    def parse_salutations( self, transcription ):
        """
        Takes a string of words and returns a tuple of two strings.
        The first string is the salutations, and the second string is the remaining string after the salutations.

        :param transcription: str
        :return: tuple of two strings
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
    
    def get_gist( self, question ):
        
        prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/agents/gist.txt" )
        prompt = prompt_template.format( question=question )
        # ¡OJO! LLM should be runtime configurable
        llm = Llm( model=Llm.GROQ_LLAMA3_70B, debug=self.debug, verbose=self.verbose )
        results = llm.query_llm( prompt=prompt )
        gist = dux.get_value_by_xml_tag_name( results, "gist", default_value="" ).strip()
        
        return gist
    
    def push_job( self, question ):
        
        run_previous_best_snapshot = False
        similar_snapshots = [ ]
        
        # check to see if the queue isn't accepting jobs (because it's waiting for response to a previous request)
        if not self.is_accepting_jobs():
            
            msg = f"The human responded '{question}'"
            # from app import emit_audio
            # emit_audio( msg )
            du.print_banner( msg )
            # TODO: make LLM runtime configurable
            # default_url = "¡OJO! We shouldn't have to set this value here!"
            run_previous_best_snapshot = ConfirmationDialogue( model=Llm.GROQ_LLAMA3_1_70B, debug=self.debug, verbose=self.verbose ).confirmed( question )
            
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
            question_gist = self.get_gist( question )
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
                msg = f"Is that the same as: {best_snapshot.question_gist}?"
                du.print_banner( msg )
                print( "Blocking object pushed onto queue, waiting for response..." )
                from app import emit_audio
                emit_audio( msg )
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
                from app import emit_audio
                emit_audio( f"{self.hemming_and_hawing[ random.randint( 0, len( self.hemming_and_hawing ) - 1 ) ]} I'm gonna ask our research librarian about that" )
                search = GibSearch( query=question_gist )
                search.search_and_summarize_the_web()
                msg = search.get_results( scope="summary" )
            
            elif command == "agent router go to calendar":
                agent = CalendaringAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                msg = starting_a_new_job.format( agent_type="calendaring" )
                ding_for_new_job = True
            elif command == "agent router go to math":
                if question.lower().strip().startswith( "refactor " ):
                    agent = self._get_math_refactoring_agent( question, question_gist, salutation_plus_question, self.push_counter )
                    msg = starting_a_new_job.format( agent_type="math refactoring" )
                else:
                    agent = MathAgent( question=salutation_plus_question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                    msg = starting_a_new_job.format( agent_type="math" )
                ding_for_new_job = True
            elif command == "agent router go to todo list":
                agent = TodoListAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                msg = starting_a_new_job.format( agent_type="todo list" )
                ding_for_new_job = True
            elif command == "agent router go to date and time":
                agent = DateAndTimeAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                msg = starting_a_new_job.format( agent_type="date and time" )
                ding_for_new_job = True
            elif command == "agent router go to weather":
                agent = WeatherAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                msg = starting_a_new_job.format( agent_type="weather" )
                # ding_for_new_job = False
            elif command == "agent router go to receptionist" or command == "none":
                print( f"Routing '{command}' to receptionist..." )
                agent = ReceptionistAgent( question=question, question_gist=question_gist, last_question_asked=salutation_plus_question, push_counter=self.push_counter, debug=True, verbose=False, auto_debug=self.auto_debug, inject_bugs=self.inject_bugs )
                # Randomly grab hemming and hawing string and prepend it to a randomly chosen thinking string
                msg = f"{self.hemming_and_hawing[ random.randint( 0, len( self.hemming_and_hawing ) - 1 ) ]} {self.thinking[ random.randint( 0, len( self.thinking ) - 1 ) ]}".strip()
                # ding_for_new_job = False
            else:
                msg = du.print_banner( f"TO DO: Implement else case command {command}" )
                print( msg )
                from app import emit_audio
                emit_audio( f"{self.hemming_and_hawing[ random.randint( 0, len( self.hemming_and_hawing ) - 1 ) ]} {self.thinking[ random.randint( 0, len( self.thinking ) - 1 ) ]}" )
                search = GibSearch( query=question_gist )
                search.search_and_summarize_the_web()
                msg = search.get_results( scope="summary" )
                
            if ding_for_new_job:
                self.socketio.emit( 'notification_sound_update', { 'soundFile': '/static/gentle-gong.mp3' } )
            if agent is not None:
                self.push( agent )
            
            from app import emit_audio
            emit_audio( msg )
            
            return msg
            
            # agent = FunctionMappingAgent( question=question, push_counter=self.push_counter, debug=True, verbose=True )
            # self.push( agent )
            # self.socketio.emit( 'todo_update', { 'value': self.size() } )
            #
            # return f'No similar snapshots found, adding NEW FunctionMappingAgent to TODO queue. Queue size [{self.size()}]'

    def _get_math_refactoring_agent( self, question, question_gist, last_question_asked, push_counter ):
        
        # DEMO KLUDGE: if the question doesn't start with "refactor", then we're going to search for similar snapshots
        threshold = 85.0
        path_to_snapshots = du.get_project_root() + "/src/conf/long-term-memory/solutions/"
        exemplar_snapshot = self.snapshot_mgr.get_snapshots_by_question( question, question_gist=question_gist, threshold_question=95.0, threshold_gist=92.5 )[ 0 ][ 1 ]
        similar_snapshots = self.snapshot_mgr.get_snapshots_by_code_similarity( exemplar_snapshot, threshold=threshold )
        
        agent = MathRefactoringAgent( similar_snapshots=similar_snapshots, path_to_solutions=path_to_snapshots, debug=True, verbose=False )
        return agent
    
    def _dump_code( self, best_snapshot ):
        
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
                
    def _queue_best_snapshot( self, best_snapshot, best_score=100.0 ):
            
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
                from app import emit_audio
                emit_audio( f"{self.size()} job{suffix} ahead of this one" )
            else:
                print( "No jobs ahead of this one in the todo Q" )
            
            self.push( job )
            self.socketio.emit( 'todo_update', { 'value': self.size() } )
            
            return f'Job added to queue. Queue size [{self.size()}]'
    
    def _get_routing_command( self, question ):
        
        router_prompt_template = du.get_file_as_string( du.get_project_root() + self.config_mgr.get( "agent_router_prompt_path_wo_root" ) )
        
        prompt        = router_prompt_template.format( voice_command=question ),
        model         = self.config_mgr.get( "router_and_vox_command_model" )
        is_completion = self.config_mgr.get( "router_and_vox_command_is_completion", return_type="boolean", default=False )
        
        llm      = Llm( model=model, is_completion=is_completion, debug=self.debug, verbose=self.verbose )
        response = llm.query_llm( prompt=prompt )
        print( f"LLM response: [{response}]" )
        # Parse results
        command = dux.get_value_by_xml_tag_name( response, "command" )
        args    = dux.get_value_by_xml_tag_name( response, "args" )
        
        return command, args
    
# Add me
if __name__ == "__main__":
    
    queue = TodoFifoQueue( None, None, None )
    input_string = "Good morning, my dearest receptionist. How are you feeling today?"
    # input_string = "Greetings little buddy! What's your name?"
    salutations, question = queue.parse_salutations( input_string )
    print( salutations )
    print( question )