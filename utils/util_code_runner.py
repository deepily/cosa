import os
import subprocess
from subprocess import PIPE, run
from typing import Any, Optional

debug = os.getenv( "GIB_CODE_EXEC_DEBUG", "False" ) == "True"
import cosa.utils.util as du

@staticmethod
def initialize_code_response_dict() -> dict[str, Any]:
    """
    Initialize the code response dictionary with default values.
    
    Requires:
        - None
        
    Ensures:
        - Returns a dictionary with default unsuccessful run state
        - Contains 'return_code' set to -1
        - Contains 'output' set to "No code run yet"
    """
    # defaults to unsuccessful run state
    return {
        "return_code": -1,
             "output": "No code run yet"
    }

def _ensure_proper_appendages( code: list[str], always_appended: list[str] ) -> list[str]:
    """
    Ensure proper appendages are added to code list without duplication.
    
    Requires:
        - code is a list of code lines
        - always_appended is a list of lines to append
        
    Ensures:
        - Returns code with always_appended lines added
        - Removes duplicates based on normalized keys
        - Preserves order of original code
    """
    # du.print_banner( "code BEFORE:", prepend_nl=True )
    # du.print_list( code )
    #
    # Instantiate an ordered dictionary using the code list to populate the keys and the values. The key string should have all of the spaces removed and lowercased
    code_dict = { line.replace( " ", "" ).lower(): line for i, line in enumerate( code ) }
    # Print the dictionary in Json format
    if debug: print( du.get_debug_json( code_dict ) )
    
    # Iterate through the always_appended list and check if the key is in the code dictionary
    for line in always_appended:
        key = line.replace( " ", "" ).lower()
        if key in code_dict:
            # If the key is in the dictionary, remove it from the dictionary
            code_dict.pop( key )
    
    code = list( code_dict.values() )
    # du.print_banner( "code AFTER:", prepend_nl=True )
    # du.print_list( code )
    #
    # Append the always_appended list to the code list
    code = code + always_appended

    return code

# def _ensure_proper_appendages( code, always_appended ):
#
#     du.print_banner( "_ensure_proper_appendages", prepend_nl=True )
#     print( "always_appended", always_appended )
#     len_always_appended = -len( always_appended )
#     print( f"len_always_appended [{len_always_appended}]" )
#
#     # Check if the last N elements of 'code' match 'always_appended'
#     if code[ len_always_appended: ] != always_appended:
#
#         print( "code[ len( always_appended ): ] != always_appended" )
#         print( "code", code[ len_always_appended: ] )
#
#         # Identify any elements in 'always_appended' that are already in 'code' but not in the correct position
#         to_remove = set( code[ len_always_appended: ] ) & set( always_appended )
#         print( "to_remove", to_remove )
#
#         # Create a new list excluding the elements found above, to ensure they are not duplicated
#         cleaned_code = [ line for line in code if line not in to_remove ]
#
#         # Append 'always_appended' to the end of the list
#         cleaned_code.extend( always_appended )
#
#         return cleaned_code
#
#     else:
#
#         return code

def _append_post_function_code( code: list[str], code_return_type: str, example_code: str, path_to_df: Optional[str]=None, debug: bool=False, verbose: bool=False ) -> list[str]:
    """
    Append post-function invocation code to process and print the solution.
    
    Requires:
        - code is a list of code lines
        - code_return_type is one of: "dataframe", "string", or other valid types
        - example_code is a string containing the function invocation example
        - path_to_df is None or a valid filepath string
        - debug is a boolean flag
        - verbose is a boolean flag
        
    Ensures:
        - Returns modified code list with example code and print statements appended
        - For dataframe type, adds dataframe display code
        - For other types, adds appropriate print statements
        - Preserves the original code order
    
    When added, example and print code should look ~like this:
    <pre><code>
    code[ -2 ] = "solution = get_time()"
    code[ -1 ] = "print( solution )"
    </code></pre>
    -- or --
    <pre><code>
    code[ -4 ] = "df = pd.read_csv( du.get_project_root() + '/src/conf/long-term-memory/events.csv' )"
    code[ -3 ] = "df = dup.cast_to_datetime( df, 'start_date' )
    code[ -2 ] = "solution = get_events_this_week( df )"
    code[ -1 ] = "print( solution.to_xml( index=False )"
    </code></pre>
    """
    # code_return_type if occasionally 'pandas.core.frame.DataFrame', so we need to extract the last part of the string
    code_return_type = code_return_type.lower().split( "." )[ -1 ]
    
    always_appended = []
    
    # Conditionally apply the first two
    if path_to_df is not None:
        # 1st
        always_appended.append( f"df = pd.read_csv( du.get_project_root() + '{path_to_df}' )" )
        # 2nd
        always_appended.append( "df = dup.cast_to_datetime( df, debug=debug )" )
        
    # 3rd: Always append the example code
    always_appended.append( example_code )
    
    # 4th: Conditionally append the properly formatted print statement
    if debug and verbose: print( "return_type [{}]".format( code_return_type ) )
    if code_return_type == "dataframe":
        always_appended.append( "print( solution.to_xml( index=False ) )" )
    else:
        always_appended.append( "print( solution )" )
        
    code = _ensure_proper_appendages( code, always_appended )
    return code

