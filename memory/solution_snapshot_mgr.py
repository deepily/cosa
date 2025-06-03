import os
from typing import Optional, Any

import cosa.utils.util as du
from cosa.memory import solution_snapshot as ss
# from lib.memory.question_embeddings_dict import QuestionEmbeddingsDict
from cosa.memory.question_embeddings_table import QuestionEmbeddingsTable


class SolutionSnapshotManager:
    """
    Manages solution snapshots stored as JSON files.
    
    Handles loading, searching, and managing solution snapshots with
    embedding-based similarity search capabilities.
    """
    def __init__( self, path: str, debug: bool=False, verbose: bool=False ) -> None:
        """
        Initialize the solution snapshot manager.
        
        Requires:
            - path is a valid directory path
            - Directory contains JSON snapshot files
            
        Ensures:
            - Loads all snapshots from directory
            - Creates lookup dictionaries by question and gist
            - Initializes embeddings table
            
        Raises:
            - OSError if directory doesn't exist
        """
        
        self.debug                              = debug
        self.verbose                            = verbose
        self.path                               = path
       
        self._snapshots_by_question             = None
        self._snapshots_by_synonymous_questions = None
        self._snapshots_by_question_gist        = None
        self._question_embeddings_tbl           = None
        
        self.load_snapshots()
        
    def load_snapshots( self ) -> None:
        """
        Load all snapshots from the directory.
        
        Requires:
            - self.path is set
            - Directory exists
            
        Ensures:
            - Populates all snapshot dictionaries
            - Initializes embeddings table
            - Prints debug info if enabled
            
        Raises:
            - None (handles errors internally)
        """
        self._snapshots_by_question             = self._load_snapshots_by_question()
        self._snapshots_by_synonymous_questions = self._load_snapshots_by_synonymous_questions( self._snapshots_by_question )
        self._snapshots_by_question_gist        = self._load_snapshots_by_gist( self._snapshots_by_question )
        self._question_embeddings_tbl           = QuestionEmbeddingsTable()
        
        if self.debug:
            print( self )
            if self.verbose: self.print_snapshots()
        
    def _load_snapshots_by_question( self ) -> dict[str, Any]:
        """
        Load snapshots indexed by question.
        
        Requires:
            - self.path is a valid directory
            - Directory contains JSON files
            
        Ensures:
            - Returns dict mapping questions to snapshots
            - Filters out hidden files and non-JSON files
            
        Raises:
            - None (handles errors internally)
        """
        snapshots_by_question = { }
        if self.debug: print( f"Loading snapshots by question from [{self.path}]..." )
        
        filtered_files = [ file for file in os.listdir( self.path ) if not file.startswith( "._" ) and file.endswith( ".json" ) ]
        if self.debug and self.verbose: du.print_list( filtered_files )
        
        for file in filtered_files:
            json_file = os.path.join( self.path, file )
            snapshot = ss.SolutionSnapshot.from_json_file( json_file, debug=self.debug )
            snapshots_by_question[ snapshot.question ] = snapshot
    
        return snapshots_by_question
    
    def _load_snapshots_by_gist( self, snapshots_by_question: dict[str, Any] ) -> dict[str, tuple[float, Any]]:
        """
        Create gist-based index of snapshots.
        
        Requires:
            - snapshots_by_question is populated
            
        Ensures:
            - Returns dict mapping gists to (score, snapshot) tuples
            - Includes all synonymous gists
            
        Raises:
            - None
        """
        snapshots_by_gist = { }
        if self.debug: print( f"Loading by gist snapshots from [{self.path}]..." )
        
        for _, snapshot in snapshots_by_question.items():
            for question, similarity_score in snapshot.synonymous_question_gists.items():
                snapshots_by_gist[ question ] = ( similarity_score, snapshot )
        
        du.print_banner( f"Found [{len( snapshots_by_gist )}] synonymous gists", prepend_nl=True )
        # print out all synonymous gists that are not the same as the gist
        for question_gist in snapshots_by_gist.keys():
            # if question_gist != snapshots_by_gist[ question_gist ][ 1 ].question_gist:
            print( f"Q [{snapshots_by_gist[ question_gist ][ 1 ].question}] has synonymous gist [{question_gist}]" )
        print()
        return snapshots_by_gist
    
    def _load_snapshots_by_synonymous_questions( self, snapshots_by_question: dict[str, Any] ) -> dict[str, tuple[float, Any]]:
        """
        Create synonymous question index.
        
        Requires:
            - snapshots_by_question is populated
            
        Ensures:
            - Returns dict mapping synonymous questions to (score, snapshot) tuples
            - Includes all synonymous questions from snapshots
            
        Raises:
            - None
        """
        snapshots_by_synomymous_questions = { }
        
        for _, snapshot in snapshots_by_question.items():
            for question, similarity_score in snapshot.synonymous_questions.items():
                snapshots_by_synomymous_questions[ question ] = ( similarity_score, snapshot )
                
        du.print_banner( f"Found [{len( snapshots_by_synomymous_questions )}] synonymous questions", prepend_nl=True )
        # print out all synonymous questions that are not the same as the question
        for question in snapshots_by_synomymous_questions.keys():
            if question != snapshots_by_synomymous_questions[ question ][ 1 ].question:
                print( f"Snapshot Q [{snapshots_by_synomymous_questions[ question ][ 1 ].question}] has synonymous Q [{question}]" )
            
        print()
        return snapshots_by_synomymous_questions
    
    def add_snapshot( self, snapshot: ss.SolutionSnapshot ) -> None:
        """
        Add a new snapshot to the manager.
        
        Requires:
            - snapshot is a valid SolutionSnapshot
            - snapshot.question is set
            
        Ensures:
            - Adds snapshot to question index
            - Writes snapshot to file
            
        Raises:
            - None
        """
        self._snapshots_by_question[ snapshot.question ] = snapshot
        snapshot.write_current_state_to_file()
    
    # ¡OJO! Doesn't appear to be called by anything
    # get the questions embedding if it exists otherwise generate it and add it to the dictionary
    # def get_question_embedding( self, question ):
    #
    #     if self.question_embeddings_tbl.has( question ):
    #         return self.question_embeddings_tbl[ question ]
    #     else:
    #         question_embedding = ss.SolutionSnapshot.generate_embedding( question )
    #
    #     return question_embedding
    
    def _question_exists( self, question: str ) -> bool:
        """
        Check if exact question exists.
        
        Requires:
            - question is a string
            
        Ensures:
            - Returns True if question in index
            - Returns False otherwise
            
        Raises:
            - None
        """
        return question in self._snapshots_by_question
    
    def _synonymous_question_exists( self, question: str ) -> bool:
        """
        Check if synonymous question exists.
        
        Requires:
            - question is a string
            
        Ensures:
            - Returns True if in synonymous questions
            - Returns False otherwise
            
        Raises:
            - None
        """
        return question in self._snapshots_by_synonymous_questions
    
    def _question_gist_exists( self, question_gist: Optional[str] ) -> bool:
        """
        Check if question gist exists.
        
        Requires:
            - question_gist may be None or string
            
        Ensures:
            - Returns True if gist exists in index
            - Returns False if None or not found
            
        Raises:
            - None
        """
        if self.debug: print( f"question_gist is not None: {question_gist is not None} and question_gist in self._snapshots_by_question_gist: {question_gist in self._snapshots_by_question_gist} " )
        return question_gist is not None and question_gist in self._snapshots_by_question_gist
    
    def get_gists( self ) -> list[str]:
        """
        Get all question gists.
        
        Requires:
            - Gist index is populated
            
        Ensures:
            - Returns list of all gist strings
            
        Raises:
            - None
        """
        return list(self._snapshots_by_question_gist.keys())
    
    def delete_snapshot( self, question: str, delete_file: bool=False ) -> bool:
        """
        Delete a snapshot by question.
        
        Requires:
            - question is a string
            
        Ensures:
            - Removes snapshot from index if found
            - Optionally deletes file from filesystem
            - Returns True if deleted, False if not found
            
        Raises:
            - None
        """
        # clean up the question string before querying
        question = ss.SolutionSnapshot.remove_non_alphanumerics( question )
        
        if self._question_exists( question ):
            if delete_file:
                print( f"Deleting snapshot file [{question}]...", end="" )
                snapshot = self._snapshots_by_question[ question ]
                snapshot.delete_file()
                print( "Done!" )
            return True
            print( f"Deleting snapshot from manager [{question}]...", end="" )
            del self._snapshots_by_question[ question ]
            print( "Done!" )
        else:
            print( f"Snapshot with question [{question}] does not exist!" )
            return False
        
    def _get_snapshots_by_question_similarity( self, question: str, question_gist: Optional[str]=None, threshold_question: float=100.0, threshold_gist: float=100.0, limit: int=7, exclude_non_synonymous_questions: bool=True ) -> list[tuple[float, Any]]:
        """
        Find similar snapshots using embeddings.
        
        Requires:
            - question is a non-empty string
            - thresholds are between 0 and 100
            - limit is positive integer
            
        Ensures:
            - Returns list of (score, snapshot) tuples
            - Sorted by similarity descending
            - Limited to requested count
            - Excludes blacklisted questions if requested
            
        Raises:
            - None
        """
        print( f"_get_snapshots_by_question_similarity( '{question}' )..." )
        
        # Generate the embedding for the question if it doesn't already exist
        if not self._question_embeddings_tbl.has( question ):
            question_embedding = ss.SolutionSnapshot.generate_embedding( question )
            self._question_embeddings_tbl.add_embedding( question, question_embedding )
        else:
            print( f"Embedding for question [{question}] already exists!" )
            question_embedding = self._question_embeddings_tbl.get_embedding( question )
            
        # generate the embedding for the question gist if it doesn't already exist
        question_gist_embedding = [ ]
        if question_gist is not None and not self._question_embeddings_tbl.has( question_gist ):
            question_gist_embedding = ss.SolutionSnapshot.generate_embedding( question_gist )
            self._question_embeddings_tbl.add_embedding( question_gist, question_gist_embedding )
        else:
            print( f"Embedding for question gist [{question_gist}] already exists!" )
            question_gist_embedding = self._question_embeddings_tbl.get_embedding( question_gist )
        if self.debug and self.verbose: print( f"question_gist_embedding: {question_gist_embedding[0:16]}" )
            
        similar_snapshots  = [ ]
        
        # Iterate the snapshots and compare the question embeddings
        for snapshot in self._snapshots_by_question.values():
            
            if exclude_non_synonymous_questions and question in snapshot.non_synonymous_questions:
                if self.debug:
                    du.print_banner( f"Snapshot [{question}] is in the NON synonymous list!", prepend_nl=True)
                    print( f"Snapshot [{question}] has been blacklisted by [{snapshot.question}]" )
                    print( "Continuing to next snapshot..." )
                continue
                
            similarity_score = ss.SolutionSnapshot.get_embedding_similarity( question_embedding, snapshot.question_embedding )
            
            if similarity_score >= threshold_question:
                similar_snapshots.append( ( similarity_score, snapshot ) )
                if self.debug: print( f"Score [{similarity_score:.2f}]% for question [{snapshot.question}] IS similar enough to [{question}]" )
            else:
                if self.debug and self.verbose: print( f"Score [{similarity_score:.2f}]% for question [{snapshot.question}] is NOT similar enough to [{question}]" )
        
        # Iterate snapshots by question gist and compare the embeddings
        if question_gist is not None:
            for snapshot in self._snapshots_by_question_gist.values():
                similarity_score = ss.SolutionSnapshot.get_embedding_similarity( question_gist_embedding, snapshot[ 1 ].question_embedding )
                if similarity_score >= threshold_gist:
                    similar_snapshots.append( ( similarity_score, snapshot[ 1 ] ) )
                    if self.debug:
                        print( f"Score [{similarity_score:.2f}]% for gist [{snapshot[ 1 ].question_gist}] IS similar enough to [{question_gist}]" )
                        # print( f"[{question}] ~= [{snapshot[ 1 ].question}]" )
                else:
                    if self.debug and self.verbose: print( f"Score [{similarity_score:.2f}]% for gist [{snapshot[ 1 ].question_gist}] is NOT similar enough to [{question_gist}]" )

        # Sort by similarity score, descending
        similar_snapshots.sort( key=lambda x: x[ 0 ], reverse=True )
        
        print()
        if len( similar_snapshots ) > 0:
            du.print_banner( f"Found [{len( similar_snapshots )}] similar snapshots for question [{question}]", prepend_nl=True )
            for snapshot in similar_snapshots:
                print( f"Score [{snapshot[ 0 ]:.2f}]% for [{question}] == [{snapshot[ 1 ].question}]" )
        else:
            print( f"Could NOT find any snapshots similar to Q [{question}] G [{question_gist}]" )
        
        return similar_snapshots[ :limit ]
    
    def get_snapshots_by_code_similarity( self, exemplar_snapshot: ss.SolutionSnapshot, threshold: float=85.0, limit: int=-1 ) -> list[tuple[float, Any]]:
        """
        Find snapshots with similar code.
        
        Requires:
            - exemplar_snapshot has code_embedding
            - threshold is between 0 and 100
            
        Ensures:
            - Returns list of (score, snapshot) tuples
            - Sorted by similarity descending
            - Limited to requested count (-1 for all)
            
        Raises:
            - None
        """
        # code_snapshot      = ss.SolutionSnapshot( code_embedding=source_snapshot.code_embedding )
        original_question = du.truncate_string( exemplar_snapshot.question, max_len=32 )
        similar_snapshots  = [ ]
        
        # Iterate the code in the code list and print it to the console
        if self.debug and self.verbose:
            du.print_banner( f"Source code for [{original_question}]:", prepend_nl=True)
            for line in exemplar_snapshot.code: print( line )
            print()
        
        for snapshot in self._snapshots_by_question.values():
            
            similarity_score   = snapshot.get_code_similarity( exemplar_snapshot )
            question_truncated = du.truncate_string( snapshot.question, max_len=32 )
            
            if similarity_score >= threshold:
                
                similar_snapshots.append( ( similarity_score, snapshot ) )
                if self.debug and self.verbose:
                    du.print_banner( f"Code score [{similarity_score}] for snapshot [{question_truncated}] IS similar to the provided code", end="\n" )
                    du.print_list( snapshot.code )
            else:
                if self.debug:
                    print( f"Code score [{similarity_score}] for snapshot [{question_truncated}] is NOT similar to the provided code", end="\n" )
            
        # Sort by similarity score, descending
        similar_snapshots.sort( key=lambda x: x[ 0 ], reverse=True )
        
        print()
        for snapshot in similar_snapshots:
            print( f"Code similarity score [{snapshot[ 0 ]}] for [{original_question}] == [{du.truncate_string( snapshot[ 1 ].question, max_len=32 )}]" )
        
        if limit == -1:
            return similar_snapshots
        else:
            return similar_snapshots[ :limit ]
    
    def get_snapshots_by_question( self, question: str, question_gist: Optional[str]=None, threshold_question: float=100.0, threshold_gist: float=100.0, limit: int=7, debug: bool=False ) -> list[tuple[float, Any]]:
        """
        Find snapshots matching a question.
        
        Requires:
            - question is a non-empty string
            - thresholds are between 0 and 100
            
        Ensures:
            - Returns list of (score, snapshot) tuples
            - Checks exact match, synonyms, gists, then similarity
            - Limited to requested count
            
        Raises:
            - None
        """
        question = ss.SolutionSnapshot.remove_non_alphanumerics( question )
        
        # escape single quotes in the question gist, instead of nuking all the valuable non-alphanumeric characters in a gist string
        if question_gist is not None:
            question_gist = ss.SolutionSnapshot.escape_single_quotes( question_gist )
            du.print_banner( f"Escaped question_gist: [{question_gist}]", prepend_nl=True )
        # question_gist = ss.SolutionSnapshot.remove_non_alphanumerics( question_gist )
        print( f"get_snapshots_by_question( '{question}', '{question_gist}', with threshold_question [{threshold_question}] and threshold_gist [{threshold_gist}] )..." )
        
        # Check if the question exists in the snapshot dictionary, if it does, return it
        if self._question_exists( question ):
            
            if debug: print( f"Exact match: Snapshot with question [{question}] exists!" )
            similar_snapshots = [ (100.0, self._snapshots_by_question[ question ]) ]
            
        # Check if the question exists in the synonymous questions dictionary, if it does, return it
        elif self._synonymous_question_exists( question ) and self._snapshots_by_synonymous_questions[ question ][ 0 ] >= threshold_question:
            
            score    = self._snapshots_by_synonymous_questions[ question ][ 0 ]
            snapshot = self._snapshots_by_synonymous_questions[ question ][ 1 ]
            similar_snapshots = [ (score, snapshot) ]
            print( f"Snapshot with synonymous question for [{question}] exists: [{snapshot.question}] similarity score [{score}] >= [{threshold_question}]" )
            
        # Check if the gist exists in the gist dictionary, if it does, return it
        elif self._question_gist_exists( question_gist ) and self._snapshots_by_question_gist[ question_gist ][ 0 ] >= threshold_gist:
            
            score    = self._snapshots_by_question_gist[ question_gist ][ 0 ]
            snapshot = self._snapshots_by_question_gist[ question_gist ][ 1 ]
            similar_snapshots = [ (score, snapshot) ]
            print( f"Snapshot with gist for [{question}] exists: [{snapshot.question_gist}] similarity score [{score}] >= [{threshold_gist}]" )
        
        else:
            print( "No exact match, synonymous question or exact gist found, searching for similar questions and gists..." )
            similar_snapshots = self._get_snapshots_by_question_similarity( question, question_gist=question_gist, threshold_question=threshold_question, threshold_gist=threshold_gist, limit=limit )
        
        if len( similar_snapshots ) > 0:
            
            if debug: print( f"Found [{len( similar_snapshots )}] similar snapshots" )
            for snapshot in similar_snapshots:
                if debug: print( f"score [{snapshot[ 0 ]}] for [{question}] == [{snapshot[ 1 ].question}]" )
        else:
            if debug: print( f"Could not find any snapshots similar to [{question}]" )
            
        return similar_snapshots
        
    def __str__( self ) -> str:
        """
        String representation of manager.
        
        Requires:
            - None
            
        Ensures:
            - Returns formatted string with count and path
            
        Raises:
            - None
        """
        return f"[{len( self._snapshots_by_question )}] snapshots by question loaded from [{self.path}]"

    def print_snapshots( self ) -> None:
        """
        Print all loaded snapshots.
        
        Requires:
            - Snapshots are loaded
            
        Ensures:
            - Prints count and questions to console
            
        Raises:
            - None
        """
        du.print_banner( f"Total snapshots: [{len( self._snapshots_by_question )}]", prepend_nl=True )
        
        for question, snapshot in self._snapshots_by_question.items():
            print( f"Question: [{question}]" )
            
        print()

if __name__ == "__main__":
    
    path_to_snapshots = du.get_project_root() + "/src/conf/long-term-memory/solutions/"
    snapshot_mgr = SolutionSnapshotManager( path_to_snapshots, debug=False )
    # print( snapshot_mgr )
    
    # exemplar_snapshot = snapshot_mgr.get_snapshots_by_question( "What concerts do I have this week?" )[ 0 ][ 1 ]
    #
    # similar_snapshots = snapshot_mgr.get_snapshots_by_code_similarity( exemplar_snapshot, threshold=90.0 )
    
    # questions = [
    #     "what day comes after tomorrow?",
    #     "what day is today?",
    #     "Why is the sky blue?",
    #     "What's today's date?",
    #     "What is today's date?"
    # ]
    # for question in questions:
    #
    #     du.print_banner( f"Question: [{question}]", prepend_nl=True )
    #     similar_snapshots = snapshot_mgr.get_snapshots_by_question( question )
    #
    #     if len( similar_snapshots ) > 0:
    #             lines_of_code = similar_snapshots[ 0 ][ 1 ].code
    #             for line in lines_of_code:
    #                 print( line )
        
        