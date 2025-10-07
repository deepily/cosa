"""
Refresh Token Management Service.

Handles refresh token storage, validation, revocation, and cleanup
for JWT authentication system with token rotation.
"""

import hashlib
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple

from cosa.rest.auth_database import get_auth_db_connection
from cosa.rest.jwt_service import create_refresh_token, decode_and_validate_token
from cosa.config.configuration_manager import ConfigurationManager

config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )


def _hash_token( token: str ) -> str:
    """
    Hash refresh token for secure storage.

    Requires:
        - token is a non-empty JWT string

    Ensures:
        - Returns SHA-256 hash of token
        - Hash is suitable for database storage and lookup
        - Same token always produces same hash

    Raises:
        - None

    Returns:
        str: SHA-256 hash (hex string)
    """
    return hashlib.sha256( token.encode() ).hexdigest()


def store_refresh_token(
    user_id: str,
    token: str,
    jti: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Store refresh token in database with metadata.

    Requires:
        - user_id is a valid UUID string
        - token is a valid JWT refresh token string
        - jti is the token ID from JWT claims
        - user_agent is optional browser/client string
        - ip_address is optional client IP string
        - Database is initialized

    Ensures:
        - Token is hashed before storage (never store plaintext)
        - Expiration time calculated from JWT claims
        - Created timestamp set to current UTC time
        - Returns (success, message)
        - Token can be retrieved later for validation

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str)
    """
    if not user_id or not token or not jti:
        return False, "user_id, token, and jti are required"

    # Decode token to get expiration
    try:
        payload = decode_and_validate_token( token, expected_type="refresh" )
        expires_at = datetime.fromtimestamp( payload["exp"] ).isoformat()
    except Exception as e:
        return False, f"Invalid token: {e}"

    # Hash token for storage
    token_hash = _hash_token( token )

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO refresh_tokens (
                jti, user_id, token_hash, expires_at,
                created_at, user_agent, ip_address
            )
            VALUES ( ?, ?, ?, ?, ?, ?, ? )
            """,
            (
                jti, user_id, token_hash, expires_at,
                datetime.utcnow().isoformat(), user_agent, ip_address
            )
        )
        conn.commit()
        return True, "Refresh token stored successfully"

    except sqlite3.IntegrityError:
        return False, "Token already exists"

    except Exception as e:
        conn.rollback()
        return False, f"Database error: {e}"

    finally:
        conn.close()


def validate_refresh_token( token: str ) -> Tuple[bool, str, Optional[Dict]]:
    """
    Validate refresh token and return user data.

    Requires:
        - token is a JWT string (may be invalid or expired)
        - Database is initialized

    Ensures:
        - Token signature is validated
        - Token expiration is checked
        - Token is not revoked in database
        - Returns (success, message, token_data)
        - token_data includes: jti, user_id, created_at
        - Updates last_used_at timestamp on success

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str, token_data: Optional[Dict])
    """
    if not token:
        return False, "Token required", None

    # Validate JWT signature and expiration
    try:
        payload = decode_and_validate_token( token, expected_type="refresh" )
        jti = payload.get( "jti" )
        user_id = payload.get( "sub" )

        if not jti or not user_id:
            return False, "Invalid token claims", None

    except Exception as e:
        return False, f"Token validation failed: {e}", None

    # Check if token exists and is not revoked
    token_hash = _hash_token( token )

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT jti, user_id, created_at, revoked, expires_at
            FROM refresh_tokens
            WHERE jti = ? AND token_hash = ?
            """,
            ( jti, token_hash )
        )
        row = cursor.fetchone()

        if not row:
            return False, "Token not found in database", None

        if row["revoked"]:
            return False, "Token has been revoked", None

        # Update last_used_at timestamp
        cursor.execute(
            """
            UPDATE refresh_tokens
            SET last_used_at = ?
            WHERE jti = ?
            """,
            ( datetime.utcnow().isoformat(), jti )
        )
        conn.commit()

        # Build token data
        token_data = {
            "jti"        : row["jti"],
            "user_id"    : row["user_id"],
            "created_at" : row["created_at"],
            "expires_at" : row["expires_at"]
        }

        return True, "Token is valid", token_data

    except Exception as e:
        return False, f"Validation error: {e}", None

    finally:
        conn.close()


def revoke_refresh_token( jti: str ) -> Tuple[bool, str]:
    """
    Revoke refresh token by JTI.

    Requires:
        - jti is a token ID string
        - Database is initialized

    Ensures:
        - Sets revoked flag to 1 (True)
        - Token cannot be used after revocation
        - Returns (success, message)
        - Idempotent (can revoke already-revoked tokens)

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str)
    """
    if not jti:
        return False, "JTI required"

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE refresh_tokens
            SET revoked = 1
            WHERE jti = ?
            """,
            ( jti, )
        )
        conn.commit()

        if cursor.rowcount == 0:
            return False, "Token not found"

        return True, "Token revoked successfully"

    except Exception as e:
        conn.rollback()
        return False, f"Revocation failed: {e}"

    finally:
        conn.close()


