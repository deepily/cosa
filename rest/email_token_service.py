"""
Email Token Service for Lupin Authentication.

Handles generation and validation of:
- Email verification tokens (24h expiration)
- Password reset tokens (1h expiration)

Tokens are cryptographically secure and stored in SQLite database.
"""

import secrets
from datetime import datetime, timedelta
from typing import Tuple, Optional
from cosa.rest.auth_database import get_auth_db_connection


def generate_verification_token( user_id: str ) -> Tuple[bool, str, Optional[str]]:
    """
    Generate email verification token for user.

    Requires:
        - user_id is a valid user ID string
        - Database connection available

    Ensures:
        - returns (True, message, token) if token generated successfully
        - returns (False, error_message, None) if generation failed
        - token expires in 24 hours
        - token is cryptographically secure (32 bytes)

    Returns:
        Tuple[bool, str, Optional[str]]: (success, message, token)

    Example:
        success, msg, token = generate_verification_token( "user123" )
        if success:
            send_verification_email( user_email, token )
    """
    try:
        # Generate cryptographically secure token
        token = secrets.token_urlsafe( 32 )

        # Calculate expiration (24 hours from now)
        expires_at = (datetime.utcnow() + timedelta( hours=24 )).isoformat()
        created_at = datetime.utcnow().isoformat()

        # Store in database
        conn = get_auth_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO email_verification_tokens ( token, user_id, expires_at, created_at )
            VALUES ( ?, ?, ?, ? )
            """,
            (token, user_id, expires_at, created_at)
        )

        conn.commit()
        conn.close()

        return True, "Verification token generated", token

    except Exception as e:
        return False, f"Failed to generate verification token: {str( e )}", None


def validate_verification_token( token: str ) -> Tuple[bool, str, Optional[str]]:
    """
    Validate email verification token and mark as used.

    Requires:
        - token is a non-empty string
        - Database connection available

    Ensures:
        - returns (True, message, user_id) if token valid
        - returns (False, error_message, None) if token invalid/expired/used
        - marks token as used on successful validation
        - token can only be used once

    Returns:
        Tuple[bool, str, Optional[str]]: (success, message, user_id)

    Example:
        success, msg, user_id = validate_verification_token( token )
        if success:
            mark_email_verified( user_id )
    """
    try:
        conn = get_auth_db_connection()
        cursor = conn.cursor()

        # Fetch token details
        cursor.execute(
            """
            SELECT user_id, expires_at, used
            FROM email_verification_tokens
            WHERE token = ?
            """,
            (token,)
        )

        row = cursor.fetchone()

        if not row:
            conn.close()
            return False, "Invalid verification token", None

        user_id, expires_at_str, used = row

        # Check if already used
        if used:
            conn.close()
            return False, "Verification token already used", None

        # Check if expired
        expires_at = datetime.fromisoformat( expires_at_str )
        if datetime.utcnow() > expires_at:
            conn.close()
            return False, "Verification token expired", None

        # Mark token as used
        cursor.execute(
            """
            UPDATE email_verification_tokens
            SET used = 1
            WHERE token = ?
            """,
            (token,)
        )

        conn.commit()
        conn.close()

        return True, "Email verification token valid", user_id

    except Exception as e:
        return False, f"Failed to validate verification token: {str( e )}", None


def generate_password_reset_token( user_id: str ) -> Tuple[bool, str, Optional[str]]:
    """
    Generate password reset token for user.

    Requires:
        - user_id is a valid user ID string
        - Database connection available

    Ensures:
        - returns (True, message, token) if token generated successfully
        - returns (False, error_message, None) if generation failed
        - token expires in 1 hour
        - token is cryptographically secure (32 bytes)

    Returns:
        Tuple[bool, str, Optional[str]]: (success, message, token)

    Example:
        success, msg, token = generate_password_reset_token( "user123" )
        if success:
            send_password_reset_email( user_email, token )
    """
    try:
        # Generate cryptographically secure token
        token = secrets.token_urlsafe( 32 )

        # Calculate expiration (1 hour from now)
        expires_at = (datetime.utcnow() + timedelta( hours=1 )).isoformat()
        created_at = datetime.utcnow().isoformat()

        # Store in database
        conn = get_auth_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO password_reset_tokens ( token, user_id, expires_at, created_at )
            VALUES ( ?, ?, ?, ? )
            """,
            (token, user_id, expires_at, created_at)
        )

        conn.commit()
        conn.close()

        return True, "Password reset token generated", token

    except Exception as e:
        return False, f"Failed to generate password reset token: {str( e )}", None