def _remove_all_but_the_1st_of_repeated_lines( the_list: list[str], search_string: str ) -> list[str]:
    """
    Remove all but the first occurrence of lines containing the search string.
    
    Requires:
        - the_list is a list of strings
        - search_string is a non-empty string to search for
        
    Ensures:
        - Returns a new list with only the first occurrence of lines containing search_string
        - All subsequent occurrences of lines containing search_string are removed
        - Order of remaining elements is preserved
        - Lines not containing search_string are kept unchanged
    """
    # From: https://chat.openai.com/c/db28026c-444d-4a4b-b24b-bbb88fa52521
    match_indices = [ ]
    
    # Iterate through the list to find matches
    for i, item in enumerate( the_list ):
        item_trimmed = item.strip()
        if item_trimmed.startswith( search_string ):
            match_indices.append( i )
    
    # Remove the first occurrence from the match indices to keep it
    if match_indices: match_indices.pop( 0 )
    
    # Sort the match indices in descending order to remove items starting from the end
    for index in sorted( match_indices, reverse=True ):
        the_list.pop( index )
    
    return the_list

def _get_imports( path_to_df: Optional[str] ) -> list[str]:
    """
    Generate import statements based on whether a dataframe path is provided.
    
    Requires:
        - path_to_df is None or a valid file path string
        
    Ensures:
        - Returns a list of import statements
        - If path_to_df is None: returns basic imports only
        - If path_to_df is provided: includes pandas imports and dataframe loading code
        - Always includes sys, path, and basic utility imports
    """
    # if there's no dataframe to open or prep, then skip it
    if path_to_df is None:
        code_preamble = [
            "import datetime",
            "import pytz",
        ]
    else:
        # Otherwise, do a bit of prep for pandas & cleanup
        code_preamble = [
            "import datetime",
            "import pytz",
            "import pandas as pd",
            "import lib.utils.util as du",
            "import lib.utils.util_pandas as dup",
            "",
            "debug = {}".format( debug ),
            "",
        ]
    return code_preamble


def _remove_consecutive_empty_strings( strings: list[str] ) -> list[str]:
    """
    Remove consecutive empty strings from a list, keeping only single empty strings.
    
    Requires:
        - strings is a list of strings (may contain empty strings)
        
    Ensures:
        - Returns a new list with consecutive empty strings reduced to single empty string
        - Non-empty strings are preserved in their original order
        - Single empty strings between non-empty strings are preserved
        - Removes only consecutive duplicate empty strings
    """
    # Initialize an empty list to store the result
    result = [ ]
    
    # Iterate through the list with index
    for i in range( len( strings ) ):
        
        # Check if the current string is zero-length
        if strings[ i ] == "":
            # If it's the first element or the previous element is not a zero-length string, add it to the result
            if i == 0 or strings[ i - 1 ] != "":
                result.append( strings[ i ] )
        else:
            # If the current string is not zero-length, add it to the result
            result.append( strings[ i ] )
            
    return result

