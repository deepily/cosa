from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Optional
import os
from .user_id_generator import get_user_info, email_to_system_id

# For now, we'll mock the Firebase Admin SDK
# In production, you would use: import firebase_admin
# from firebase_admin import credentials, auth

# Mock Firebase initialization
FIREBASE_INITIALIZED = False

def init_firebase():
    """
    Initialize Firebase Admin SDK with mock implementation.
    
    Requires:
        - None
        
    Ensures:
        - Sets FIREBASE_INITIALIZED to True
        - Prints initialization message
        - Idempotent (safe to call multiple times)
        
    Raises:
        - None
    """
    global FIREBASE_INITIALIZED
    if not FIREBASE_INITIALIZED:
        print("[AUTH] Initializing Firebase Admin SDK (MOCKED)")
        # In production:
        # cred = credentials.Certificate("path/to/serviceAccountKey.json")
        # firebase_admin.initialize_app(cred)
        FIREBASE_INITIALIZED = True


# Create security scheme
security = HTTPBearer()


async def verify_firebase_token(token: str) -> Dict:
    """
    Verify Firebase ID token and return decoded claims.
    
    Requires:
        - token is a non-empty string
        - token follows expected format (mock_token_* or mock_token_email_*)
        
    Ensures:
        - Returns dictionary with complete user information
        - Dictionary includes uid, email, name, email_verified fields
        - User data is looked up or generated for unknown system IDs
        - Prints verification success message
        
    Raises:
        - HTTPException with 401 status if token format is invalid
        - HTTPException with 401 status if email format is invalid in email-based tokens
        - HTTPException with 401 status if system ID is empty
    """
    try:
        # MOCK: In production, this would be:
        # decoded_token = auth.verify_id_token(token)
        
        # For mocking, we'll decode email-based format: "mock_token_email_user@example.com"
        if not token.startswith("mock_token_"):
            raise ValueError("Invalid mock token format")
        
        # Check if it's the new email-based format
        if token.startswith("mock_token_email_"):
            email = token.replace("mock_token_email_", "")
            if not email or '@' not in email:
                raise ValueError("Invalid email in token")
            # Convert email to system ID internally
            system_id = email_to_system_id(email)
        else:
            # Legacy format for backward compatibility
            system_id = token.replace("mock_token_", "")
            if not system_id:
                raise ValueError("No system ID in token")
        
        # Look up user by system ID using centralized user database
        user_data = get_user_info( system_id )
        if not user_data:
            # Generate default user info for unknown system IDs (for testing)
            user_data = {
                "uid": system_id,
                "email": f"{system_id}@generated.local",
                "name": system_id.split('_')[0].capitalize(),
                "email_verified": False
            }
            print( f"[AUTH] Generated user info for unknown system ID: {system_id}" )
        else:
            # Add uid field for Firebase compatibility
            user_data["uid"] = system_id
            
        # Return mock decoded token with real user structure
        decoded_token = {
            "uid": user_data["uid"],
            "email": user_data["email"],
            "email_verified": user_data["email_verified"],
            "name": user_data["name"],
            "picture": None,
            "iss": "https://securetoken.google.com/mock-project",
            "aud": "mock-project",
            "auth_time": 1234567890,
            "user_id": user_data["uid"],  # Legacy field for compatibility
            "sub": user_data["uid"],
            "iat": 1234567890,
            "exp": 9999999999,  # Far future
            "firebase": {
                "identities": {"email": [user_data["email"]]},
                "sign_in_provider": "password"
            }
        }
        
        print(f"[AUTH] Token verified for user: [{user_data['name']}] ({user_data['uid']})")
        return decoded_token
        
    except Exception as e:
        print(f"[AUTH] Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """
    FastAPI dependency to get the current authenticated user.
    
    Requires:
        - credentials contains valid HTTPAuthorizationCredentials
        - credentials.credentials is a valid token string
        
    Ensures:
        - Firebase is initialized before token verification
        - Returns complete user information dictionary
        - Token is extracted and verified successfully
        
    Raises:
        - HTTPException with 401 status if token verification fails
        - Any exceptions from verify_firebase_token are propagated
    """
    # Initialize Firebase if needed
    init_firebase()
    
    # Extract token
    token = credentials.credentials
    
    # Verify token and get user info
    user_info = await verify_firebase_token(token)
    
    return user_info


async def get_current_user_id(
    current_user: Dict = Depends(get_current_user)
) -> str:
    """
    FastAPI dependency to extract just the user ID from authenticated user.
    
    Requires:
        - current_user is a valid user dictionary from get_current_user
        - current_user contains 'uid' key
        
    Ensures:
        - Returns the user's unique identifier as a string
        - Provides simplified access to user ID for endpoints that only need ID
        
    Raises:
        - KeyError if 'uid' key is missing from current_user dictionary
    """
    return current_user["uid"]


# Optional: Create a dependency for optional authentication
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[Dict]:
    """
    FastAPI dependency for endpoints with optional authentication.
    
    Requires:
        - credentials may be None or valid HTTPAuthorizationCredentials
        
    Ensures:
        - Returns None if no credentials provided
        - Returns None if token verification fails (does not raise exceptions)
        - Returns complete user dictionary if valid token provided
        - Firebase is initialized before attempting verification
        
    Raises:
        - None (all exceptions are caught and result in None return)
    """
    if not credentials:
        return None
        
    try:
        init_firebase()
        token = credentials.credentials
        return await verify_firebase_token(token)
    except:
        return None