import cosa.utils.util as du
import cosa.utils.util_xml as dux
from cosa.app.configuration_manager import ConfigurationManager
from cosa.agents.v010.llm_client_factory import LlmClientFactory


class Gister:
    """
    Extracts concise gists from questions using LLM.
    
    This class handles the extraction of main intents from user questions
    by using prompt templates and LLM processing.
    """
    
    def __init__( self, debug=False, verbose=False ):
        """
        Initialize the Gister with its own configuration and LLM factory.
        
        Requires:
            - debug is a boolean
            - verbose is a boolean
            
        Ensures:
            - Creates internal ConfigurationManager instance
            - Creates internal LlmClientFactory instance
            - Sets debug and verbose flags
        """
        self.debug       = debug
        self.verbose     = verbose
        self.config_mgr  = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
        self.llm_factory = LlmClientFactory()
        
        if self.debug: print( "Gister initialized" )
    
    def get_gist( self, utterance: str ) -> str:
        """
        Extract the gist of a question using LLM.

        Requires:
            - utterance is a non-empty string
            - Gist prompt template exists

        Ensures:
            - Returns a concise gist of the question
            - Uses LLM to extract main intent for multi-word utterances
            - Returns utterance directly if it contains no spaces
            - Returns empty string if extraction fails

        Raises:
            - FileNotFoundError if prompt template missing
        """
        # Shortcut: if utterance has no spaces, return it directly
        if " " not in utterance.strip():
            if self.debug: print( f"Shortcut: returning single word/token '{utterance}' without LLM" )
            return utterance.strip()
        
        prompt_template_path = self.config_mgr.get( "prompt template for gist generation" )
        prompt_template = du.get_file_as_string( du.get_project_root() + prompt_template_path )
        prompt = prompt_template.format( utterance=utterance )
        
        llm_spec_key = self.config_mgr.get( "llm spec key for gist generation" )
        llm_client = self.llm_factory.get_client( llm_spec_key, debug=self.debug, verbose=self.verbose )
        results = llm_client.run( prompt )
        gist = dux.get_value_by_xml_tag_name( results, "gist", default_value="" ).strip()
        
        return gist


def quick_smoke_test():
    """
    Quick smoke test for Gister functionality.
    
    Tests the complete workflow of extracting a gist from a question.
    """
    du.print_banner( "Gister Smoke Test", prepend_nl=True )
    
    try:
        # Initialize Gister
        print( "Creating Gister instance..." )
        gister = Gister( debug=False, verbose=False )
        print( "✓ Gister created successfully" )
        
        # Test gist extraction with multiple utterances
        test_utterances = [
            "What's the date?",
            "What is today's date?",
            "What is the date today?",
            "It's hot in here.",
            "It is hot in here!",
            "I'm too hot!",
            "I am too hot!",
            "I am hot!",
            "I'm hot",
            "202-409-4959",
            "foo@bar.com"
        ]
        
        print( f"\nTesting {len(test_utterances)} utterances:" )
        print( "=" * 60 )
        
        for i, utterance in enumerate( test_utterances, 1 ):
            print( f"\n{i}. Input: '{utterance}'" )
            
            try:
                gist = gister.get_gist( utterance )
                if gist:
                    print( f"   ✓ Gist: '{gist}'" )
                else:
                    print( f"   ✗ No gist extracted" )
            except Exception as e:
                print( f"   ✗ Error: {str(e)}" )
        
        du.print_banner( "Smoke Test Complete", prepend_nl=True )
        
    except Exception as e:
        print( f"✗ Smoke test failed: {str(e)}" )
        du.print_banner( "Smoke Test Failed", prepend_nl=True )


if __name__ == "__main__":
    quick_smoke_test()