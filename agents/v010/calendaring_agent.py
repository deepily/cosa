import json
from typing import tuple, Any

from cosa.agents.v010.agent_base import AgentBase


class CalendaringAgent( AgentBase ):
    """
    Agent for handling calendar-related queries and operations.
    
    This agent processes questions about events, dates, and scheduling
    using a DataFrame of calendar event data.
    """
    
    def __init__( self, question: str="", last_question_asked: str="", question_gist: str="", routing_command: str="agent router go to calendar", push_counter: int=-1, debug: bool=False, verbose: bool=False, auto_debug: bool=False, inject_bugs: bool=False ) -> None:
        """
        Initialize calendaring agent with events data.
        
        Requires:
            - df_path_key 'path_to_events_df_wo_root' exists in config
            - Events CSV file contains 'event_type' column
            - Calendar routing command exists in config
            
        Ensures:
            - Loads events DataFrame from configured path
            - Initializes prompt with calendar metadata
            - Sets up XML response tags for calendar operations
            
        Raises:
            - FileNotFoundError if events CSV file missing
            - KeyError if required config keys missing
        """
        
        super().__init__( df_path_key="path_to_events_df_wo_root", question=question, question_gist=question_gist, last_question_asked=last_question_asked, routing_command=routing_command, push_counter=push_counter, debug=debug, verbose=verbose, auto_debug=auto_debug, inject_bugs=inject_bugs )

        self.prompt = self._get_prompt()
        
        self.xml_response_tag_names = [ "question", "thoughts", "code", "example", "returns", "explanation" ]
        
    def _get_prompt( self ) -> str:
        """
        Generate prompt with calendar data metadata.
        
        Requires:
            - self.last_question_asked is set
            - Events DataFrame is loaded
            - self.prompt_template exists
            
        Ensures:
            - Returns formatted prompt with question and metadata
            - Includes column names, event types, and sample data
            
        Raises:
            - None
        """
        
        column_names, unique_event_types, head = self._get_metadata()
        
        return self.prompt_template.format( question=self.last_question_asked, column_names=column_names, unique_event_types=unique_event_types, head=head )
    
    def _get_metadata( self ) -> tuple[list[str], list[str], str]:
        """
        Extract metadata from events DataFrame.
        
        Requires:
            - self.df is loaded with events data
            - DataFrame has 'event_type' column
            
        Ensures:
            - Returns tuple of (column_names, unique_event_types, xml_sample)
            - XML sample includes first 2 and last 2 rows
            - XML is formatted with 'events' root tag
            
        Raises:
            - AttributeError if DataFrame not properly initialized
        """
        
        column_names = self.df.columns.tolist()
        unique_event_types = self.df[ "event_type" ].unique().tolist()
        
        head = self.df.head( 2 ).to_xml( index=False )
        head = head + self.df.tail( 2 ).to_xml( index=False )
        head = head.replace( "data>", "events>" ).replace( "<?xml version='1.0' encoding='utf-8'?>", "" )
        
        return column_names, unique_event_types, head
        
    def restore_from_serialized_state( self, file_path: str ) -> None:
        """
        Restore calendaring agent state from JSON file.
        
        Requires:
            - file_path points to valid JSON file
            
        Ensures:
            - Raises NotImplementedError (not implemented)
            
        Raises:
            - NotImplementedError always
        """
        
        raise NotImplementedError( f"CalendaringAgent.restore_from_serialized_state( file_path={file_path} ) not implemented" )
    
if __name__ == "__main__":
    
    # Test the CalendaringAgent with various queries
    test_questions = [
        "What events do I have this week?",
        "Show me all birthdays this month",
        "What meetings are scheduled for tomorrow?"
    ]
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n=== Test {i}: {question} ===")
        
        try:
            # Initialize the calendaring agent
            cal_agent = CalendaringAgent(
                question=question,
                last_question_asked=question,
                question_gist=question,
                debug=True,
                verbose=True,
                auto_debug=True
            )
            
            # Run the prompt
            print("\nRunning prompt...")
            response_dict = cal_agent.run_prompt()
            
            # Run the code if available
            if cal_agent.is_code_runnable():
                print("\nRunning code...")
                code_result = cal_agent.run_code()
                print(f"Code output: {code_result.get('output', 'No output')}")
                
                # Run formatter to get conversational response
                print("\nRunning formatter...")
                cal_agent.run_formatter()
                print(f"Formatted response: {cal_agent.answer_conversational}")
            else:
                print("No runnable code generated")
                
        except Exception as e:
            print(f"Test failed with error: {e}")
        
        print("-" * 50)