from typing import Optional, Any

import cosa.utils.util as du
import cosa.utils.util_code_runner as ucr

class RunnableCode:
    """
    Base class for agents that can execute generated code.
    
    Provides common functionality for code execution, validation,
    and result handling.
    """
    
    def __init__( self, debug: bool=False, verbose: bool=False ) -> None:
        """
        Initialize runnable code base class.
        
        Requires:
            - None
            
        Ensures:
            - Initializes debug and verbose flags
            - Sets up empty response dictionaries
            - Initializes error and answer attributes
            
        Raises:
            - None
        """
        
        self.debug                = debug
        self.verbose              = verbose
        
        self.prompt_response      = None
        self.prompt_response_dict = None
        
        self.code_response_dict   = None
        self.answer               = None
        self.error                = None

    def print_code( self, msg: str="Code", end: Optional[str]=None ) -> None:
        """
        Print formatted code listing with line numbers.
        
        Requires:
            - self.prompt_response_dict contains 'code' list
            
        Ensures:
            - Prints code with banner and line numbers
            - Optionally adds custom end string
            
        Raises:
            - KeyError if 'code' not in response dict
        """
        
        du.print_banner( msg, prepend_nl=True )
        du.print_list( self.prompt_response_dict[ "code" ] )
        
        if end is not None: print( end=end )
    
    def is_code_runnable( self ) -> bool:
        """
        Check if code is available to run.
        
        Requires:
            - self.prompt_response_dict is initialized
            
        Ensures:
            - Returns True if code list is non-empty
            - Returns False and prints message if no code
            
        Raises:
            - None
        """
        
        if self.prompt_response_dict is not None and self.prompt_response_dict[ "code" ] != []:
            return True
        else:
            print( "No code to run: self.response_dict[ 'code' ] = [ ]" )
            return False
        
    def run_code( self, path_to_df: Optional[str]=None, inject_bugs: bool=False ) -> dict[str, Any]:
        """
        Execute the generated code safely.
        
        Requires:
            - self.prompt_response_dict contains 'code' and 'example'
            - Code is syntactically valid (unless inject_bugs=True)
            
        Ensures:
            - Returns execution results in code_response_dict
            - Sets self.error if execution fails
            - Sets self.answer if execution succeeds
            - Updates self.code_response_dict
            
        Raises:
            - None (errors captured in response dict)
        """
        
        if self.debug: du.print_banner( f"RunnableCode.run_code( path_to_df={path_to_df}, debug={self.debug}, verbose={self.verbose} )", prepend_nl=True )
        
        self.code_response_dict = ucr.assemble_and_run_solution(
            self.prompt_response_dict[ "code" ],
            self.prompt_response_dict[ "example" ],
            path_to_df=path_to_df,
            solution_code_returns=self.prompt_response_dict.get( "returns", "string" ),
            debug=self.debug, inject_bugs=inject_bugs
        )
        if self.code_response_dict[ "return_code" ] != 0:
            self.error  = self.code_response_dict[ "output" ]
            self.answer = None
        else:
            self.error  = None
            self.answer = self.code_response_dict[ "output" ]
        
        if self.debug and self.verbose:
            du.print_banner("Code output", prepend_nl=True )
            for line in self.code_response_dict[ "output" ].split( "\n" ):
                print( line )
                
        return self.code_response_dict
    
    def code_ran_to_completion( self ) -> bool:
        """
        Check if code executed successfully.
        
        Requires:
            - self.code_response_dict is set from run_code
            
        Ensures:
            - Returns True if return_code is 0
            - Returns False otherwise
            
        Raises:
            - None
        """
        
        return self.code_response_dict is not None and self.code_response_dict.get( "return_code", -1 ) == 0
    
    def get_code_and_metadata( self ) -> dict[str, Any]:
        """
        Get code execution results and metadata.
        
        Requires:
            - self.code_response_dict is initialized
            
        Ensures:
            - Returns complete execution response dictionary
            
        Raises:
            - None
        """
        
        return self.code_response_dict
    
# Add main method
if __name__ == "__main__":
    
    pass