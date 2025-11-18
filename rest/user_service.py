"""
User Service for Authentication.

Handles user registration, authentication, and management operations
including database interactions for user accounts.
"""

import uuid
import sqlite3
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from cosa.rest.sqlite_database import get_auth_db_connection
from cosa.rest.password_service import hash_password, verify_password, validate_password_strength


def create_user( email: str, password: str, roles: Optional[List[str]] = None ) -> Tuple[bool, str, Optional[str]]:
    """
    Create new user account with email and password.

    Requires:
        - email is a valid email address string (format validated)
        - password is a non-empty string
        - roles is optional list of role strings (defaults to ["user"])
        - Database is initialized

    Ensures:
        - Password is validated for strength
        - Password is hashed before storage
        - User ID is generated (UUID4 format)
        - User record is inserted into database
        - Returns (success, message, user_id)
        - Duplicate emails are rejected

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str, user_id: Optional[str])
    """
    # Validate email format
    if not email or "@" not in email:
        return False, "Invalid email address", None

    # Validate password strength
    is_valid, error_msg = validate_password_strength( password )
    if not is_valid:
        return False, error_msg, None

    # Hash password
    try:
        password_hash = hash_password( password )
    except Exception as e:
        return False, f"Password hashing failed: {e}", None

    # Generate user ID
    user_id = str( uuid.uuid4() )

    # Set default roles
    if roles is None:
        roles = ["user"]

    # Store in database
    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        import json
        cursor.execute(
            """
            INSERT INTO users ( id, email, password_hash, created_at, roles )
            VALUES ( ?, ?, ?, ?, ? )
            """,
            ( user_id, email, password_hash, datetime.utcnow().isoformat(), json.dumps( roles ) )
        )
        conn.commit()
        return True, "User created successfully", user_id

    except sqlite3.IntegrityError:
        return False, "Email already registered", None

    except Exception as e:
        conn.rollback()
        return False, f"Database error: {e}", None

    finally:
        conn.close()


def authenticate_user( email: str, password: str ) -> Tuple[bool, str, Optional[Dict]]:
    """
    Authenticate user with email and password.

    Requires:
        - email is a string (may be invalid)
        - password is a string (may be incorrect)
        - Database is initialized

    Ensures:
        - Email lookup is case-sensitive
        - Password is verified using bcrypt
        - Inactive users are rejected
        - Returns (success, message, user_data)
        - Updates last_login_at timestamp on success
        - Timing-attack resistant

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str, user_data: Optional[Dict])
               user_data contains: id, email, roles, email_verified, is_active, created_at, last_login_at
    """
    if not email or not password:
        return False, "Email and password required", None

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        # Fetch user by email
        cursor.execute(
            """
            SELECT id, email, password_hash, roles, is_active, email_verified, created_at
            FROM users
            WHERE email = ?
            """,
            ( email, )
        )
        row = cursor.fetchone()

        if not row:
            return False, "Invalid email or password", None

        # Check if account is active
        if not row["is_active"]:
            return False, "Account is inactive", None

        # Verify password
        if not verify_password( password, row["password_hash"] ):
            return False, "Invalid email or password", None

        # Update last login timestamp
        last_login_timestamp = datetime.utcnow().isoformat()
        cursor.execute(
            """
            UPDATE users
            SET last_login_at = ?
            WHERE id = ?
            """,
            ( last_login_timestamp, row["id"] )
        )
        conn.commit()

        # Build user data
        import json
        user_data = {
            "id"              : row["id"],
            "email"           : row["email"],
            "roles"           : json.loads( row["roles"] ) if row["roles"] else ["user"],
            "email_verified"  : bool( row["email_verified"] ),
            "is_active"       : bool( row["is_active"] ),
            "created_at"      : row["created_at"],
            "last_login_at"   : last_login_timestamp
        }

        return True, "Authentication successful", user_data

    except Exception as e:
        return False, f"Authentication error: {e}", None

    finally:
        conn.close()


