import cosa.utils.util as du

from cosa.agents.agent_base import AgentBase
from cosa.memory.solution_snapshot_mgr import SolutionSnapshotManager
class MathRefactoringAgent( AgentBase ):
    
    def __init__( self, similar_snapshots=[], path_to_solutions="/src/conf/long-term-memory/solutions", routing_command="agent router go to math refactoring", debug=False, verbose=False ):
        
        super().__init__( routing_command=routing_command, debug=debug, verbose=verbose )
        
        du.print_banner( "MathRefactoringAgent.__init__()" )
        self.debug             = debug
        self.verbose           = verbose
        
        self.path_to_solutions = path_to_solutions
        self.similar_snapshots = similar_snapshots
        
        self.snippets          = self._preprocess_similar_snapshots()
        self.prompt            = self.prompt_template.format( snippet_count=len( similar_snapshots ), snippets=self.snippets )
        
        self.error             = None
        self.code_responses    = None
        
        self.xml_response_tag_names = [ "thoughts", "brainstorm", "evaluation", "code", "examples", "returns", "explanation" ]

    def _preprocess_similar_snapshots( self ):
        
        i = 1
        snippets = []
        if self.debug and self.verbose: print()
        
        for snapshot in self.similar_snapshots:
        
            snippet = "\n".join( snapshot[ 1 ].code )
            snippet = f"Snippet {i} for question `{snapshot[ 1 ].question}`: \n{snippet}"
            snippets.append( snippet )
            
            if self.debug and self.verbose: print( snippet, end="\n\n" )
            i += 1
            
        return "\n".join( snippets )
    # def _get_system_message( self ):
    #
    #     self._preprocess_similar_snapshots()
    #
    #     snippet_count = len( self.snippets )
    #
    #     system_message = f"""
    #     I'm going to show you {snippet_count} Python code snippets that are similar, along with the questions they were created to answer.
    #     How would you coalesce or refactor them so that you only need to call one function in all {snippet_count} scenarios?
    #     How would you name the function in a way that clearly explains exactly what the date range is, e.g., 'get_this_months_events_by_type', as well as what the function does?
    #     Descriptive function names MUST look like: `get_birthday_by_name`, or `get_todays_events`, `get_todays_events_by_type`, `get_tomorrows_events`, `get_this_weeks_events`, `get_this_weeks_events_by_type`,`get_this_months_events_by_type`, etc.,
    #
    #     As you generate the Python 3.10 code needed to answer this question, I want you to:
    #
    #     1) Think: Before you do anything, think out loud about what I'm asking you to do, including the steps that you will need to take to solve this problem.
    #     Be critical of your thought process! How will you handle the edge cases? For example, what will you do if your query does not return a result?
    #     2) Code: Generate a verbatim list of code that you used to arrive at your answer, one line of code per item on the list. The code must be complete,
    #     syntactically correct, and capable of running to completion. You must allow for the possibility that your query may not return a result.
    #     3) Document: Create a GPT function signature (gpt_function_signatures) that can be used by GPT to call the function you create. The function signature MUST be
    #     syntactically correct.
    #     4) Generate examples: Generate a dictionary containing the code examples needed to call the function you created, one line of code per question provided.
    #     The example function calls must be complete, syntactically correct, and capable of running to completion. Each example must be wrapped in a print statement.
    #     5) Explain: Briefly and succinctly explain your code in plain English.
    #
    #     Format: return your response as a syntactically correct JSON object with the following fields and formatting:
    #     {{
    #         "thoughts": "Your thoughts",
    #         "code": [],
    #         "function_name": "The name of your function. It must describe the time period being filtered, e.g., `get_tomorrows_events`, get_todays_events`, etc.",
    #         "parameters": "The parameters to your function, only two are allowed: the 1st will always be `df` and the 2nd will always be **kwargs. All keys in the
    #         **kwargs dictionary MUST be the names of the pandas field they correspond to in the dataframe.",
    #         "gpt_function_signatures":"[
    #         {{
    #             "name": "get_current_weather",
    #             "description": "Gets the current weather in a given location",
    #             "parameters": {{
    #                 "type": "object",
    #                 "properties": {{
    #                     "location": {{
    #                         "type": "string",
    #                         "description": "The city and state, e.g. San Francisco, CA",
    #                     }},
    #                     "unit": {{"type": "string", "enum": ["celsius", "fahrenheit"]}},
    #                 }},
    #                 "required": ["location"],
    #             }},
    #         }}]",
    #         "returns": "Object type of the variable `solution`",
    #         "examples": {{}}, a dictionary containing the questions and example code, one line of code per question provided.
    #         "python_version": "3.10",
    #         "explanation": "A brief explanation of your code",
    #         "error": "Verbatim stack trace or description of issues encountered while attempting to carry out this task."
    #     }}"""
    #
    #     return system_message
    #
    # def _get_user_message( self ):
    #
    #     snippets_string = "\n\n".join( self.snippets )
    #
    #     user_message = f"""
    #     {snippets_string}
    #
    #     Begin!
    #     """
    #
    #     return user_message
    #
    # def is_prompt_executable( self ):
    #
    #     if len( self.snippets ) == 0:
    #         return False
    #     else:
    #         return True
    #
    # def run_prompt( self, prompt_model=Llm_v0.GPT_4 ):
    #
    #     prompt_model = Llm_v0.GPT_4
    #
    #     self._print_token_count( self.system_message, message_name="system_message", model=prompt_model )
    #     self._print_token_count( self.user_message, message_name="user_message", model=prompt_model )
    #
    #     self.prompt_response      = self._query_llm( self.system_message, self.user_message, model=prompt_model, debug=self.debug )
    #     # This is another example of GPT injecting a little bit of formatting randomicity into the response
    #     self.prompt_response      = self.prompt_response.replace( "\n", "" ).strip( '"' )
    #     self.prompt_response_dict = json.loads( self.prompt_response )
    #
    #     if self.debug and self.verbose: print( json.dumps( self.prompt_response_dict, indent=4 ) )
    #
    #     # Test for no code returned and throw error
    #     if self.prompt_response_dict[ "code" ] == [ ]:
    #         stem = "No code was returned."
    #         # Save for debugging by LLM later
    #         self.error = f"{stem} LLM error: {self.prompt_response_dict[ 'error' ]}"
    #         raise ValueError( stem )
    #
    #     if self.prompt_response_dict[ "examples" ] == [ ]:
    #         self.error = self.prompt_response_dict[ "error" ]
    #         raise ValueError( "No examples were returned." )
    #
    #     return self.prompt_response_dict
    #
    # def refactor_code( self, update_example_code=True, debug=False ):
    #
    #     agent_src_root = du.get_project_root() + "/src/"
    #     agent_lib_chunk = "lib/autogen/"
    #
    #     code_write_metadata = self._write_code_and_metadata_to_unique_files(
    #         agent_src_root, agent_lib_chunk, "util_calendaring_", code_suffix=".py", debug=debug
    #     )
    #     if debug:
    #         print( f"File     count: [{code_write_metadata[ 'count' ]}]" )
    #         print( f"File file_name: [{code_write_metadata[ 'file_name' ]}]" )
    #         print( f"File repo_path: [{code_write_metadata[ 'repo_path' ]}]" )
    #         print( f"File   io_path: [{code_write_metadata[ 'io_path' ]}]" )
    #         print( f"File    abbrev: [{code_write_metadata[ 'abbrev' ]}]" )
    #         print( f"File    import: [{code_write_metadata[ 'import' ]}]", end="\n\n" )
    #
    #         print( f"File call_template: [{code_write_metadata[ 'call_template' ]}]" )
    #         print( f"File     signature: [{code_write_metadata[ 'gpt_function_signature' ]}]", end="\n\n" )
    #
    #     response_dict = self._update_example_code( self.prompt_response_dict.copy(), code_write_metadata, code_write_metadata )
    #
    #     if update_example_code: self._update_snapshot_code( self.similar_snapshots, response_dict, debug=debug )
    #
    # def is_code_runnable( self ):
    #
    #     for similar_snapshot in self.similar_snapshots:
    #         if similar_snapshot[ 1 ].code == [ ]:
    #             print( "No code to run: similar_snapshot[ 1 ].code = [ ]" )
    #             return False
    #     else:
    #         return True
    #
    # def run_code( self ):
    #
    #     self.code_responses = []
    #
    #     for similar_snapshot in self.similar_snapshots:
    #
    #         code_response = ucr.assemble_and_run_solution(
    #             similar_snapshot[ 1 ].code, path_to_df="/src/conf/long-term-memory/events.csv", debug=self.debug
    #         )
    #         if self.debug and self.verbose:
    #             du.print_banner( "Code output", prepend_nl=True )
    #             for line in code_response[ "output" ].split( "\n" ):
    #                 print( line )
    #
    #             print()
    #
    #         self.code_responses.append( code_response )
    #
    #     return self.code_responses
    #
    # def format_output( self ):
    #
    #     du.print_banner( "TODO: Implement format_output()", expletive=True )
    #     return None
    #
    # def get_parameter_names( self, signature_dict, debug=False ):
    #
    #     if debug:
    #         print( f"signature_dict: {signature_dict}" )
    #         print( f"type( signature_dict ): {type(signature_dict)}" )
    #
    #     params = [ ]
    #     for k, v in signature_dict[ "parameters" ][ "properties" ].items():
    #         if k != "df":
    #             params.append( k )
    #             if debug: print( k, v )
    #         else:
    #             if debug: print( "skipping df" )
    #
    #     return params
    #
    # def get_function_signature( self, raw_signature ):
    #
    #     # Try to get the GPT function signature from the response dictionary...
    #     try:
    #         gpt_function_signature = json.loads( raw_signature )[ 0 ]
    #
    #     # ...but if it fails, try to fix it here
    #     except json.decoder.JSONDecodeError as e:
    #
    #         du.print_banner( "Fixing json.decoder.JSONDecodeError in GPT function signature...", prepend_nl=True )
    #
    #         # Replace matched patterns with double quotes
    #         # simplistic match: beginning or end of words
    #         # pattern = r"'(?=\w)|(?<=\w)'"
    #         # more complex match: beginning or end of words with parens
    #         pattern = r"'(?=\w)|(?<=\w|[\)])'"
    #         fixed_signature = re.sub( pattern, '"', raw_signature )
    #         print( fixed_signature, end="\n\n" )
    #
    #         # Encode the string as a JSON object
    #         gpt_function_signature = json.loads( fixed_signature )[ 0 ]
    #
    #     return gpt_function_signature
    #
    # def _write_code_and_metadata_to_unique_files(
    #         self, agent_src_root, agent_lib_dir, file_name_prefix, code_suffix=".py", metadata_suffix=".json", debug=False
    # ):
    #
    #     # Get the code and function signature from the response dictionary,
    #     # ¡OJO! The function signature requires a bit of munging before serializing it as Json
    #     # TODO: If getting the GPT function signature is going to be this flaky, do it as a separate chat completion with GPT
    #     code                   = self.prompt_response_dict[ "code" ]
    #     raw_signature          = self.prompt_response_dict[ "gpt_function_signatures" ]
    #     gpt_function_signature = self.get_function_signature( raw_signature )
    #     # munged_signature       = raw_signature.replace( "'", '"' ).strip( '"' )
    #     if debug:
    #         print( f"Raw signature: ###{raw_signature}###" )
    #         # print( f"Munged signature: ###{munged_signature}###" )
    #
    #     # Get the list of files in the agent_lib_path directory
    #     files = os.listdir( agent_src_root + agent_lib_dir )
    #
    #     # Count the number of files with the name {file_name_prefix}{}{suffix}"
    #     count = sum( 1 for file in files if file.startswith( file_name_prefix ) and file.endswith( code_suffix ) )
    #
    #     # Format the file name with the count
    #     file_name = f"{file_name_prefix}{count}{code_suffix}"
    #     util_name = f"{file_name_prefix}{count}"
    #
    #     # Build import 'as' string:
    #     # Grab everything up to the first appearance of a digit
    #     non_digits = util_name.split( "_" )[ :-1 ]
    #     # Grab the first letter of every non-digit chunk
    #     first_letters = "".join( [ item[ 0 ] for item in non_digits ] )
    #     # Create something like this: uc3, from this: util_calendaring_3
    #     abbrev = f"{first_letters}{count}"
    #     as_chunk = f"as {abbrev}"
    #     # Create something like this: import lib.util_calendaring_2 as uc2
    #     import_str = f"import {agent_lib_dir.replace( '/', '.' )}{util_name} {as_chunk}"
    #
    #     # Build the function all template: uc2.get_todays_events( df, 'event_type' ).
    #     # ¡OJO! Since we know that the first parameter is always 'df', the only thing that varies is the second parameter, there is no third fourth etc.
    #     kw_arg_1      = self.get_parameter_names( gpt_function_signature, debug=debug )
    #     call_template = f"{abbrev}.{gpt_function_signature[ 'name' ]}( df, {kw_arg_1[ 0 ]}='{kw_arg_1[ 0 ]}' )"
    #     gpt_function_signature[ "call_template" ] = call_template
    #     gpt_function_signature[ "import_as"     ] = import_str
    #
    #     # Write the code to the repo path
    #     repo_path = os.path.join( agent_src_root, agent_lib_dir, file_name )
    #     print( f"Writing file [{repo_path}]... ", end="" )
    #     du.write_lines_to_file( repo_path, code )
    #     # Set the permissions of the file to be world-readable and writable
    #     os.chmod( repo_path, 0o666 )
    #     print( "Done!" )
    #
    #     # Write the function signature to the repo path
    #     repo_path = os.path.join( agent_src_root, agent_lib_dir, file_name.replace( code_suffix, metadata_suffix ) )
    #     print( f"Writing file [{repo_path}]... ", end="" )
    #     du.write_string_to_file( repo_path, json.dumps( gpt_function_signature, indent=4 ) )
    #     # Set the permissions of the file to be world-readable and writable
    #     os.chmod( repo_path, 0o666 )
    #     print( "Done!" )
    #
    #     # Write the file to the io/execution path
    #     io_path = f"{du.get_project_root()}/io/{agent_lib_dir}{file_name}"
    #     print( f"Writing file [{io_path}]... ", end="" )
    #     du.write_lines_to_file( io_path, code )
    #     # Set the permissions of the file to be world-readable and writable
    #     os.chmod( io_path, 0o666 )
    #     print( "Done!", end="\n\n" )
    #
    #     results = {
    #         "file_name"    : file_name,
    #         "repo_path"    : repo_path,
    #         "io_path"      : io_path,
    #         "count"        : count,
    #         "abbrev"       : abbrev,
    #         "import"       : import_str,
    #         "call_template": call_template,
    #         "gpt_function_signature": gpt_function_signature
    #     }
    #
    #     return results
    #
    # def _update_example_code( self, refactoring_response_dict, code_metadata, debug=False ):
    #
    #     function_name = refactoring_response_dict[ "function_name" ]
    #
    #     # Update the examples dictionary so that it contains a list of source code needed to execute the freshly minted function
    #     for key, value in refactoring_response_dict[ "examples" ].items():
    #
    #         # if debug: print( f"Before: {key}: {value}" )
    #         if type( value ) is not list:
    #             value = value.replace( function_name, f"{code_metadata[ 'abbrev' ]}.{function_name}" )
    #             value = [ code_metadata[ 'import' ], value ]
    #         # else:
    #         #     if debug: print( f"No need to update [{value}]" )
    #         # if debug: print( f" After: {key}: {value}" )
    #
    #         refactoring_response_dict[ "examples" ][ key ] = value
    #
    #     return refactoring_response_dict
    #
    # def _update_snapshot_code( self, snapshots, refactoring_response_dict, debug=False ):
    #
    #     for snapshot in snapshots:
    #
    #         if debug:
    #             du.print_banner( f"BEFORE updating `{snapshot[ 1 ].question}`...", prepend_nl=False )
    #             for line in snapshot[ 1 ].code: print( line )
    #             print( "\n" )
    #
    #         # Update the code, using the question as the key
    #         new_code = refactoring_response_dict[ "examples" ][ snapshot[ 1 ].question ]
    #         snapshot[ 1 ].set_code( new_code )
    #         snapshot[ 1 ].self.code_type = "refactored"
    #         snapshot[ 1 ].write_current_state_to_file()
    #
    #         if debug:
    #             du.print_banner( f" AFTER updating `{snapshot[ 1 ].question}`...", prepend_nl=False )
    #             for line in snapshot[ 1 ].code: print( line )
    #             print( "\n" )
    
    def restore_from_serialized_state( file_path ):
        
        raise NotImplementedError( "MathRefactoringAgent.restore_from_serialized_state() not implemented" )

    def do_all( self ):
        
        self.run_prompt()
        self.run_code()
        self.format_output()
        
        return self.answer_conversational
    
    def is_code_runnable( self ):
        
        return False
    
    def run_code( self, auto_debug=None, inject_bugs=None ):
        
        print( "NOT Running code, this is a DEMO MathRefactoringAgent" )
        self.code_response_dict = {
            "return_code": 0,
            "output"     : "No code to run, this is a demo refactoring agent"
        }
        return self.code_response_dict
    
    def code_ran_to_completion( self ):
        
        # This is a necessary lie to satisfy the interface
        return True
    
    def format_output( self ):
        
        self.answer_conversational = f'Found {len( self.prompt_response_dict[ "examples" ] )} candidates for refactoring'
        
        return self.answer_conversational
    
if __name__ == "__main__":
    
    # print( du.get_project_root() )

    question = "What's the square root of 144?"
    question_gist = "What is the square root of 144?"
    # question = "What's 5 times 5?"
    # question_gist = "What is 5 times 5?"

    threshold         = 85.0
    path_to_snapshots = du.get_project_root() + "/src/conf/long-term-memory/solutions/"
    snapshot_mgr      = SolutionSnapshotManager( path_to_snapshots, debug=True )
    exemplar_snapshot = snapshot_mgr.get_snapshots_by_question( question, question_gist=question_gist, threshold_question=95.0, threshold_gist=92.5 )[ 0 ][ 1 ]
    similar_snapshots = snapshot_mgr.get_snapshots_by_code_similarity( exemplar_snapshot, threshold=threshold )
    # similar_snapshots = snapshot_mgr.get_snapshots_by_question( question, threshold_question=95.0, threshold_gist=90.0 )

    agent = MathRefactoringAgent( similar_snapshots=similar_snapshots, path_to_solutions="/src/conf/long-term-memory/solutions", debug=True, verbose=False )
    # print( agent.prompt )
    # agent.run_prompt()
    print( agent.do_all() )