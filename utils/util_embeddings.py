"""
Utility module for OpenAI embedding functionality.
Handles embedding generation with proper error handling.
"""

import openai
import cosa.utils.util as du
import cosa.utils.util_stopwatch as sw
from cosa.app.configuration_manager import ConfigurationManager


def generate_embedding( text: str, debug: bool=False ) -> list[ float ]:
    """
    Generate OpenAI embedding for text.
    
    Requires:
        - text is a non-empty string
        - OpenAI API key is available
        - 'embedding model name' is configured
        - debug is a boolean (defaults to False)
        
    Ensures:
        - Returns a list of floats on success
        - Returns empty list on API errors
        - Logs detailed error information for troubleshooting
        - Reduces output verbosity when debug=False
        
    Note:
        - Continues execution even if embedding generation fails
    """
    timer = sw.Stopwatch( msg=f"Generating embedding for [{du.truncate_string( text )}]...", silent=False )
    
    try:
        # Get configuration manager
        config_mgr = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
        
        # Get embedding model name from config - NO FALLBACK
        embedding_model = config_mgr.get( "embedding model name" )
        
        if debug:
            print( f"\nConfiguration details:" )
            print( f"  Embedding model: {embedding_model}" )
            print( f"  API key location: {du.get_project_root()}/src/conf/keys/openai" )
        
        if not embedding_model:
            du.print_banner( "CONFIGURATION ERROR - MISSING EMBEDDING MODEL", prepend_nl=True )
            print( "The 'embedding model name' key is not configured." )
            print( "" )
            print( "TO FIX THIS ERROR:" )
            print( f"1. Add 'embedding model name' to your configuration file" )
            print( f"2. Common values: 'text-embedding-ada-002', 'text-embedding-3-small', 'text-embedding-3-large'" )
            print( f"3. Check the configuration file specified in your config block" )
            du.print_banner( "CANNOT GENERATE EMBEDDINGS", prepend_nl=True )
            return [ ]
        
        # Get API key
        api_key = du.get_api_key( "openai" )
        
        if debug:
            print( f"  API key (first 10 chars): {api_key[ :10 ] if api_key else 'NOT FOUND'}..." )
            print( f"  OpenAI client version: {openai.__version__}" )
        
        # Create a dedicated OpenAI client for embeddings that bypasses environment variables
        # This ensures we always use OpenAI's API for embeddings, not local completion servers
        embedding_client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.openai.com/v1"  # Force use of OpenAI's API for embeddings
        )
        
        if debug:
            print( f"\nAttempting to generate embedding with model: {embedding_model}" )
            print( f"Using OpenAI API endpoint: https://api.openai.com/v1" )
        
        response = embedding_client.embeddings.create(
            input=text,
            model=embedding_model
        )
        timer.print( "Done!", use_millis=True )
        
        embedding = response.data[ 0 ].embedding
        if debug: print( f"\nSuccess! Generated embedding with {len( embedding )} dimensions" )
        
        return embedding
    
    except openai.NotFoundError as e:
        # Get model name for error message
        try:
            config_mgr = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
            embedding_model = config_mgr.get( "embedding model name" )
        except:
            embedding_model = "[UNKNOWN - CONFIG ERROR]"
        
        du.print_banner( "EMBEDDING API ERROR - 404 NOT FOUND", prepend_nl=True )
        print( "The OpenAI embedding service returned a 404 error." )
        print( "This usually means one of the following:" )
        print( "1. Your OpenAI API key is invalid or expired" )
        print( f"2. The embedding model '{embedding_model}' is not accessible" )
        print( "3. Your account doesn't have access to the embeddings API" )
        print( "" )
        print( "TO FIX THIS ERROR:" )
        print( f"1. Check your API key in: {du.get_project_root()}/src/conf/keys/openai" )
        print( "2. Verify your OpenAI account has embedding API access" )
        print( "3. Test your API key at: https://platform.openai.com/account/api-keys" )
        print( f"4. Verify embedding model name in config: '{embedding_model}'" )
        print( "" )
        print( f"Error details: {e}" )
        print( f"Error type: {type( e )}" )
        print( f"Error response: {getattr( e, 'response', 'No response attribute' )}" )
        du.print_banner( "CONTINUING WITHOUT EMBEDDINGS", prepend_nl=True )
        
        # Return empty embedding to allow execution to continue
        return [ ]
    
    except Exception as e:
        du.print_banner( f"EMBEDDING API ERROR - {type( e ).__name__}", prepend_nl=True )
        print( f"Failed to generate embedding: {e}" )
        print( f"Error type: {type( e )}" )
        print( f"Error details: {repr( e )}" )
        print( "Continuing without embeddings..." )
        du.print_banner( "CONTINUING WITHOUT EMBEDDINGS", prepend_nl=True )
        
        # Return empty embedding to allow execution to continue
        return [ ]


def quick_smoke_test():
    """Run quick smoke tests with various inputs to validate embedding functionality."""
    du.print_banner( "OpenAI Embedding Smoke Test", prepend_nl=True )
    
    # Test cases
    test_texts = [
        "What time is it?",
        "Hello world",
        "The quick brown fox jumps over the lazy dog"
    ]
    
    for i, text in enumerate( test_texts, 1 ):
        print( f"\nTest {i}: '{text}'" )
        print( "-" * 40 )
        
        embedding = generate_embedding( text, debug=False )
        
        if embedding:
            print( f"✓ Success: Generated embedding with {len( embedding )} dimensions" )
            print( f"  First 5 values: {embedding[ :5 ]}" )
        else:
            print( "✗ Failed: No embedding generated" )
        
        print()

if __name__ == "__main__":
    quick_smoke_test()
