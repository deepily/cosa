import cosa.utils.util as du
import cosa.utils.util_embeddings as due

from cosa.memory.solution_snapshot import SolutionSnapshot as ss
from cosa.app.configuration_manager import ConfigurationManager
from cosa.utils.util_stopwatch import Stopwatch

import lancedb
from typing import Any


# def singleton( cls ):
#
#     instances = { }
#
#     def wrapper( *args, **kwargs ):
#
#         if cls not in instances:
#             print( "Instantiating QuestionEmbeddingsTable() singleton...", end="\n\n" )
#             instances[ cls ] = cls( *args, **kwargs )
#         else:
#             print( "Reusing QuestionEmbeddingsTable() singleton..." )
#
#         return instances[ cls ]
#
#     return wrapper

class QuestionEmbeddingsTable():
    """
    Manages question embeddings storage in LanceDB.
    
    Caches embeddings for questions to avoid regenerating them.
    Supports embedding lookup and storage.
    """
    def __init__( self, debug: bool=False, verbose: bool=False, *args, **kwargs ) -> None:
        """
        Initialize the question embeddings table.
        
        Requires:
            - GIB_CONFIG_MGR_CLI_ARGS environment variable is set or defaults available
            - Database path is valid in configuration
            
        Ensures:
            - Opens connection to LanceDB
            - Opens question_embeddings_tbl
            - Prints table row count
            
        Raises:
            - FileNotFoundError if database path invalid
            - lancedb errors propagated
        """
        
        self.debug       = debug
        self.verbose     = verbose
        self._config_mgr = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
        
        uri = du.get_project_root() + self._config_mgr.get( "database_path_wo_root" )
        
        db = lancedb.connect( uri )
        
        self._question_embeddings_tbl = db.open_table( "question_embeddings_tbl" )
        
        print( f"Opened question_embeddings_tbl w/ [{self._question_embeddings_tbl.count_rows()}] rows" )
        
    def has( self, question: str ) -> bool:
        """
        Check if a question exists in the embeddings table.
        
        Requires:
            - question is a non-empty string
            - Table is initialized
            
        Ensures:
            - Returns True if question exists in table
            - Returns False if question not found
            - Performs exact string match
            
        Raises:
            - None
        """
        if self.debug: timer = Stopwatch( msg=f"has( '{question}' )" )
        du.print_banner( f"[{question}]" )
        # Escape single quotes by doubling them to prevent SQL parsing errors
        escaped_question = question.replace( "'", "''" )
        synonyms = self._question_embeddings_tbl.search().where( f"question = '{escaped_question}'" ).limit( 1 ).select( [ "question" ] ).to_list()
        if self.debug: timer.print( "Done!", use_millis=True )
        
        return len( synonyms ) > 0
    
    def get_embedding( self, question: str ) -> list[float]:
        """
        Get the embedding for the given question string.
        
        Requires:
            - question is a non-empty string
            - Table is initialized
            
        Ensures:
            - Returns embedding from table if found
            - Generates new embedding if not in table
            - Does not add generated embedding to table
            - Returns list of 1536 floats
            
        Raises:
            - None (handles exceptions internally)
        """
        if self.debug: timer = Stopwatch( msg=f"get_embedding( '{question}' )", silent=True )
        try:
            # Escape single quotes by doubling them to prevent SQL parsing errors
            escaped_question = question.replace( "'", "''" )
            rows_returned = self._question_embeddings_tbl.search().where( f"question = '{escaped_question}'" ).limit( 1 ).select( [ "embedding" ] ).to_list()
        except Exception as e:
            du.print_stack_trace( e, explanation="search() failed", caller="QuestionEmbeddingsTable.get_embedding()" )
            rows_returned = []
        if self.debug: timer.print( f"Done! w/ {len( rows_returned )} rows returned", use_millis=True )
        
        if not rows_returned:
            return due.generate_embedding( question, debug=self.debug )
        else:
            return rows_returned[ 0 ][ "embedding"]
        
    def add_embedding( self, question: str, embedding: list[float] ) -> None:
        """
        Add a question and its embedding to the table.
        
        Requires:
            - question is a non-empty string
            - embedding is a list of 1536 floats
            - Table is initialized
            
        Ensures:
            - Adds row to table with question and embedding
            - Handles LanceDB errors gracefully
            
        Raises:
            - None (catches and logs errors)
        """
        new_row = [ { "question": question, "embedding": embedding } ]
        # Lance DB fails when a database is accessed via samba mount on OS X
        try:
            self._question_embeddings_tbl.add( new_row )
        except Exception as e:
            du.print_stack_trace( e, explanation="add() failed", caller="QuestionEmbeddingsTable.add_embedding()" )
    
    # def _init_tbl( self ):
    #
    #     # question_embeddings_dict = QuestionEmbeddingsDict()
    #     # question_embeddings_dict = dict( question_embeddings_dict )
    #     #
    #     # df = pd.DataFrame(list(question_embeddings_dict.items()), columns=[ "question", "embedding" ] )
    #     # print( df.head() )
    #     # print( df.info() )
    #     # print( type( df.iloc[ 0 ][ "embedding" ][ 0 ] ) )
    #     #
    #     # df_dict = df.to_dict( orient="records")
    #
    #     self.config_mgr = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
    #
    #     uri = du.get_project_root() + self.config_mgr.get( "database_path_wo_root" )
    #
    #     db = lancedb.connect( uri )
    #
    #     # db.drop_table( "question_embeddings_tbl" )
    #     # import pyarrow as pa
    #     #
    #     # schema = pa.schema(
    #     #     [
    #     #         pa.field( "question", pa.string() ),
    #     #         pa.field( "embedding", pa.list_( pa.float32(), 1536 ) )
    #     #     ]
    #     # )
    #     # self.question_embeddings_tbl = db.create_table( "question_embeddings_tbl", schema=schema )
    #     # self.question_embeddings_tbl.create_fts_index( "question" )
    #     # print( f"New: Table.count_rows: {self.question_embeddings_tbl.count_rows()}" )
    #     # self.question_embeddings_tbl.add( df_dict )
    #     # print( f"New: Table.count_rows: {self.question_embeddings_tbl.count_rows()}" )
    #
    #     print( db.table_names() )
    #     self.question_embeddings_tbl = db.open_table( "question_embeddings_tbl" )
    #     du.print_banner( "Table:" )
    #     print( self.question_embeddings_tbl.head( 10 ) )
    #
    #     schema = self.question_embeddings_tbl.schema
    #
    #     du.print_banner( "Schema:" )
    #     print( schema )
    #
    #     print( f"BEFORE: Table.count_rows: {self.question_embeddings_tbl.count_rows()}" )
    #     question = "and you may ask yourself well how did I get here"
    #     embedding = due.generate_embedding( question )
    #     print( f"'{question}': embedding length: {len( embedding )}" )
    #     new_row = [ { "question": question, "embedding": embedding } ]
    #     self.question_embeddings_tbl.add( new_row )
    #     print( f"AFTER: Table.count_rows: {self.question_embeddings_tbl.count_rows()}" )
    #
    #     # question_embeddings_tbl.create_fts_index( "question" )
    #
    #     questions = [ question ] + [ "what time is it", "well how did I get here", "what is the time", "what is the time now", "what time is it now", "what is the current time", "What day is today", "Whats todays date" ]
    #     timer = Stopwatch()
    #     for question in questions:
    #         synonyms = self.question_embeddings_tbl.search().where( f"question = '{question}'" ).limit( 1 ).select( [ "question", "embedding" ] ).to_list()
    #         du.print_banner( f"Synonyms for '{question}': {len( synonyms )} found" )
    #         for synonym in synonyms:
    #             print( f"{synonym[ 'question' ]}: embedding length: {len( synonym[ 'embedding' ] )} embedding: {synonym[ 'embedding' ][ :5 ]}" )
    #
    #     timer.print( "Search time", use_millis=True )
    #     delta_ms = timer.get_delta_ms()
    #     print( f"Average search time: {delta_ms / len( questions )} ms" )
    #
    #     # result = self.question_embeddings_tbl.search( "what time is it" ).limit( 2 ).to_pandas()
    #     # print( result )
        

if __name__ == '__main__':
    
    question_embeddings_tbl = QuestionEmbeddingsTable()
    question_1 = "what time is it"
    print( f"'{question_1}': in embeddings table [{question_embeddings_tbl.has( question_1 )}]" )
    question_2 = "well how did I get here"
    print( f"'{question_2}': in embeddings table [{question_embeddings_tbl.has( question_2 )}]" )
    
    embedding = question_embeddings_tbl.get_embedding( question_1 )
    print( f"embedding length: {len( embedding )}" )
    