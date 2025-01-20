import sys
import os

from huggingface_hub import snapshot_download, login

# make this a class called HuggingFaceDownloader
# with a method called download_model
# that takes a repo_id as an argument
class HuggingFaceDownloader:

    def __init__( self, token=None ):
        self.token = token

    def download_model( self, repo_id ):
        
        try:
            login( token=self.token )
            snapshot_download( repo_id=repo_id )
        except Exception as e:
            print( f"Error downloading model: {e}" )
            sys.exit( 1 )

if __name__ == "__main__":

    # sanity check for command line arguments
    if len( sys.argv ) != 2:
        print( "Usage: python hf_downloader.py <repo_id>" )
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
    downloader = HuggingFaceDownloader( token=hf_token )
    downloader.download_model( repo_id )
    
    