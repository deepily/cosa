import cosa.utils.util as du
import cosa.utils.util_xml as dux
from cosa.config.configuration_manager import ConfigurationManager
from cosa.agents.llm_client_factory import LlmClientFactory
from cosa.agents.io_models.xml_models import SimpleResponse
from cosa.agents.io_models.utils.prompt_template_processor import PromptTemplateProcessor
from cosa.memory.gist_cache_table import GistCacheTable
from cosa.memory.normalizer import Normalizer


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
            - Configures XML parsing strategy (baseline or structured)
        """
        self.debug       = debug
        self.verbose     = verbose
        self.config_mgr  = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
        self.llm_factory = LlmClientFactory()

        # Check if Pydantic parsing is enabled for Gister
        self.use_pydantic = self.config_mgr.get( "gister use pydantic xml parsing", default=False, return_type="boolean" )

        # Initialize normalizer for cache key generation
        self._normalizer = Normalizer()

        # Initialize gist cache if enabled
        self.cache_enabled = self.config_mgr.get( "gister cache enabled", default=True, return_type="boolean" )
        self._gist_cache = None

        if self.cache_enabled:
            db_uri      = du.get_project_root() + self.config_mgr.get( "solution snapshots lancedb path" )
            table_name  = self.config_mgr.get( "gister cache table name", default="gist_cache" )
            self._gist_cache = GistCacheTable( db_uri, table_name=table_name, debug=self.debug, verbose=self.verbose )

        if self.debug:
            parsing_mode = "Pydantic (structured)" if self.use_pydantic else "baseline"
            cache_status = "enabled" if self.cache_enabled else "disabled"
            print( f"Gister initialized with {parsing_mode} XML parsing, cache {cache_status}" )

    def get_gist( self, utterance: str ) -> str:
        """
        Extract the gist of a question using LLM with caching.

        Requires:
            - utterance is a non-empty string
            - Gist prompt template exists

        Ensures:
            - Returns a concise gist of the question
            - Uses cached gist if available (5ms vs 500ms)
            - Uses LLM to extract main intent for multi-word utterances
            - Returns utterance directly if it contains no spaces
            - Caches LLM results for future lookups
            - Returns empty string if extraction fails

        Raises:
            - FileNotFoundError if prompt template missing

        Performance:
            - Cache hit: ~5ms
            - Cache miss: ~525ms (500ms LLM + 25ms cache write)
            - Expected hit rate: 70-80%
        """
        # Shortcut: if utterance has no spaces, return it directly
        if " " not in utterance.strip():
            if self.debug: print( f"Shortcut: returning single word/token '{utterance}' without LLM" )
            return utterance.strip()

        # Check cache first if enabled
        if self.cache_enabled and self._gist_cache is not None:
            cached_gist = self._gist_cache.get_cached_gist( utterance )
            if cached_gist is not None:
                if self.debug: print( f"Cache HIT for '{du.truncate_string( utterance )}' → '{cached_gist}'" )
                return cached_gist

            if self.debug: print( f"Cache MISS for '{du.truncate_string( utterance )}' - calling LLM" )

        # Cache miss or cache disabled - generate via LLM
        gist = self._generate_gist_via_llm( utterance )

        # Store in cache if enabled and gist was generated successfully
        if self.cache_enabled and self._gist_cache is not None and gist:
            normalized = self._normalizer.normalize( utterance )
            self._gist_cache.cache_gist( utterance, gist, normalized=normalized )

        return gist

    def _generate_gist_via_llm( self, utterance: str ) -> str:
        """
        Generate gist by calling LLM (internal helper method).

        Requires:
            - utterance is a non-empty string with spaces

        Ensures:
            - Returns gist extracted from LLM response
            - Returns empty string if extraction fails

        Raises:
            - FileNotFoundError if prompt template missing

        Performance:
            - ~500ms per call (LLM latency)
        """
        prompt_template_path = self.config_mgr.get( "prompt template for gist generation" )
        prompt_template = du.get_file_as_string( du.get_project_root() + prompt_template_path )

        # Process the template to replace {{PYDANTIC_XML_EXAMPLE}} with actual XML
        processor = PromptTemplateProcessor( debug=self.debug, verbose=self.verbose )
        prompt_template = processor.process_template( prompt_template, 'gist generation' )

        # Now format with the utterance
        prompt = prompt_template.format( utterance=utterance )

        # Add debug to see actual prompt
        if self.debug and self.verbose:
            print( f"Gister prompt being sent to LLM:\n{prompt[:500]}..." )

        llm_spec_key = self.config_mgr.get( "llm spec key for gist generation" )
        llm_client = self.llm_factory.get_client( llm_spec_key, debug=self.debug, verbose=self.verbose )
        results = llm_client.run( prompt )

        if self.use_pydantic:
            # Use Pydantic SimpleResponse model for structured parsing
            try:
                response_model = SimpleResponse.from_xml( results )
                gist = response_model.get_content()
                if gist is None:
                    gist = ""
                    if self.debug: print( "Warning: Pydantic parsing returned None content" )
                gist = gist.strip()
                if self.debug and self.verbose: print( f"Pydantic parsing extracted gist: '{gist}'" )
            except Exception as e:
                if self.debug: print( f"Pydantic parsing failed, falling back to baseline: {e}" )
                # Fallback to baseline parsing
                gist = dux.get_value_by_xml_tag_name( results, "gist", default_value="" ).strip()
        else:
            # Use baseline XML parsing
            gist = dux.get_value_by_xml_tag_name( results, "gist", default_value="" ).strip()
            if self.debug and self.verbose: print( f"Baseline parsing extracted gist: '{gist}'" )

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