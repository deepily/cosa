"""
two_word_id_generator.py

A Python module that provides functionality for generating unique, memorable two-word IDs.
The IDs consist of a combination of an adjective and a noun, ensuring that each combination is unique by tracking previously generated IDs.
This module employs the Singleton design pattern to ensure that only one instance of the ID generator exists throughout the runtime.

Classes:
    TwoWordIDGenerator: A class responsible for generating unique two-word combinations and ensuring no duplicates.

Decorators:
    singleton: A decorator that enforces the Singleton design pattern on a class, ensuring only one instance is created.

Usage Example:
    >>> generator = TwoWordIdGenerator()
    >>> unique_id = generator.get_id()
    >>> print(unique_id)
    'bright lion'

    # Ensure the Singleton pattern:
    >>> another_generator = TwoWordIdGenerator()
    >>> print(generator is another_generator)
    True

Attributes:
    adjectives (list): A list of adjectives to be used for generating combinations.
    nouns (list): A list of nouns to be used for generating combinations.
    generated_ids (set): A set storing all previously generated unique IDs to prevent duplicates.

Methods:
    generate_unique_id(): Generates a unique two-word ID by combining an adjective and a noun.

"""

import random
from functools import wraps

# Singleton decorator
def singleton( cls ):
    instances = { }
    
    @wraps( cls )
    def get_instance( *args, **kwargs ):
        if cls not in instances:
            instances[ cls ] = cls( *args, **kwargs )
        return instances[ cls ]
    
    return get_instance


# The TwoWordIDGenerator class with a singleton decorator
@singleton
class TwoWordIdGenerator:
    def __init__( self ):
        # List of adjectives and nouns
        self.adjectives = [
            'beautiful', 'quick', 'shiny', 'clever', 'silent', 'brave', 'lazy', 'strong',
            'fierce', 'gentle', 'happy', 'sad', 'wild', 'calm', 'bright', 'dark',
            'wise', 'foolish', 'fast', 'slow', 'bold', 'timid', 'eager', 'relaxed',
            'loyal', 'faithful', 'mighty', 'tiny', 'graceful', 'clumsy', 'proud', 'humble'
        ]
        self.nouns = [
            'giraffe', 'lion', 'falcon', 'tiger', 'elephant', 'panda', 'dolphin', 'rhino',
            'zebra', 'koala', 'owl', 'wolf', 'fox', 'bear', 'whale', 'eagle',
            'shark', 'penguin', 'cheetah', 'kangaroo', 'octopus', 'rabbit', 'squirrel', 'otter',
            'turtle', 'hawk', 'chimp', 'moose', 'bison', 'leopard', 'goat', 'sheep'
        ]
        
        # Dictionary to store generated unique combinations
        self.generated_ids = set()  # Using a set for faster lookup
    
    def get_id( self ):
        """Generate a unique two-word identifier
        
        This method randomly selects an adjective and a noun from the
        pre-defined lists and combines them to form a unique identifier.
        The generated identifier is stored in the `generated_ids` set
        to ensure that it is not generated again.
        """
        while True:
            # Generate a random adjective and noun combination
            adjective = random.choice( self.adjectives )
            noun = random.choice( self.nouns )
            combination = f"{adjective} {noun}"
            
            # Check if this combination has already been generated
            if combination not in self.generated_ids:
                # If unique, store it in the dictionary and return it
                self.generated_ids.add( combination )
                return combination

if __name__ == "__main__":
    
    # Example usage
    generator = TwoWordIdGenerator()
    unique_id = generator.get_id()
    print( f"Generated unique ID: {unique_id}" )
    
    # Creating another "instance" will return the same generator
    another_generator = TwoWordIdGenerator()
    print( f"Same instance? {generator is another_generator}" )
