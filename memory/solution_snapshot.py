import hashlib
import os
import glob
import json
import copy
import regex as re
from collections import OrderedDict
from typing import Optional, Union, Any

import cosa.utils.util as du
import cosa.utils.util_stopwatch as sw
import cosa.utils.util_code_runner as ucr
import cosa.utils.util_xml as dux

from cosa.agents.v010.runnable_code import RunnableCode
from cosa.agents.v010.raw_output_formatter import RawOutputFormatter

import numpy as np
from cosa.memory.embedding_manager import EmbeddingManager

class SolutionSnapshot( RunnableCode ):
    """
    Captures and persists a complete solution to a question.
    
    Stores question, code, embeddings, and execution results for
    future reuse and similarity matching.
    """
    @staticmethod
    def get_timestamp( microseconds: bool = False ) -> str:
        """
        Get current timestamp with optional microsecond precision.
        
        Requires:
            - None
            
        Ensures:
            - Returns formatted datetime string
            - Default format: "YYYY-MM-DD @ HH:MM:SS TZ" 
            - Microsecond format: "YYYY-MM-DD @ HH:MM:SS.ffffff TZ"
            
        Args:
            microseconds: If True, include microseconds for unique IDs (default: False)
            
        Raises:
            - None
        """
        if microseconds:
            return du.get_current_datetime( format_str='%Y-%m-%d @ %H:%M:%S.%f %Z' )
        else:
            return du.get_current_datetime()
    
    @staticmethod
    def remove_non_alphanumerics( input: str, replacement_char: str="" ) -> str:
        """
        Remove non-alphanumeric characters from input.
        
        Requires:
            - input is a string
            - replacement_char is a string
            
        Ensures:
            - Returns lowercase string with non-alphanumeric chars replaced
            - Preserves spaces
            
        Raises:
            - None
        """
        regex = re.compile( "[^a-zA-Z0-9 ]" )
        cleaned_output = regex.sub( replacement_char, input ).lower()
        
        return cleaned_output
    
    @staticmethod
    def escape_single_quotes( input: str ) -> str:
        """
        Remove single quotes from input.
        
        Requires:
            - input is a string
            
        Ensures:
            - Returns string with single quotes removed
            
        Raises:
            - None
        """
        return input.replace( "'", "" )
    
    
    @staticmethod
    def generate_id_hash( push_counter: int, run_date: str ) -> str:
        """
        Generate unique ID hash for snapshot using microsecond-precision timestamp.
        
        Requires:
            - push_counter is an integer (ignored - kept for backward compatibility)
            - run_date is a string with microsecond precision
            
        Ensures:
            - Returns SHA256 hash as hex string
            - Uses only run_date for uniqueness (microsecond precision eliminates collisions)
            - Maintains API compatibility with existing code
            
        Raises:
            - None
        """
        # Use only timestamp for uniqueness - microsecond precision eliminates collisions
        # push_counter parameter kept for backward compatibility but ignored
        return hashlib.sha256( run_date.encode() ).hexdigest()
    
    @staticmethod
    def get_default_stats_dict() -> dict:
        """
        Get default runtime statistics dictionary.
        
        Requires:
            - None
            
        Ensures:
            - Returns dict with all required stats fields
            - Initial values set appropriately
            
        Raises:
            - None
        """
        return {
           "first_run_ms": 0,
            "run_count"  : -1,
            "total_ms"   : 0,
            "mean_run_ms": 0,
            "last_run_ms": 0,
          "time_saved_ms": 0
        }
    
    @staticmethod
    def get_embedding_similarity( this_embedding: list[float], that_embedding: list[float] ) -> float:
        """
        Calculate similarity between two embeddings.
        
        Requires:
            - Both embeddings are lists of floats
            - Both embeddings have same length
            
        Ensures:
            - Returns similarity score as percentage (0-100)
            - Uses dot product calculation
            
        Raises:
            - None
        """
        return np.dot( this_embedding, that_embedding ) * 100
    
    def __init__( self, push_counter: int=-1, question: str="", question_gist: str="", synonymous_questions: OrderedDict=OrderedDict(), synonymous_question_gists: OrderedDict=OrderedDict(), non_synonymous_questions: list=[],
                  last_question_asked: str="", answer: str="", answer_conversational: str="", error: str="", routing_command: str="",
                  created_date: str=get_timestamp(), updated_date: str=get_timestamp(), run_date: str=get_timestamp(),
                  runtime_stats: dict=get_default_stats_dict(),
                  id_hash: str="", solution_summary: str="", code: list[str]=[], code_returns: str="", code_example: str="", code_type: str="raw", thoughts: str="",
                  programming_language: str="Python", language_version: str="3.10",
                  question_embedding: list[float]=[ ], question_gist_embedding: list[float]=[ ], solution_embedding: list[float]=[ ], code_embedding: list[float]=[ ], thoughts_embedding: list[float]=[ ],
                  solution_directory: str="/src/conf/long-term-memory/solutions/", solution_file: Optional[str]=None, user_id: str="ricardo_felipe_ruiz_6bdc", debug: bool=False, verbose: bool=False
                  ) -> None:
        """
        Initialize a solution snapshot.
        
        Requires:
            - All string parameters are strings or empty
            - All list parameters are lists or empty
            - Embeddings are lists of floats when provided
            - user_id must be a valid system ID
            
        Ensures:
            - Initializes all fields with provided or default values
            - Generates missing embeddings if content provided
            - Creates unique ID hash if not provided
            - Writes to file if embeddings were generated
            - user_id is stored for ownership tracking but excluded from serialization
            
        Raises:
            - None (handles errors internally)
        """
        
        super().__init__( debug=debug, verbose=verbose )
        
        # Initialize embedding manager
        self._embedding_mgr = EmbeddingManager( debug=debug, verbose=verbose )
        
        # track updates to internal state as the object is instantiated
        dirty                      = False
        
        self.push_counter          = push_counter
        self.question              = SolutionSnapshot.remove_non_alphanumerics( question )
        self.question_gist         = question_gist
        # self.question_gist         = SolutionSnapshot.remove_non_alphanumerics( question_gist )
        self.thoughts              = thoughts
        
        self.answer                = answer
        self.answer_conversational = answer_conversational
        self.error                 = error
        self.routing_command       = routing_command
        self.user_id               = user_id
        
        # Is there is no synonymous questions to be found then just recycle the current question
        # Handle corrupted data: ensure synonymous_questions is a valid dict/OrderedDict
        if not isinstance( synonymous_questions, dict ):
            if self.debug: print( f"WARNING: synonymous_questions is invalid type {type(synonymous_questions)}, defaulting to empty OrderedDict" )
            synonymous_questions = OrderedDict()
            
        if len( synonymous_questions ) == 0:
            synonymous_questions[ question ] = 100.0
            self.synonymous_questions = synonymous_questions
        else:
            self.synonymous_questions = synonymous_questions
            
        # Is there is no synonymous gists to be found then just recycle the current gist
        # Handle corrupted data: ensure synonymous_question_gists is a valid dict/OrderedDict
        if not isinstance( synonymous_question_gists, dict ):
            if self.debug: print( f"WARNING: synonymous_question_gists is invalid type {type(synonymous_question_gists)}, defaulting to empty OrderedDict" )
            synonymous_question_gists = OrderedDict()
            
        if len( synonymous_question_gists ) == 0:
            synonymous_question_gists[ question_gist ] = 100.0
            self.synonymous_question_gists = synonymous_question_gists
        else:
            self.synonymous_question_gists = synonymous_question_gists
            
        self.non_synonymous_questions = non_synonymous_questions
            
        self.last_question_asked   = last_question_asked
        
        self.solution_summary      = solution_summary
        
        self.code                  = code
        self.code_returns          = code_returns
        self.code_example          = code_example
        self.code_type             = code_type
        
        # metadata surrounding the question and the solution
        self.updated_date          = updated_date
        self.created_date          = created_date
        self.run_date              = run_date
        self.runtime_stats         = runtime_stats
        
        if id_hash == "":
            self.id_hash           = SolutionSnapshot.generate_id_hash( self.push_counter, self.run_date )
        else:
            self.id_hash           = id_hash
        self.programming_language  = programming_language
        self.language_version      = language_version
        self.solution_directory    = solution_directory
        self.solution_file         = solution_file
        
        # If the question embedding is empty, generate it
        if question != "" and not question_embedding:
            self.question_embedding = self._embedding_mgr.generate_embedding( question, normalize_for_cache=True )
            dirty = True
        else:
            self.question_embedding = question_embedding
            
        # If the gist embedding is empty, generate it
        if question_gist != "" and not question_gist_embedding:
            self.question_gist_embedding = self._embedding_mgr.generate_embedding( question_gist, normalize_for_cache=True )
            dirty = True
        else:
            self.question_gist_embedding = question_gist_embedding
        
        # If the code embedding is empty, generate it
        if code and not code_embedding:
            self.code_embedding = self._embedding_mgr.generate_embedding( " ".join( code ), normalize_for_cache=False )
            dirty = True
        else:
            self.code_embedding = code_embedding
    
        # If the solution embedding is empty, generate it
        if solution_summary and not solution_embedding:
            self.solution_embedding = self._embedding_mgr.generate_embedding( solution_summary, normalize_for_cache=True )
            dirty = True
        else:
            self.solution_embedding = solution_embedding

        # If the thoughts embedding is empty, generate it
        if thoughts and not thoughts_embedding:
            self.thoughts_embedding = self._embedding_mgr.generate_embedding( thoughts, normalize_for_cache=True )
            dirty = True
        else:
            self.thoughts_embedding = thoughts_embedding
            
        # Save changes if we've made any change as while loading
        if dirty: self.write_current_state_to_file()
        
    @classmethod
    def from_json_file( cls, filename: str, debug: bool=False ) -> 'SolutionSnapshot':
        """
        Load snapshot from JSON file.
        
        Requires:
            - filename is a valid file path
            - File contains valid JSON data
            
        Ensures:
            - Returns new SolutionSnapshot instance
            - All fields populated from JSON data
            
        Raises:
            - FileNotFoundError if file doesn't exist
            - JSONDecodeError if invalid JSON
        """
        if debug: print( f"Reading {filename}..." )
        with open( filename, "r" ) as f:
            data = json.load( f )
        
        return cls( **data )
    
    @classmethod
    def create( cls, agent: Any ) -> 'SolutionSnapshot':
        """
        Create snapshot from agent instance.
        
        Requires:
            - agent has required attributes (question, code, etc.)
            - agent.prompt_response_dict is populated
            
        Ensures:
            - Returns new SolutionSnapshot with agent data
            - Copies all relevant fields from agent
            
        Raises:
            - AttributeError if agent missing required fields
        """
        print( "(create_solution_snapshot) TODO: Reconcile how we're going to get a dynamic path to the solution file's directory" )
        
        # Instantiate a new SolutionSnapshot object using the contents of the calendaring or function mapping agent
        return SolutionSnapshot(
                         question=agent.question,
                    question_gist=agent.question_gist,
              last_question_asked=agent.last_question_asked,
                  routing_command=agent.routing_command,
             synonymous_questions=OrderedDict( { agent.question: 100.0 } ),
        synonymous_question_gists=OrderedDict( { agent.question_gist: 100.0 } ),
                            error=agent.prompt_response_dict.get( "error", "" ),
                 solution_summary=agent.prompt_response_dict.get( "explanation", "N/A" ),
                             code=agent.prompt_response_dict.get( "code", "N/A" ),
                     code_returns=agent.prompt_response_dict.get( "returns", "N/A" ),
                     code_example=agent.prompt_response_dict.get( "example", "N/A" ),
                         thoughts=agent.prompt_response_dict.get( "thoughts", "N/A" ),
                           answer=agent.code_response_dict.get( "output", "N/A" ),
            answer_conversational=agent.answer_conversational
               
               # TODO: Reconcile how we're going to get a dynamic path to the solution file's directory
               # solution_directory=calendaring_agent.solution_directory
        )
    
    def add_synonymous_question( self, question: str, salutation: str="", score: float=100.0 ) -> None:
        """
        Add a synonymous question to the snapshot.
        
        Requires:
            - question is a non-empty string
            - score is between 0 and 100
            
        Ensures:
            - Adds question to synonymous_questions if not present
            - Updates last_question_asked with full text
            - Updates timestamp if question added
            
        Raises:
            - None
        """
        # We're doing a mechanical peel off of the salutation before it even gets here, and adding it back in for conversationality sake here
        # Also: Add last question in unmodified form before cleaning it
        if len( salutation ) > 0:
            self.last_question_asked = salutation + " " + question
        else:
            self.last_question_asked = question
        
        question = SolutionSnapshot.remove_non_alphanumerics( question )
        
        if question not in self.synonymous_questions:
            self.synonymous_questions[ question ] = score
            self.updated_date = self.get_timestamp()
        else:
            print( f"Question [{question}] is already listed as a synonymous question." )
        
    def get_last_synonymous_question( self ) -> str:
        """
        Get the most recently added synonymous question.
        
        Requires:
            - synonymous_questions is not empty
            
        Ensures:
            - Returns last question in ordered dict
            
        Raises:
            - IndexError if no synonymous questions
        """
        return list( self.synonymous_questions.keys() )[ -1 ]
        
    def complete( self, answer: str, code: list[str]=[ ], solution_summary: str="" ) -> None:
        """
        Complete the snapshot with execution results.
        
        Requires:
            - answer is a string
            - code is a list of strings
            - solution_summary is a string
            
        Ensures:
            - Sets answer, code, and solution summary
            - Generates embeddings for code and summary
            
        Raises:
            - None
        """
        self.answer = answer
        self.set_code( code )
        self.set_solution_summary( solution_summary )
        # self.completion_date  = SolutionSnapshot.get_current_datetime()
        
    def set_solution_summary( self, solution_summary: str ) -> None:
        """
        Set solution summary and generate embedding.
        
        Requires:
            - solution_summary is a string
            
        Ensures:
            - Updates solution_summary field
            - Generates new embedding
            - Updates timestamp
            
        Raises:
            - None
        """
        self.solution_summary = solution_summary
        self.solution_embedding = self._embedding_mgr.generate_embedding( solution_summary, normalize_for_cache=True )
        self.updated_date = self.get_timestamp()

    def set_code( self, code: list[str] ) -> None:
        """
        Set code and generate embedding.
        
        Requires:
            - code is a list of strings
            
        Ensures:
            - Updates code field
            - Generates embedding from joined code
            - Updates timestamp
            
        Raises:
            - None
        """
        # ¡OJO! code is a list of strings, not a string!
        self.code           = code
        self.code_embedding = self._embedding_mgr.generate_embedding( " ".join( code ), normalize_for_cache=False )
        self.updated_date   = self.get_timestamp()
    
    def get_question_similarity( self, other_snapshot: 'SolutionSnapshot' ) -> float:
        """
        Calculate question similarity with another snapshot.
        
        Requires:
            - Both snapshots have question embeddings
            
        Ensures:
            - Returns similarity score as percentage (0-100)
            - Uses dot product calculation
            
        Raises:
            - ValueError if either embedding is missing
        """
        if not self.question_embedding or not other_snapshot.question_embedding:
            raise ValueError( "Both snapshots must have a question embedding to compare." )
        return np.dot( self.question_embedding, other_snapshot.question_embedding ) * 100
    
    def get_question_gist_similarity( self, other_snapshot: 'SolutionSnapshot' ) -> float:
        """
        Calculate question gist similarity with another snapshot.
        
        Requires:
            - Both snapshots have question gist embeddings
            
        Ensures:
            - Returns similarity score as percentage (0-100)
            - Uses dot product calculation
            
        Raises:
            - ValueError if either embedding is missing
        """
        if not self.question_gist_embedding or not other_snapshot.question_gist_embedding:
            raise ValueError( "Both snapshots must have a question gist embedding to compare." )
        
        return np.dot( self.question_gist_embedding, other_snapshot.question_gist_embedding ) * 100
    
    def get_solution_summary_similarity( self, other_snapshot: 'SolutionSnapshot' ) -> float:
        """
        Calculate solution summary similarity with another snapshot.
        
        Requires:
            - Both snapshots have solution embeddings
            
        Ensures:
            - Returns similarity score as percentage (0-100)
            - Uses dot product calculation
            
        Raises:
            - ValueError if either embedding is missing
        """
        if not self.solution_embedding or not other_snapshot.solution_embedding:
            raise ValueError( "Both snapshots must have a solution summary embedding to compare." )
        
        return np.dot( self.solution_embedding, other_snapshot.solution_embedding ) * 100
    
    def get_code_similarity( self, other_snapshot: 'SolutionSnapshot' ) -> float:
        """
        Calculate code similarity with another snapshot.
        
        Requires:
            - Both snapshots have code embeddings
            
        Ensures:
            - Returns similarity score as percentage (0-100)
            - Uses dot product calculation
            
        Raises:
            - ValueError if either embedding is missing
        """
        if not self.code_embedding or not other_snapshot.code_embedding:
            raise ValueError( "Both snapshots must have a code embedding to compare." )
        
        return np.dot( self.code_embedding, other_snapshot.code_embedding ) * 100
    
    def to_jsons( self, verbose: bool=True ) -> str:
        """
        Serialize snapshot to JSON string.
        
        Requires:
            - Object is properly initialized
            
        Ensures:
            - Returns valid JSON string
            - Excludes non-serializable fields
            - All data preserved for loading
            
        Raises:
            - JSON serialization errors
        """
        # TODO: decide what we're going to exclude from serialization, and why or why not!
        # Right now I'm just doing this for the sake of expediency as I'm playing with class inheritance for agents
        fields_to_exclude = [ "prompt_response", "prompt_response_dict", "code_response_dict", "phind_tgi_url", "config_mgr", "_embedding_mgr", "websocket_id", "user_id" ]
        data = { field: value for field, value in self.__dict__.items() if field not in fields_to_exclude }
        return json.dumps( data )
        
    def get_copy( self ) -> 'SolutionSnapshot':
        """
        Get shallow copy of snapshot.
        
        Requires:
            - None
            
        Ensures:
            - Returns new instance with same values
            - Shallow copy (references shared)
            
        Raises:
            - None
        """
        return copy.copy( self )
    
    def get_html( self ) -> str:
        """
        Get HTML representation of snapshot.
        
        Requires:
            - id_hash, run_date, last_question_asked are set
            
        Ensures:
            - Returns HTML list item string
            - Includes play and delete spans
            
        Raises:
            - None
        """
        return f"<li id='{self.id_hash}'><span class='play'>{self.run_date} Q: {self.last_question_asked}</span> <span class='delete'></span></li>"
     
    def write_current_state_to_file( self ) -> None:
        """
        Write snapshot to JSON file.
        
        Requires:
            - solution_directory is valid path
            - All required fields populated
            
        Ensures:
            - Creates JSON file with snapshot data
            - Generates unique filename if needed
            - Sets file permissions to 0o666
            
        Raises:
            - OSError if file operations fail
        """
        # Get the project root directory
        project_root = du.get_project_root()
        # Define the directory where the file will be saved
        directory = f"{project_root}{self.solution_directory}"
        
        if self.solution_file is None:
            
            print( "NO solution_file value provided (Must be a new object). Generating a unique file name..." )
            # Generate filename based on the first 64 characters of the question
            # filename_base = du.truncate_string( self.question, max_len=64 ).replace( " ", "-" )
            filename_base = du.truncate_string( self.remove_non_alphanumerics( self.question, replacement_char="_" ), max_len=64 ).replace( " ", "-" )
            # Get a list of all files that start with the filename base
            existing_files = glob.glob( f"{directory}{filename_base}-*.json" )
            # The count of existing files will be used to make the filename unique
            file_count = len( existing_files )
            # generate the file name
            filename = f"{filename_base}-{file_count}.json"
            self.solution_file = filename
        
        else:
            
            print( f"solution_file value provided: [{self.solution_file}]..." )
        
        # Generate the full file path
        file_path = f"{directory}{self.solution_file}"
        # Print the file path for debugging purposes
        print( f"File path: {file_path}", end="\n\n" )
        # Write the JSON string to the file
        with open( file_path, "w" ) as f:
            f.write( self.to_jsons() )
        
        # Set the file permissions to world-readable and writable
        os.chmod( file_path, 0o666 )
        
    def delete_file( self ) -> None:
        """
        Delete snapshot file from filesystem.
        
        Requires:
            - solution_file and solution_directory are set
            
        Ensures:
            - Removes file if it exists
            - Prints status message
            
        Raises:
            - None (handles errors internally)
        """
        file_path = f"{du.get_project_root()}{self.solution_directory}{self.solution_file}"
        
        if os.path.isfile( file_path ):
            os.remove( file_path )
            print( f"Deleted file [{file_path}]" )
        else:
            print( f"File [{file_path}] does not exist" )
            
    def update_runtime_stats( self, timer ) -> None:
        """
        Updates the runtime stats for this object
        
        Uses the timer object to calculate the delta between now and when this object was instantiated

        :return: None
        """
        delta_ms = timer.get_delta_ms()
        
        # We're now tracking the first time which is expensive to calculate, after that we're tracking all subsequent cashed runs
        if self.runtime_stats[ "run_count" ] == -1:
            self.runtime_stats[ "first_run_ms"  ]  = delta_ms
            self.runtime_stats[ "run_count"     ]  = 0
        else:
            self.runtime_stats[ "run_count"     ] += 1
            self.runtime_stats[ "total_ms"      ] += delta_ms
            self.runtime_stats[ "mean_run_ms"   ]  = int( self.runtime_stats[ "total_ms" ] / self.runtime_stats[ "run_count" ] )
            self.runtime_stats[ "last_run_ms"   ]  = delta_ms
            self.runtime_stats[ "time_saved_ms" ]  = ( self.runtime_stats[ "first_run_ms" ] * self.runtime_stats[ "run_count" ] ) - self.runtime_stats[ "total_ms" ]
    
    def run_code( self, debug: bool=False, verbose: bool=False ) -> dict:
        """
        Execute stored code.
        
        Requires:
            - code, code_example, code_returns are populated
            - routing_command determines data file path
            
        Ensures:
            - Executes code using code runner
            - Updates answer with output
            - Returns code response dictionary
            
        Raises:
            - Code execution errors propagated
        """
        if self.routing_command == "agent router go to todo list":
            path_to_df = "/src/conf/long-term-memory/todo.csv"
        elif self.routing_command == "agent router go to calendar":
            path_to_df = "/src/conf/long-term-memory/events.csv"
        else:
            path_to_df = None
            
        self.code_response_dict = ucr.assemble_and_run_solution(
            self.code, self.code_example, solution_code_returns=self.code_returns, path_to_df=path_to_df, debug=debug
        )
        self.answer             = self.code_response_dict[ "output" ]
        
        if debug and verbose:
            du.print_banner( "Code output", prepend_nl=True )
            for line in self.code_response_dict[ "output" ].split( "\n" ):
                print( line )
        
        return self.code_response_dict
    
    def run_formatter( self ) -> str:
        """
        Format raw output for conversational response.
        
        Requires:
            - last_question_asked, answer, routing_command are set
            
        Ensures:
            - Creates formatted conversational answer
            - Extracts rephrased answer if available
            - Returns formatted string
            
        Raises:
            - None
        """
        # du.print_banner( f"Formatting output for {self.routing_command}" )
        formatter                  = RawOutputFormatter( self.last_question_asked, self.answer, self.routing_command, debug=self.debug, verbose=self.verbose )
        self.answer_conversational = formatter.run_formatter()
        
        if self.debug and self.verbose: print( f" PRE self.answer_conversational: [{self.answer_conversational}]" )
        self.answer_conversational = dux.get_value_by_xml_tag_name( self.answer_conversational, "rephrased-answer", default_value=self.answer_conversational )
        if self.debug and self.verbose: print( f"POST self.answer_conversational: [{self.answer_conversational}]" )
        
        return self.answer_conversational
    
    def formatter_ran_to_completion( self ) -> bool:
        """
        Check if formatter completed successfully.
        
        Requires:
            - None
            
        Ensures:
            - Returns True if answer_conversational is set
            - Returns False otherwise
            
        Raises:
            - None
        """
        return self.answer_conversational is not None
    
