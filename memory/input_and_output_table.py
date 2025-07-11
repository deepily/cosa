import cosa.utils.util as du
from cosa.memory.embedding_manager import EmbeddingManager

from cosa.memory.question_embeddings_table import QuestionEmbeddingsTable
from cosa.memory.solution_snapshot import SolutionSnapshot as ss
from cosa.config.configuration_manager import ConfigurationManager
from cosa.utils.util_stopwatch import Stopwatch

import lancedb
import threading
from typing import Optional, Any

# @singleton
class InputAndOutputTable():
    """
    Manages input/output data storage in LanceDB.
    
    Handles storage and retrieval of conversation history, including
    embeddings for semantic search.
    """
    def __init__( self, debug: bool=False, verbose: bool=False ) -> None:
        """
        Initialize the input/output table.
        
        Requires:
            - LUPIN_CONFIG_MGR_CLI_ARGS environment variable is set or defaults available
            - Database path is valid in configuration
            
        Ensures:
            - Opens connection to LanceDB
            - Opens or creates input_and_output_tbl
            - Initializes question embeddings table
            
        Raises:
            - FileNotFoundError if database path invalid
            - lancedb errors propagated
        """
        
        self.debug          = debug
        self.verbose        = verbose
        self._config_mgr    = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
        self._embedding_mgr = EmbeddingManager( debug=debug, verbose=verbose )
        
        self.db = lancedb.connect( du.get_project_root() + self._config_mgr.get( "database_path_wo_root" ) )
        self._input_and_output_tbl    = self.db.open_table( "input_and_output_tbl" )
        self._question_embeddings_tbl = QuestionEmbeddingsTable( debug=self.debug, verbose=self.verbose )

        print( f"Opened input_and_output_tbl w/ [{self._input_and_output_tbl.count_rows()}] rows" )

        # if self.debug and self.verbose:
        #     du.print_banner( "Tables:" )
        #     print( self.db.table_names() )
        #     du.print_banner( "Table:" )
        #     print( self._input_and_output_tbl.select( [ "date", "time", "input", "output_final" ] ).head( 10 ) )
        
    def insert_io_row( self, date: str=du.get_current_date(), time: str=du.get_current_time( include_timezone=False ),
        input_type: str="", input: str="", input_embedding: list[float]=[], output_raw: str="", output_final: str="", output_final_embedding: list[float]=[], solution_path_wo_root: Optional[str]=None, async_embedding: bool=None
    ) -> None:
        """
        Insert a new row into the input/output table.
        
        Requires:
            - All string parameters are non-None
            - Embeddings are lists of floats or empty
            - async_embedding is boolean or None
            
        Ensures:
            - Row is added to table with provided data
            - Missing embeddings are generated if not provided (sync or async)
            - Returns immediately if async_embedding is True
            - Table row count is incremented
            
        Args:
            async_embedding: If True, generate embeddings asynchronously.
                           If None, use value from configuration.
                           If False, generate embeddings synchronously.
            
        Raises:
            - None (handles errors gracefully)
        """
        
        # ¡OJO! The embeddings are optional. If not provided, they will be generated.
        # In this case the only embedding that we are caching is the one that corresponds to the query/input, otherwise known
        # as the 'question' in the solution snapshot object and the 'query' in the self._question_embeddings_tbl object.
        # TODO: Make consistent the use of the terms 'input', 'query' and 'question'. While they are synonymous that's not necessarily clear to the casual reader.
        # Get debug text truncation length from config first (needed for timer message)
        debug_truncate_len = self._config_mgr.get( "debug text truncation length", default=48, return_type="int" )
        timer = Stopwatch( msg=f"insert_io_row( '{input[ :debug_truncate_len ]}...' )", silent=True )
        
        # Check if we should generate embeddings asynchronously
        if async_embedding is None:
            # Get from configuration, default to True
            async_embedding = self._config_mgr.get( "async embedding generation", default=True, return_type="boolean" )
            if self.debug: print( f"Got async_embedding from config: {async_embedding}" )
        
        # Generate embeddings based on async setting
        if async_embedding and (not input_embedding or not output_final_embedding):
            # Async mode: generate embeddings in background thread, then insert complete row
            if self.debug: print( "Using async embedding generation..." )
            timer.print( "Method returning immediately (async embedding generation started)", use_millis=True, end="\n" )
            
            # Start background thread to generate embeddings and insert row
            def generate_embeddings_and_insert():
                async_timer = Stopwatch( msg=f"Async embedding generation for '{input[:debug_truncate_len]}...'", silent=False )
                try:
                    # Generate missing embeddings with cache hit detection
                    if not input_embedding:
                        if self.debug: print( f"  Generating input embedding for: '{input[:debug_truncate_len]}...'" )
                        # Check if it's in cache by trying the has() method first
                        input_cache_hit = self._question_embeddings_tbl.has( input )
                        if self.debug: print( f"  Input embedding cache {'HIT' if input_cache_hit else 'MISS'}" )
                        final_input_embedding = self._question_embeddings_tbl.get_embedding( input )
                    else:
                        final_input_embedding = input_embedding
                        if self.debug: print( f"  Input embedding provided (skipping generation)" )
                    
                    if not output_final_embedding:
                        output_str = str(output_final) if output_final else ""
                        if self.debug: print( f"  Generating output embedding for: '{output_str[:debug_truncate_len]}...'" )
                        # Note: EmbeddingManager handles its own cache hit detection internally
                        final_output_embedding = self._embedding_mgr.generate_embedding( output_final, normalize_for_cache=True )
                    else:
                        final_output_embedding = output_final_embedding
                        if self.debug: print( f"  Output embedding provided (skipping generation)" )
                    
                    # Create complete row with all embeddings
                    new_row = [ {
                        "date"                             : date,
                        "time"                             : time,
                        "input_type"                       : input_type,
                        "input"                            : input,
                        "input_embedding"                  : final_input_embedding,
                        "output_raw"                       : output_raw,
                        "output_final"                     : output_final,
                        "output_final_embedding"           : final_output_embedding,
                        "solution_path_wo_root"            : solution_path_wo_root
                    } ]
                    
                    # Insert complete row
                    self._input_and_output_tbl.add( new_row )
                    
                    async_timer.print( f"Async completion! I/O table now has {self._input_and_output_tbl.count_rows()} rows", use_millis=True )
                    
                    if self.debug:
                        print( f"  Input embedding dimensions: {len(final_input_embedding)}" )
                        print( f"  Output embedding dimensions: {len(final_output_embedding)}" )
                        
                except Exception as e:
                    async_timer.print( f"FAILED after", use_millis=True )
                    du.print_banner( f"ASYNC EMBEDDING GENERATION FAILED", expletive=True )
                    print( f"Failed to generate embeddings and insert row for input: '{input[:debug_truncate_len]}...'" )
                    print( f"Error: {e}" )
                    du.print_stack_trace( e, explanation="Async embedding generation failed", caller="insert_io_row async thread" )
            
            # Start background thread
            embedding_thread = threading.Thread( target=generate_embeddings_and_insert, daemon=True )
            embedding_thread.start()
            
        else:
            # Sync mode: generate embeddings before inserting (original behavior)
            if self.debug: print( "Using synchronous embedding generation..." )
            
            new_row = [ {
                "date"                             : date,
                "time"                             : time,
                "input_type"                       : input_type,
                "input"                            : input,
                "input_embedding"                  : input_embedding if input_embedding else self._question_embeddings_tbl.get_embedding( input ),
                "output_raw"                       : output_raw,
                "output_final"                     : output_final,
                "output_final_embedding"           : output_final_embedding if output_final_embedding else self._embedding_mgr.generate_embedding( output_final, normalize_for_cache=True ),
                "solution_path_wo_root"            : solution_path_wo_root
            } ]
            self._input_and_output_tbl.add( new_row )
            timer.print( f"Done! I/O table now has {self._input_and_output_tbl.count_rows()} rows", use_millis=True, end="\n" )
        
    def get_knn_by_input( self, search_terms: str, k: int=10 ) -> list[dict]:
        """
        Get k-nearest neighbors by input embedding.
        
        Requires:
            - search_terms is a non-empty string
            - k is a positive integer
            - Embeddings table is initialized
            
        Ensures:
            - Returns list of k most similar inputs
            - Uses dot product similarity metric
            - Results include input and output_final fields
            - Returns empty list if embeddings are unavailable
            
        Raises:
            - None
        """
        timer = Stopwatch( msg="get_knn_by_input() called..." )
        
        # First, convert the search_terms string into an embedding. The embedding table caches all question embeddings
        search_terms_embedding = self._question_embeddings_tbl.get_embedding( search_terms )
        
        # Check if we got a valid embedding (not empty)
        if not search_terms_embedding:
            du.print_banner( "SKIPPING KNN SEARCH - NO EMBEDDINGS" )
            print( "Cannot perform similarity search without embeddings" )
            print( "Returning empty results" )
            return []
        
        # Perform vector similarity search
        search_query = self._input_and_output_tbl.search( search_terms_embedding, vector_column_name="input_embedding" )
        search_results = search_query.metric( "dot" ).limit( k ).select( [ "input", "output_final", "input_embedding" ] )
        
        # Convert to list format, handling potential PyArrow Table results
        try:
            knn = search_results.to_list()
        except AttributeError:
            # If to_list() doesn't exist, try pandas conversion
            knn = search_results.to_pandas().to_dict( 'records' )
        
        timer.print( "Done!", use_millis=True )
        
        if self.debug and self.verbose and knn:
            print( f"KNN search returned {len(knn)} results" )
            print( f"First result keys: {list(knn[0].keys())}" )
            
            # Check if we have input_embedding in results
            if "input_embedding" in knn[0]:
                print( "✓ input_embedding field found in results" )
                # Compare first few embedding values
                result_embedding = knn[0]["input_embedding"]
                print( f"Search embedding length: {len(search_terms_embedding)}" )
                print( f"Result embedding length: {len(result_embedding)}" )
                
                # Compare first 5 values instead of 32 to reduce noise
                print( "Comparing first 5 embedding values:" )
                for i in range( min(5, len(search_terms_embedding), len(result_embedding)) ):
                    match = abs(result_embedding[i] - search_terms_embedding[i]) < 0.0001  # Float comparison with tolerance
                    print( f"  {i}: {match} (result: {result_embedding[i]:.6f}, search: {search_terms_embedding[i]:.6f})" )
            else:
                print( "✗ input_embedding field NOT found in results" )
                print( f"Available fields: {list(knn[0].keys())}" )
        
        return knn
    
    def get_all_io( self, max_rows: int=1000 ) -> list[dict]:
        """
        Get all input/output pairs up to max_rows.
        
        Requires:
            - max_rows is a positive integer
            - Table is initialized
            
        Ensures:
            - Returns list of dictionaries with IO data
            - Limited to max_rows results
            - Includes date, time, input_type, input, output_final
            - Warns if results truncated
            
        Raises:
            - None
        """
        timer = Stopwatch( msg=f"get_all_io( max_rows={max_rows} ) called..." )
        
        results = self._input_and_output_tbl.search().select( [ "date", "time", "input_type", "input", "output_final" ] ).limit( max_rows ).to_list()
        row_count = len( results )
        timer.print( f"Done! Returning [{row_count}] rows", use_millis=True )
        
        if row_count == max_rows:
            print( f"WARNING: Only returning [{max_rows}] rows out of [{self._input_and_output_tbl.count_rows()}]. Increase max_rows to see more data." )
        
        return results
    
    def get_io_stats_by_input_type( self, max_rows: int=1000 ) -> dict[str, int]:
        """
        Get statistics grouped by input_type.
        
        Requires:
            - max_rows is a positive integer
            - Table is initialized
            
        Ensures:
            - Returns dictionary mapping input_type to count
            - Uses pandas for grouping operations
            - Limited to max_rows for processing
            - Warns if results truncated
            
        Raises:
            - None
        """
        timer = Stopwatch( msg=f"get_io_stats_by_input_type( max_rows={max_rows} ) called..." )
        
        stats_df = self._input_and_output_tbl.search().select( [ "input_type" ] ).limit( max_rows ).to_pandas()
        row_count = len( stats_df )
        timer.print( f"Done! Returning [{row_count}] rows for summarization", use_millis=True )
        if row_count == max_rows:
            print( f"WARNING: Only returning [{max_rows}] rows out of [{self._input_and_output_tbl.count_rows()}]. Increase max_rows to see more data." )
        
        # Add a count column to the dataframe, which will be used to summarize the data
        stats_df[ "count" ] = stats_df.groupby( [ "input_type" ] )[ "input_type" ].transform( "count" )
        # Create a dictionary from the dataframe, setting the input_type as the index (key) and the count column as the value
        stats_dict = stats_df.set_index( 'input_type' )[ 'count' ].to_dict()
        
        return stats_dict
    
    def get_all_qnr( self, max_rows: int=50 ) -> list[dict]:
        """
        Get all questions and responses for agent router commands.
        
        Requires:
            - max_rows is a positive integer
            - Table is initialized
            
        Ensures:
            - Returns list of agent router interactions
            - Filters by input_type starting with 'agent router go to'
            - Limited to max_rows results
            - Warns if results truncated
            
        Raises:
            - None
        """
        timer = Stopwatch( msg=f"get_all_qnr( max_rows={max_rows} ) called..." )
        
        where_clause = "input_type LIKE 'agent router go to %'"
        results = self._input_and_output_tbl.search().where( where_clause ).limit( max_rows ).select(
            [ "date", "time", "input_type", "input", "output_final" ]
        ).to_list()
        
        row_count = len( results )
        timer.print( f"Done! Returning [{row_count}] rows of QnR", use_millis=True )
        if row_count == max_rows:
            print( f"WARNING: Only returning [{max_rows}] rows. Increase max_rows to see more data." )
        
        return results
    
    def init_tbl( self ) -> None:
        """
        Initialize the input/output table schema.
        
        Requires:
            - Database connection is established
            
        Ensures:
            - Creates table with proper schema
            - Sets up all required fields and types
            - Creates FTS indexes for search
            - Overwrites existing table if present
            
        Raises:
            - lancedb errors propagated
        """
        du.print_banner( "Tables:" )
        print( self.db.table_names() )
        
        # self.db.drop_table( "input_and_output_tbl" )
        import pyarrow as pa

        schema = pa.schema(
            [
                pa.field( "date",                     pa.string() ),
                pa.field( "time",                     pa.string() ),
                pa.field( "input_type",               pa.string() ),
                pa.field( "input",                    pa.string() ),
                pa.field( "input_embedding",          pa.list_( pa.float32(), 1536 ) ),
                pa.field( "output_raw",               pa.string() ),
                pa.field( "output_final",             pa.string() ),
                pa.field( "output_final_embedding",   pa.list_( pa.float32(), 1536 ) ),
                pa.field( "solution_path_wo_root",    pa.string() ),
            ]
        )
        self._input_and_output_tbl = self.db.create_table( "input_and_output_tbl", schema=schema, mode="overwrite" )
        self._input_and_output_tbl.create_fts_index( "input", replace=True )
        self._input_and_output_tbl.create_fts_index( "input_type", replace=True )
        self._input_and_output_tbl.create_fts_index( "date", replace=True )
        self._input_and_output_tbl.create_fts_index( "time", replace=True )
        self._input_and_output_tbl.create_fts_index( "output_final", replace=True )
        
        # self._query_and_response_tbl.add( df_dict )
        # print( f"New: Table.count_rows: {self._query_and_response_tbl.count_rows()}" )
        
        # du.print_banner( "Tables:" )
        # print( self.db.table_names() )
        
        # schema = self._query_and_response_tbl.schema
        #
        # du.print_banner( "Schema:" )
        # print( schema )

        # querys = [ query ] + [ "what time is it", "what day is today", "well how did I get here" ]
        # timer = Stopwatch()
        # for query in querys:
        #     results = self._query_and_response_tbl.search().where( f"query = '{query}'" ).limit( 1 ).select( [ "date", "time", "input", "output_final", "output_raw" ] ).to_list()
        #     du.print_banner( f"Synonyms for '{query}': {len( results )} found" )
        #     for result in results:
        #         print( f"Date: [{result[ 'date' ]}], Time: [{result[ 'time' ]}], Query: [{result[ 'query' ]}], Response: [{result[ 'response_conversational' ]}] Raw: [{result[ 'response_raw' ]}]" )
        #
        # timer.print( "Search time", use_millis=True )
        # delta_ms = timer.get_delta_ms()
        # print( f"Average search time: {delta_ms / len( querys )} ms" )
        
