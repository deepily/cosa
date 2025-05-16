import cosa.utils.util as du
import cosa.utils.util_xml as dux

from cosa.agents.v010.llm_client_factory import LlmClientFactory
from cosa.agents.v010.llm_client import LlmClient
from cosa.app.configuration_manager import ConfigurationManager

class ConfirmationDialogue:
    """
    A utility class for confirming yes/no responses using LLMs.
    
    This class does not inherit from AgentBase as it's designed to be
    a lightweight utility for confirmation dialogs rather than a full agent.
    
    Configuration:
        - "prompt_template_for_confirmation_dialog": Path to the prompt template file (required)
        - "llm_spec_key_for_confirmation_dialog": LLM model specification (required when model_name not provided)
    """
    
    def __init__( self, model_name=None, config_mgr=None, debug=False, verbose=False ):
        
        self.config_mgr = config_mgr or ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
        
        # Use provided model_name, or get from config
        if model_name is None:
            model_name = self.config_mgr.get( 
                "llm_spec_key_for_confirmation_dialog"
            )
        
        self.model_name = model_name
        self.debug = debug
        self.verbose = verbose
        self.prompt = None
        
        # Get prompt template path from config
        prompt_template_path = self.config_mgr.get( 
            "prompt_template_for_confirmation_dialog"
        )
        self.prompt_template = du.get_file_as_string( du.get_project_root() + prompt_template_path )
    
    def confirmed( self, utterance, default=None ):
        """
        Determines if the response is a confirmed 'yes' or 'no'.

        :param utterance: The utterance string to evaluate.
        :param default: The optional default boolean value to return in ambiguous cases.
                       If not provided and the response is ambiguous, a ValueError is raised.
        :return: True if the response is 'yes', False if 'no', and default if provided 
                 for ambiguous cases. Raises ValueError if response is ambiguous and no 
                 default is provided.
        :raises ValueError: If the response is ambiguous and no default value is provided.
        """
        self.prompt = self.prompt_template.format( utterance=utterance )
        
        # Use v010 LLM client factory pattern
        factory = LlmClientFactory()
        llm = factory.get_client( self.model_name, debug=self.debug, verbose=self.verbose )
        results = llm.run( self.prompt )
        
        response = dux.get_value_by_xml_tag_name( results, "summary" ).strip().lower()
        
        if response == "yes":
            return True
        elif response == "no":
            return False
        elif default is not None:
            return default
        else:
            raise ValueError( f"Ambiguous response '{response}' has no default value provided. Ask the user for clarification." )
        
if __name__ == "__main__":
    
    # Test various utterances with the confirmation dialogue
    test_utterances = [
        ("Yes, please proceed.", True),
        ("No, I don't think so.", False),
        ("I'm not sure if this is a good idea.", None),  # Ambiguous
        ("Absolutely!", True),
        ("Not a chance!", False),
        ("You bet it is!", True),
        ("Maybe... I don't know.", None),  # Ambiguous
        ("Definitely not.", False),
        ("Sure thing!", True)
    ]
    
    print("=== Testing ConfirmationDialogue ===")
    
    # Create a single instance for testing
    confirmation_dialogue = ConfirmationDialogue(
        model_name=LlmClient.GROQ_LLAMA_3_1_8B,  # Using LlmClient constant
        debug=True,
        verbose=True
    )
    
    for utterance, expected in test_utterances:
        print(f"\nUtterance: '{utterance}'")
        action_confirmed = confirmation_dialogue.confirmed(utterance, default=None)
        
        # For ambiguous cases, we expect default (None)
        if expected is None:
            expected_text = "Ambiguous (default)"
        else:
            expected_text = "Yes" if expected else "No"
            
        result_text = "Yes" if action_confirmed else ("No" if action_confirmed is False else "Ambiguous")
        
        print(f"Expected: {expected_text}")
        print(f"Got: {result_text}")
        print(f"Match: {'✅' if action_confirmed == expected else '❌'}")
        print("-" * 30)
