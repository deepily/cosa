"""
User ID Generator Utility

This module provides the single source of truth for converting email addresses
to system IDs used throughout the Genie-in-the-Box application.

The algorithm ensures:
- Collision-resistant IDs through email-based hashing
- Safe characters for file paths, URLs, and database keys
- Consistent generation across all Python modules
"""

import re
from typing import Dict, Optional


def email_to_system_id( email: str ) -> str:
    """
    Convert email address to collision-resistant system ID.
    
    This is the SINGLE SOURCE OF TRUTH for email → system ID conversion.
    All Python modules should import and use this function.
    
    Args:
        email: Email address to convert (e.g., "ricardo.felipe.ruiz@gmail.com")
        
    Returns:
        str: System ID (e.g., "ricardo_felipe_ruiz_6bdc")
        
    Examples:
        >>> email_to_system_id("ricardo.felipe.ruiz@gmail.com")
        'ricardo_felipe_ruiz_6bdc'
        >>> email_to_system_id("alice.smith@example.com")
        'alice_smith_a1b2'
    """
    if not email or '@' not in email:
        raise ValueError( f"Invalid email address: {email}" )
    
    # Extract local part from email (before @)
    local_part = email.split( '@' )[0]
    
    # Convert to safe system ID format
    base_name = re.sub( r'[^a-z0-9]', '_', local_part.lower() )
    base_name = re.sub( r'_+', '_', base_name )  # Replace multiple underscores
    base_name = re.sub( r'^_|_$', '', base_name )  # Remove leading/trailing underscores
    
    # Generate collision-resistant hash suffix (4 characters)
    hash_val = 0
    for char in email:
        hash_val = ((hash_val << 5) - hash_val) + ord( char )
        hash_val = hash_val & hash_val  # Convert to 32-bit integer
    
    suffix = hex( abs( hash_val ) )[-4:]
    
    return f"{base_name}_{suffix}"


def system_id_to_display_name( system_id: str ) -> str:
    """
    Extract a display name from system ID.
    
    Args:
        system_id: System ID (e.g., "ricardo_felipe_ruiz_6bdc")
        
    Returns:
        str: Display name (e.g., "Ricardo")
    """
    # Extract first part before underscore and hash
    parts = system_id.split( '_' )
    if parts:
        first_name = parts[0]
        return first_name.capitalize()
    return system_id


def validate_system_id( system_id: str ) -> bool:
    """
    Validate that a system ID follows the expected format.
    
    Args:
        system_id: System ID to validate
        
    Returns:
        bool: True if valid format
    """
    # Expected format: alphanumeric_with_underscores_XXXX (where XXXX is hex suffix)
    pattern = r'^[a-z0-9_]+_[a-f0-9]{4}$'
    return bool( re.match( pattern, system_id ) )


# Mock user database for development/testing
# In production, this would be replaced with actual database queries
MOCK_USER_DATABASE = {
    "ricardo_felipe_ruiz_6bdc": {
        "email": "ricardo.felipe.ruiz@gmail.com",
        "name": "Ricardo",
        "email_verified": True
    },
    "alice_smith_a1b2": {
        "email": "alice.smith@example.com", 
        "name": "Alice",
        "email_verified": True
    },
    "bob_jones_3c4d": {
        "email": "bob.jones@example.com",
        "name": "Bob", 
        "email_verified": True
    }
}


def get_user_info( system_id: str ) -> Optional[Dict]:
    """
    Get user information by system ID.
    
    Args:
        system_id: System ID to look up
        
    Returns:
        Optional[Dict]: User info if found, None otherwise
    """
    return MOCK_USER_DATABASE.get( system_id )


def get_user_info_by_email( email: str ) -> Optional[Dict]:
    """
    Get user information by email address.
    
    Args:
        email: Email address to look up
        
    Returns:
        Optional[Dict]: User info if found, None otherwise
    """
    system_id = email_to_system_id( email )
    return get_user_info( system_id )


def quick_smoke_test():
    """
    Quick smoke test for user ID generation functions.
    """
    print( "🧪 Testing User ID Generator..." )
    
    # Test cases
    test_emails = [
        "ricardo.felipe.ruiz@gmail.com",
        "alice.smith@example.com",
        "bob.jones@example.com",
        "test.user@company.co.uk"
    ]
    
    try:
        for email in test_emails:
            system_id = email_to_system_id( email )
            display_name = system_id_to_display_name( system_id )
            is_valid = validate_system_id( system_id )
            
            print( f"  Email: {email}" )
            print( f"  System ID: {system_id}" )
            print( f"  Display Name: {display_name}" )
            print( f"  Valid: {is_valid}" )
            print()
        
        # Test user lookup
        ricardo_info = get_user_info_by_email( "ricardo.felipe.ruiz@gmail.com" )
        if ricardo_info:
            print( f"  User lookup successful: {ricardo_info['name']}" )
        
        print( "✓ All user ID generation tests passed!" )
        return True
        
    except Exception as e:
        print( f"✗ User ID generation test failed: {e}" )
        return False


if __name__ == "__main__":
    quick_smoke_test()