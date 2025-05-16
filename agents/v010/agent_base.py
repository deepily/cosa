import abc
import json
import os
from typing import Optional, Any

import pandas as pd

import cosa.utils.util as du
import cosa.utils.util_pandas        as dup
import cosa.utils.util_xml as dux
import cosa.memory.solution_snapshot as ss

from cosa.agents.v010.raw_output_formatter import RawOutputFormatter

from cosa.agents.v010.llm_client_factory import LlmClientFactory
from cosa.agents.v010.runnable_code import RunnableCode
from cosa.app.configuration_manager import ConfigurationManager
from cosa.memory.solution_snapshot import SolutionSnapshot
from cosa.agents.v010.two_word_id_generator import TwoWordIdGenerator

class AgentBase( RunnableCode, abc.ABC ):
    
    STATE_INITIALIZING         = "initializing"
    STATE_WAITING_TO_RUN       = "waiting to run"
    STATE_RUNNING              = "running"
    STATE_WAITING_FOR_RESPONSE = "running waiting for response"
    STATE_STOPPED_ERROR        = "error"
    STATE_STOPPED_DONE         = "done"
    
    # ROUTING_COMMAND_TEMPLATE         = "agent router go to {routing_command}"
    # PROMPT_TEMPLATE_KEY_TEMPLATE     = "prompt template for agent router go to {routing_command}"
    # LLM_SPEC_KEY_TEMPLATE            = "llm spec key for agent router go to {routing_command}"
    # SERIALIZATION_TOPIC_KEY_TEMPLATE = "serialization topic for agent router go to {routing_command}"
    #
    # @staticmethod
    # def build_routing_command( routing_command ):
    #     """
    #     Returns the routing command for the given routing command.
    #     """
    #     return AgentBase.ROUTING_COMMAND_TEMPLATE.format( routing_command=routing_command )
    
    @abc.abstractmethod
    def restore_from_serialized_state( file_path: str ) -> 'AgentBase':
        """
        Restore an agent from a serialized JSON state file.
        
        Requires:
            - file_path is a valid path to an existing JSON file
            - JSON file contains all necessary agent state information
            
        Ensures:
            - Returns a new AgentBase instance with restored state
            - All instance variables are properly initialized from the file
            
        Raises:
            - NotImplementedError (must be implemented by subclasses)
        """
        pass
    
    def __init__( self, df_path_key: Optional[str]=None, question: str="", question_gist: str="", last_question_asked: str="", push_counter: int=-1, routing_command: Optional[str]=None, debug: bool=False, verbose: bool=False, auto_debug: bool=False, inject_bugs: bool=False ) -> None:
        """
        Initialize a base agent with configuration and state.
        
        Requires:
            - routing_command must be provided for proper initialization
            - df_path_key (if provided) must map to a valid CSV file path in config
            
        Ensures:
            - execution_state is set to STATE_INITIALIZING then STATE_WAITING_TO_RUN
            - config_mgr is properly initialized
            - model_name and prompt_template are loaded from config
            - DataFrame is loaded and datetime columns cast if df_path_key provided
            - All instance variables are initialized
            
        Raises:
            - KeyError if routing_command configuration keys are missing
            - FileNotFoundError if template or DataFrame file not found
        """
        
        self.execution_state       = AgentBase.STATE_INITIALIZING
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
            
        self.execution_state = AgentBase.STATE_WAITING_TO_RUN
    
    def get_html( self ) -> str:
        """
        Generate HTML representation of this agent instance.
        
        Requires:
            - id_hash, run_date, and last_question_asked are initialized
            
        Ensures:
            - Returns a formatted HTML <li> element with agent info
            - HTML includes unique id, timestamp, and question
            
        Raises:
            - None
        """
        return f"<li id='{self.id_hash}'>{self.run_date} Q: {self.last_question_asked}</li>"
    
    @abc.abstractmethod
    def restore_from_serialized_state( file_path: str ) -> 'AgentBase':
        """
        Restore an agent from a serialized JSON state file.
        
        Requires:
            - file_path is a valid path to an existing JSON file
            - JSON file contains all necessary agent state information
            
        Ensures:
            - Returns a new AgentBase instance with restored state
            - All instance variables are properly initialized from the file
            
        Raises:
            - NotImplementedError (must be implemented by subclasses)
        """
        pass
    
    def serialize_to_json( self, subtopic: Optional[str]=None ) -> None:
        """
        Serialize agent state to a JSON file for persistence.
        
        Requires:
            - config_mgr has valid 'serialization topic' for routing_command
            - /io/log directory exists and is writable
            
        Ensures:
            - Creates JSON file with agent state (excluding do_not_serialize fields)
            - File is saved with descriptive name including topic, question, and timestamp
            - File permissions are set to 0o666
            - Prints confirmation of serialization path
            
        Raises:
            - OSError if file cannot be created or permissions cannot be set
            - KeyError if required config keys are missing
        """

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
        
    def _update_response_dictionary( self, response: str ) -> dict[str, Any]:
        """
        Parse LLM response XML into structured dictionary.
        
        Requires:
            - response is a valid XML string
            - self.xml_response_tag_names is defined with expected tags
            
        Ensures:
            - Returns dictionary with parsed values for each expected tag
            - 'code' and 'examples' tags are parsed as nested lists
            - Other tags are parsed as simple string values
            
        Raises:
            - None (malformed XML results in empty/partial dictionary)
        """
        
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
    
    def run_prompt( self, include_raw_response: bool=False ) -> dict[str, Any]:
        """
        Execute the prompt against the configured LLM.
        
        Requires:
            - self.prompt is set to a valid prompt string
            - self.model_name is configured
            - LLM client factory can provide client for model_name
            
        Ensures:
            - Returns parsed response dictionary with expected XML tags
            - Updates self.prompt_response_dict with parsed values
            - If include_raw_response=True, adds raw XML and question to dict
            
        Raises:
            - LLM-specific exceptions if prompt execution fails
        """

        factory = LlmClientFactory()  # No arguments for the singleton constructor
        llm = factory.get_client( self.model_name, debug=self.debug, verbose=self.verbose )
        
        if self.debug: print( f"Prompt: {self.prompt}" )
        response = llm.run( self.prompt )
        if self.debug: print( f"Response: {response}" )
        
        # Parse XML-esque response
        self.prompt_response_dict = self._update_response_dictionary( response )
        
        # Add raw response if requested. This is useful for creating synthetic datasets
        if include_raw_response:
            self.prompt_response_dict[ "xml_response" ]        = response
            self.prompt_response_dict[ "last_question_asked" ] = self.last_question_asked
        
        return self.prompt_response_dict
    
    def run_code( self, auto_debug: Optional[bool]=None, inject_bugs: Optional[bool]=None ) -> dict[str, Any]:
        """
        Execute generated code with optional debugging.
        
        Requires:
            - self.prompt_response_dict contains 'code' and 'example' fields
            - Code is syntactically valid Python (unless inject_bugs=True)
            
        Ensures:
            - Returns code response dictionary with output/error info
            - If code runs successfully, sets self.error to None
            - If auto_debug=True and code fails, attempts iterative debugging
            - Updates self.code_response_dict with results
            
        Raises:
            - None (errors are captured in response dictionary)
        """
        
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
            from cosa.agents.v010.iterative_debugging_agent import IterativeDebuggingAgent

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
    
    def is_format_output_runnable( self ) -> bool:
        """
        Check if output formatting is available.
        
        Requires:
            - None
            
        Ensures:
            - Prints not implemented message
            - Returns False (base implementation)
            
        Raises:
            - None
        """
        print( "AgentBase.is_format_output_runnable() not implemented" )
        return False
    
    def run_formatter( self ) -> str:
        """
        Format raw output into conversational response.
        
        Requires:
            - self.last_question_asked is set
            - self.code_response_dict contains 'output' field
            - self.routing_command is configured for formatter
            
        Ensures:
            - Returns formatted conversational answer
            - Updates self.answer_conversational with result
            
        Raises:
            - KeyError if required formatter config is missing
        """
        
        formatter = RawOutputFormatter( self.last_question_asked, self.code_response_dict[ "output" ], self.routing_command, debug=self.debug, verbose=self.verbose )
        self.answer_conversational = formatter.run_formatter()
        
        return self.answer_conversational
    
    # Create a message to check and see if the formatting ran to completion
    def formatter_ran_to_completion( self ) -> bool:
        """
        Check if formatter completed successfully.
        
        Requires:
            - None
            
        Ensures:
            - Returns True if answer_conversational is set
            - Returns False if answer_conversational is None
            
        Raises:
            - None
        """
        return self.answer_conversational is not None
    
    def do_all( self ) -> str:
        """
        Execute complete agent workflow: prompt -> code -> format.
        
        Requires:
            - Agent is properly initialized with prompt and config
            
        Ensures:
            - Runs prompt execution, code execution, and formatting
            - Returns final conversational answer
            - Updates all relevant instance variables
            
        Raises:
            - Any exceptions from run_prompt, run_code, or run_formatter
        """
        
        self.run_prompt()
        self.run_code()
        self.run_formatter()
        
        return self.answer_conversational