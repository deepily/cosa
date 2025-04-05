import os
import random
import pandas as pd
from xmlschema import XMLSchema

import cosa.utils.util as du
import cosa.utils.util_xml as dux
from cosa.training.xml_prompt_generator import XmlPromptGenerator
from cosa.training.xml_response_validator import XmlResponseValidator

class XmlCoordinator:
    """
    Coordinates prompt generation and response validation for XML-based fine-tuning.
    
    This class combines the functionality of XmlPromptGenerator and XmlResponseValidator,
    providing a unified interface for working with XML-based prompts and responses.
    
    Responsibilities:
    - Generate and format prompts using various templates
    - Run validation on model responses
    - Calculate and report performance metrics
    - Generate training/testing data splits
    """
    
    def __init__( self, path_prefix=du.get_project_root(), tgi_url="http://172.17.0.4:3000", debug=False, verbose=False, silent=False, init_prompt_templates=True ):
        self.debug                = debug
        self.verbose              = verbose
        self.silent               = silent
        self.path_prefix          = path_prefix
        self.tgi_url              = tgi_url
        
        # Initialize the component classes
        self.prompt_generator     = XmlPromptGenerator( path_prefix=path_prefix, debug=debug, verbose=verbose, silent=silent )
        self.response_validator   = XmlResponseValidator( debug=debug, verbose=verbose )
        
        # Counters and state
        self._call_counter        = 0
        
        # For backward compatibility - provide direct access to key properties
        if init_prompt_templates:
            self.interjections    = self.prompt_generator.interjections
            self.salutations      = self.prompt_generator.salutations
            self._xml_schema      = self.response_validator._xml_schema
    
    # Public methods from XmlPromptGenerator
    def get_interjections( self, requested_length=None ):
        """
        Gets a list of interjections for more natural language generation.
        
        Args:
            requested_length (int, optional): Number of interjections to return
            
        Returns:
            list: List of interjection phrases
        """
        return self.prompt_generator.get_interjections( requested_length )
    
    def get_salutations( self, requested_length=500 ):
        """
        Gets randomized salutations with computer names.
        
        Args:
            requested_length (int, optional): Number of salutations to return
            
        Returns:
            list: List of formatted salutations
        """
        return self.prompt_generator.get_salutations( requested_length )
    
    def insert_interjection( self, text, interjections=None ):
        """
        Inserts a random interjection into the provided text.
        
        Args:
            text (str): The text to modify
            interjections (list, optional): List of interjections to choose from
            
        Returns:
            tuple: (inserted_interjection, modified_text)
        """
        return self.prompt_generator.insert_interjection( text, interjections )
    
    def prepend_salutation( self, text, salutations=None ):
        """
        Prepends a random salutation to the given text.
        
        Args:
            text (str): The text to modify
            salutations (list, optional): List of salutations to choose from
            
        Returns:
            tuple: (chosen_salutation, modified_text)
        """
        return self.prompt_generator.prepend_salutation( text, salutations )
    
    def get_prompt_template( self, name ):
        """
        Returns a formatted prompt template for the specified command type.
        
        Args:
            name (str): The command type ('vox command' or 'agent router')
            
        Returns:
            str: Formatted prompt template
            
        Raises:
            ValueError: If an unknown prompt template name is provided
        """
        return self.prompt_generator.get_prompt_template( name )
    
    def serialize_prompt( self, prompt, prompt_path ):
        """
        Writes a prompt to a file.
        
        Args:
            prompt (str): The prompt to serialize
            prompt_path (str): Path to save the prompt
        """
        self.prompt_generator.serialize_prompt( prompt, prompt_path )
    
    def serialize_prompts( self, prompt_path_prefix ):
        """
        Writes all prompt templates to files.
        
        Args:
            prompt_path_prefix (str): Directory prefix for saving prompts
        """
        self.prompt_generator.serialize_prompts( prompt_path_prefix )
    
    # Public methods from XmlResponseValidator
    def is_valid_xml( self, xml_str ):
        """
        Checks if XML is valid according to schema.
        
        Args:
            xml_str (str): XML string to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        return self.response_validator.is_valid_xml( xml_str )
    
    def contains_valid_xml_tag( self, xml_str, tag_name ):
        """
        Checks if XML contains a specific tag.
        
        Args:
            xml_str (str): XML string to check
            tag_name (str): Tag name to look for
            
        Returns:
            bool: True if tag exists, False otherwise
        """
        return self.response_validator.contains_valid_xml_tag( xml_str, tag_name )
    
    def is_response_exact_match( self, response, answer ):
        """
        Checks if response exactly matches expected answer.
        
        Args:
            response (str): Generated response
            answer (str): Expected answer
            
        Returns:
            bool: True if exact match, False otherwise
        """
        return self.response_validator.is_response_exact_match( response, answer )
    
    def contains_correct_response_values( self, response, answer ):
        """
        Check if the most common formatting error (```xml) is hiding a correct <response>...</response>
        
        Args:
            response (str): Generated response
            answer (str): Expected answer
            
        Returns:
            bool: True if the response contains correct values, False otherwise
        """
        return self.response_validator.contains_correct_response_values( response, answer )
    
    def tag_values_are_equal( self, response, answer, tag_name="command" ):
        """
        Checks if a specific tag's value in response matches the value in answer.
        
        Args:
            response (str): Generated response
            answer (str): Expected answer
            tag_name (str, optional): Tag name to compare. Defaults to "command".
            
        Returns:
            bool: True if tag values match, False otherwise
        """
        return self.response_validator.tag_values_are_equal( response, answer, tag_name )
    
    # Shared methods for generating and validating prompts
    def reset_call_counter( self ):
        """
        Resets the internal call counter to zero.
        """
        self._call_counter = 0
    
    def build_compound_vox_cmd_training_prompts( self, sample_size_per_command=2000 ):
        """
        Builds training prompts for compound voice commands.
        
        Args:
            sample_size_per_command (int): Number of samples to generate per command
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated training prompts
        """
        instructions, inputs, outputs, prompts, gpt_messages, commands = self._get_6_empty_lists()
        
        gpt_instruction = self.prompt_generator.vox_cmd_instruction_template_gpt.format( command_choices=self.prompt_generator.vox_cmd_commands )
        
        # For each browser command, load the corresponding file and generate prompts
        for compound_command in self.prompt_generator.vox_cmd_compound_commands.keys():
            
            du.print_banner( f"Building prompts for compound VOX command [{ compound_command }]", prepend_nl=True, end="\n" )
            counter = 1
            # The first 100 lines are properly spelled
            raw_lines = du.get_file_as_list( self.path_prefix + self.prompt_generator.vox_cmd_compound_commands[ compound_command ], clean=True )[ 0:100 ]
            
            # Determine which kind of compound synthetically created lines we need to build prompts for
            if compound_command.startswith( "search " ):
                arguments   = self.prompt_generator.get_search_terms( len( raw_lines ) )
                placeholder = "SEARCH_TERMS"
            elif compound_command.startswith( "go to " ):
                arguments   = self.prompt_generator.get_domain_names( len( raw_lines ) )
                placeholder = "DOMAIN_NAME"
            else:
                raise Exception( f"Unknown voice command [{ compound_command }]" )
            
            for raw_line in raw_lines:
                
                for args in arguments:
                    
                    voice_command = raw_line.replace( placeholder, args )
                    
                    instruction = self.prompt_generator.vox_cmd_instruction_template.format( command_choices=self.prompt_generator.vox_cmd_commands )
                    human_says  = self.prompt_generator.common_human_says_template.format( voice_command=voice_command )
                    input_text  = self.prompt_generator.common_input_template.format( human_says=human_says, response_format=self.prompt_generator.common_response_format )
                    output      = self.prompt_generator.common_output_template.format( command=compound_command, args=args )
                    prompt      = self.prompt_generator._get_prompt_instruction_format( instruction, input_text )
                    
                    instructions.append( instruction )
                    inputs.append( input_text )
                    outputs.append( output )
                    prompts.append( prompt )
                    commands.append( compound_command )
                    
                    gpt_messages.append( self._get_gpt_messages_dict( gpt_instruction, voice_command, compound_command, args ) )
                    
                    self._do_conditional_print( counter, voice_command )
                    counter += 1
            
            print()
        
        compound_qna_df = pd.DataFrame( { "command": commands, "instruction": instructions, "input": inputs, "output": outputs, "prompt": prompts, "gpt_message": gpt_messages } )
        compound_qna_df = self._prune_duplicates_and_sample( compound_qna_df, sample_size=( sample_size_per_command * len( self.prompt_generator.vox_cmd_compound_commands ) ), sample_size_per_command=sample_size_per_command )
        
        return compound_qna_df
    
    def build_simple_vox_cmd_training_prompts( self, sample_size_per_command=400 ):
        """
        Builds training prompts for simple voice commands.
        
        Args:
            sample_size_per_command (int): Number of samples to generate per command
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated training prompts
        """
        instructions, inputs, outputs, prompts, gpt_messages, commands = self._get_6_empty_lists()
        
        gpt_instruction = self.prompt_generator.vox_cmd_instruction_template_gpt.format( command_choices=self.prompt_generator.vox_cmd_commands )
        
        for simple_command in self.prompt_generator.vox_cmd_simple_commands.keys():
            
            du.print_banner( f"Building prompts for simple VOX command [{ simple_command }]", prepend_nl=True, end="\n" )
            counter = 1
            
            raw_lines = du.get_file_as_list( self.path_prefix + self.prompt_generator.vox_cmd_simple_commands[ simple_command ], clean=True )
            
            for raw_line in raw_lines:
                
                instruction = self.prompt_generator.vox_cmd_instruction_template.format( command_choices=self.prompt_generator.vox_cmd_commands )
                human_says  = self.prompt_generator.common_human_says_template.format( voice_command=raw_line )
                input_text  = self.prompt_generator.common_input_template.format( human_says=human_says, response_format=self.prompt_generator.common_response_format )
                output      = self.prompt_generator.common_output_template.format( command=simple_command, args="" )
                prompt      = self.prompt_generator._get_prompt_instruction_format( instruction, input_text )
                
                instructions.append( instruction )
                inputs.append( input_text )
                outputs.append( output )
                prompts.append( prompt )
                commands.append( simple_command )
                
                gpt_messages.append( self._get_gpt_messages_dict( gpt_instruction, raw_line, simple_command, "" ) )
                
                self._do_conditional_print( counter, raw_line )
                counter += 1
            
        simple_command_qna_df = pd.DataFrame( { "command": commands, "instruction": instructions, "input": inputs, "output": outputs, "prompt": prompts, "gpt_message": gpt_messages } )
        simple_command_qna_df = self._prune_duplicates_and_sample( simple_command_qna_df, sample_size=( sample_size_per_command * len( self.prompt_generator.vox_cmd_simple_commands ) ), sample_size_per_command=sample_size_per_command )
        
        return simple_command_qna_df
    
    def build_compound_agent_router_training_prompts( self, sample_size_per_command=2000 ):
        """
        Builds training prompts for compound agent router commands.
        
        Args:
            sample_size_per_command (int): Number of samples to generate per command
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated training prompts
        """
        instructions, inputs, outputs, prompts, gpt_messages, commands = self._get_6_empty_lists()
    
        gpt_instruction = self.prompt_generator.agent_router_instruction_template_gpt.format( command_choices=self.prompt_generator.agent_router_commands )
        
        # For each browser command, load the corresponding file and generate prompts
        for compound_command in self.prompt_generator.agent_router_compound_commands.keys():
            
            du.print_banner( f"Building prompts for compound AGENT ROUTER command [{ compound_command }]", prepend_nl=True, end="\n" )
            counter = 1
            
            raw_lines = du.get_file_as_list( self.path_prefix + self.prompt_generator.agent_router_compound_commands[ compound_command ], clean=True, randomize=True )[ 0:100 ]
            
            if compound_command in [ "agent router go to weather", "agent router go to date and time" ]:
                arguments   = self.prompt_generator.get_cities_and_countries( len( raw_lines ) )
                placeholder = "GEOGRAPHIC_LOCATION"
            elif compound_command == "agent router go to receptionist":
                arguments   = self._get_receptionist_titles( len( raw_lines ) )
                placeholder = "RECEPTIONIST_TITLE"
            elif compound_command == "agent router go to calendar":
                arguments   = self._get_events_values( len( raw_lines ) )
                placeholder = ""
            else:
                raise Exception( f"Unknown voice command [{ compound_command }]" )
            
            for raw_line in raw_lines:
                    
                for args in arguments:
                    
                    if compound_command == "agent router go to calendar":
                        voice_command = raw_line.replace( "PLACE", "" )
                        for key in args.keys():
                            voice_command = voice_command.replace( key, args[ key ] )
                        # Reset args to an empty string, NOT a dictionary
                        args = ""
                    else:
                        voice_command = raw_line.replace( placeholder, args )
                        
                    _, voice_command = self.prompt_generator.insert_interjection( voice_command, self.prompt_generator.interjections )
                    _, voice_command = self.prompt_generator.prepend_salutation( voice_command, self.prompt_generator.salutations )
                    
                    instruction   = self.prompt_generator.agent_router_instruction_template.format( command_choices=self.prompt_generator.agent_router_commands )
                    human_says    = self.prompt_generator.common_human_says_template.format( voice_command=voice_command )
                    input_text    = self.prompt_generator.common_input_template.format( human_says=human_says, response_format=self.prompt_generator.common_response_format )
                    output        = self.prompt_generator.common_output_template.format( command=compound_command, args=args )
                    prompt        = self.prompt_generator._get_prompt_instruction_format( instruction, input_text )
                    
                    instructions.append( instruction )
                    inputs.append( input_text )
                    outputs.append( output )
                    prompts.append( prompt )
                    commands.append( compound_command )
                    
                    gpt_messages.append( self._get_gpt_messages_dict( gpt_instruction, voice_command, compound_command, args ) )
                    
                    self._do_conditional_print( counter, voice_command )
                    counter += 1
            
            print()
        
        compound_agent_router_qna_df = pd.DataFrame( { "command": commands, "instruction": instructions, "input": inputs, "output": outputs, "prompt": prompts, "gpt_message": gpt_messages } )
        compound_agent_router_qna_df = self._prune_duplicates_and_sample( compound_agent_router_qna_df, sample_size=( sample_size_per_command * len( self.prompt_generator.vox_cmd_compound_commands ) ), sample_size_per_command=sample_size_per_command )
        
        return compound_agent_router_qna_df
    
    def build_compound_function_mapping_training_prompts( self, sample_size_per_command=2000, analyze_bigrams=False, max_questions=2 ):
        """
        Builds training prompts for function mapping.
        
        Args:
            sample_size_per_command (int): Number of samples to generate per command
            analyze_bigrams (bool): Whether to analyze bigrams in questions
            max_questions (int): Maximum number of questions to generate
            
        Returns:
            pandas.DataFrame or None: DataFrame containing the generated training prompts, or None
        """
        instructions, inputs, outputs, prompts, gpt_messages, commands = self._get_6_empty_lists()
    
        gpt_instruction = self.prompt_generator.agent_router_instruction_template_gpt.format( command_choices=self.prompt_generator.agent_router_commands )
        
        # For each function mapping entry, load the corresponding file and generate prompts
        for routing_key in self.prompt_generator.agent_function_mapping_compound_commands.keys():
            
            du.print_banner( f"Building prompts for compound FUNCTION MAPPING [{ routing_key }]", prepend_nl=True, end="\n" )
            
            path     = self.path_prefix + self.prompt_generator.agent_function_mapping_compound_commands[ routing_key ]
            boundary = "<!-- QnR Boundary -->"
            if path.endswith( ".txt" ):
                
                print( f"Loading RAW question data from [{ path }]..." )
                raw_lines = du.get_file_as_list( path, clean=True, randomize=True )
                if analyze_bigrams: self._analyze_bigrams( raw_lines, "DEFAULT_LOCATION" )
                
                locations = self.prompt_generator.get_cities_and_countries( requested_length=None )
                placeholders_and_values = { "DEFAULT_LOCATION": locations }
                
                questions = self._build_function_mapping_questions( raw_lines, placeholders_and_values )
                responses = self._generate_function_mapping_response_objects( questions, max_questions=max_questions )
                count     = len( responses )
                counter   = 0
                
                # Write the responses to an XML file of the same name
                output_path = path.replace( ".txt", ".xml" )
                with open( output_path, "w", encoding="utf-8" ) as f:
                    
                    f.write( "<qnrs>\n" )
                    for response in responses:
                        if self.debug and self.verbose:
                            print( f"Writing '{ response[ 'last_question_asked' ] }'..." )
                        elif self.debug:
                            print( ".", end="" )
                        f.write( "<qnr>\n" )
                        f.write( "<question>" + response[ "last_question_asked" ] + "</question>\n" )
                        f.write( response[ "xml_response" ] + "\n" )
                        f.write( "</qnr>\n" )
                        counter += 1
                        # Don't write a boundary after the last question
                        if counter < count: f.write( f"{ boundary }\n" )
                    f.write( "</qnrs>\n" )
                
                if self.debug and not self.verbose: print()
                print( f"Saved { counter } QnRs to [{ output_path }]" )
                
            elif path.endswith( ".xml" ):
                
                msg = f"Loading XML QnR data from [{ path }]..."
                print( msg )
                xml_data = du.get_file_as_string( path )
                qnrs     = xml_data.split( boundary )
                msg      = f"{ msg } Done! Loaded { len( qnrs ) } QnR pairs."
                print( msg )
                
            else:
                
                extension = path.split( "." )[ -1 ]
                raise Exception( f"Unknown function mapping file type [*.{ extension }] for routing_key [{ routing_key }]" )

        return None
    
    def _analyze_bigrams( self, raw_lines, placeholder ):
        """
        Analyzes bigrams in raw lines.
        
        Args:
            raw_lines (list): List of raw lines
            placeholder (str): Placeholder to analyze
        """
        du.print_banner( f"Analyzing bigrams for placeholder [{ placeholder }]...", prepend_nl=True )
        
        # Do a quick and dirty search and summary for DEFAULT_LOCATION
        bigrams = []
        
        for line in raw_lines:
            
            found = False
            words = line.split( " " )
            
            for idx, word in enumerate( words ):
                if placeholder in word and idx >= 1:
                    bigrams.append( words[ idx - 1 ] + " " + words[ idx ] )
                    found = True
                    break
                    
            if not found:
                bigrams.append( f"No placeholder '{ placeholder }' provided" )
                
        # Count the bigrams
        from collections import Counter
        bigram_counter = Counter( bigrams )
        # Print out the most common bigrams sorted descending
        for bigram, count in bigram_counter.most_common():
            print( f"{ bigram }: { count }" )
    
    def _build_function_mapping_questions( self, raw_lines, placeholders_and_values ):
        """
        Builds function mapping questions.
        
        Args:
            raw_lines (list): List of raw lines
            placeholders_and_values (dict): Dictionary of placeholders and values
            
        Returns:
            list: List of function mapping questions
        """
        du.print_banner( "Building function mapping questions...", prepend_nl=True)
        lines   = []
        for line in raw_lines:
            
            # Iterate over placeholders and substitute random values for them
            for placeholder, values in placeholders_and_values.items():
                line = line.replace( placeholder, random.choice( values ) )
            
            # Insert interjections and salutations
            _, line = self.prompt_generator.insert_interjection( line, self.prompt_generator.interjections )
            _, line = self.prompt_generator.prepend_salutation( line, self.prompt_generator.salutations )
            lines.append( line )
            if self.debug:print( line )
        
        return lines
    
    def _generate_function_mapping_response_objects( self, questions, max_questions=None ):
        """
        Generates function mapping response objects.
        
        Args:
            questions (list): List of questions
            max_questions (int, optional): Maximum number of questions to process
            
        Returns:
            list: List of response objects
        """
        from cosa.utils.util_stopwatch import Stopwatch
        
        # If max_questions is None, the slice will be all the questions
        questions = questions[ 0:max_questions ]
        responses = []
        counter   = 0
        
        timer = Stopwatch( msg=f"Generating function mapping for { len( questions ) } questions..." )
        for question in questions:
            
            counter += 1
            from cosa.agents.function_mapping_search import FunctionMappingSearch
            mapper = FunctionMappingSearch( question=question, last_question_asked=question, debug=self.debug, verbose=self.verbose )
            du.print_banner( f"Question { counter } of { len( questions ) }: { question }", end="\n", prepend_nl=True )
            prompt_response_dict = mapper.run_prompt( include_raw_response=True )
            
            responses.append( prompt_response_dict )
            
            # Print out some ~progress stats
            delta_ms            = timer.get_delta_ms()
            time_elapsed        = int( delta_ms / 1000 )
            ms_per_question     = int( round( delta_ms / counter, 0 ) )
            time_per_question   = int( ms_per_question / 1000 )
            questions_remaining = len( questions ) - counter
            seconds_remaining   = int( ms_per_question * questions_remaining / 1000 )
            
            print( f"Time elapsed { time_elapsed:,} seconds. Average time per question: { time_per_question:,} seconds. { questions_remaining } questions remaining, ETA: { seconds_remaining:,} seconds...", end="\n\n" )
        
        timer.print( msg="Done!", use_millis=False )
        print( f"Average time per question: { round( timer.get_delta_ms() / len( questions ), 0 ):,} ms" )
        
        return responses
    
    def build_simple_agent_router_training_prompts( self, sample_size_per_command=400 ):
        """
        Builds training prompts for simple agent router commands.
        
        Args:
            sample_size_per_command (int): Number of samples to generate per command
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated training prompts
        """
        instructions, inputs, outputs, prompts, gpt_messages, commands = self._get_6_empty_lists()
        
        gpt_instruction = self.prompt_generator.agent_router_instruction_template_gpt.format( command_choices=self.prompt_generator.agent_router_commands )
        
        for simple_command in self.prompt_generator.agent_router_simple_commands.keys():
            
            du.print_banner( f"Building prompts for simple AGENT ROUTER command [{ simple_command }]", prepend_nl=True, end="\n" )
            counter = 1
            
            raw_lines = du.get_file_as_list( self.path_prefix + self.prompt_generator.agent_router_simple_commands[ simple_command ], clean=True )
            
            for raw_line in raw_lines:
                
                _, raw_line = self.prompt_generator.insert_interjection( raw_line, self.prompt_generator.interjections )
                _, raw_line = self.prompt_generator.prepend_salutation( raw_line, self.prompt_generator.salutations )
                
                instruction = self.prompt_generator.vox_cmd_instruction_template.format( command_choices=self.prompt_generator.agent_router_commands )
                human_says  = self.prompt_generator.common_human_says_template.format( voice_command=raw_line )
                input_text  = self.prompt_generator.common_input_template.format( human_says=human_says, response_format=self.prompt_generator.common_response_format )
                output      = self.prompt_generator.common_output_template.format( command=simple_command, args="" )
                prompt      = self.prompt_generator._get_prompt_instruction_format( instruction, input_text )
                
                instructions.append( instruction )
                inputs.append( input_text )
                outputs.append( output )
                prompts.append( prompt )
                commands.append( simple_command )
                
                gpt_messages.append( self._get_gpt_messages_dict( gpt_instruction, raw_line, simple_command, "" ) )
                
                self._do_conditional_print( counter, raw_line )
                counter += 1
            
        simple_agent_router_qna_df = pd.DataFrame( { "command": commands, "instruction": instructions, "input": inputs, "output": outputs, "prompt": prompts, "gpt_message": gpt_messages } )
        simple_agent_router_qna_df = self._prune_duplicates_and_sample( simple_agent_router_qna_df, sample_size=( sample_size_per_command * len( self.prompt_generator.vox_cmd_simple_commands ) ), sample_size_per_command=sample_size_per_command )
        
        return simple_agent_router_qna_df
    
    def build_all_training_prompts( self, sample_size_per_compound_command=2000, sample_size_per_simple_command=400 ):
        """
        Builds all training prompts by combining all command types.
        
        Args:
            sample_size_per_compound_command (int): Number of samples to generate per compound command
            sample_size_per_simple_command (int): Number of samples to generate per simple command
            
        Returns:
            pandas.DataFrame: Combined DataFrame containing all generated training prompts
        """
        compound_vox_cmd_qna_df       = self.build_compound_vox_cmd_training_prompts( sample_size_per_command=sample_size_per_compound_command )
        simple_vox_cmd_qna_df         = self.build_simple_vox_cmd_training_prompts( sample_size_per_command=sample_size_per_simple_command )
        
        compound_router_qna_df        = self.build_compound_agent_router_training_prompts( sample_size_per_command=sample_size_per_compound_command )
        simple_router_qna_df          = self.build_simple_agent_router_training_prompts( sample_size_per_command=sample_size_per_simple_command )
        
        # Stack both dataframes vertically
        all_qna_df = pd.concat( [ compound_vox_cmd_qna_df, simple_vox_cmd_qna_df, compound_router_qna_df, simple_router_qna_df ], ignore_index=True )
        
        # Group by command and count the number of rows per command
        command_counts = all_qna_df.groupby( "command" ).count().reset_index()[ [ "command", "input" ] ]
        # sort by command ascending
        command_counts = command_counts.sort_values( "command", ascending=True )
        du.print_banner( f"Command counts for all { all_qna_df.shape[ 0 ]:,} training prompts", prepend_nl=True)
        print( command_counts )
        
        # Calculate Max, min, and mean prompt lengths
        all_qna_df[ "prompt_length" ] = all_qna_df[ "prompt" ].apply( lambda cell: len( cell ) )
        max_prompt_length  = all_qna_df[ "prompt_length" ].max()
        min_prompt_length  = all_qna_df[ "prompt_length" ].min()
        mean_prompt_length = all_qna_df[ "prompt_length" ].mean()
        
        # Delete the prompt_length column
        all_qna_df.drop( columns=[ "prompt_length" ], inplace=True )
        
        du.print_banner( f"Max, min, and mean prompt CHARACTER counts for all { all_qna_df.shape[ 0 ]:,} training prompts", prepend_nl=True)
        print( f"Max  prompt length [{ max_prompt_length:,}] characters" )
        print( f"Min  prompt length [{ min_prompt_length:,}] characters" )
        print( f"Mean prompt length [{ round( mean_prompt_length, 1 ):,}] characters" )
        
        # Now calculate max min and mean word counts in the prompt column
        all_qna_df[ "prompt_word_count" ] = all_qna_df[ "prompt" ].apply( lambda cell: len( cell.split( " " ) ) )
        max_prompt_word_count  = all_qna_df[ "prompt_word_count" ].max()
        min_prompt_word_count  = all_qna_df[ "prompt_word_count" ].min()
        mean_prompt_word_count = all_qna_df[ "prompt_word_count" ].mean()
        
        # Delete the prompt_word_count column
        all_qna_df.drop( columns=[ "prompt_word_count" ], inplace=True )
        
        du.print_banner( f"Max, min, and mean prompt WORD counts for all { all_qna_df.shape[ 0 ]:,} training prompts", prepend_nl=True )
        print( f"Max  prompt length [{ max_prompt_word_count:,}] words" )
        print( f"Min  prompt length [{ min_prompt_word_count:,}] words" )
        print( f"Mean prompt length [{ round( mean_prompt_word_count, 1 ):,}] words" )
        
        return all_qna_df
    
    def query_llm_tgi( self, prompt, model_name, max_new_tokens=1024, temperature=0.25, top_k=10, top_p=0.9, silent=False ):
        """
        Queries a TGI server with a prompt.
        
        Args:
            prompt (str): The prompt to send to the model
            model_name (str): Name of the model to use
            max_new_tokens (int): Maximum number of tokens to generate
            temperature (float): Temperature for generation
            top_k (int): Top-k sampling parameter
            top_p (float): Top-p sampling parameter
            silent (bool): Whether to suppress output
            
        Returns:
            str: Generated response
        """
        from huggingface_hub import InferenceClient
        from cosa.utils.util_stopwatch import Stopwatch
    
        timer = Stopwatch( msg=f"Asking LLM [{ model_name }]...".format( model_name ), silent=silent )
        
        client         = InferenceClient( self.tgi_url )
        token_list     = []
        ellipsis_count = 0
        
        if self.debug and self.verbose:
            for line in prompt.split( "\n" ):
                print( line )
        
        for token in client.text_generation(
            prompt, max_new_tokens=max_new_tokens, stream=True, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=[ "</response>" ]
        ):
            if self.debug:
                print( token, end="" )
            else:
                if not silent: print( ".", end="" )
                ellipsis_count += 1
                if ellipsis_count == 120:
                    ellipsis_count = 0
                    print()
                
            token_list.append( token )
            
        response = "".join( token_list ).strip()
        
        timer.print( msg="Done!", use_millis=True, prepend_nl=True, end="\n" )
        tokens_per_second = len( token_list ) / ( timer.get_delta_ms() / 1000.0 )
        print( f"Tokens per second [{ round( tokens_per_second, 1 ) }]" )
        
        if self.debug:
            print( f"Token list length [{ len( token_list ) }]" )
            if self.verbose:
                for line in response.split( "\n" ):
                    print( line )
        
        return response
    
    def generate_responses( self, df, tokenizer=None, model=None, switch="tgi", model_name=None, max_new_tokens=1024, temperature=0.25, top_k=10, top_p=0.9, device="cuda:0", debug=False, verbose=False, silent=False ):
        """
        Generates responses for a given DataFrame using various LLM backends.
        
        Args:
            df (pandas.DataFrame): DataFrame with prompts
            tokenizer: Tokenizer for the model
            model: Model to use
            switch (str): LLM backend to use ('tgi', 'deepily', 'openai', 'huggingface')
            model_name (str): Name of the model to use
            max_new_tokens (int): Maximum number of tokens to generate
            temperature (float): Temperature for generation
            top_k (int): Top-k sampling parameter
            top_p (float): Top-p sampling parameter
            device (str): Device to use for inference
            debug (bool): Whether to enable debug output
            verbose (bool): Whether to enable verbose output
            silent (bool): Whether to suppress output
            
        Returns:
            pandas.DataFrame: DataFrame with generated responses
        """
        from cosa.utils.util_stopwatch import Stopwatch
        import torch
        from huggingface_hub import InferenceClient
        import openai
        from cosa.agents.llm import Llm
        
        self.reset_call_counter()
        rows = df.shape[0]
        
        timer = Stopwatch( msg=f"Generating responses for { rows:,} rows...", silent=silent )
        
        # Save the original debug/verbose settings
        original_debug = self.debug
        original_verbose = self.verbose
        
        # Use the passed parameters if provided
        if debug is not None:
            self.debug = debug
        if verbose is not None:
            self.verbose = verbose
        
        try:
            if switch == "tgi":
                if self.debug: print( f"Using TGI w/ model_name [{ model_name }]..." )
                df[ "response" ]  = df[ "prompt" ].apply( lambda cell: self._get_response_to_prompt( cell, rows, timer=timer, switch=switch, model_name=model_name, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, silent=silent ) )
            elif switch == "deepily":
                if self.debug: print( f"Using DEEPILY w/ model_name [{ model_name }]..." )
                df[ "response" ]  = df[ "prompt" ].apply( lambda cell: self._get_response_to_prompt( cell, rows, model=model, timer=timer, switch=switch, model_name=model_name, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, silent=silent ) )
            elif switch == "openai":
                if self.debug: print( f"Using OPENAI w/ model_name [{ model_name }]..." )
                df[ "response" ]  = df[ "gpt_message" ].apply( lambda cell: self._get_response_to_prompt( cell, rows, timer=timer, switch=switch, model_name=model_name, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, silent=silent ) )
            elif switch == "huggingface":
                if self.debug: print( f"Using HuggingFace model_name [{ model_name }] in memory...", end="\n\n" )
                df[ "response" ]  = df[ "prompt" ].apply( lambda cell: self._get_response_to_prompt( cell, rows, timer=timer, switch=switch, model_name=model_name, tokenizer=tokenizer, model=model, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, device=device, silent=silent, debug=self.debug, verbose=self.verbose ) )
            else:
                raise Exception( f"Unknown runtime llm datasource switch [{ switch }]" )
        finally:
            # Restore original debug/verbose settings
            self.debug = original_debug
            self.verbose = original_verbose
        
        timer.print( msg="Done!", use_millis=False, prepend_nl=True, end="\n" )
        ms_per_item = timer.get_delta_ms() / ( rows * 1.0 )
        print( f"[{ round( ms_per_item, 1 ):,}] ms per item" )
        
        return df
    
    def validate_responses( self, df ):
        """
        Validates responses in a dataframe using the response validator.
        
        Args:
            df (pandas.DataFrame): DataFrame with responses
            
        Returns:
            pandas.DataFrame: DataFrame with validation columns
        """
        return self.response_validator.validate_responses( df )
    
    def print_validation_stats( self, df, title="Validation Stats" ):
        """
        Prints validation statistics.
        
        Args:
            df (pandas.DataFrame): DataFrame with validation columns
            title (str): Title for the validation stats
            
        Returns:
            pandas.DataFrame: Stats dataframe
        """
        return self.response_validator.print_validation_stats( df, title=title )
    
    def get_train_test_validate_split( self, df, sample_size=1000, test_size=0.2, test_validate_size=0.5, stratify="command" ):
        """
        Splits a DataFrame into training, testing, and validation sets.
        
        Args:
            df (pandas.DataFrame): DataFrame to split
            sample_size (int): Number of samples to use
            test_size (float): Fraction of data to use for testing (0.0-1.0)
            test_validate_size (float): Fraction of testing data to use for validation (0.0-1.0)
            stratify (str): Column name to use for stratified sampling
            
        Returns:
            tuple: (train_df, test_df, validate_df)
        """
        from sklearn.model_selection import train_test_split
        
        sampled_df = df[ [ "command", "instruction", "input", "output", "prompt", "gpt_message" ] ].sample( sample_size, random_state=42 ).copy()
        
        # Split the dataframe into train and (test+validate)
        train_df, test_validate_df = train_test_split( sampled_df, test_size=test_size, random_state=42, stratify=sampled_df[ stratify ] )
        
        # Then split (test+validate) into test and validate
        test_df, validate_df = train_test_split( test_validate_df, test_size=test_validate_size, random_state=42, stratify=test_validate_df[ stratify ] )
        
        return train_df, test_df, validate_df
    
    def write_ttv_split_to_jsonl( self, train_df, test_df, validate_df ):
        """
        Writes train/test/validate splits to JSONL files.
        
        Args:
            train_df (pandas.DataFrame): Training data
            test_df (pandas.DataFrame): Testing data
            validate_df (pandas.DataFrame): Validation data
        """
        import os
        
        du.print_banner( "Writing train, test, validate splits to jsonl...", prepend_nl=True)
        print( f"   train_df.shape: { train_df.shape[ 0 ]:,} x { train_df.shape[ 1 ]}" )
        print( f"    test_df.shape: { test_df.shape[ 0 ]:,} x { test_df.shape[ 1 ]}" )
        print( f"validate_df.shape: { validate_df.shape[ 0 ]:,} x { validate_df.shape[ 1 ]}" )
        
        path = self.path_prefix + "/src/ephemera/prompts/data/voice-commands-xml-train.jsonl"
        train_df.to_json( path, orient="records", lines=True )
        os.chmod( path, 0o666 )
        
        path = self.path_prefix + "/src/ephemera/prompts/data/voice-commands-xml-test.jsonl"
        test_df.to_json( path, orient="records", lines=True )
        os.chmod( path, 0o666 )
        
        path = self.path_prefix + "/src/ephemera/prompts/data/voice-commands-xml-validate.jsonl"
        validate_df.to_json( path, orient="records", lines=True )
        os.chmod( path, 0o666 )
        
        # GPT Training set
        path = self.path_prefix + "/src/ephemera/prompts/data/voice-commands-xml-train-gpt.jsonl"
        train_df.gpt_message.to_json( path, orient="records", lines=True )
        os.chmod( path, 0o666 )
        
        path = self.path_prefix + "/src/ephemera/prompts/data/voice-commands-xml-test-gpt.jsonl"
        test_df.gpt_message.to_json( path, orient="records", lines=True )
        os.chmod( path, 0o666 )
        
        path = self.path_prefix + "/src/ephemera/prompts/data/voice-commands-xml-validate-gpt.jsonl"
        validate_df.gpt_message.to_json( path, orient="records", lines=True )
        os.chmod( path, 0o666 )
    
    def compare_validation_results( self, before_df, after_df, title="Validation Comparison" ):
        """
        Compares validation results between two dataframes.
        
        Args:
            before_df (pandas.DataFrame): DataFrame with validation results before
            after_df (pandas.DataFrame): DataFrame with validation results after
            title (str): Title for the comparison
            
        Returns:
            pandas.DataFrame: Comparison dataframe
        """
        return self.response_validator.compare_validation_results( before_df, after_df, title=title )
    
    # Helper methods
    def _get_6_empty_lists( self ):
        """
        Returns 6 empty lists for storing prompt generation data.
        
        Returns:
            tuple: (instructions, inputs, outputs, prompts, gpt_messages, commands)
        """
        return [], [], [], [], [], []
    
    def _get_gpt_messages_dict( self, gpt_instruction, voice_command, compound_command, args ):
        """
        Creates a GPT messages dictionary.
        
        Args:
            gpt_instruction (str): System instruction
            voice_command (str): User's voice command
            compound_command (str): Expected command response
            args (str): Command arguments
            
        Returns:
            dict: Formatted GPT messages dictionary
        """
        return {
            "messages": [
                { "role": "system", "content": gpt_instruction },
                { "role": "user", "content": voice_command },
                { "role": "assistant", "content": self.prompt_generator.common_output_template.format( command=compound_command, args=args ) }
            ]
        }
    
    def _do_conditional_print( self, counter, voice_command, interval=10 ):
        """
        Conditionally prints progress information.
        
        Args:
            counter (int): Current counter value
            voice_command (str): Voice command to print
            interval (int): Print interval
        """
        if counter % interval == 0:
            if self.debug:
                print( voice_command )
            else:
                print( ".", end="" )
                if counter % ( interval * 100 ) == 0:
                    print()
    
    def _prune_duplicates_and_sample( self, df, sample_size=1000, sample_size_per_command=-1 ):
        """
        Removes duplicates and samples from a DataFrame.
        
        Args:
            df (pandas.DataFrame): DataFrame to process
            sample_size (int): Total sample size
            sample_size_per_command (int): Sample size per command
            
        Returns:
            pandas.DataFrame: Processed DataFrame
        """
        du.print_banner( "Pruning potential duplicates by 'input' values...", prepend_nl=True )
        
        rows_pre = df.shape[ 0 ]
        print( f" PRE { rows_pre:,} training inputs..." )
        df.drop_duplicates( subset=[ "input" ], inplace=True )
        rows_post  = df.shape[ 0 ]
        dupes_rows = rows_pre - rows_post
        dupes_pct  = dupes_rows / rows_pre * 100.0
        print( f"POST { rows_post:,} training inputs. Deleted { dupes_rows:,} rows = { dupes_pct:.1f }% duplicate questions" )
        
        if rows_post < sample_size:
            print( f"WARNING: Sample size [{ sample_size:,}] > rows_post [{ rows_post:,}]. Returning all [{ rows_post:,}] rows.")
            return df
        else:
            # Sample the dataframe Using proportional distributions represented by the weights value
            du.print_banner( f"Sampling { sample_size:,} rows/command from the pruned dataframe using the following weights:", prepend_nl=True )
            weights = df[ "command" ].value_counts( normalize=True )
            print( weights )
            weights = df[ "command" ].value_counts( normalize=False )
            print( weights )
            
            return df.groupby( "command" ).sample( sample_size_per_command, random_state=42 )
    
    def _get_receptionist_titles( self, requested_length=10 ):
        """
        Gets placeholder receptionist titles.
        
        Args:
            requested_length (int): Number of titles to return
            
        Returns:
            list: List of receptionist titles
        """
        return self.prompt_generator._get_placeholder_values( "/src/ephemera/prompts/data/placeholders-receptionist-titles.txt", requested_length=requested_length )
    
    def _get_events_values( self, requested_length=100 ):
        """
        Gets placeholder calendar event values.
        
        Args:
            requested_length (int): Number of events to return
            
        Returns:
            list: List of event dictionaries
        """
        events      = self.prompt_generator._get_placeholder_values( "/src/ephemera/prompts/data/placeholders-calendaring-events.txt", requested_length=None )
        locations   = self.prompt_generator._get_placeholder_values( "/src/ephemera/prompts/data/placeholders-calendaring-locations.txt", requested_length=None )
        start_times = self.prompt_generator._get_placeholder_values( "/src/ephemera/prompts/data/placeholders-calendaring-dates-and-times.txt", requested_length=None )
        people      = self.prompt_generator._get_placeholder_values( "/src/ephemera/prompts/data/placeholders-calendaring-people.txt", requested_length=None )
        
        events_values = []
        
        for i in range( requested_length ):
            events_values.append( {
                "EVENT_TYPE": random.choice( events ),
                "LOCATION"  : random.choice( locations ),
                "START_TIME": random.choice( start_times ),
                "PEOPLE"    : random.choice( people ),
                "PLACE"     : ""
            } )
        return events_values
    
    def _get_response_to_prompt(
        self, prompt, rows, model=None, switch="tgi", model_name=None, timer=None, tokenizer=None,
        max_new_tokens=1024, temperature=0.25, top_k=10, top_p=0.9, device="cuda:0", silent=False, debug=False, verbose=False
    ):
        """
        Gets a response to a specific prompt using the specified LLM backend.
        
        Args:
            prompt: The prompt to generate a response for
            rows (int): Total number of rows being processed
            Various other parameters controlling the generation and backend selection
            
        Returns:
            str: Generated response
        """
        import openai
        import torch
        from huggingface_hub import InferenceClient
        import cosa.app.util_llm_client as du_llm_client
        from cosa.agents.llm import Llm
        
        self._call_counter += 1
        
        print( f"Processing call [{ self._call_counter:03d }] out of [{ rows }] = [{ round( self._call_counter / rows * 100.0, 1 ) }%]... ", end="" )
        
        # calculate remaining time
        if timer is not None:
            try:
                elapsed_ms = timer.get_delta_ms()
                ms_per_item = elapsed_ms / ( self._call_counter * 1.0 )
                remaining_ms = ( rows - self._call_counter ) * ms_per_item
                remaining_seconds = int( remaining_ms / 1000 )
                # calculate remaining minutes
                if remaining_seconds > 60:
                    remaining_minutes = int( remaining_seconds / 60 )
                    remaining_seconds = remaining_seconds % 60
                    print( f"ETA mm:ss { remaining_minutes:}:{ remaining_seconds:02d }" )
                else:
                    print( f"ETA: { remaining_seconds } seconds" )
            except Exception as e:
                print( f"ETA: Error '{ e }'" )
        
        # Handle different LLM backends
        if switch == "tgi":
            client = InferenceClient( self.tgi_url )
            token_list = []
            ellipsis_count = 0
            
            if debug and verbose:
                for line in prompt.split( "\n" ):
                    print( line )
            
            for token in client.text_generation(
                prompt, max_new_tokens=max_new_tokens, stream=True, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=[ "</response>" ]
            ):
                if debug:
                    print( token, end="" )
                else:
                    if not silent: print( ".", end="" )
                    ellipsis_count += 1
                    if ellipsis_count == 120:
                        ellipsis_count = 0
                        print()
                    
                token_list.append( token )
                
            response = "".join( token_list ).strip()
            return response
            
        elif switch == "deepily":
            llm = Llm( model=model, debug=debug, verbose=verbose )
            results = llm.query_llm( prompt=prompt, temperature=temperature, top_p=top_p, top_k=top_k )
            return results
            
        elif switch == "openai":
            openai.api_key = du.get_api_key( "openai", project_root=du.get_project_root() )
            response = openai.chat.completions.create(
                model=Llm.extract_model_name( model_name ),
                messages=prompt[ "messages" ],
                temperature=temperature,
                max_tokens=max_new_tokens,
                top_p=top_p,
                frequency_penalty=0.0,
                presence_penalty=0.0
            )
            return response.choices[ 0 ].message.content.strip()
            
        elif switch == "huggingface":
            return du_llm_client.query_llm_in_memory( model, tokenizer, prompt, device=device, model_name=model_name, max_new_tokens=max_new_tokens, silent=silent, debug=debug, verbose=verbose )
            
        else:
            raise Exception( f"Unknown switch [{ switch }]" )