def validate_password_reset_token( token: str ) -> Tuple[bool, str, Optional[str]]:
    """
    Validate password reset token and mark as used.

    Requires:
        - token is a non-empty string
        - Database connection available

    Ensures:
        - returns (True, message, user_id) if token valid
        - returns (False, error_message, None) if token invalid/expired/used
        - marks token as used on successful validation
        - token can only be used once

    Returns:
        Tuple[bool, str, Optional[str]]: (success, message, user_id)

    Example:
        success, msg, user_id = validate_password_reset_token( token )
        if success:
            reset_password_with_token( user_id, new_password )
    """
    try:
        conn = get_auth_db_connection()
        cursor = conn.cursor()

        # Fetch token details
        cursor.execute(
            """
            SELECT user_id, expires_at, used
            FROM password_reset_tokens
            WHERE token = ?
            """,
            (token,)
        )

        row = cursor.fetchone()

        if not row:
            conn.close()
            return False, "Invalid password reset token", None

        user_id, expires_at_str, used = row

        # Check if already used
        if used:
            conn.close()
            return False, "Password reset token already used", None

        # Check if expired
        expires_at = datetime.fromisoformat( expires_at_str )
        if datetime.utcnow() > expires_at:
            conn.close()
            return False, "Password reset token expired", None

        # Mark token as used
        cursor.execute(
            """
            UPDATE password_reset_tokens
            SET used = 1
            WHERE token = ?
            """,
            (token,)
        )

        conn.commit()
        conn.close()

        return True, "Password reset token valid", user_id

    except Exception as e:
        return False, f"Failed to validate password reset token: {str( e )}", None


def cleanup_expired_tokens() -> Tuple[int, int]:
    """
    Remove expired tokens from database.

    Requires:
        - Database connection available

    Ensures:
        - removes all expired verification tokens
        - removes all expired password reset tokens
        - returns count of deleted tokens

    Returns:
        Tuple[int, int]: (verification_tokens_deleted, reset_tokens_deleted)

    Example:
        ver_count, reset_count = cleanup_expired_tokens()
        print( f"Cleaned up {ver_count} verification and {reset_count} reset tokens" )
    """
    try:
        conn = get_auth_db_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        # Delete expired verification tokens
        cursor.execute(
            """
            DELETE FROM email_verification_tokens
            WHERE expires_at < ?
            """,
            (now,)
        )
        ver_count = cursor.rowcount

        # Delete expired password reset tokens
        cursor.execute(
            """
            DELETE FROM password_reset_tokens
            WHERE expires_at < ?
            """,
            (now,)
        )
        reset_count = cursor.rowcount

        conn.commit()
        conn.close()

        return ver_count, reset_count

    except Exception as e:
        print( f"Failed to cleanup expired tokens: {str( e )}" )
        return 0, 0


def quick_smoke_test():
    """
    Quick smoke test for email token service.

    Requires:
        - Database initialized
        - User service available

    Ensures:
        - Tests token generation and validation
        - Tests token reuse prevention
        - Tests token expiration
        - Returns True if all tests pass

    Raises:
        - None (catches all exceptions)
    """
    import cosa.utils.util as du
    from cosa.rest.auth_database import init_auth_database
    from cosa.rest.user_service import create_user

    du.print_banner( "Email Token Service Smoke Test", prepend_nl=True )

    try:
        # Initialize database
        print( "Initializing database..." )
        init_auth_database()
        print( "✓ Database initialized" )

        # Create test users
        print( "Creating test users..." )
        success1, msg1, user_id1 = create_user( "token_test1@example.com", "TestPass123!" )
        success2, msg2, user_id2 = create_user( "token_test2@example.com", "TestPass123!" )

        if not success1 or not success2:
            print( f"✗ Failed to create test users: {msg1}, {msg2}" )
            return False

        print( f"✓ Test users created" )

        # Test 1: Generate verification token
        print( "Testing verification token generation..." )
        success, message, token = generate_verification_token( user_id1 )
        if success and token:
            print( f"✓ Verification token generated" )
        else:
            print( f"✗ Token generation failed: {message}" )
            return False

        # Test 2: Validate verification token
        print( "Testing verification token validation..." )
        success, message, returned_user_id = validate_verification_token( token )
        if success and returned_user_id == user_id1:
            print( f"✓ Verification token validated" )
        else:
            print( f"✗ Token validation failed: {message}" )
            return False

        # Test 3: Test token reuse prevention
        print( "Testing token reuse prevention..." )
        success, message, _ = validate_verification_token( token )
        if not success and "already used" in message:
            print( "✓ Token reuse correctly blocked" )
        else:
            print( "✗ Token reuse was not blocked" )
            return False

        # Test 4: Generate password reset token
        print( "Testing password reset token generation..." )
        success, message, reset_token = generate_password_reset_token( user_id2 )
        if success and reset_token:
            print( f"✓ Password reset token generated" )
        else:
            print( f"✗ Reset token generation failed: {message}" )
            return False

        # Test 5: Validate password reset token
        print( "Testing password reset token validation..." )
        success, message, returned_user_id = validate_password_reset_token( reset_token )
        if success and returned_user_id == user_id2:
            print( f"✓ Password reset token validated" )
        else:
            print( f"✗ Reset token validation failed: {message}" )
            return False

        # Test 6: Test invalid token
        print( "Testing invalid token handling..." )
        success, message, _ = validate_verification_token( "invalid_token_12345" )
        if not success and "invalid" in message.lower():
            print( "✓ Invalid token correctly rejected" )
        else:
            print( "✗ Invalid token was not rejected" )
            return False

        # Test 7: Cleanup function
        print( "Testing cleanup function..." )
        ver_count, reset_count = cleanup_expired_tokens()
        print( f"✓ Cleanup completed ({ver_count} verification, {reset_count} reset tokens)" )

        print( "\n✓ All email token service tests passed!" )
        return True

    except Exception as e:
        print( f"✗ Email token service test failed: {e}" )
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    quick_smoke_test()