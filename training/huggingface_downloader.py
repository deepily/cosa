import sys
import os

from huggingface_hub import snapshot_download, login

if __name__ == "__main__":

    # get the first argument passed in
    if len( sys.argv ) < 2:
        print( "Usage: python huggingface_downloader.py <repo_id>" )
        sys.exit( 1 )
    # sanity check for huggingface home
    if not os.getenv( "HF_HOME" ):
        print( "Please set the HF_HOME environment variable to the directory where you want to download models" )
        sys.exit( 1 )
        
    # Authenticate with Hugging Face
    hf_token = os.getenv( "HF_TOKEN" )
    if not hf_token:
        print( "Please set the HF_TOKEN environment variable with your Hugging Face API token" )
        sys.exit( 1 )
    
    repo_id = sys.argv[ 1 ]
    
    # Download the model
    try:
        # Log in using the token
        login( token=hf_token )
        snapshot_download( repo_id=repo_id )
    except Exception as e:
        print( f"Error downloading model: {e}" )
        sys.exit( 1 )