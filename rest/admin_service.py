"""
Admin Service for User Management.

Provides administrative functions for managing users, roles, and account status.
All functions include audit logging and self-protection rules.
"""

import json
import secrets
import string
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from cosa.rest.auth_database import get_auth_db_connection
from cosa.rest.user_service import get_user_by_id, get_user_by_email
from cosa.rest.password_service import hash_password, validate_password_strength
from cosa.rest.refresh_token_service import revoke_all_user_tokens
from cosa.rest.auth_audit import log_auth_event


def list_users(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    role_filter: Optional[str] = None,
    status_filter: Optional[str] = None
) -> Tuple[List[Dict], int]:
    """
    List all users with pagination and filtering.

    Requires:
        - limit is a positive integer (max 1000)
        - offset is a non-negative integer
        - search is optional string for email filtering
        - role_filter is optional: 'admin' or 'user'
        - status_filter is optional: 'active' or 'inactive'
        - Database connection available

    Ensures:
        - Returns (users_list, total_count) tuple
        - Users list limited to specified count
        - Total count reflects filtered results
        - Users sorted by created_at DESC

    Returns:
        Tuple[List[Dict], int]: (users list, total count)

    Example:
        users, total = list_users( limit=50, offset=0, search="alice" )
        print( f"Found {total} users, showing {len( users )}" )
    """
    # Validate and cap limit
    limit = min( limit, 1000 )

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        # Build WHERE clause
        where_clauses = []
        params = []

        # Email search filter
        if search:
            where_clauses.append( "email LIKE ?" )
            params.append( f"%{search}%" )

        # Role filter
        if role_filter and role_filter in ['admin', 'user']:
            where_clauses.append( "roles LIKE ?" )
            params.append( f'%"{role_filter}"%' )

        # Status filter
        if status_filter:
            if status_filter == 'active':
                where_clauses.append( "is_active = 1" )
            elif status_filter == 'inactive':
                where_clauses.append( "is_active = 0" )

        # Construct WHERE clause
        where_sql = " AND ".join( where_clauses ) if where_clauses else "1=1"

        # Get total count
        count_query = f"SELECT COUNT(*) FROM users WHERE {where_sql}"
        cursor.execute( count_query, params )
        total_count = cursor.fetchone()[0]

        # Get users
        query = f"""
            SELECT id, email, roles, email_verified, is_active, created_at, last_login_at
            FROM users
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute( query, params + [limit, offset] )
        rows = cursor.fetchall()

        users = [
            {
                "id"              : row["id"],
                "email"           : row["email"],
                "roles"           : json.loads( row["roles"] ) if row["roles"] else ["user"],
                "email_verified"  : bool( row["email_verified"] ),
                "is_active"       : bool( row["is_active"] ),
                "created_at"      : row["created_at"],
                "last_login_at"   : row["last_login_at"]
            }
            for row in rows
        ]

        return users, total_count

    except Exception as e:
        print( f"Error listing users: {e}" )
        return [], 0

    finally:
        conn.close()


def get_user_details( user_id: str ) -> Optional[Dict]:
    """
    Get detailed user information with additional stats.

    Requires:
        - user_id is a valid UUID string
        - Database connection available

    Ensures:
        - Returns enhanced user dict or None
        - Includes audit log count and failed login count
        - Password hash is NOT included

    Returns:
        Optional[Dict]: Enhanced user data or None if not found

    Example:
        details = get_user_details( "user-uuid-123" )
        if details:
            print( f"User has {details['audit_log_count']} audit entries" )
    """
    if not user_id:
        return None

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        # Get user with stats
        cursor.execute(
            """
            SELECT
                u.id,
                u.email,
                u.roles,
                u.email_verified,
                u.is_active,
                u.created_at,
                u.last_login_at,
                (SELECT COUNT(*) FROM auth_audit_log WHERE user_id = u.id) as audit_count,
                (SELECT COUNT(*) FROM failed_login_attempts WHERE email = u.email) as failed_login_count
            FROM users u
            WHERE u.id = ?
            """,
            ( user_id, )
        )
        row = cursor.fetchone()

        if not row:
            return None

        user_details = {
            "id"                  : row["id"],
            "email"               : row["email"],
            "roles"               : json.loads( row["roles"] ) if row["roles"] else ["user"],
            "email_verified"      : bool( row["email_verified"] ),
            "is_active"           : bool( row["is_active"] ),
            "created_at"          : row["created_at"],
            "last_login_at"       : row["last_login_at"],
            "audit_log_count"     : row["audit_count"],
            "failed_login_count"  : row["failed_login_count"]
        }

        return user_details

    except Exception as e:
        print( f"Error getting user details: {e}" )
        return None

    finally:
        conn.close()


def update_user_roles(
    admin_user_id: str,
    target_user_id: str,
    new_roles: List[str],
    admin_email: str = "unknown",
    admin_ip: str = "unknown"
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Update user roles with self-protection and audit logging.

    Requires:
        - admin_user_id is valid UUID of admin performing action
        - target_user_id is valid UUID of user being modified
        - new_roles is non-empty list of valid role strings
        - Valid roles are: 'admin', 'user'

    Ensures:
        - Validates roles are in allowed list
        - Prevents admin from removing own admin role
        - Updates roles in database
        - Logs action to audit trail
        - Returns (success, message, updated_user)

    Raises:
        - None (returns error in tuple)

    Returns:
        Tuple[bool, str, Optional[Dict]]: (success, message, user_data)

    Example:
        success, msg, user = update_user_roles(
            admin_user_id = "admin-uuid",
            target_user_id = "user-uuid",
            new_roles = ["user", "admin"],
            admin_email = "admin@example.com",
            admin_ip = "192.168.1.1"
        )
    """
    # Validate roles
    valid_roles = ["admin", "user"]
    if not new_roles or not all( role in valid_roles for role in new_roles ):
        return False, f"Invalid roles. Allowed: {', '.join( valid_roles )}", None

    # Self-protection: Cannot remove own admin role
    if admin_user_id == target_user_id and "admin" not in new_roles:
        return False, "Cannot remove your own admin role", None

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        # Get current user data
        target_user = get_user_by_id( target_user_id )
        if not target_user:
            return False, "User not found", None

        old_roles = target_user["roles"]

        # Update roles
        cursor.execute(
            """
            UPDATE users
            SET roles = ?
            WHERE id = ?
            """,
            ( json.dumps( new_roles ), target_user_id )
        )
        conn.commit()

        # Log to audit
        log_auth_event(
            event_type  = "admin_role_update",
            user_id     = admin_user_id,
            email       = admin_email,
            ip_address  = admin_ip,
            details     = f"Updated roles for {target_user['email']}: {old_roles} → {new_roles}",
            success     = True
        )

        # Get updated user
        updated_user = get_user_by_id( target_user_id )

        return True, "User roles updated successfully", updated_user

    except Exception as e:
        conn.rollback()
        return False, f"Role update failed: {e}", None

    finally:
        conn.close()


