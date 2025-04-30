import requests
import json

import openai

from huggingface_hub            import InferenceClient
from groq                       import Groq
import google.generativeai      as genai
from langchain.chains.qa_with_sources.stuff_prompt import template
from openai import OpenAI

from cosa.app.configuration_manager import ConfigurationManager
from cosa.utils.util                import print_banner
from cosa.utils.util_stopwatch      import Stopwatch
from cosa.agents.llm_completion     import get_completion

import cosa.utils.util              as du


class Llm:
    
    GPT_4             = "OpenAI/gpt-4-turbo-2024-04-09"
    GPT_3_5           = "OpenAI/gpt-3.5-turbo-0125"
    # PHIND_34B_v2      = "TGI/Phind-CodeLlama-34B-v2"
    QWEN_2_5_32B      = "Deepily/kaitchup/Qwen2.5-Coder-32B-Instruct-AutoRound-GPTQ-4bit"
    PHI_4_14B         = "Deepily/kaitchup/Phi-4-AutoRound-GPTQ-4bit"
    GROQ_MIXTRAL_8X78 = "Groq/mixtral-8x7b-32768"
    GROQ_LLAMA2_70B   = "Groq/llama2-70b-4096"
    GROQ_LLAMA3_70B   = "Groq/llama3-70b-8192"
    GROQ_LLAMA3_1_70B = "Groq/llama-3.1-70b-versatile"
    GROQ_LLAMA3_1_8B  = "Groq/llama-3.1-8b-instant"
    GOOGLE_GEMINI_PRO = "Google/gemini-1.5-pro-latest"
    
    DEEPILY_PREFIX    = "Deepily"
    # DEEPILY_MINISTRAL_8B_2410 = "Deepily//mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-02-12-at-02-05/autoround-4-bits-sym.gptq/2025-02-12-at-02-27"
    DEEPILY_MINISTRAL_8B_2410 = "Deepily//mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-02-12-at-02-05/autoround-4-bits-sym.gptq/2025-02-12-at-02-27"
    
    DEFAULT_LOCAL_COMPLETIONS_URL  = "http://192.168.1.21:3000/v1/completions"
    # TODO: these static dictionaries would be populated dynamically at runtime using the configuration manager
    local_completions_dict = {
        DEEPILY_MINISTRAL_8B_2410: "http://192.168.1.21:3000/v1/completions",
                        PHI_4_14B: "http://192.168.1.21:3001/v1/completions"
    }
    local_chat_dict = {
        # PHI_4_14B: "http://192.168.1.21:3001/v1/chat/completions"
    }
    
    @staticmethod
    def extract_model_name( compound_name ):
        
        # Model names are stored in the format "Groq/{model_name} in the config_mgr file
        if "/" in compound_name:
            return compound_name[ compound_name.index( "/" ) + 1: ]
            # return compound_name.split( "/" )[ 1 ]
        else:
            du.print_banner( f"WARNING: Model name [{compound_name}] doesn't isn't in 'Make/model' format! Returning entire string as is" )
            return compound_name
    
    @staticmethod
    def get_model( mnt_point, prefix=DEEPILY_PREFIX ):
        
        model = f"{prefix}/{mnt_point}"
        if "//" not in model:
            raise ValueError( f"ERROR: Model [{model}] not in 'prefix//mnt/point' format!" )
        return model

    def __init__( self, model=PHI_4_14B, config_mgr=None, default_url=None, is_completion=False, debug=False, verbose=False ):
        
        # deprecation check for default URL
        if default_url is not None:
            msg = "DEPRECATED: 'default_url' will be removed in future versions!"
            du.print_banner( msg=msg, expletive=True )
            raise ValueError( msg )
            
        self.timer          = None
        self.debug          = debug
        self.verbose        = verbose
        self.model          = model
        self.config_mgr     = config_mgr
        self.is_completion  = is_completion
        
        self.local_inference_url = self._get_local_inference_url()
        # self.local_inference_url = du.get_local_inference_url_for_this_context( default_url=default_url )
    
    def _get_local_inference_url( self ):
        
        # if self.debug: print( f"Using model {self.model} to select local inference URL" )
        
        if self.model in Llm.local_completions_dict:
            return Llm.local_completions_dict[ self.model ]
        elif self.model in Llm.local_chat_dict:
            return Llm.local_chat_dict[ self.model ]
        else:
            if self.debug: print( f"Using default local inference URL [{Llm.DEFAULT_LOCAL_COMPLETIONS_URL}]" )
            return Llm.DEFAULT_LOCAL_COMPLETIONS_URL
        
    def _start_timer( self, msg="Asking LLM [{model}]..." ):
        
        msg        = msg.format( model=self.model )
        self.timer = Stopwatch( msg=msg )
        
    def _stop_timer( self, msg="Done!", chunks=[ ] ):
        
        print()
        self.timer.print( msg=msg, use_millis=True, end="\n" )
        
        if chunks:
            chunks_per_second = len( chunks ) / ( self.timer.get_delta_ms() / 1000.0 )
            print( f"Chunks per second [{round( chunks_per_second, 1 )}]" )
        
    def _do_conditional_print( self, chunk, ellipsis_count=0, debug=False ):
        
        if debug:
            print( chunk, end="" )
        else:
            print( ".", end="" )
            ellipsis_count += 1
            if ellipsis_count == 120:
                ellipsis_count = 0
                print()
                
        return ellipsis_count
    
    def query_llm( self, model=None, prompt_yaml=None, prompt=None, preamble=None, question=None, max_new_tokens=1024, temperature=0.5, top_k=100, top_p=0.25, stop_sequences=None, debug=None, verbose=None ):
        
        if debug   is None: debug   = self.debug
        if verbose is None: verbose = self.verbose
        # print( f"Model: [{model}]")
        # print( f"self.model: [{self.model}]")
        
        try:
            if self.debug: print( "Skipping sanity check for prompt and preamble..." )
            
            # Allow us to override the prompt, preamble, and question set when instantiated
            if model is not None: self.model = model
            
            elif self.model == Llm.GOOGLE_GEMINI_PRO:
                
                # Quick sanity check
                if prompt is None: raise ValueError( "ERROR: Prompt is `None`!" )
                return self._query_llm_google(
                    prompt, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=stop_sequences, debug=debug, verbose=verbose
                )
            
            elif self.model.startswith( Llm.DEEPILY_PREFIX ):
                
                if not self.is_completion:
                    return self._query_vllm_openai_chat( prompt, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=stop_sequences, debug=debug, verbose=verbose )
                else:
                    return self._query_vllm_KLUDGE_completion( prompt, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=stop_sequences, debug=debug, verbose=verbose )
            else:
                # Test for divisibility if receiving an "all in one" non chatbot type prompt
                if prompt is not None:
                    
                    input_present        = "### Input:" in prompt
                    user_message_present = "### User Message" in prompt
                    
                    if not input_present and not user_message_present:
                        msg = "ERROR: Prompt isn't divisible, '### Input:' and '### User Message:' not found in prompt!"
                        print( msg )
                        print( f"Prompt: [{prompt}]" )
                        raise ValueError( msg )
                    
                    if input_present:
                        preamble = prompt.split( "### Input:" )[ 0 ]
                        question = prompt.split( "### Input:" )[ 1 ]
                    
                    if user_message_present:
                        preamble = prompt.split( "### User Message" )[ 0 ]
                        question = prompt.split( "### User Message" )[ 1 ]
                        
                    # Strip out prompt markers
                    preamble = preamble.replace( "### System Prompt", "" )
                    preamble = preamble.replace( "### Input:", "" )
                    preamble = preamble.replace( "### Instruction:", "" )
                    preamble = preamble.replace( "### Task:", "" )
                    preamble = preamble.replace( "Use the Task and Input given below to write a Response that can solve the following Task.", "" )
    
                    question = question.replace( "### Input:", "" )
                    question = question.replace( "### User Message", "" )
                    question = question.replace( "### Assistant", "" )
                    question = question.replace( "### Response:", "" )
                    
                    # Strip out leading and trailing white space
                    preamble = preamble.strip()
                    question = question.strip()
                    
                    if debug and verbose:
                        du.print_banner( "Preamble:")
                        print( preamble )
                        du.print_banner( "Question:")
                        print( question )
                    
                elif preamble is None or question is None:
                    raise ValueError( "ERROR: Preamble or question is `None`!" )
                
                # if self.model == Llm.QWEN_2_5_32B:
                if self.model.startswith( "kaitchup/" ):
                    return self._query_my_local_vllm( preamble, question, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=stop_sequences, debug=debug, verbose=verbose )
                # elif self.model.startswith( "Deepily/" ):
                #     return self._query_vllm_openai_chat( preamble, question, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=stop_sequences, debug=debug, verbose=verbose )
                elif self.model.startswith( "OpenAI/" ):
                    return self._query_llm_openai( preamble, question, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=stop_sequences, debug=debug, verbose=verbose )
                elif self.model.startswith( "Groq/" ):
                    return self._query_llm_groq( preamble, question, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=stop_sequences, debug=debug, verbose=verbose )
                elif self.model.startswith( "Google/" ):
                    return self._query_llm_google( preamble, question, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p, stop_sequences=stop_sequences, debug=debug, verbose=verbose )
                else:
                    raise ValueError( f"ERROR: Model [{self.model}] not recognized!" )
                
        except ConnectionError as ce:
            
            du.print_stack_trace( ce, explanation="ConnectionError: Server isn't responding", caller="Llm.query_llm()" )
            return "I'm sorry Dave, the LLM server isn't responding. Please check system logs."
    
    def _query_llm_google( self, prompt, max_new_tokens=1024, temperature=0.25, top_k=10, top_p=0.25, stop_sequences=[ "</response>" ], stream=True, debug=None, verbose=None ):
        
        if debug   is None: debug   = self.debug
        if verbose is None: verbose = self.verbose
        
        if debug and verbose: print( prompt )
        
        self._start_timer()
        genai.configure( api_key=du.get_api_key( "google" ) )
        
        generation_config = {
                  "temperature": temperature,
                        "top_p": top_p,
                        "top_k": top_k,
            "max_output_tokens": max_new_tokens,
               "stop_sequences": stop_sequences
        }
        model    = genai.GenerativeModel( "models/" + Llm.extract_model_name( self.model ) )
        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=None,
            stream=stream
        )
        
        chunks = [ ]
        ellipsis_count = 0
        
        # Chunks are not the same as tokens, specifically for Google models
        for chunk in response:
            chunks.append( chunk.text )
            ellipsis_count = self._do_conditional_print( chunk.text, ellipsis_count, debug=debug )

        self._stop_timer( chunks=chunks )
        
        # According to the documentation, stop sequences will not be returned with the chunks, So append the most likely: response
        return "".join( chunks ).strip() + "</response>"
    
    def _query_llm_groq( self, preamble, query, prompt_yaml=None, max_new_tokens=1024, temperature=0.25, stop_sequences=[ "</response>" ], top_k=10, top_p=0.9, debug=False, verbose=False ):
        
        client = Groq( api_key=du.get_api_key( "groq" ) )
        stream = client.chat.completions.create(
            messages=[
                { "role"   : "system", "content": preamble },
                { "role"   : "user", "content": query }
            ],
            # Model names are stored in the format "Groq/{model_name} in the config_mgr file
            model=Llm.extract_model_name( self.model ),
            temperature=temperature,
            max_tokens=max_new_tokens,
            top_p=top_p,
            # Not used by groq: https://console.groq.com/docs/text-chat
            # top_k=top_k,
            stop=stop_sequences,
            stream=True,
        )
        self._start_timer()
        chunks = [ ]
        ellipsis_count = 0
        for chunk in stream:
            
            chunks.append( str( chunk.choices[ 0 ].delta.content ) )
            ellipsis_count = self._do_conditional_print( chunk.choices[ 0 ].delta.content, ellipsis_count, debug=debug )
            
        self._stop_timer( chunks=chunks )
        
        return "".join( chunks ).strip()
    
    def _query_vllm_KLUDGE_completion(
            # self, preamble, query, max_new_tokens=1024, temperature=0.25, top_k=10, top_p=0.25, stop_sequences=[ "</response>" ],
            self, prompt, max_new_tokens=1024, temperature=0.25, top_k=10, top_p=0.25, stop_sequences=[ "</response>" ],
            debug=False, verbose=False
    ):
        print( f"COMPLETION self._query_vllm_KLUDGE_completion(...) called" )
        print( f"URL: [{self.local_inference_url}]" )
        return get_completion( prompt, url=self.local_inference_url, model=self.extract_model_name( self.model ) )
        
    def _query_vllm_openai_chat(
        self, prompt, max_new_tokens=1024, temperature=0.25, top_k=10, top_p=0.25, stop_sequences=[ "</response>" ],
        debug=False, verbose=False
    ):
        if self.debug or debug: print( f"CHAT self._query_vllm_openai_chat(...) called" )
        # Set the headers
        headers = {
            "Content-Type" : "application/json",
            # "Authorization": f"Bearer {'your-api-key' if required else 'EMPTY'}"
        }
        
        # Define the payload
        payload = {
            "model"      : self.extract_model_name( self.model ),
            "prompt"     : prompt,
            "max_tokens" : max_new_tokens,
            "temperature": temperature,
            "top_p"      : top_p,
            "top_k"      : top_k,
            # "stop"       : stop_sequences
        }
        # Send the request
        self._start_timer()
        response = requests.post( self.local_inference_url, headers=headers, data=json.dumps( payload ) )
        self._stop_timer()
        
        # check for 200 return code
        if response.status_code != 200:
            
            du.print_banner( f"ERROR: HTTP status code [{response.status_code}] for payload:" )
            print( json.dumps( payload, indent=4 ) )
            du.print_banner( "Response:" )
            print( json.dumps( response.json(), indent=4 ) )
            
            raise ValueError( f"ERROR: HTTP status code [{response.status_code}]" )
        
        # Parse the response
        completion = response.json()
        
        return completion[ 'choices' ][ 0 ][ 'text' ].strip()
    
    def _query_llm_openai( self, preamble, query, max_new_tokens=1024, temperature=0.25, top_k=10, top_p=0.25, stop_sequences=[ "</response>" ], debug=False, verbose=False ):
        
        openai.api_key = du.get_api_key( "openai" )
        
        self._start_timer()
        
        stream = openai.chat.completions.create(
            # Model names are stored in the format "OpenAI/{model_name} in the config_mgr file
            model=Llm.extract_model_name( self.model ),
            messages=[
                { "role": "system", "content": preamble },
                { "role": "user", "content": query }
            ],
            max_tokens=max_new_tokens,
            # It's recommended to use top P or temperature but not both... TODO: decide which one to use
            # https://platform.openai.com/docs/api-reference/chat/create
            temperature=temperature,
            top_p=top_p,
            # Not used by open AI?
            # top_k=top_k,
            # Zero is the default value for frequency and presence penalties
            frequency_penalty=0.0,
            presence_penalty=0.0,
            stop=stop_sequences,
            stream=True
        )
        chunks         = [ ]
        ellipsis_count = 0
        for chunk in stream:
            if chunk.choices[ 0 ].delta.content is not None:
                chunks.append( chunk.choices[ 0 ].delta.content )
                ellipsis_count = self._do_conditional_print( chunk.choices[ 0 ].delta.content, ellipsis_count, debug=debug )
                
        self._stop_timer( chunks=chunks )
        response = "".join( chunks ).strip()
        
        return response
    
    def _query_my_local_vllm(
        self, preamble, question, max_new_tokens=1024, temperature=0.5, top_k=10, top_p=0.25,
        stop_sequences=[ "</response>", "></s>" ], debug=False, verbose=False
    ):
        if debug:
            print( f"preamble: [{preamble}]" )
            print( f"question: [{question}]" )
        
        # Set OpenAI's API key and API base to use vLLM's API server.
        openai_api_key = "EMPTY"
        openai_api_base = self.local_inference_url
        if debug and verbose: print( f"Calling: [{openai_api_base}]" )
        
        client = OpenAI(
            api_key=openai_api_key,
            base_url=openai_api_base,
        )
        self._start_timer()
        
        # Munge the model name
        # vLLM Model names are stored in adhoc formats, unlike the super predictable "OpenAI/{model_name} in the config_mgr file
        if self.model.startswith( "kaitchup" ):
            vllm_model_name = self.model
        elif self.model.startswith( "ModelPath" ):
            vllm_model_name = self.model[ 9: ]
        else:
            raise ValueError( f"ERROR: Model [{self.model}] not recognized!" )
            
        stream = client.chat.completions.create(
            model=vllm_model_name,
            messages=[
                { "role": "system", "content": preamble },
                { "role": "user", "content": question },
            ],
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_new_tokens,
            extra_body={
                "repetition_penalty": 1.05,
            },
            stream=True
        )
        chunks = [ ]
        ellipsis_count = 0
        for chunk in stream:
            if chunk.choices[ 0 ].delta.content is not None:
                chunks.append( chunk.choices[ 0 ].delta.content )
                ellipsis_count = self._do_conditional_print( chunk.choices[ 0 ].delta.content, ellipsis_count, debug=debug )
        self._stop_timer( chunks=chunks )
        
        return "".join( chunks ).strip()
    
