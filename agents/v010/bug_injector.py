import cosa.utils.util as du
import cosa.utils.util_xml as dux

from cosa.agents.v010.agent_base import AgentBase
from cosa.agents.v010.llm_client_factory import LlmClientFactory

class BugInjector( AgentBase ):
    def __init__( self, code, example="", debug=True, verbose=True ):
        
        super().__init__( df_path_key=None, debug=debug, verbose=verbose, routing_command="agent router go to bug injector" )
        
        self.prompt_response_dict   = {
            "code"   : code,
            "example": example
        }
        self.prompt                 = self._get_prompt()
        
    def _get_prompt( self ):
        
        code_with_line_numbers = du.get_source_code_with_line_numbers( self.prompt_response_dict[ "code" ].copy(), join_str="\n" )
        
        return self.prompt_template.format( code_with_line_numbers=code_with_line_numbers )
    
    def run_prompt( self, **kwargs ):
        
        if self.debug: print( "BugInjector.run_prompt() called..." )
        
        factory = LlmClientFactory()
        llm = factory.get_client( self.model_name, debug=self.debug, verbose=self.verbose )
        response = llm.run( self.prompt )
        
        line_number = int( dux.get_value_by_xml_tag_name( response, "line-number", default_value="-1" ) )
        bug         = dux.get_value_by_xml_tag_name( response, "bug", default_value="" )
        
        if line_number == -1:
            du.print_banner( f"Invalid response from [{self.model_name}]", expletive=True )
            print( response )
        elif line_number > len( self.prompt_response_dict[ "code" ] ):
            du.print_banner( f"Invalid response from [{self.model_name}]", expletive=True )
            print( f"Line number [{line_number}] out of bounds, code[] length is [{len(self.prompt_response_dict[ 'code' ])}]" )
            print( response )
        elif line_number == 0:
            du.print_banner( f"Invalid response from [{self.model_name}]", expletive=True )
            print( f"Line number [{line_number}] is invalid, line numbers SHOULD start at 1" )
            print( response )
        else:
            if self.debug:
                du.print_banner( "BEFORE: untouched code", prepend_nl=True, end="\n" )
                du.print_list( self.prompt_response_dict[ "code" ] )
                
            if self.debug: print( f"Bug generated for line_number: [{line_number}], bug: [{bug}]" )
            # prepend a blank line to the code, so that the line numbers align with the line numbers in the prompt
            self.prompt_response_dict[ "code" ] = [ "" ] + self.prompt_response_dict[ "code" ]
            # todo: do i need to handle possibly mangled preceding white space? if so see: https://chat.openai.com/c/59098430-c164-482e-a82e-01d6c6769978
            self.prompt_response_dict[ "code" ][ line_number ] = bug

        if self.debug:
            du.print_banner( "AFTER: updated code", prepend_nl=True, end="\n" )
            du.print_list( self.prompt_response_dict[ "code" ] )
            
        return self.prompt_response_dict
    
    def restore_from_serialized_state( self, file_path ):
        
        raise NotImplementedError( "BugInjector.restore_from_serialized_state() not implemented" )

if __name__ == "__main__":
    
    code = [
        "import datetime",
        "import pytz",
        "def get_time():",
        "    import datetime",
        "    now = datetime.datetime.now()",
        "    tz_name = 'America/New_York'",
        "    tz = pytz.timezone( tz_name )",
        "    tz_date = now.astimezone( tz )",
        "    return tz_date.strftime( '%I:%M %p %Z' )",
        "solution = get_time()",
        "print( solution )"
    ]
    
    bug_injector  = BugInjector( code, example="solution = get_time()", debug=True, verbose=True )
    code_response_dict = bug_injector.run_code()
    bug_injector.print_code( msg="BEFORE: Bug Injection", end="\n" )
    
    response_dict = bug_injector.run_prompt()
    bug_injector.run_code()
    
    bug_injector.print_code( msg=" AFTER: Bug Injection" )