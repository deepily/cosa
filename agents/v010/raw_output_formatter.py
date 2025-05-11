from cosa.utils import util     as du
from cosa.utils import util_xml as dux

from cosa.app.configuration_manager      import ConfigurationManager
from cosa.agents.v010.llm_client_factory import LlmClientFactory

class RawOutputFormatter:
    
    def __init__(self, question, raw_output, routing_command, thoughts="", code="", debug=False, verbose=False ):
        
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
    
    def format_output( self ):

        response = self.llm.run( self.prompt )
        output   = dux.get_value_by_xml_tag_name( response, "rephrased-answer" )

        return output
    
    def _get_prompt( self ):

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
    print( formatter.format_output() )