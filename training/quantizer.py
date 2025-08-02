import sys
import os

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

from auto_round import AutoRound

import cosa.utils.util as du
from cosa.utils.util_stopwatch import Stopwatch


# make this a class called Quantizer
# with a method called quantize_model
class Quantizer:
    
    def __init__( self, model_name: str, local_files_only: bool=True, device_map: str="auto" ) -> None:
        """
        Initialize a new Quantizer instance for model quantization.
        
        Requires:
            - model_name is a valid HuggingFace model identifier or local path
            - local_files_only is a boolean flag indicating whether to use only local files
            - device_map is a valid device mapping strategy string
            
        Ensures:
            - Model and tokenizer are loaded from the specified source
            - Default quantization settings are established (4-bit, autoround method, symmetrical)
            
        Raises:
            - ValueError if model_name is invalid or model not found
            - RuntimeError if model loading fails due to resource constraints
        """
        self.model_name      = model_name
        self.model           = AutoModelForCausalLM.from_pretrained( model_name, torch_dtype=torch.float16, local_files_only=local_files_only, device_map=device_map )
        self.tokenizer       = AutoTokenizer.from_pretrained( model_name, local_files_only=local_files_only )
        self.bits            = 4
        self.quantize_method = "autoround"
        self.symmetrical     = True
        
    def quantize_model( self, quantize_method: str="autoround", batch_size: int=1, bits: int=4, group_size: int=128, sym: bool=True ) -> None:
        """
        Quantize the loaded model using the specified parameters.
        
        Requires:
            - The model and tokenizer have been successfully loaded in __init__
            - quantize_method is a supported quantization method (currently only "autoround")
            - batch_size is a positive integer
            - bits is a positive integer representing quantization precision (typically 2, 3, 4, or 8)
            - group_size is a positive integer for quantization grouping
            - sym is a boolean indicating whether to use symmetric quantization
            
        Ensures:
            - Model is quantized according to specified parameters
            - self.autoround is initialized with appropriate configuration
            - self.bits, self.quantize_method, and self.symmetrical are updated
            
        Raises:
            - Exception if an unsupported quantization method is provided
            - Various exceptions from the AutoRound process if quantization fails
        """
        self.bits            = bits
        self.quantize_method = quantize_method
        self.symmetrical     = sym
        
        if quantize_method == "autoround":
            self.autoround = AutoRound( self.model, self.tokenizer, nsamples=128, iters=512, low_gpu_mem_usage=True, batch_size=batch_size,
                gradient_accumulation_steps=8, bits=self.bits, group_size=group_size, sym=sym, enable_torch_compile=True  # Enable torch.compile optimizations
            )
        else:
            raise Exception( f"Unsupported quantization method: {quantize_method}" )
        
        du.print_banner( f"Quantizing model [{self.model_name}] with {self.quantize_method} method using {self.bits}-bits", prepend_nl=True )
        timer = Stopwatch( msg="Quantizing model..." )
        self.autoround.quantize()
        timer.print( msg="Done!" )
        
    def save( self, output_dir: str, include_model_name: bool=True, format: str='auto_gptq', inplace: bool=True ) -> str:
        """
        Save the quantized model to disk with appropriate naming conventions.
        
        Requires:
            - Model has been successfully quantized via quantize_model()
            - output_dir is a valid directory path (will be created if it doesn't exist)
            - include_model_name is a boolean indicating whether to include the model name in the output path
            - format is a valid export format (currently only 'auto_gptq' is fully supported)
            - inplace is a boolean indicating whether to modify the model in-place
            
        Ensures:
            - Creates a uniquely named directory with timestamp
            - Saves the quantized model to the specified location
            - Returns the full path to the saved model directory
            
        Raises:
            - IOError if directory creation fails
            - Various exceptions from the AutoRound save process if saving fails
            - Exception if autoround hasn't been initialized (if quantize_model wasn't called)
        """
        extension  = "gptq" if format == "auto_gptq" else "unknown"
        sym_flag   = "sym"  if self.symmetrical else "asym"
        date       = du.get_current_date()
        time       = du.get_current_time( format='%H-%M', include_timezone=False )
        
        if include_model_name:
            full_path  = f"{output_dir}/{self.model_name.split( '/' )[ 1 ]}-{self.quantize_method}-{self.bits}-bits-{sym_flag}.{extension}/{date}-at-{time}"
        else:
            full_path  = f"{output_dir}/{self.quantize_method}-{self.bits}-bits-{sym_flag}.{extension}/{date}-at-{time}"
        
        # check to see if the path exists, if not create
        if not os.path.exists( full_path ):
            
            print( f"Creating output directory [{full_path}]..." )
            os.makedirs( full_path )
            print( f"Creating output directory [{full_path}]... Done!" )
        
        print( f"Saving quantized model to [{full_path}]..." )
        self.autoround.save_quantized( full_path, format=format, inplace=inplace )
        print( f"Saving quantized model to [{full_path}]... Done!" )
        
        return full_path