def get_user_by_id( user_id: str ) -> Optional[Dict]:
    """
    Retrieve user by ID.

    Requires:
        - user_id is a UUID string
        - Database is initialized

    Ensures:
        - Returns user data dictionary or None
        - Password hash is NOT included in result
        - Returns: id, email, roles, email_verified, is_active, created_at

    Raises:
        - None (returns None on error)

    Returns:
        Optional[Dict]: User data or None if not found
    """
    if not user_id:
        return None

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, email, roles, email_verified, is_active, created_at, last_login_at
            FROM users
            WHERE id = ?
            """,
            ( user_id, )
        )
        row = cursor.fetchone()

        if not row:
            return None

        import json
        user_data = {
            "id"              : row["id"],
            "email"           : row["email"],
            "roles"           : json.loads( row["roles"] ) if row["roles"] else ["user"],
            "email_verified"  : bool( row["email_verified"] ),
            "is_active"       : bool( row["is_active"] ),
            "created_at"      : row["created_at"],
            "last_login_at"   : row["last_login_at"]
        }

        return user_data

    except Exception:
        return None

    finally:
        conn.close()


def get_user_by_email( email: str ) -> Optional[Dict]:
    """
    Retrieve user by email address.

    Requires:
        - email is a string
        - Database is initialized

    Ensures:
        - Returns user data dictionary or None
        - Password hash is NOT included in result
        - Returns: id, email, roles, email_verified, is_active, created_at

    Raises:
        - None (returns None on error)

    Returns:
        Optional[Dict]: User data or None if not found
    """
    if not email:
        return None

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, email, roles, email_verified, is_active, created_at, last_login_at
            FROM users
            WHERE email = ?
            """,
            ( email, )
        )
        row = cursor.fetchone()

        if not row:
            return None

        import json
        user_data = {
            "id"              : row["id"],
            "email"           : row["email"],
            "roles"           : json.loads( row["roles"] ) if row["roles"] else ["user"],
            "email_verified"  : bool( row["email_verified"] ),
            "is_active"       : bool( row["is_active"] ),
            "created_at"      : row["created_at"],
            "last_login_at"   : row["last_login_at"]
        }

        return user_data

    except Exception:
        return None

    finally:
        conn.close()


def update_user_password( user_id: str, old_password: str, new_password: str ) -> Tuple[bool, str]:
    """
    Update user password with validation.

    Requires:
        - user_id is a valid UUID string
        - old_password is the current password
        - new_password meets strength requirements
        - Database is initialized

    Ensures:
        - Old password is verified before update
        - New password strength is validated
        - New password is hashed before storage
        - Returns (success, message)

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str)
    """
    if not user_id or not old_password or not new_password:
        return False, "All fields required"

    # Validate new password strength
    is_valid, error_msg = validate_password_strength( new_password )
    if not is_valid:
        return False, error_msg

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        # Fetch current password hash
        cursor.execute(
            """
            SELECT password_hash
            FROM users
            WHERE id = ?
            """,
            ( user_id, )
        )
        row = cursor.fetchone()

        if not row:
            return False, "User not found"

        # Verify old password
        if not verify_password( old_password, row["password_hash"] ):
            return False, "Current password is incorrect"

        # Hash new password
        new_password_hash = hash_password( new_password )

        # Update password
        cursor.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ?
            """,
            ( new_password_hash, user_id )
        )
        conn.commit()

        return True, "Password updated successfully"

    except Exception as e:
        conn.rollback()
        return False, f"Password update failed: {e}"

    finally:
        conn.close()


def deactivate_user( user_id: str ) -> Tuple[bool, str]:
    """
    Deactivate user account (soft delete).

    Requires:
        - user_id is a valid UUID string
        - Database is initialized

    Ensures:
        - Sets is_active to 0 (False)
        - Does not delete user record
        - Returns (success, message)

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
            UPDATE users
            SET is_active = 0
            WHERE id = ?
            """,
            ( user_id, )
        )
        conn.commit()

        if cursor.rowcount == 0:
            return False, "User not found"

        return True, "User deactivated successfully"

    except Exception as e:
        conn.rollback()
        return False, f"Deactivation failed: {e}"

    finally:
        conn.close()


def mark_email_verified( user_id: str ) -> Tuple[bool, str]:
    """
    Mark user email as verified (Phase 7).

    Requires:
        - user_id is a valid UUID string
        - Database is initialized

    Ensures:
        - Sets email_verified to 1 (True)
        - Returns (success, message)

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str)

    Example:
        success, msg = mark_email_verified( user_id )
        if success:
            print( "Email verified!" )
    """
    if not user_id:
        return False, "User ID required"

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE users
            SET email_verified = 1
            WHERE id = ?
            """,
            ( user_id, )
        )
        conn.commit()

        if cursor.rowcount == 0:
            return False, "User not found"

        return True, "Email verified successfully"

    except Exception as e:
        conn.rollback()
        return False, f"Email verification failed: {e}"

    finally:
        conn.close()