def quick_smoke_test():
    """Quick smoke test to validate SolutionSnapshot functionality."""
    du.print_banner( "SolutionSnapshot Smoke Test", prepend_nl=True )
    
    # Test embedding generation
    print( "Testing embedding generation..." )
    embedding_mgr = EmbeddingManager( debug=True )
    embedding = embedding_mgr.generate_embedding( "what time is it", normalize_for_cache=True )
    if embedding:
        print( f"✓ Generated embedding with {len( embedding )} dimensions" )
    else:
        print( "✗ Failed to generate embedding" )
    
    # Test basic snapshot creation
    print( "\nTesting snapshot creation..." )
    today = SolutionSnapshot( question="what day is today" )
    print( f"✓ Created snapshot with ID: {today.id_hash}" )
    
    # Test similarity scoring between snapshots
    print( "\nTesting similarity scoring..." )
    tomorrow = SolutionSnapshot( question="what day is tomorrow" )
    blah = SolutionSnapshot( question="i feel so blah today" )
    
    snapshots = [ today, tomorrow, blah ]
    
    for snapshot in snapshots:
        if today.question_embedding and snapshot.question_embedding:
            score = today.get_question_similarity( snapshot )
            print( f"Score: [{score:.1f}] for '{snapshot.question}' vs '{today.question}'" )
    
    print( "\n✓ SolutionSnapshot smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()