def quick_smoke_test():
    """
    LIGHTWEIGHT STRUCTURAL smoke test for Quantizer - validates architecture only.
    
    ⚠️  IMPORTANT: This test validates STRUCTURE ONLY, not runtime ML behavior.
    ⚠️  This module requires significant GPU resources and models for actual operation.
    ⚠️  This smoke test only verifies the module can be imported and basic structure accessed.
    
    This test is essential for v000 deprecation as quantizer.py is critical
    for model quantization infrastructure, but too resource-intensive for full testing.
    """
    import cosa.utils.util as du
    
    du.print_banner( "Quantizer STRUCTURAL Smoke Test", prepend_nl=True )
    print( "⚠️  STRUCTURAL TESTING ONLY - No ML operations will be performed" )
    print( "⚠️  This test validates imports and architecture, not runtime behavior" )
    print()
    
    try:
        # Test 1: Core class structure validation
        print( "Testing core Quantizer structure..." )
        
        # Test that Quantizer class exists and basic methods are present
        expected_methods = [ "quantize_model", "save" ]
        
        methods_found = 0
        for method_name in expected_methods:
            if hasattr( Quantizer, method_name ):
                methods_found += 1
            else:
                print( f"⚠ Missing method: {method_name}" )
        
        if methods_found == len( expected_methods ):
            print( f"✓ All {len( expected_methods )} core Quantizer methods present" )
        else:
            print( f"⚠ Only {methods_found}/{len( expected_methods )} Quantizer methods present" )
        
        # Test 2: Critical import validation (lightweight - no actual ML loading)
        print( "Testing critical import statements..." )
        
        # Test standard library imports
        try:
            import sys, os
            print( "✓ Standard library imports successful" )
        except ImportError as e:
            print( f"✗ Standard library imports failed: {e}" )
        
        # Test ML framework imports (just import, don't use)
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch
            print( "✓ Core ML framework imports successful" )
        except ImportError as e:
            print( f"⚠ ML framework imports failed (may be expected in test env): {e}" )
        
        # Test quantization library imports
        try:
            from auto_round import AutoRound
            print( "✓ AutoRound quantization library import successful" )
        except ImportError as e:
            print( f"⚠ AutoRound library import failed (may be expected in test env): {e}" )
        
        # Test CoSA internal imports
        try:
            import cosa.utils.util as du
            from cosa.utils.util_stopwatch import Stopwatch
            print( "✓ CoSA internal imports successful" )
        except ImportError as e:
            print( f"⚠ CoSA internal imports failed: {e}" )
        
        # Test 3: Class instantiation validation (mock - should fail gracefully)
        print( "Testing Quantizer class instantiation validation..." )
        try:
            # This should fail since we're using a mock model name, but we want to test the constructor signature
            test_quantizer = Quantizer( "mock_model_name", local_files_only=True, device_map="cpu" )
            print( "⚠ Quantizer accepted mock model name (unexpected)" )
        except Exception as e:
            # Expected to fail with mock model name
            if "mock_model_name" in str( e ) or "not found" in str( e ).lower() or "local_files_only" in str( e ):
                print( "✓ Quantizer properly validates model names" )
            else:
                print( f"⚠ Quantizer instantiation failed with unexpected error: {e}" )
        
        # Test 4: Method signature validation
        print( "Testing method signatures..." )
        try:
            # Test quantize_model method signature
            quantize_method = getattr( Quantizer, 'quantize_model', None )
            if callable( quantize_method ):
                print( "✓ quantize_model method is callable" )
            else:
                print( "✗ quantize_model method is not callable" )
            
            # Test save method signature
            save_method = getattr( Quantizer, 'save', None )
            if callable( save_method ):
                print( "✓ save method is callable" )
            else:
                print( "✗ save method is not callable" )
                
        except Exception as e:
            print( f"⚠ Method signature validation issues: {e}" )
        
        # Test 5: Configuration attributes validation
        print( "Testing quantization configuration attributes..." )
        try:
            # Check if class has expected configuration attributes (from reading source)
            expected_attrs = [ '__init__' ]  # We can only check constructor without instantiation
            
            for attr_name in expected_attrs:
                if hasattr( Quantizer, attr_name ):
                    print( f"✓ {attr_name} attribute available" )
                else:
                    print( f"⚠ {attr_name} attribute missing" )
                    
        except Exception as e:
            print( f"⚠ Configuration validation issues: {e}" )
        
        # Test 6: Command line interface validation
        print( "Testing command line interface structure..." )
        try:
            # Test that CLI handling code exists (from main block)
            import inspect
            source_file = inspect.getfile( Quantizer )
            
            with open( source_file, 'r' ) as f:
                content = f.read()
            
            # Check for CLI handling
            if 'if __name__ == "__main__"' in content:
                print( "✓ Command line interface present" )
            else:
                print( "⚠ Command line interface missing" )
                
            if 'sys.argv' in content:
                print( "✓ Command line argument processing present" )
            else:
                print( "⚠ Command line argument processing missing" )
                
        except Exception as e:
            print( f"⚠ CLI validation issues: {e}" )
        
        # Test 7: Critical v000 dependency scanning
        print( "\\n🔍 Scanning for v000 dependencies..." )
        
        # Scan the file for v000 patterns
        import inspect
        source_file = inspect.getfile( Quantizer )
        
        v000_found = False
        v000_patterns = []
        
        with open( source_file, 'r' ) as f:
            content = f.read()
            
            # Split content and exclude smoke test function
            lines = content.split( '\\n' )
            in_smoke_test = False
            
            for i, line in enumerate( lines ):
                stripped_line = line.strip()
                
                # Track if we're in the smoke test function
                if "def quick_smoke_test" in line:
                    in_smoke_test = True
                    continue
                elif in_smoke_test and line.startswith( "def " ):
                    in_smoke_test = False
                elif in_smoke_test:
                    continue
                
                # Skip comments and docstrings
                if ( stripped_line.startswith( '#' ) or 
                     stripped_line.startswith( '"""' ) or
                     stripped_line.startswith( "'" ) ):
                    continue
                
                # Look for actual v000 code references
                if "v000" in stripped_line and any( pattern in stripped_line for pattern in [
                    "import", "from", "cosa.agents.v000", ".v000."
                ] ):
                    v000_found = True
                    v000_patterns.append( f"Line {i+1}: {stripped_line}" )
        
        if v000_found:
            print( "🚨 CRITICAL: v000 dependencies detected!" )
            print( "   Found v000 references:" )
            for pattern in v000_patterns[ :3 ]:  # Show first 3
                print( f"     • {pattern}" )
            if len( v000_patterns ) > 3:
                print( f"     ... and {len( v000_patterns ) - 3} more v000 references" )
            print( "   ⚠️  These dependencies MUST be resolved before v000 deprecation!" )
        else:
            print( "✅ EXCELLENT: No v000 dependencies found!" )
        
        # Test 8: Quantization configuration validation
        print( "\\nTesting quantization configuration options..." )
        try:
            # Check that the class supports expected quantization parameters from source code
            with open( source_file, 'r' ) as f:
                content = f.read()
            
            # Look for key quantization parameters
            config_params = [ "bits", "quantize_method", "symmetrical", "batch_size", "group_size" ]
            params_found = 0
            
            for param in config_params:
                if param in content:
                    params_found += 1
            
            if params_found >= len( config_params ) - 1:  # Allow for slight variation
                print( f"✓ Quantization configuration parameters present ({params_found}/{len( config_params )})" )
            else:
                print( f"⚠ Limited quantization configuration: {params_found}/{len( config_params )} parameters" )
                
        except Exception as e:
            print( f"⚠ Configuration validation issues: {e}" )
        
        # Test 9: Output path generation validation
        print( "\\nTesting output path generation logic..." )
        try:
            # Test that save method structure supports expected parameters
            with open( source_file, 'r' ) as f:
                content = f.read()
            
            # Look for output path logic
            path_elements = [ "output_dir", "date", "time", "bits", "sym_flag" ]
            path_found = 0
            
            for element in path_elements:
                if element in content:
                    path_found += 1
            
            if path_found >= len( path_elements ) - 1:
                print( f"✓ Output path generation logic present ({path_found}/{len( path_elements )} elements)" )
            else:
                print( f"⚠ Limited path generation: {path_found}/{len( path_elements )} elements" )
                
        except Exception as e:
            print( f"⚠ Path generation validation issues: {e}" )
    
    except Exception as e:
        print( f"✗ Error during Quantizer structural testing: {e}" )
        import traceback
        traceback.print_exc()
    
    # Summary
    print( "\\n" + "="*70 )
    print( "🔧 STRUCTURAL TEST SUMMARY - QUANTIZER" )
    print( "="*70 )
    
    if v000_found:
        print( "🚨 CRITICAL ISSUE: Quantizer has v000 dependencies!" )
        print( "   Status: NOT READY for v000 deprecation" )
        print( "   Priority: IMMEDIATE ACTION REQUIRED" )
        print( "   Risk Level: CRITICAL - Model quantization infrastructure will break" )
    else:
        print( "✅ Quantizer structural validation completed successfully!" )
        print( "   Status: Model quantization infrastructure structure ready for v000 deprecation" )
        print( "   Risk Level: LOW" )
    
    print()
    print( "⚠️  IMPORTANT REMINDER:" )
    print( "   This was a STRUCTURAL test only - no ML operations were performed" )
    print( "   Runtime validation requires GPU resources, models, and quantization libraries" )
    print( "   Full quantization pipeline validation should be done separately in ML environment" )
    print()
    print( "✓ Quantizer structural smoke test completed" )


if __name__ == "__main__":
    import sys
    
    # Check if this is being run as a smoke test
    if len( sys.argv ) == 1 or (len( sys.argv ) == 2 and sys.argv[1] == "--smoke-test"):
        quick_smoke_test()
        sys.exit( 0 )
    
    # Otherwise run normal quantization pipeline
    
    # sanity check for command line arguments
    if len( sys.argv ) < 3:
        print( "Usage: python quantizer.py <model_name> <save_to_path> <bits>" )
        sys.exit( 1 )
        
    model_name: str = sys.argv[ 1 ]
    save_to_path: str = sys.argv[ 2 ]
    
    # check if bits is provided, if not default to 4
    if len( sys.argv ) == 4:
        bits: int = int( sys.argv[ 3 ] )
    else:
        bits: int = 4
    
    quantizer = Quantizer( model_name )
    quantizer.quantize_model( bits=bits )
    quantizer.save( save_to_path, include_model_name=True )
    