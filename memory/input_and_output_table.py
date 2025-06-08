import cosa.utils.util as du
import cosa.utils.util_embeddings as due

from cosa.memory.question_embeddings_table import QuestionEmbeddingsTable
from cosa.memory.solution_snapshot import SolutionSnapshot as ss
from cosa.app.configuration_manager import ConfigurationManager
from cosa.utils.util_stopwatch import Stopwatch

import lancedb
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
            - GIB_CONFIG_MGR_CLI_ARGS environment variable is set or defaults available
            - Database path is valid in configuration
            
        Ensures:
            - Opens connection to LanceDB
            - Opens or creates input_and_output_tbl
            - Initializes question embeddings table
            
        Raises:
            - FileNotFoundError if database path invalid
            - lancedb errors propagated
        """
        
        self.debug       = debug
        self.verbose     = verbose
        self._config_mgr = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
        
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
        input_type: str="", input: str="", input_embedding: list[float]=[], output_raw: str="", output_final: str="", output_final_embedding: list[float]=[], solution_path_wo_root: Optional[str]=None
    ) -> None:
        """
        Insert a new row into the input/output table.
        
        Requires:
            - All string parameters are non-None
            - Embeddings are lists of floats or empty
            
        Ensures:
            - Row is added to table with provided data
            - Missing embeddings are generated if not provided
            - Table row count is incremented
            
        Raises:
            - None (handles errors gracefully)
        """
        
        # ¡OJO! The embeddings are optional. If not provided, they will be generated.
        # In this case the only embedding that we are caching is the one that corresponds to the query/input, otherwise known
        # as the 'question' in the solution snapshot object and the 'query' in the self._question_embeddings_tbl object.
        # TODO: Make consistent the use of the terms 'input', 'query' and 'question'. While they are synonymous that's not necessarily clear to the casual reader.
        timer = Stopwatch( msg=f"insert_io_row( '{input[ :64 ]}...' )", silent=True )
        
        new_row = [ {
            "date"                             : date,
            "time"                             : time,
            "input_type"                       : input_type,
            "input"                            : input,
            "input_embedding"                  : input_embedding if input_embedding else self._question_embeddings_tbl.get_embedding( input ),
            "output_raw"                       : output_raw,
            "output_final"                     : output_final,
            "output_final_embedding"           : output_final_embedding if output_final_embedding else due.generate_embedding( output_final, debug=self.debug ),
            "solution_path_wo_root"            : solution_path_wo_root
        } ]
        self._input_and_output_tbl.add( new_row )
        timer.print( "Done! I/O table now has {self._input_and_output_tbl.count_rows()} rows", use_millis=True, end="\n" )
        
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
        
        knn = self._input_and_output_tbl.search(
            search_terms_embedding, vector_column_name="input_embedding"
        ).metric( "dot" ).limit( k ).select( [ "input", "output_final" ] ).to_list()
        timer.print( "Done!", use_millis=True )
        
        if self.debug and self.verbose:
            # Compare the embeddings for the search_terms and for the query_embedding fields
            for i in range( 32 ):
                print( knn[ 0 ][ "input_embedding" ][ i ] == search_terms_embedding[ i ], knn[ 0 ][ "input_embedding" ][ i ], search_terms_embedding[ i ] )
    
            # Are the search term embeddings and the query embeddings equal?
            print( 'knn[ 0 ][ "input_embedding" ] == search_terms_embedding:', knn[ 0 ][ "input_embedding" ] == search_terms_embedding )
        
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
    # foo = due.generate_embedding( "what time is it" )
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
    