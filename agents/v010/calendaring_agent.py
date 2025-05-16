import json

from cosa.agents.v010.agent_base import AgentBase


class CalendaringAgent( AgentBase ):
    
    def __init__( self, question="", last_question_asked="", question_gist="", routing_command="agent router go to calendar", push_counter=-1, debug=False, verbose=False, auto_debug=False, inject_bugs=False ):
        
        super().__init__( df_path_key="path_to_events_df_wo_root", question=question, question_gist=question_gist, last_question_asked=last_question_asked, routing_command=routing_command, push_counter=push_counter, debug=debug, verbose=verbose, auto_debug=auto_debug, inject_bugs=inject_bugs )

        self.prompt = self._get_prompt()
        
        self.xml_response_tag_names = [ "question", "thoughts", "code", "example", "returns", "explanation" ]
        
    def _get_prompt( self ):
        
        column_names, unique_event_types, head = self._get_metadata()
        
        return self.prompt_template.format( question=self.last_question_asked, column_names=column_names, unique_event_types=unique_event_types, head=head )
    
    def _get_metadata( self ):
        
        column_names = self.df.columns.tolist()
        unique_event_types = self.df[ "event_type" ].unique().tolist()
        
        head = self.df.head( 2 ).to_xml( index=False )
        head = head + self.df.tail( 2 ).to_xml( index=False )
        head = head.replace( "data>", "events>" ).replace( "<?xml version='1.0' encoding='utf-8'?>", "" )
        
        return column_names, unique_event_types, head
        
    def restore_from_serialized_state( self, file_path ):
        
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