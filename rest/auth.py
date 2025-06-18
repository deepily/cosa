from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Optional
import os

# For now, we'll mock the Firebase Admin SDK
# In production, you would use: import firebase_admin
# from firebase_admin import credentials, auth

# Mock Firebase initialization
FIREBASE_INITIALIZED = False

def init_firebase():
    """
    Initialize Firebase Admin SDK.
    
    In production, this would:
    - Load service account credentials
    - Initialize firebase_admin app
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
    
    Args:
        token: The Firebase ID token to verify
        
    Returns:
        dict: Decoded token claims including user_id
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # MOCK: In production, this would be:
        # decoded_token = auth.verify_id_token(token)
        
        # For mocking, we'll decode a simple format: "mock_token_userId"
        if not token.startswith("mock_token_"):
            raise ValueError("Invalid mock token format")
            
        user_id = token.replace("mock_token_", "")
        if not user_id:
            raise ValueError("No user ID in token")
            
        # Return mock decoded token
        decoded_token = {
            "uid": user_id,
            "email": f"{user_id}@example.com",
            "email_verified": True,
            "name": f"User {user_id}",
            "picture": None,
            "iss": "https://securetoken.google.com/mock-project",
            "aud": "mock-project",
            "auth_time": 1234567890,
            "user_id": user_id,
            "sub": user_id,
            "iat": 1234567890,
            "exp": 9999999999,  # Far future
            "firebase": {
                "identities": {"email": [f"{user_id}@example.com"]},
                "sign_in_provider": "password"
            }
        }
        
        print(f"[AUTH] Token verified for user: [{user_id}]")
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
    Dependency to get the current authenticated user.
    
    Extracts the bearer token from the Authorization header,
    verifies it with Firebase, and returns the user info.
    
    Args:
        credentials: The HTTP authorization credentials
        
    Returns:
        dict: User information from the decoded token
        
    Raises:
        HTTPException: If authentication fails
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
    Dependency to get just the user ID.
    
    Args:
        current_user: The current user dict from get_current_user
        
    Returns:
        str: The user's ID
    """
    return current_user["uid"]


# Optional: Create a dependency for optional authentication
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[Dict]:
    """
    Dependency for endpoints that optionally support authentication.
    
    Returns None if no valid token is provided, otherwise returns user info.
    """
    if not credentials:
        return None
        
    try:
        init_firebase()
        token = credentials.credentials
        return await verify_firebase_token(token)
    except:
        return None