if __name__ == '__main__':
    
    # import numpy as np
    # embedding_mgr = EmbeddingManager( debug=True )
    # foo = embedding_mgr.generate_embedding( "what time is it", debug=True )
    # print( "Sum of foo", np.sum( foo ) )
    # print( "dot product of foo and foo", np.dot( foo, foo ) * 100 )
    #
    io_tbl = InputAndOutputTable( debug=True )
    qnr = io_tbl.get_all_qnr( max_rows=100 )
    # qnr = io_tbl.get_all_io( max_rows=100 )
    for row in qnr:
        print( row[ "date" ], row[ "time" ], row[ "input_type" ], row[ "input" ], row[ "output_final" ] )
    
    # query_and_response_tbl.init_tbl()
    # results = query_and_response_tbl.get_knn_by_input( "what time is it", k=5 )
    # for row in results:
    #     print( row[ "input" ], row[ "output_final" ], row[ "_distance" ] )
    
    # stats_dict = io_tbl.get_io_stats_by_input_type()
    # for k, v in stats_dict.items():
    #     print( f"input_type: [{k}] called [{v}] times" )


def quick_smoke_test():
    """Run comprehensive smoke test for InputAndOutputTable with async support."""
    du.print_banner( "InputAndOutputTable Smoke Test", prepend_nl=True )
    
    import time
    
    try:
        # Initialize table
        print( "Test 1: InputAndOutputTable initialization..." )
        io_table = InputAndOutputTable( debug=True, verbose=True )
        print( "✓ InputAndOutputTable initialized successfully" )
        
        initial_rows = io_table._input_and_output_tbl.count_rows()
        print( f"Initial table rows: {initial_rows}" )
        
        # Helper function to wait for async completion
        def wait_for_async_completion( expected_rows, timeout_seconds=30 ):
            """Poll database until expected rows appear or timeout"""
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                current_rows = io_table._input_and_output_tbl.count_rows()
                if current_rows >= expected_rows:
                    # Verify latest row has embeddings
                    latest_rows = io_table._input_and_output_tbl.head( 1 ).to_pandas().to_dict( 'records' )
                    if latest_rows and len( latest_rows[0]['input_embedding'] ) > 0 and len( latest_rows[0]['output_final_embedding'] ) > 0:
                        return True, current_rows
                time.sleep( 0.1 )  # Poll every 100ms
            return False, io_table._input_and_output_tbl.count_rows()
        
        # Test 2: Synchronous insertion
        print( f"\nTest 2: Synchronous insertion..." )
        sync_input = "What time is it?"
        sync_output = "The current time is 3:30 PM."
        
        io_table.insert_io_row(
            input_type="smoke_test_sync",
            input=sync_input,
            output_raw=sync_output,
            output_final=sync_output,
            async_embedding=False  # Force sync mode
        )
        
        sync_rows = io_table._input_and_output_tbl.count_rows()
        print( f"✓ Sync insertion completed. Rows: {initial_rows} → {sync_rows}" )
        
        # Test 3: Asynchronous insertion
        print( f"\nTest 3: Asynchronous insertion..." )
        async_input = "How is the weather today?"
        async_output = "The weather is sunny with a temperature of 75°F."
        expected_async_rows = sync_rows + 1
        
        io_table.insert_io_row(
            input_type="smoke_test_async",
            input=async_input,
            output_raw=async_output,
            output_final=async_output,
            async_embedding=True  # Force async mode
        )
        
        print( f"Method returned immediately. Waiting for async completion..." )
        async_success, final_async_rows = wait_for_async_completion( expected_async_rows )
        
        if async_success:
            print( f"✓ Async insertion completed. Rows: {sync_rows} → {final_async_rows}" )
        else:
            print( f"✗ Async insertion timed out or failed. Rows: {sync_rows} → {final_async_rows}" )
        
        # Test 4: Configuration-based async (default behavior)
        print( f"\nTest 4: Configuration-based async behavior..." )
        config_input = "Tell me a joke"
        config_output = "Why don't scientists trust atoms? Because they make up everything!"
        expected_config_rows = final_async_rows + 1
        
        io_table.insert_io_row(
            input_type="smoke_test_config",
            input=config_input,
            output_raw=config_output,
            output_final=config_output
            # async_embedding=None - uses config default
        )
        
        print( f"Method returned (using config default). Waiting for completion..." )
        config_success, final_config_rows = wait_for_async_completion( expected_config_rows )
        
        if config_success:
            print( f"✓ Config-based insertion completed. Rows: {final_async_rows} → {final_config_rows}" )
        else:
            print( f"✗ Config-based insertion timed out. Rows: {final_async_rows} → {final_config_rows}" )
        
        # Test 5: Cache hit testing
        print( f"\nTest 5: Cache hit testing..." )
        cache_input = sync_input  # Reuse same input to trigger cache hit
        cache_output = "It's still 3:30 PM (from cache test)."
        expected_cache_rows = final_config_rows + 1
        
        print( f"Inserting duplicate input to test cache hits: '{cache_input[:32]}...'" )
        io_table.insert_io_row(
            input_type="smoke_test_cache",
            input=cache_input,
            output_raw=cache_output,
            output_final=cache_output,
            async_embedding=True
        )
        
        cache_success, final_cache_rows = wait_for_async_completion( expected_cache_rows )
        
        if cache_success:
            print( f"✓ Cache hit test completed. Rows: {final_config_rows} → {final_cache_rows}" )
        else:
            print( f"✗ Cache hit test timed out. Rows: {final_config_rows} → {final_cache_rows}" )
        
        # Test 6: Debug truncation configuration
        print( f"\nTest 6: Debug truncation configuration..." )
        current_truncate_len = io_table._config_mgr.get( "debug text truncation length", default=48, return_type="int" )
        print( f"Current debug truncation length: {current_truncate_len}" )
        
        long_input = "This is a very long input message that should be truncated in debug output to test the configurable truncation length feature we just implemented."
        long_output = "This is a correspondingly long output message that should also be truncated appropriately."
        
        io_table.insert_io_row(
            input_type="smoke_test_truncation",
            input=long_input,
            output_raw=long_output,
            output_final=long_output,
            async_embedding=True
        )
        print( f"✓ Debug truncation test completed (check output above for truncation)" )
        
        # Test 7: KNN search functionality
        print( f"\nTest 7: Semantic search (KNN) functionality..." )
        try:
            search_results = io_table.get_knn_by_input( "time", k=3 )
            print( f"Found {len(search_results)} similar results for 'time'" )
            
            if search_results:
                print( f"Result structure keys: {list(search_results[0].keys())}" )
                
                for i, result in enumerate( search_results[:2] ):  # Show first 2
                    input_text = result.get('input', 'N/A')[:40]
                    output_text = result.get('output_final', 'N/A')[:40]
                    distance = result.get('_distance', 'N/A')
                    
                    # Handle distance formatting
                    if isinstance(distance, (int, float)):
                        distance_str = f"{distance:.3f}"
                    else:
                        distance_str = str(distance)
                    
                    print( f"  {i+1}. '{input_text}...' → '{output_text}...' (distance: {distance_str})" )
                
                print( f"✓ KNN search working" )
            else:
                print( f"✗ KNN search returned no results" )
                
        except Exception as search_error:
            print( f"✗ KNN search failed: {search_error}" )
            print( f"  Error type: {type(search_error).__name__}" )
        
        # Final summary
        final_total_rows = io_table._input_and_output_tbl.count_rows()
        rows_added = final_total_rows - initial_rows
        print( f"\n✓ Smoke test summary:" )
        print( f"  Initial rows: {initial_rows}" )
        print( f"  Final rows: {final_total_rows}" )
        print( f"  Rows added: {rows_added}" )
        print( f"  Tests completed: 7/7" )
        
    except Exception as e:
        print( f"✗ Error during smoke test: {e}" )
        du.print_stack_trace( e, explanation="Smoke test failed", caller="quick_smoke_test()" )
    
    print( "\n✓ InputAndOutputTable smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()
    