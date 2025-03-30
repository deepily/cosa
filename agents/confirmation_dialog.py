from cosa.agents.llm import Llm

import cosa.utils.util as du
import cosa.utils.util_xml as dux

class ConfirmationDialogue( Llm ):
    
    def __init__( self, model=Llm.GROQ_LLAMA3_70B, config_mgr=None, debug=False, verbose=False ):
        
        super().__init__( model=model, config_mgr=config_mgr, debug=debug, verbose=verbose )
        
        self.model  = model
        self.prompt = None
        
        self.prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/agents/confirmation-yes-no.txt" )
    
    def confirmed( self, utterance, default=False ):
        """
        Determines if the response is a confirmed 'yes' or 'no'.

        :param utterance: The utterance string to evaluate.
        :param default: The default boolean value to return in ambiguous cases.
        :return: True if the response is 'yes', False if 'no', and default for ambiguous cases.
        """
        self.prompt = self.prompt_template.format( utterance=utterance )
        
        results = self.query_llm( prompt=self.prompt )
        response = dux.get_value_by_xml_tag_name( results, "summary" ).strip().lower()
        
        if response == "yes":
            return True
        elif response == "no":
            return False
        else:
            return default
        
if __name__ == "__main__":
    
    confirmation_dialogue = ConfirmationDialogue( model=Llm.GROQ_LLAMA3_1_8B, debug=True, verbose=True )
    
    utterance = "I'm not sure if this is a good idea."
    action_confirmed = confirmation_dialogue.confirmed( utterance )
    print( f"Action confirmed: {action_confirmed}" )
    
    utterance = "You bet it is!"
    print( ConfirmationDialogue( model=Llm.GROQ_LLAMA3_1_70B, debug=True, verbose=True ).confirmed( utterance ) )
