from cosa.agents.v010.agent_base import AgentBase

class DateAndTimeAgent( AgentBase ):
    """
    Agent for handling date and time related queries.
    
    This agent processes questions about current time, time zones, dates,
    and temporal calculations using code generation.
    """
    
    def __init__( self, question: str="", question_gist: str="", last_question_asked: str="", push_counter: int=-1, routing_command: str="agent router go to date and time", debug: bool=False, verbose: bool=False, auto_debug: bool=False, inject_bugs: bool=False ) -> None:
        """
        Initialize date and time agent.
        
        Requires:
            - Date and time routing command exists in config
            - Valid prompt template for date/time queries
            
        Ensures:
            - Initializes with date and time routing
            - Sets up prompt with question
            - Defines expected XML response tags
            
        Raises:
            - KeyError if required config missing
        """
        
        super().__init__( df_path_key=None, question=question, question_gist=question_gist, last_question_asked=last_question_asked, routing_command=routing_command, push_counter=push_counter, debug=debug, verbose=verbose, auto_debug=auto_debug, inject_bugs=inject_bugs )
        
        self.prompt = self.prompt_template.format( question=self.question )
        self.xml_response_tag_names   = [ "thoughts", "brainstorm", "evaluation", "code", "example", "returns", "explanation" ]
    
        # self.serialize_prompt_to_json = self.config_mgr.get( "agent_todo_list_serialize_prompt_to_json", default=False, return_type="boolean" )
        # self.serialize_code_to_json   = self.config_mgr.get( "agent_todo_list_serialize_code_to_json",   default=False, return_type="boolean" )
    
    def restore_from_serialized_state( self, file_path: str ) -> None:
        """
        Restore date and time agent state from JSON file.
        
        Requires:
            - file_path points to valid JSON file
            
        Ensures:
            - Raises NotImplementedError (not implemented)
            
        Raises:
            - NotImplementedError always
        """
        
        raise NotImplementedError( "DateAndTimeAgent.restore_from_serialized_state() not implemented" )
    
    
def quick_smoke_test():
    """Quick smoke test to validate DateAndTimeAgent functionality."""
    import cosa.utils.util as du
    
    du.print_banner( "DateAndTimeAgent Smoke Test", prepend_nl=True )
    
    # Test with a single question for completion
    question = "What time is it in Washington DC?"
    
    try:
        print( f"Testing question: '{question}'" )
        date_agent = DateAndTimeAgent( question=question, debug=True, verbose=False, auto_debug=False )
        print( "✓ DateAndTimeAgent created successfully" )
        
        # Run through the complete agent workflow
        print( "Running prompt..." )
        date_agent.run_prompt()
        print( "✓ Prompt execution completed" )
        
        print( "Running code..." )
        date_agent.run_code()
        print( "✓ Code execution completed" )
        
        print( "Running formatter..." )
        date_agent.run_formatter()
        print( "✓ Formatter execution completed" )
        
        print( f"✓ Final response: {date_agent.answer_conversational}" )
        
    except Exception as e:
        print( f"✗ Error during agent execution: {e}" )
    
    print( "\n✓ DateAndTimeAgent smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()