def toggle_user_status(
    admin_user_id: str,
    target_user_id: str,
    is_active: bool,
    admin_email: str = "unknown",
    admin_ip: str = "unknown"
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Toggle user account status with self-protection and session invalidation.

    Requires:
        - admin_user_id is valid UUID of admin performing action
        - target_user_id is valid UUID of user being modified
        - is_active is boolean status value

    Ensures:
        - Prevents admin from deactivating self
        - Updates is_active status in database
        - Revokes all refresh tokens if deactivating
        - Logs action to audit trail
        - Returns (success, message, updated_user)

    Raises:
        - None (returns error in tuple)

    Returns:
        Tuple[bool, str, Optional[Dict]]: (success, message, user_data)

    Example:
        success, msg, user = toggle_user_status(
            admin_user_id = "admin-uuid",
            target_user_id = "user-uuid",
            is_active = False,  # Deactivate
            admin_email = "admin@example.com",
            admin_ip = "192.168.1.1"
        )
    """
    # Self-protection: Cannot deactivate self
    if admin_user_id == target_user_id and not is_active:
        return False, "Cannot deactivate your own account", None

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        # Get current user data
        target_user = get_user_by_id( target_user_id )
        if not target_user:
            return False, "User not found", None

        # Update status
        cursor.execute(
            """
            UPDATE users
            SET is_active = ?
            WHERE id = ?
            """,
            ( 1 if is_active else 0, target_user_id )
        )
        conn.commit()

        # Revoke all tokens if deactivating
        if not is_active:
            revoke_all_user_tokens( target_user_id )

        # Log to audit
        status_text = "activated" if is_active else "deactivated"
        log_auth_event(
            event_type  = "admin_status_update",
            user_id     = admin_user_id,
            email       = admin_email,
            ip_address  = admin_ip,
            details     = f"User {target_user['email']} {status_text}",
            success     = True
        )

        # Get updated user
        updated_user = get_user_by_id( target_user_id )

        message = f"User {status_text} successfully"
        return True, message, updated_user

    except Exception as e:
        conn.rollback()
        return False, f"Status update failed: {e}", None

    finally:
        conn.close()


def admin_reset_password(
    admin_user_id: str,
    target_user_id: str,
    admin_email: str = "unknown",
    admin_ip: str = "unknown",
    reason: str = ""
) -> Tuple[bool, str, Optional[str]]:
    """
    Generate temporary password for user (admin password reset).

    Requires:
        - admin_user_id is valid UUID of admin performing action
        - target_user_id is valid UUID of user being reset
        - reason is optional audit note

    Ensures:
        - Generates crypto-secure 16-character password
        - Password meets strength requirements
        - Password is hashed and stored
        - Password is returned ONCE (not stored plain)
        - Logs action to audit trail
        - Returns (success, message, temp_password)

    Raises:
        - None (returns error in tuple)

    Returns:
        Tuple[bool, str, Optional[str]]: (success, message, temporary_password)

    Example:
        success, msg, temp_pw = admin_reset_password(
            admin_user_id = "admin-uuid",
            target_user_id = "user-uuid",
            admin_email = "admin@example.com",
            admin_ip = "192.168.1.1",
            reason = "User forgot password, email unavailable"
        )
        if success:
            print( f"Temporary password: {temp_pw}" )
    """
    # Get target user
    target_user = get_user_by_id( target_user_id )
    if not target_user:
        return False, "User not found", None

    # Generate crypto-secure temporary password
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    temp_password = ''.join( secrets.choice( alphabet ) for _ in range( 16 ) )

    # Validate password meets strength requirements
    is_valid, error_msg = validate_password_strength( temp_password )
    if not is_valid:
        # Retry with longer password if validation fails
        temp_password = ''.join( secrets.choice( alphabet ) for _ in range( 20 ) )
        is_valid, error_msg = validate_password_strength( temp_password )
        if not is_valid:
            return False, f"Failed to generate valid password: {error_msg}", None

    # Hash password
    try:
        password_hash = hash_password( temp_password )
    except Exception as e:
        return False, f"Password hashing failed: {e}", None

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    try:
        # Update password
        cursor.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ?
            """,
            ( password_hash, target_user_id )
        )
        conn.commit()

        # Log to audit
        audit_details = f"Admin password reset for {target_user['email']}"
        if reason:
            audit_details += f" - Reason: {reason}"

        log_auth_event(
            event_type  = "admin_password_reset",
            user_id     = admin_user_id,
            email       = admin_email,
            ip_address  = admin_ip,
            details     = audit_details,
            success     = True
        )

        return True, "Password reset successfully", temp_password

    except Exception as e:
        conn.rollback()
        return False, f"Password reset failed: {e}", None

    finally:
        conn.close()