if __name__ == "__main__":
    
    config_mgr = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
    
    # prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/agents/gist.txt" )
    # prompt = prompt_template.format( question='How many "R"s are in the word "strawberry"?' )
    
    # prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/agents/confirmation-yes-no.txt" )
    # prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/vox-command-template.txt" )
    # template_path = du.get_project_root() + config_mgr.get( "vox_command_prompt_path_wo_root" )
    template_path = du.get_project_root() + "/src/conf/prompts/agent-router-template-completion.txt"
    
    # prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/vox-command-template-completion-mistral-8b.txt" )
    prompt_template = du.get_file_as_string( template_path )
    
    # utterance = "Yes, I think I can do that."
    # utterance = "Umm, yeah, maybe not today, okay?"
    # utterance = "No, I don't think that's going to work."
    # utterance = "Sure, why not?"
    # prompt = prompt_template.format( utterance=utterance )
    # voice_command = "I want you to open a new tab and do a Google scholar search on agentic behaviors"
    voice_command = "can I please talk to a human?"
    prompt = prompt_template.format( voice_command=voice_command )
    # print( prompt )
    # model         = config_mgr.get( "router_and_vox_command_model" )
    
    # url           = config_mgr.get( "router_and_vox_command_url" )
    is_completion = config_mgr.get( "router_and_vox_command_is_completion", return_type="boolean", default=False )
    debug         = config_mgr.get( "app_debug",   return_type="boolean", default=False )
    verbose       = config_mgr.get( "app_verbose", return_type="boolean", default=False )
    model         = Llm.get_model( "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-04-08-at-21-26/autoround-4-bits-sym.gptq/2025-04-08-at-21-47" )
    llm = Llm( model=model, is_completion=is_completion, debug=debug, verbose=verbose )
    #
    results = llm.query_llm( prompt=prompt )
    print( results )
    # gist = dux.get_value_by_xml_tag_name( results, "summary" ).strip()
    # print( gist )
    
    