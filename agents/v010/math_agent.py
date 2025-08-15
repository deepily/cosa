import cosa.utils.util as du
import cosa.utils.util_xml as dux

from cosa.utils.util_stopwatch import Stopwatch
from cosa.memory.solution_snapshot import SolutionSnapshot
from cosa.agents.v010.agent_base import AgentBase

class MathAgent( AgentBase ):
    """
    Agent for solving mathematical problems and calculations.
    
    This agent generates Python code to solve math questions,
    using the last_question_asked for maximum specificity.
    """
    
    def __init__( self, question: str="", question_gist: str="", last_question_asked: str="", push_counter: int=-1, routing_command: str="agent router go to math", user_id: str="ricardo_felipe_ruiz_6bdc", debug: bool=False, verbose: bool=False, auto_debug: bool=False, inject_bugs: bool=False ) -> None:
        """
        Initialize math agent for mathematical computations.
        
        Requires:
            - Math routing command exists in config
            - Valid prompt template for math queries
            
        Ensures:
            - Uses last_question_asked for specificity from voice transcription
            - Sets up prompt with full question text
            - Defines expected XML response tags
            
        Raises:
            - KeyError if required config missing
        """
        
        super().__init__( df_path_key=None, question=question, question_gist=question_gist, last_question_asked=last_question_asked, routing_command=routing_command, push_counter=push_counter, user_id=user_id, debug=debug, verbose=verbose, auto_debug=auto_debug, inject_bugs=inject_bugs )
        
        # du.print_banner( "MathAgent.__init__()" )
        print( "¡OJO! MathAgent is using last_question_asked because it wants all the specificity contained within the voice to text transcription" )
        
        self.prompt = self.prompt_template.format( question=self.last_question_asked )
        self.xml_response_tag_names   = [ "thoughts", "brainstorm", "evaluation", "code", "example", "returns", "explanation" ]
    
        # self.serialize_prompt_to_json = self.config_mgr.get( "agent_todo_list_serialize_prompt_to_json", default=False, return_type="boolean" )
        # self.serialize_code_to_json   = self.config_mgr.get( "agent_todo_list_serialize_code_to_json",   default=False, return_type="boolean" )
    
    def restore_from_serialized_state( self, file_path: str ) -> None:
        """
        Restore math agent state from JSON file.
        
        Requires:
            - file_path points to valid JSON file
            
        Ensures:
            - Raises NotImplementedError (not implemented)
            
        Raises:
            - NotImplementedError always
        """
        
        raise NotImplementedError( "MathAgent.restore_from_serialized_state() not implemented" )
    
    def run_formatter( self ) -> str:
        """
        Format math output based on configuration.
        
        Requires:
            - self.code_response_dict contains 'output' field
            - Config has 'formatter_prompt_for_math_terse' setting
            
        Ensures:
            - Returns formatted answer
            - If terse_output=True, returns raw output
            - Otherwise uses parent formatter
            - Updates self.answer_conversational
            
        Raises:
            - KeyError if output missing from response
        """
        
        """
        Format the output based on the configuration for math agent.

        If 'formatter_prompt_for_math_terse' is True, set the answer as the output from 'code_response_dict'.
        Otherwise, call the superclass method 'run_formatter' and set the answer accordingly.
        """
        terse_output = self.config_mgr.get( "formatter_prompt_for_math_terse", default=False, return_type="boolean" )
        
        if terse_output:
            if self.debug: print( "MathAgent.run_formatter() terse_output=True. NOT consulting with a formatter before returning an answer." )
            self.answer_conversational = self.code_response_dict[ "output" ]
        else:
            super().run_formatter()
            
        return self.answer_conversational

def quick_smoke_test():
    """Quick smoke test to validate MathAgent functionality."""
    import cosa.utils.util as du
    
    du.print_banner( "MathAgent Smoke Test", prepend_nl=True )
    
    # Test with a math question for completion
    question = "What's the square root of 144?"
    
    try:
        print( f"Testing question: '{question}'" )
        math_agent = MathAgent( question=question, debug=True, verbose=False, auto_debug=False )
        print( "✓ MathAgent created successfully" )
        
        # Run through the complete agent workflow
        print( "Running prompt..." )
        math_agent.run_prompt()
        print( "✓ Prompt execution completed" )
        
        print( "Running code..." )
        math_agent.run_code()
        print( "✓ Code execution completed" )
        
        print( "Running formatter..." )
        math_agent.run_formatter()
        print( "✓ Formatter execution completed" )
        
        print( f"✓ Final response: {math_agent.answer_conversational}" )
        
    except Exception as e:
        print( f"✗ Error during math agent execution: {e}" )
    
    print( "\n✓ MathAgent smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()