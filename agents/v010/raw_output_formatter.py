from cosa.utils import util     as du
from cosa.utils import util_xml as dux

from cosa.app.configuration_manager      import ConfigurationManager
from cosa.agents.v010.llm_client_factory import LlmClientFactory

class RawOutputFormatter:
    """
    Formatter for converting raw agent output to conversational responses.
    
    Uses LLM to rephrase technical output into natural language.
    """
    
    def __init__(self, question: str, raw_output: str, routing_command: str, thoughts: str="", code: str="", debug: bool=False, verbose: bool=False ) -> None:
        """
        Initialize output formatter with context.
        
        Requires:
            - question and raw_output are non-empty strings
            - routing_command maps to valid formatter config
            - Config has formatter template and LLM spec
            
        Ensures:
            - Loads appropriate formatter template
            - Initializes LLM client for formatting
            - Wraps optional thoughts/code in XML tags
            - Removes XML declarations from raw_output
            
        Raises:
            - KeyError if formatter config missing
            - FileNotFoundError if template missing
        """
        
        self.debug       = debug
        self.verbose     = verbose
        
        self.question    = question
        if thoughts != "":
            self.thoughts = f"<thoughts>{thoughts}</thoughts>"
        else:
            self.thoughts = ""
        if code != "":
            self.code = f"<code>{code}</code>"
        else:
            self.code = ""
        self.raw_output  = raw_output.replace( "<?xml version='1.0' encoding='utf-8'?>", "" )
        
        self.config_mgr            = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS", debug=self.debug, verbose=self.verbose, silent=True )

        self.routing_command       = routing_command
        template_path              = self.config_mgr.get( f"formatter template for {routing_command}" )
        model_name                 = self.config_mgr.get( f"formatter llm spec for {routing_command}" )

        self.formatting_template   = du.get_file_as_string( du.get_project_root() + template_path )
        self.prompt                = self._get_prompt()

        factory                    = LlmClientFactory( debug=self.debug, verbose=self.verbose )
        self.llm                   = factory.get_client( model_name, debug=self.debug, verbose=self.verbose )
    
    def run_formatter( self ) -> str:
        """
        Execute formatter prompt to rephrase output.
        
        Requires:
            - self.prompt is set with formatting prompt
            - LLM is accessible via self.llm
            
        Ensures:
            - Returns rephrased answer from 'rephrased-answer' XML tag
            - Natural language response suitable for users
            
        Raises:
            - LLM exceptions if formatting fails
            - XML parsing errors if response malformed
        """

        response = self.llm.run( self.prompt )
        output   = dux.get_value_by_xml_tag_name( response, "rephrased-answer" )

        return output
    
    def _get_prompt( self ) -> str:
        """
        Generate formatting prompt based on routing command.
        
        Requires:
            - self.formatting_template is loaded
            - Question and raw_output are set
            
        Ensures:
            - Returns prompt with appropriate context
            - Includes thoughts/code for certain routing commands
            - Formatted according to template requirements
            
        Raises:
            - None
        """

        if self.routing_command in [ "agent router go to receptionist", "agent router go to math" ]:
            return self.formatting_template.format( question=self.question, raw_output=self.raw_output, thoughts=self.thoughts, code=self.code )
        else:
            return self.formatting_template.format( question=self.question, raw_output=self.raw_output )
    
if __name__ == "__main__":
    
    # routing_command = "agent router go to date and time"
    # routing_command = "agent router go to calendar"
    routing_command = "agent router go to receptionist"
    question          = "my friend and i think you are pretty cool like really fucking cool! my friend thinks i should ask you how you would respond to someone who said they wanted to rub your face in their pussy"
    thoughts          = "The query seems to be asking about how I would respond to a potentially offensive or inappropriate question. I need to consider the context and maintain a professional tone in my response."
    raw_output        = "As an AI, I am programmed to follow guidelines and respond to queries in a helpful and appropriate manner. If someone were to ask me to perform an inappropriate action or provide explicit content, I would simply respond with a message that I am unable to assist with such requests."
   
    formatter = RawOutputFormatter( question, raw_output, routing_command, thoughts=thoughts, debug=True, verbose=True )
    print( formatter.run_formatter() )