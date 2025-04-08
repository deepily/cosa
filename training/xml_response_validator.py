import pandas as pd
from xmlschema import XMLSchema

import cosa.utils.util as du
import cosa.utils.util_xml as dux

class XmlResponseValidator:
    """
    Validates XML responses and calculates performance metrics.
    
    Responsible for:
    - Validating XML structure
    - Comparing responses to expected outputs
    - Calculating accuracy metrics
    - Producing validation reports
    """
    
    def __init__( self, debug=False, verbose=False ):
        self.debug           = debug
        self.verbose         = verbose
        self._xml_schema     = self._get_xml_schema()
    
    def _get_xml_schema( self ):
        """
        Creates the XML schema for validation.
        
        Returns:
            XMLSchema: Schema object for validating responses
        """
        xsd_string = """
        <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
          <xs:element name="response">
            <xs:complexType>
              <xs:sequence>
                <xs:element name="command" type="xs:string"/>
                <xs:element name="args" type="xs:string"/>
              </xs:sequence>
            </xs:complexType>
          </xs:element>
        </xs:schema>
        """
        
        return XMLSchema( xsd_string )
    
    def is_valid_xml( self, xml_str ):
        """
        Checks if XML is valid according to schema.
        
        Args:
            xml_str (str): XML string to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            return self._xml_schema.is_valid( xml_str )
        except Exception:
            return False
    
    def contains_valid_xml_tag( self, xml_str, tag_name ):
        """
        Checks if XML contains a specific tag.
        
        Args:
            xml_str (str): XML string to check
            tag_name (str): Tag name to look for
            
        Returns:
            bool: True if tag exists, False otherwise
        """
        try:
            return f"<{tag_name}>" in xml_str and f"</{tag_name}>" in xml_str
        except Exception:
            return False
    
    def is_response_exact_match( self, response, answer ):
        """
        Checks if response exactly matches expected answer.
        
        Args:
            response (str): Generated response
            answer (str): Expected answer
            
        Returns:
            bool: True if exact match, False otherwise
        """
        # Remove white space outside XML tags
        response = dux.strip_all_white_space( response )
        answer   = dux.strip_all_white_space( answer )
        
        if self.debug and self.verbose:
            print( f"response: [{response}]" )
            print( f"  answer: [{answer}]" )
            
        return response == answer
    
    def contains_correct_response_values( self, response, answer ):
        """
        Check if the most common formatting error (```xml) is hiding a correct <response>...</response>
        
        Args:
            response (str): Generated response
            answer (str): Expected answer
            
        Returns:
            bool: True if the response contains correct values, False otherwise
        """
        response_tag = dux.get_xml_tag_and_value_by_name( response, "response", default_value="broken" )
        if response_tag == "broken":
            return False
        
        return self.is_response_exact_match( response_tag, answer )
    
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
        command_response = dux.get_value_by_xml_tag_name( response, tag_name, default_value="broken" )
        command_answer   = dux.get_value_by_xml_tag_name( answer, tag_name, default_value="broken" )
        
        return command_response != "broken" and command_answer != "broken" and command_response == command_answer
    
    def validate_responses( self, df ):
        """
        Validates responses in a dataframe.
        
        Args:
            df (pandas.DataFrame): Dataframe with 'response' and 'output' columns
            
        Returns:
            pandas.DataFrame: DataFrame with added validation columns
        """
        # Validate the structure and content of the xml response
        df["response_xml_is_valid"]       = df["response"].apply( lambda cell: self.is_valid_xml( cell ) )
        df["contains_response"]           = df["response"].apply( lambda cell: self.contains_valid_xml_tag( cell, "response" ) )
        df["contains_command"]            = df["response"].apply( lambda cell: self.contains_valid_xml_tag( cell, "command" ) )
        df["contains_args"]               = df["response"].apply( lambda cell: self.contains_valid_xml_tag( cell, "args" ) )
        df["response_is_exact"]           = df.apply( lambda row: self.is_response_exact_match( row["response"], row["output"] ), axis=1 )
        df["response_has_correct_values"] = df.apply( lambda row: self.contains_correct_response_values( row["response"], row["output"] ), axis=1 )
        df["command_is_correct"]          = df.apply( lambda row: self.tag_values_are_equal( row["response"], row["output"], tag_name="command" ), axis=1 )
        df["args_is_correct"]             = df.apply( lambda row: self.tag_values_are_equal( row["response"], row["output"], tag_name="args" ), axis=1 )
        
        return df
    
    def print_validation_stats( self, df, title="Validation Stats" ):
        """
        Prints validation statistics.
        
        Args:
            df (pandas.DataFrame): Dataframe with validation columns
            title (str, optional): Title for the stats display. Defaults to "Validation Stats".
            
        Returns:
            pandas.DataFrame: Stats dataframe with accuracy per command
        """
        du.print_banner( title, prepend_nl=True )
        print( f"               Is valid xml {df.response_xml_is_valid.mean() * 100:.1f}%" )
        print( f"        Contains <response> {df.contains_response.mean() * 100:.1f}%" )
        print( f"         Contains <command> {df.contains_command.mean() * 100:.1f}%" )
        print( f"            Contains <args> {df.contains_args.mean() * 100:.1f}%" )
        print( f"          Response is exact {df.response_is_exact.mean() * 100:.1f}%" )
        print( f"Response has correct values {df.response_has_correct_values.mean() * 100:.1f}%" )
        print( f"         Command is correct {df.command_is_correct.mean() * 100:.1f}%" )
        print( f"            Args is correct {df.args_is_correct.mean() * 100:.1f}%" )
        
        # Calculate accuracy per command
        cols                = ["command", "response_is_exact"]
        stats_df           = df[cols].copy()
        stats_df           = stats_df.groupby( "command" )["response_is_exact"].agg( ["mean", "sum", "count"] ).reset_index()
        
        # Format the percentages
        stats_df["mean"]   = stats_df["mean"].apply( lambda cell: f"{cell * 100:.2f}%" )
        # Sorts by mean ascending: Remember it's now a string we're sorting
        stats_df           = stats_df.sort_values( "mean", ascending=False )
        # Since I can't delete the index and not affect the other values, I'll just set the index to an empty string
        stats_df.index     = [""] * stats_df.shape[0]

        du.print_banner( f"{title}: Accuracy per command", prepend_nl=True )
        print( stats_df )
        
        return stats_df
    
    def get_validation_stats( self, df ):
        """
        Get validation statistics as a dictionary.
        
        Args:
            df (pandas.DataFrame): Dataframe with validation columns
            
        Returns:
            dict: Dictionary with validation statistics
        """
        stats = {
            "valid_xml_percent"        : df.response_xml_is_valid.mean() * 100,
            "contains_response_percent": df.contains_response.mean() * 100,
            "contains_command_percent" : df.contains_command.mean() * 100,
            "contains_args_percent"    : df.contains_args.mean() * 100,
            "response_exact_percent"   : df.response_is_exact.mean() * 100,
            "correct_values_percent"   : df.response_has_correct_values.mean() * 100,
            "command_correct_percent"  : df.command_is_correct.mean() * 100,
            "args_correct_percent"     : df.args_is_correct.mean() * 100,
        }
        
        # Add per-command statistics
        command_stats = df.groupby( "command" )["response_is_exact"].mean().to_dict()
        stats["per_command"] = {cmd: val * 100 for cmd, val in command_stats.items()}
        
        return stats
    
    def compare_validation_results( self, before_df, after_df, title="Validation Comparison" ):
        """
        Compares validation results between two dataframes.
        
        Args:
            before_df (pandas.DataFrame): Dataframe with validation results before
            after_df (pandas.DataFrame): Dataframe with validation results after
            title (str, optional): Title for the comparison. Defaults to "Validation Comparison".
            
        Returns:
            pandas.DataFrame: Comparison dataframe
        """
        metrics = [
            "response_xml_is_valid", "contains_response", "contains_command",
            "contains_args", "response_is_exact", "response_has_correct_values",
            "command_is_correct", "args_is_correct"
        ]
        
        metric_names = [
            "Valid XML", "Contains <response>", "Contains <command>",
            "Contains <args>", "Exact response match", "Correct response values",
            "Command is correct", "Args are correct"
        ]
        
        before_vals = [before_df[m].mean() * 100 for m in metrics]
        after_vals = [after_df[m].mean() * 100 for m in metrics]
        diff_vals = [after - before for after, before in zip( after_vals, before_vals )]
        
        comparison_df = pd.DataFrame({
            "Metric": metric_names,
            "Before (%)": [f"{val:.1f}%" for val in before_vals],
            "After (%)": [f"{val:.1f}%" for val in after_vals],
            "Difference": [f"{'+' if val > 0 else ''}{val:.1f}%" for val in diff_vals]
        })
        
        du.print_banner( title, prepend_nl=True )
        print( comparison_df )
        
        return comparison_df