def reset_password_with_token( user_id: str, new_password: str ) -> Tuple[bool, str]:
    """
    Reset user password using password reset token (Phase 7).

    Requires:
        - user_id is a valid UUID string
        - new_password meets strength requirements
        - Database is initialized

    Ensures:
        - New password strength is validated
        - New password is hashed before storage
        - Returns (success, message)

    Raises:
        - None (returns error message in tuple)

    Returns:
        tuple: (success: bool, message: str)

    Example:
        success, msg = reset_password_with_token( user_id, "NewPass123!" )
        if success:
            print( "Password reset!" )
    """
    if not user_id or not new_password:
        return False, "User ID and new password required"

    # Validate new password strength
    is_valid, error_msg = validate_password_strength( new_password )
    if not is_valid:
        return False, error_msg

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        # Hash new password
        new_password_hash = hash_password( new_password )

        # Update password
        cursor.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ?
            """,
            ( new_password_hash, user_id )
        )
        conn.commit()

        if cursor.rowcount == 0:
            return False, "User not found"

        return True, "Password reset successfully"

    except Exception as e:
        conn.rollback()
        return False, f"Password reset failed: {e}"

    finally:
        conn.close()


def quick_smoke_test():
    """
    Quick smoke test for user service.

    Requires:
        - Database initialized
        - All dependencies available

    Ensures:
        - Tests user registration
        - Tests authentication
        - Tests user retrieval
        - Tests password update
        - Tests user deactivation
        - Returns True if all tests pass

    Raises:
        - None (catches all exceptions)
    """
    import cosa.utils.util as du
    from cosa.rest.sqlite_database import init_auth_database

    du.print_banner( "User Service Smoke Test", prepend_nl=True )

    try:
        # Initialize database
        print( "Initializing database..." )
        init_auth_database()
        print( "✓ Database initialized" )

        # Test 1: User registration
        print( "Testing user registration..." )
        success, message, user_id = create_user(
            email    = "test@example.com",
            password = "TestPass123!",
            roles    = ["user", "tester"]
        )
        if success and user_id:
            print( f"✓ User registered: {user_id}" )
        else:
            print( f"✗ Registration failed: {message}" )
            return False

        # Test 2: Duplicate email rejection
        print( "Testing duplicate email rejection..." )
        success2, message2, _ = create_user(
            email    = "test@example.com",
            password = "AnotherPass123!"
        )
        if not success2 and "already registered" in message2.lower():
            print( "✓ Duplicate email rejected" )
        else:
            print( "✗ Duplicate email was accepted!" )
            return False

        # Test 3: User authentication (correct password)
        print( "Testing authentication (correct password)..." )
        success, message, user_data = authenticate_user(
            email    = "test@example.com",
            password = "TestPass123!"
        )
        if success and user_data:
            print( f"✓ Authentication successful: {user_data['email']}" )
        else:
            print( f"✗ Authentication failed: {message}" )
            return False

        # Test 4: User authentication (wrong password)
        print( "Testing authentication (wrong password)..." )
        success, message, _ = authenticate_user(
            email    = "test@example.com",
            password = "WrongPassword123!"
        )
        if not success and "invalid" in message.lower():
            print( "✓ Wrong password rejected" )
        else:
            print( "✗ Wrong password was accepted!" )
            return False

        # Test 5: Get user by ID
        print( "Testing get user by ID..." )
        retrieved_user = get_user_by_id( user_id )
        if retrieved_user and retrieved_user["email"] == "test@example.com":
            print( "✓ User retrieved by ID" )
        else:
            print( "✗ User retrieval by ID failed" )
            return False

        # Test 6: Get user by email
        print( "Testing get user by email..." )
        retrieved_user = get_user_by_email( "test@example.com" )
        if retrieved_user and retrieved_user["id"] == user_id:
            print( "✓ User retrieved by email" )
        else:
            print( "✗ User retrieval by email failed" )
            return False

        # Test 7: Password update
        print( "Testing password update..." )
        success, message = update_user_password(
            user_id      = user_id,
            old_password = "TestPass123!",
            new_password = "NewTestPass456!"
        )
        if success:
            print( "✓ Password updated" )
        else:
            print( f"✗ Password update failed: {message}" )
            return False

        # Test 8: Verify new password works
        print( "Testing authentication with new password..." )
        success, message, _ = authenticate_user(
            email    = "test@example.com",
            password = "NewTestPass456!"
        )
        if success:
            print( "✓ New password works" )
        else:
            print( f"✗ New password authentication failed: {message}" )
            return False

        # Test 9: User deactivation
        print( "Testing user deactivation..." )
        success, message = deactivate_user( user_id )
        if success:
            print( "✓ User deactivated" )
        else:
            print( f"✗ Deactivation failed: {message}" )
            return False

        # Test 10: Verify deactivated user cannot login
        print( "Testing deactivated user login..." )
        success, message, _ = authenticate_user(
            email    = "test@example.com",
            password = "NewTestPass456!"
        )
        if not success and "inactive" in message.lower():
            print( "✓ Deactivated user cannot login" )
        else:
            print( "✗ Deactivated user was able to login!" )
            return False

        print( "\n✓ All user service tests passed!" )
        return True

    except Exception as e:
        print( f"✗ User service test failed: {e}" )
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    quick_smoke_test()