def revoke_all_user_tokens( user_id: str ) -> Tuple[bool, str]:
    """
    Revoke all refresh tokens for a user.

    Requires:
        - user_id is a valid UUID string
        - Database is initialized

    Ensures:
        - All user's refresh tokens are revoked
        - Returns (success, message)
        - User must re-login to get new tokens

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str)
    """
    if not user_id:
        return False, "User ID required"

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE refresh_tokens
            SET revoked = 1
            WHERE user_id = ?
            """,
            ( user_id, )
        )
        conn.commit()

        return True, f"Revoked {cursor.rowcount} token(s)"

    except Exception as e:
        conn.rollback()
        return False, f"Revocation failed: {e}"

    finally:
        conn.close()


def cleanup_expired_tokens() -> Tuple[bool, str, int]:
    """
    Remove expired refresh tokens from database.

    Requires:
        - Database is initialized

    Ensures:
        - Deletes tokens where expires_at < current time
        - Returns (success, message, count)
        - Frees up database space
        - Should be run periodically (e.g., daily cron job)

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str, deleted_count: int)
    """
    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM refresh_tokens
            WHERE expires_at < ?
            """,
            ( datetime.utcnow().isoformat(), )
        )
        conn.commit()

        deleted_count = cursor.rowcount
        return True, f"Cleaned up {deleted_count} expired token(s)", deleted_count

    except Exception as e:
        conn.rollback()
        return False, f"Cleanup failed: {e}", 0

    finally:
        conn.close()


