import abc
import json
import os

import pandas as pd

import cosa.utils.util as du
import cosa.utils.util_pandas        as dup
import cosa.utils.util_xml as dux
import cosa.memory.solution_snapshot as ss

from cosa.agents.llm_v0 import Llm_v0
from cosa.agents.raw_output_formatter import RawOutputFormatter
from cosa.agents.v010.runnable_code import RunnableCode
from cosa.app.configuration_manager import ConfigurationManager
from cosa.memory.solution_snapshot import SolutionSnapshot
from cosa.agents.two_word_id_generator import TwoWordIdGenerator

class AgentBase( RunnableCode, abc.ABC ):
    
    STATE_INITIALIZED = "initialized"
    STATE_WAITING_TO_RUN = "waiting to run"
    STATE_RUNNING = "running"
    STATE_RUNNING_WAITING_FOR_RESPONSE = "running waiting for response"
    STATE_STOPPED_ERROR = "error"
    STATE_STOPPED_DONE = "done"
    
    @abc.abstractmethod
    def restore_from_serialized_state( file_path ):
        pass
    
    def __init__( self, df_path_key=None, question="", question_gist="", last_question_asked="", push_counter=-1, routing_command=None, debug=False, verbose=False, auto_debug=False, inject_bugs=False ):
        
        self.debug                 = debug
        self.verbose               = verbose
        self.auto_debug            = auto_debug
        self.inject_bugs           = inject_bugs
        self.df_path_key           = df_path_key
        self.routing_command       = routing_command
        
        # Added to allow behavioral compatibility with solution snapshot object
        self.run_date              = ss.SolutionSnapshot.get_timestamp()
        self.push_counter          = push_counter
        self.id_hash               = ss.SolutionSnapshot.generate_id_hash( self.push_counter, self.run_date )
        
        self.two_word_id           = TwoWordIdGenerator().get_id()
        self.execution_state       = AgentBase.STATE_INITIALIZED
        
        # This is a bit of a misnomer, it's the unprocessed question that was asked of the agent
        self.last_question_asked   = last_question_asked
        self.question              = ss.SolutionSnapshot.remove_non_alphanumerics( question )
        self.question_gist         = question_gist
        self.answer_conversational = None
        
        self.config_mgr            = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
        
        self.df                    = None
        self.do_not_serialize      = { "df", "config_mgr", "two_word_id", "execution_state" }

        self.model_name            = self.config_mgr.get( f"llm spec key for {routing_command}" )
        template_path              = self.config_mgr.get( f"prompt template for {routing_command}" )
        self.prompt_template       = du.get_file_as_string( du.get_project_root() + template_path )
        self.prompt                = None
        
        if self.df_path_key is not None:
            
            self.df = pd.read_csv( du.get_project_root() + self.config_mgr.get( self.df_path_key ) )
            self.df = dup.cast_to_datetime( self.df )
    
    def get_html( self ):
        
        return f"<li id='{self.id_hash}'>{self.run_date} Q: {self.last_question_asked}</li>"
    
    @abc.abstractmethod
    def restore_from_serialized_state( file_path ):
        pass
    
    def serialize_to_json( self, subtopic=None ):

        # Convert object's state to a dictionary
        state_dict = self.__dict__

        # Convert object's state to a dictionary, omitting specified fields
        state_dict = { key: value for key, value in self.__dict__.items() if key not in self.do_not_serialize }

        # Constructing the filename
        # Format: "topic-year-month-day-hour-minute-second.json", limit question to the first 96 characters
        question_short = SolutionSnapshot.remove_non_alphanumerics( self.question[ :96 ] ).replace( " ", "-" )
        topic          = self.config_mgr.get( f"serialization topic for {self.routing_command}" )
        topic          = topic + "-" + subtopic if subtopic is not None else topic
        now            = du.get_current_datetime_raw()
        file_path = f"{du.get_project_root()}/io/log/{topic}-{question_short}-{now.year}-{now.month}-{now.day}-{now.hour}-{now.minute}-{now.second}.json"

        # Serialize and save to file
        with open( file_path, 'w' ) as file:
            json.dump( state_dict, file, indent=4 )
        os.chmod( file_path, 0o666 )

        print( f"Serialized to {file_path}" )
        
    def _update_response_dictionary( self, response ):
        
        if self.debug and self.verbose: print( f"update_response_dictionary called..." )
        
        prompt_response_dict = { }
        
        for xml_tag in self.xml_response_tag_names:
            
            if self.debug and self.verbose: print( f"Looking for xml_tag [{xml_tag}]" )
            
            if xml_tag in [ "code", "examples" ]:
                # the get_code method expects enclosing tags, like <code>...</code> or <examples>...</examples>
                xml_string = f"<{xml_tag}>" + dux.get_value_by_xml_tag_name( response, xml_tag ) + f"</{xml_tag}>"
                prompt_response_dict[ xml_tag ] = dux.get_nested_list( xml_string, tag_name=xml_tag, debug=self.debug, verbose=self.verbose )
            else:
                prompt_response_dict[ xml_tag ] = dux.get_value_by_xml_tag_name( response, xml_tag )
        
        return prompt_response_dict
    
    def run_prompt( self, model_name=None, temperature=0.5, top_p=0.25, top_k=10, max_new_tokens=1024, stop_sequences=None, include_raw_response=False ):
        
        if model_name is not None: self.model_name = model_name
        
        llm = Llm_v0( config_mgr=self.config_mgr, model=self.model_name, debug=self.debug, verbose=self.verbose )
        response = llm.query_llm( prompt=self.prompt, temperature=temperature, top_p=top_p, top_k=top_k, max_new_tokens=max_new_tokens, stop_sequences=stop_sequences, debug=self.debug, verbose=self.verbose )
        
        # Parse XML-esque response
        self.prompt_response_dict = self._update_response_dictionary( response )
        
        # Add raw response if requested. This is useful for creating synthetic datasets
        if include_raw_response:
            self.prompt_response_dict[ "xml_response" ]        = response
            self.prompt_response_dict[ "last_question_asked" ] = self.last_question_asked
        
        return self.prompt_response_dict
    
    def run_code( self, auto_debug=None, inject_bugs=None ):
        
        # Use this object's settings, if temporary overriding values aren't provided
        if auto_debug  is None: auto_debug  = self.auto_debug
        if inject_bugs is None: inject_bugs = self.inject_bugs
        
        # TODO: figure out where this should live, i suspect it will be best located in util_code_runner.py
        if self.debug: print( f"Executing super().run_code() with inject_bugs [{inject_bugs}] and auto_debug [{auto_debug}]..." )
        
        if self.df_path_key is not None:
            path_to_df = self.config_mgr.get( self.df_path_key, default=None )
        else:
            path_to_df = None
            
        code_response_dict = super().run_code( path_to_df=path_to_df, inject_bugs=inject_bugs )
        
        if self.code_ran_to_completion():
            
            self.error = None
            return self.code_response_dict
        
        elif auto_debug:
            
            # Iterative debugging agent extends this class: agent base
            from cosa.agents.iterative_debugging_agent import IterativeDebuggingAgent

            self.error = self.code_response_dict[ "output" ]
            
            # Start out by running the minimalistic debugger first, and then if it fails run the full debugger
            for minimalist in [ True, False ]:
                
                debugging_agent = IterativeDebuggingAgent(
                    code_response_dict[ "output" ], "/io/code.py",
                    minimalist=minimalist, example=self.prompt_response_dict[ "example" ], returns=self.prompt_response_dict.get( "returns", "string" ),
                    debug=self.debug, verbose=self.verbose
                )
                # Iterates across multiple LLMs in either minimalist or non-minimalist mode until a solution is found
                debugging_agent.run_prompts()
                
                if debugging_agent.was_successfully_debugged():
                    
                    self.prompt_response_dict[ "code" ] = debugging_agent.code
                    self.code_response_dict             = debugging_agent.code_response_dict
                    self.error                          = None
                    
                    self.print_code( msg=f"Minimalist [{minimalist}] debugging successful, corrected code returned to calling AgentBase run_code()" )
                    break
                    
                else:
                    
                    du.print_banner( f"Minimalist [{minimalist}] debugging failed, returning original code, such as it is... 😢 sniff 😢" )
        
            return self.code_response_dict
    
    def is_format_output_runnable( self ):
        
        print( "AgentBase.is_format_output_runnable() not implemented" )
        pass
    
    def format_output( self ):
        
        formatter = RawOutputFormatter( self.last_question_asked, self.code_response_dict[ "output" ], self.routing_command, debug=self.debug, verbose=self.verbose )
        self.answer_conversational = formatter.format_output()
        
        return self.answer_conversational
    
    # Create a message to check and see if the formatting ran to completion
    def formatter_ran_to_completion( self ):
        
        return self.answer_conversational is not None
    
    def do_all( self ):
        
        self.run_prompt()
        self.run_code()
        self.format_output()
        
        return self.answer_conversational