# TODO: Flip return none on timeout from true to false!
def assemble_and_run_solution( solution_code: list[str], example_code: str, path_to_df: Optional[str]=None, solution_code_returns: str="string", python_runtime: str="python3", debug: bool=False, verbose: bool=False, inject_bugs: bool=False, return_none_on_timeout: bool=True ) -> dict[str, Any]:
    """
    Assemble and execute the solution code with necessary imports and post-processing.
    
    Requires:
        - solution_code is a list of code lines to execute
        - example_code is a string with the function invocation example
        - path_to_df is None or a valid file path for dataframe input
        - solution_code_returns is one of: "string", "dataframe", etc.
        - python_runtime is a valid Python runtime command
        - debug, verbose, inject_bugs, return_none_on_timeout are boolean flags
        
    Ensures:
        - Returns a dictionary with 'return_code' and 'output' keys
        - Executes the assembled code in a subprocess
        - Handles timeouts based on return_none_on_timeout flag
        - Includes proper imports and post-processing based on return type
        - Captures both stdout and stderr from the execution
        
    Raises:
        - No exceptions raised directly, errors are captured in return dict
    """
    if debug and verbose:
        du.print_banner( "Solution code BEFORE:", prepend_nl=True)
        du.print_list( solution_code)
    
    imports       = _get_imports( path_to_df )
    solution_code = imports + solution_code
    solution_code = _append_post_function_code( solution_code, solution_code_returns, example_code, path_to_df=path_to_df, debug=debug )
    solution_code = _remove_consecutive_empty_strings( solution_code )
    
    if debug and verbose:
        du.print_banner( "Solution code AFTER:", prepend_nl=True)
        du.print_list( solution_code )
    
    if inject_bugs:
        
        from cosa.agents.v010.bug_injector import BugInjector
        
        du.print_banner( "Injecting bugs...", prepend_nl=True, expletive=True, chunk="buggy 🦂 bug injector 💉 " )
        bug_injector  = BugInjector( solution_code, example=example_code, debug=debug, verbose=verbose )
        response_dict = bug_injector.run_prompt()
        solution_code = response_dict[ "code" ]
        
    from cosa.app.configuration_manager import ConfigurationManager
    config_mgr = ConfigurationManager()
    code_file_path = config_mgr.get("code_execution_file_path")
    code_path = du.get_project_root() + code_file_path
    du.write_lines_to_file( code_path, solution_code )
    
    # Stash current working directory, so we can return to it after code has finished executing
    original_wd = os.getcwd()
    os.chdir( du.get_project_root() + "/io" )
    
    if debug: print( "Code runner executing [{}]... ".format( code_path ), end="" )
    
    # ¡OJO! Hardcoded value of python runtime... Make this runtime configurable
    try:
        results = run( [ python_runtime, code_path ], stdout=PIPE, stderr=PIPE, universal_newlines=True, timeout=60 )
    except subprocess.TimeoutExpired as e:
        
        du.print_stack_trace( e, explanation="subprocess.TimeExpired calling run(...)", caller="assemble_and_run_solution" )
        du.print_banner( "Error running this code:", prepend_nl=True, expletive=True )
        du.print_list( solution_code )
        
        # !OJO! This is a GIANT kludge, but it's a way to return a response that doesn't crash the gsm8k client
        if return_none_on_timeout:
            
            # Return to original working directory
            os.chdir( original_wd )
            
            results_dict = initialize_code_response_dict()
            results_dict[ "output" ] = None
            
            return results_dict
        else:
            raise e
    
    if debug: print( f"results.returncode = [{results.returncode}]...", end="" )
    
    if results.returncode != 0:
        if debug: print()
        output = f"ERROR executing code: \n\n{results.stderr.strip()}"
        if debug: print( output )
    else:
        if debug: print( "Done!" )
        output = results.stdout.strip()
        if output == "":
            output = "No results returned"
    
    results_dict = initialize_code_response_dict()
    results_dict[ "return_code" ] = results.returncode
    results_dict[ "output"      ] = output
    
    if debug and verbose:
        du.print_banner( "assemble_and_run_solution() output:", prepend_nl=True )
        print( results_dict[ "output" ] )
    
    # Return to original working directory
    os.chdir( original_wd )
    
    return results_dict

def test_assemble_and_run_solution( debug: bool=False, verbose: bool=False) -> None:
    """
    Test the assemble_and_run_solution function with sample code.
    
    Requires:
        - debug is a boolean flag for debug output
        - verbose is a boolean flag for verbose output
        
    Ensures:
        - Executes a test solution with dataframe processing
        - Tests the code assembly and execution pipeline
        - Prints results if debug/verbose flags are set
        - Validates the solution execution process
    """
    solution_code = [
        "def check_birthdays(df):",
        "    today = pd.Timestamp('today')",
        "    week_from_today = today + pd.DateOffset(weeks=1)",
        "    birthdays = df[(df.event_type == 'birthday') & (df.start_date <= week_from_today) & (df.end_date >= today)]",
        "    return birthdays",
        "solution = check_birthdays( df )"
    ]
    example_code = "solution = check_birthdays( df )"
    path_to_df   = "/src/conf/long-term-memory/events.csv"
    results      = assemble_and_run_solution( solution_code, example_code, solution_code_returns="dataframe", path_to_df=path_to_df, debug=debug, verbose=verbose )
    
        
if __name__ == "__main__":
    test_assemble_and_run_solution( debug=True, verbose=True )
    # pass