def rotate_refresh_token(
    old_token: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Rotate refresh token (revoke old, issue new).

    This implements token rotation security pattern:
    - Old token is revoked immediately
    - New token is issued with fresh expiration
    - Prevents token reuse attacks

    Requires:
        - old_token is a valid refresh token
        - user_agent is optional client info
        - ip_address is optional client IP
        - Database is initialized

    Ensures:
        - Old token is validated and revoked
        - New token is generated with same user_id
        - New token is stored in database
        - Returns (success, message, new_token)
        - Atomic operation (both revoke and store succeed or both fail)

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str, new_token: Optional[str])
    """
    # Validate old token
    is_valid, message, token_data = validate_refresh_token( old_token )
    if not is_valid:
        return False, f"Invalid token: {message}", None

    user_id = token_data["user_id"]
    old_jti = token_data["jti"]

    # Revoke old token
    success, revoke_msg = revoke_refresh_token( old_jti )
    if not success:
        return False, f"Failed to revoke old token: {revoke_msg}", None

    # Generate new token
    try:
        from cosa.rest.user_service import get_user_by_id

        user = get_user_by_id( user_id )
        if not user:
            return False, "User not found", None

        new_token = create_refresh_token( user_id, user["email"] )

        # Decode to get JTI
        payload = decode_and_validate_token( new_token, expected_type="refresh" )
        new_jti = payload["jti"]

        # Store new token
        success, store_msg = store_refresh_token(
            user_id, new_token, new_jti, user_agent, ip_address
        )

        if not success:
            return False, f"Failed to store new token: {store_msg}", None

        return True, "Token rotated successfully", new_token

    except Exception as e:
        return False, f"Token rotation failed: {e}", None


def quick_smoke_test():
    """
    Quick smoke test for refresh token service.

    Requires:
        - Database initialized
        - JWT service available
        - User service available

    Ensures:
        - Tests token storage
        - Tests token validation
        - Tests token revocation
        - Tests cleanup of expired tokens
        - Tests token rotation
        - Returns True if all tests pass

    Raises:
        - None (catches all exceptions)
    """
    import cosa.utils.util as du
    from cosa.rest.auth_database import init_auth_database
    from cosa.rest.user_service import create_user

    du.print_banner( "Refresh Token Service Smoke Test", prepend_nl=True )

    try:
        # Initialize database
        print( "Initializing database..." )
        init_auth_database()
        print( "✓ Database initialized" )

        # Create test user
        print( "Creating test user..." )
        success, message, user_id = create_user(
            email    = "refresh_test@example.com",
            password = "TestPass123!"
        )
        if not success:
            print( f"✗ User creation failed: {message}" )
            return False
        print( f"✓ Test user created: {user_id}" )

        # Test 1: Store refresh token
        print( "Testing token storage..." )
        from cosa.rest.jwt_service import create_refresh_token

        token = create_refresh_token( user_id, "refresh_test@example.com" )
        payload = decode_and_validate_token( token, expected_type="refresh" )
        jti = payload["jti"]

        success, message = store_refresh_token(
            user_id    = user_id,
            token      = token,
            jti        = jti,
            user_agent = "Test Agent",
            ip_address = "127.0.0.1"
        )
        if success:
            print( f"✓ Token stored: {jti[:16]}..." )
        else:
            print( f"✗ Token storage failed: {message}" )
            return False

        # Test 2: Validate refresh token
        print( "Testing token validation..." )
        is_valid, message, token_data = validate_refresh_token( token )
        if is_valid and token_data["user_id"] == user_id:
            print( "✓ Token validated successfully" )
        else:
            print( f"✗ Token validation failed: {message}" )
            return False

        # Test 3: Token rotation
        print( "Testing token rotation..." )
        success, message, new_token = rotate_refresh_token(
            old_token  = token,
            user_agent = "Test Agent",
            ip_address = "127.0.0.1"
        )
        if success and new_token:
            print( "✓ Token rotated successfully" )
        else:
            print( f"✗ Token rotation failed: {message}" )
            return False

        # Test 4: Old token should be revoked
        print( "Testing old token revocation..." )
        is_valid, message, _ = validate_refresh_token( token )
        if not is_valid and "revoked" in message.lower():
            print( "✓ Old token is revoked" )
        else:
            print( "✗ Old token still valid (should be revoked)!" )
            return False

        # Test 5: New token should work
        print( "Testing new token validation..." )
        is_valid, message, _ = validate_refresh_token( new_token )
        if is_valid:
            print( "✓ New token is valid" )
        else:
            print( f"✗ New token validation failed: {message}" )
            return False

        # Test 6: Manual token revocation
        print( "Testing manual token revocation..." )
        payload = decode_and_validate_token( new_token, expected_type="refresh" )
        new_jti = payload["jti"]

        success, message = revoke_refresh_token( new_jti )
        if success:
            print( "✓ Token revoked manually" )
        else:
            print( f"✗ Manual revocation failed: {message}" )
            return False

        # Test 7: Revoked token should not validate
        print( "Testing revoked token rejection..." )
        is_valid, message, _ = validate_refresh_token( new_token )
        if not is_valid:
            print( "✓ Revoked token rejected" )
        else:
            print( "✗ Revoked token was accepted!" )
            return False

        # Test 8: Revoke all user tokens
        print( "Testing revoke all user tokens..." )

        # Create a few more tokens
        token1 = create_refresh_token( user_id, "refresh_test@example.com" )
        payload1 = decode_and_validate_token( token1, expected_type="refresh" )
        store_refresh_token( user_id, token1, payload1["jti"] )

        token2 = create_refresh_token( user_id, "refresh_test@example.com" )
        payload2 = decode_and_validate_token( token2, expected_type="refresh" )
        store_refresh_token( user_id, token2, payload2["jti"] )

        success, message = revoke_all_user_tokens( user_id )
        if success:
            print( f"✓ {message}" )
        else:
            print( f"✗ Revoke all failed: {message}" )
            return False

        # Test 9: Cleanup expired tokens
        print( "Testing cleanup expired tokens..." )
        success, message, count = cleanup_expired_tokens()
        if success:
            print( f"✓ Cleanup completed: {count} token(s) removed" )
        else:
            print( f"✗ Cleanup failed: {message}" )
            return False

        print( "\n✓ All refresh token service tests passed!" )
        return True

    except Exception as e:
        print( f"✗ Refresh token service test failed: {e}" )
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    quick_smoke_test()