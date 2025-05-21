import re
from typing import Optional, Union

import cosa.utils.util as du

def get_value_by_xml_tag_name( xml_string: str, name: str, default_value: Optional[str]=None ) -> Union[str, None]:
    """
    Extract the value enclosed by XML tag open/close brackets.
    
    Requires:
        - xml_string is a string containing XML content
        - name is the tag name to search for
        - default_value is None or a string to return if tag not found
        
    Ensures:
        - Returns the value between <name> and </name> tags
        - Returns default_value if tag is not found
        - Returns error message if tag not found and default_value is None
        
    Example:
        get_value_by_xml_tag_name('<foo>bar</foo>', 'foo') returns 'bar'
    """
    if f"<{name}>" not in xml_string or f"</{name}>" not in xml_string:
        if default_value is None:
            return f"Error: `{name}` not found in xml_string"
        else:
            return default_value
    
    return xml_string.split( f"<{name}>" )[ 1 ].split( f"</{name}>" )[ 0 ]
    
    
def get_xml_tag_and_value_by_name( xml_string: str, name: str, default_value: Optional[str]=None ) -> str:
    """
    Extract and return the full XML tag with its value.
    
    Requires:
        - xml_string is a string containing XML content
        - name is the tag name to search for
        - default_value is None or a string to use if tag not found
        
    Ensures:
        - Returns the complete tag with value: <name>value</name>
        - Uses get_value_by_xml_tag_name to extract the value
        - Wraps the value in proper XML tags
        
    Example:
        get_xml_tag_and_value_by_name('<foo>bar</foo>', 'foo') returns '<foo>bar</foo>'
    """
    
    value = get_value_by_xml_tag_name( xml_string, name, default_value=default_value )
    name_and_value = f"<{name}>{value}</{name}>"
    
    return name_and_value

def get_nested_list( xml_string: str, tag_name: str="code", debug: bool=False, verbose: bool=False ) -> list[str]:
    """
    Extract a list of values from nested line tags within a parent tag.
    
    Requires:
        - xml_string is a string containing XML with nested <line> tags
        - tag_name is the parent tag name (default: "code")
        - debug and verbose are boolean flags for output control
        
    Ensures:
        - Returns list of strings extracted from <line> tags
        - Removes XML escapes from extracted content
        - Handles multiline content within the parent tag
        - Returns empty list if no matching tags found
    """
    # Matches all text between the opening and closing line tags, including the white space after the opening line tag
    pattern = re.compile( r"<line>(.*?)</line>" )
    lines = get_value_by_xml_tag_name( xml_string, tag_name )
    code_list = [ ]
    
    for line in lines.split( "\n" ):
            
            match = pattern.search( line )
            
            if match:
                line = match.group( 1 )
                line = remove_xml_escapes( line )
                code_list.append( line )
                if debug and verbose: print( line )
            else:
                # code_list.append( "" )
                if debug and verbose: print( "[]" )
        
    return code_list

def remove_xml_escapes( xml_string: str ) -> str:
    """
    Remove common XML escape sequences from a string.
    
    Requires:
        - xml_string is a string that may contain XML escapes
        
    Ensures:
        - Returns string with XML escapes replaced:
          - &gt; becomes >
          - &lt; becomes <
          - &amp; becomes &
        - Order of replacements prevents double-unescaping
    """
    return xml_string.replace( "&gt;", ">" ).replace( "&lt;", "<" ).replace( "&amp;", "&" )

def rescue_code_using_tick_tick_tick_syntax( raw_response_text: str, debug: bool=False ) -> str:
    """
    Extract code from markdown-style triple backtick syntax.
    
    Requires:
        - raw_response_text is a string that may contain ```python blocks
        - debug is a boolean flag for debug output
        
    Ensures:
        - Returns code wrapped in XML line tags if found
        - Returns empty string if no ```python block found
        - Strips leading/trailing whitespace
        - Converts each line to <line>content</line> format
    """
    if debug: print( f"before: [{raw_response_text}]" )
    raw_response_text = raw_response_text.strip()
    if debug: print( f"after: [{raw_response_text}]" )
    
    if raw_response_text.startswith( "```python" ) and raw_response_text.endswith( "```" ):
        
        msg = "¡Yay! Returning rescued code list using default tick tick tick syntax"
        if debug:
            du.print_banner( msg )
        else:
            print( msg )
        
        lines = raw_response_text.split( "```python" )[ 1 ]
        lines = lines.split( "```" )[ 0 ]
        lines = lines.split( "\n" )
        
        # wrap each line with a xml-esque line tag
        lines = [ f"<line>{line}</line>" for line in lines ]
        lines = "\n".join( lines )
        
        if debug:
            for line in lines.split( "\n" ): print( line )
        
        return lines
    
    else:
        
        if debug:
            du.print_banner( "¡Boo!, no ```python found, either!", expletive=True )
        else:
            print( "¡Boo!, no ```python found, either!" )
            
        return ""

def strip_all_white_space( raw_xml: str ) -> str:
    """
    Remove whitespace between XML tags.
    
    Requires:
        - raw_xml is a string containing XML content
        
    Ensures:
        - Returns XML with whitespace between tags removed
        - Preserves whitespace within tag content
        - Strips leading/trailing whitespace from entire string
        
    Example:
        strip_all_white_space('<a> <b>text</b> </a>') returns '<a><b>text</b></a>'
    """
    # Remove white space outside XML tags
    return re.sub( r'>\s+<', '><', raw_xml.strip() )