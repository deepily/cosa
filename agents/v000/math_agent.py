import time

import cosa.utils.util as du
import cosa.utils.util_xml as dux

from cosa.agents.llm_v0 import Llm_v0
from cosa.utils.util_stopwatch import Stopwatch
from cosa.memory.solution_snapshot import SolutionSnapshot
from cosa.agents.agent_base import AgentBase

class MathAgent( AgentBase ):
    def __init__( self, question="", question_gist="", last_question_asked="", push_counter=-1, routing_command="agent router go to math", debug=False, verbose=False, auto_debug=False, inject_bugs=False ):
        
        super().__init__( df_path_key=None, question=question, question_gist=question_gist, last_question_asked=last_question_asked, routing_command=routing_command, push_counter=push_counter, debug=debug, verbose=verbose, auto_debug=auto_debug, inject_bugs=inject_bugs )
        
        # du.print_banner( "MathAgent.__init__()" )
        print( "¡OJO! MathAgent is using last_question_asked because it wants all the specificity contained within the voice to text transcription" )
        self.prompt = self.prompt_template.format( question=self.last_question_asked )
        self.xml_response_tag_names   = [ "thoughts", "brainstorm", "evaluation", "code", "example", "returns", "explanation" ]
    
        # self.serialize_prompt_to_json = self.config_mgr.get( "agent_todo_list_serialize_prompt_to_json", default=False, return_type="boolean" )
        # self.serialize_code_to_json   = self.config_mgr.get( "agent_todo_list_serialize_code_to_json",   default=False, return_type="boolean" )
    
    def restore_from_serialized_state( self, file_path ):
        
        raise NotImplementedError( "DateAndTimeAgent.restore_from_serialized_state() not implemented" )
    
    def format_output( self ):
        
        """
        Format the output based on the configuration for math agent.

        If 'formatter_prompt_for_math_terse' is True, set the answer as the output from 'code_response_dict'.
        Otherwise, call the superclass method 'format_output' and set the answer accordingly.
        """
        terse_output = self.config_mgr.get( "formatter_prompt_for_math_terse", default=False, return_type="boolean" )
        
        if terse_output:
            self.answer_conversational = self.code_response_dict[ "output" ]
        else:
            super().format_output()
            
        return self.answer_conversational

if __name__ == "__main__":
    
    questions = [
        # "if I have six eggs, and my friend has six eggs, when we put them all in one basket, how many eggs do we have?",
        'Yo, einstein! How many times does the letter "R" occur in the word "strawberry"',
        # 'Yo, Einstein! How many lowercase "R"s are in the word "strawberry"?',
        # "What's the square root of 145?",
        "What's worth more: 100 pennies or three quarters?",
        "Which number is larger, 9.9 or 9.11?",
        # "What is 2+5+4+5-12+7-5?",
        "If a train travels 60 miles in 1.5 hours, how far will it travel in 2 hours?",
        # "Calculate the answer: 241 - (-241) + 1",
        "Count the number of occurrences of the letter 'L' in the word - ’LOLLAPALOOZA’.",
        "Which weighs more, a pound of water, two pounds of bricks, a pound of feathers, or three pounds of air?",
    ]
    ground_truth = [
        # "12",
        "3",
        # "3",
        # "12.041594578792296",
        "100",
        "9.9",
        # "6",
        "80.0",
        # "483",
        "4",
        "air"
    ]

    responses_1st = []
    responses_2nd = []

    assert len( questions ) == len( ground_truth ), (
        f"Length mismatch: questions({len( questions )}), "
        f"ground_truth({len( ground_truth )}), "
    )
    outer_timer   = Stopwatch()
    debug   = False
    verbose = False

    for question in questions:

        du.print_banner( f"Question: {question}" )
        timer = Stopwatch()
        agent  = MathAgent( question=SolutionSnapshot.remove_non_alphanumerics( question ), last_question_asked=question, routing_command="agent router go to math", debug=False, verbose=False )
        answer = agent.do_all()
        responses_1st.append( answer )
        timer.print( f"Math agent answered: {answer}", use_millis=True )

        timer = Stopwatch()
        answer = "Unable to answer due to a rate(?) error"
        try:
            prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/agents/plain-vanilla-question.txt" )
            prompt = prompt_template.format( question=question )
            model = Llm_v0.GOOGLE_GEMINI_PRO
            llm = Llm_v0( model=model, debug=debug, verbose=verbose )
            results = llm.query_llm( prompt=prompt )
            answer = dux.get_value_by_xml_tag_name( results, "answer" ).strip()

        except Exception as e:

            if debug:
                du.print_stack_trace( e, explanation=model, caller="Plain vanilla llm prompt", prepend_nl=True )
        finally:
            responses_2nd.append( answer )

        timer.print( f"LLM answered: {answer}", use_millis=True )

        time.sleep( 10 )

    outer_timer.print( "All questions answered" )

    for i in range( len( questions ) ):
        du.print_banner( f"Question: {questions[i]}" )
        print( f"Ground truth: [{ground_truth[i]}]" )
        print( f"  Math agent: [{responses_1st[i]}]" )
        print( f"      Gemini: [{responses_2nd[i]}]" )
        print()
    