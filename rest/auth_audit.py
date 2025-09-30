"""
Authentication Audit Logging for Lupin (Phase 8).

Provides security event logging for:
- Login successes and failures
- Registration events
- Password changes
- Email verification
- Token operations
- Other authentication events
"""

from datetime import datetime
from typing import Optional
from cosa.rest.auth_database import get_auth_db_connection


def log_auth_event(
    event_type: str,
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    ip_address: Optional[str] = None,
    details: Optional[str] = None,
    success: bool = True
) -> None:
    """
    Log authentication event to audit log.

    Requires:
        - event_type is a non-empty string
        - Database connection available

    Ensures:
        - Event logged with timestamp
        - All provided fields stored
        - Success/failure status recorded

    Raises:
        - None (catches all exceptions)

    Event Types:
        - login_success: Successful login
        - login_failure: Failed login attempt
        - logout: User logout
        - register: User registration
        - password_change: Password updated
        - password_reset_request: Password reset requested
        - password_reset_complete: Password reset completed
        - email_verify_request: Email verification requested
        - email_verify_complete: Email verified
        - token_refresh: Refresh token used
        - token_revoke: Token revoked
        - account_lockout: Account locked due to failed attempts
        - account_unlock: Account unlocked

    Example:
        log_auth_event(
            event_type  = "login_success",
            user_id     = "user123",
            email       = "user@example.com",
            ip_address  = "192.168.1.1",
            details     = "Login via web interface",
            success     = True
        )
    """
    try:
        conn = get_auth_db_connection()
        cursor = conn.cursor()

        event_time = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO auth_audit_log (
                event_type,
                user_id,
                email,
                ip_address,
                details,
                success,
                event_time
            )
            VALUES ( ?, ?, ?, ?, ?, ?, ? )
            """,
            (
                event_type,
                user_id,
                email,
                ip_address,
                details,
                1 if success else 0,
                event_time
            )
        )

        conn.commit()
        conn.close()

    except Exception as e:
        print( f"Failed to log auth event: {str( e )}" )


def get_user_audit_log( user_id: str, limit: int = 50 ) -> list:
    """
    Get audit log entries for specific user.

    Requires:
        - user_id is a non-empty string
        - limit is a positive integer
        - Database connection available

    Ensures:
        - Returns list of audit log entries
        - Sorted by most recent first
        - Limited to specified number of entries

    Returns:
        list: List of audit log entry dicts

    Example:
        entries = get_user_audit_log( "user123", limit=20 )
        for entry in entries:
            print( f"{entry['event_time']}: {entry['event_type']}" )
    """
    try:
        conn = get_auth_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                event_type,
                user_id,
                email,
                ip_address,
                details,
                success,
                event_time
            FROM auth_audit_log
            WHERE user_id = ?
            ORDER BY event_time DESC
            LIMIT ?
            """,
            (user_id, limit)
        )

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "event_type"  : row[0],
                "user_id"     : row[1],
                "email"       : row[2],
                "ip_address"  : row[3],
                "details"     : row[4],
                "success"     : bool( row[5] ),
                "event_time"  : row[6]
            }
            for row in rows
        ]

    except Exception as e:
        print( f"Failed to get user audit log: {str( e )}" )
        return []


def get_failed_logins( email: Optional[str] = None, limit: int = 50 ) -> list:
    """
    Get failed login attempts.

    Requires:
        - limit is a positive integer
        - Database connection available

    Ensures:
        - Returns list of failed login events
        - Filtered by email if provided
        - Sorted by most recent first
        - Limited to specified number of entries

    Returns:
        list: List of failed login entry dicts

    Example:
        failures = get_failed_logins( "user@example.com", limit=10 )
        for failure in failures:
            print( f"{failure['event_time']}: {failure['ip_address']}" )
    """
    try:
        conn = get_auth_db_connection()
        cursor = conn.cursor()

        if email:
            cursor.execute(
                """
                SELECT
                    event_type,
                    user_id,
                    email,
                    ip_address,
                    details,
                    success,
                    event_time
                FROM auth_audit_log
                WHERE event_type = 'login_failure' AND email = ?
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (email, limit)
            )
        else:
            cursor.execute(
                """
                SELECT
                    event_type,
                    user_id,
                    email,
                    ip_address,
                    details,
                    success,
                    event_time
                FROM auth_audit_log
                WHERE event_type = 'login_failure'
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (limit,)
            )

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "event_type"  : row[0],
                "user_id"     : row[1],
                "email"       : row[2],
                "ip_address"  : row[3],
                "details"     : row[4],
                "success"     : bool( row[5] ),
                "event_time"  : row[6]
            }
            for row in rows
        ]

    except Exception as e:
        print( f"Failed to get failed logins: {str( e )}" )
        return []


def get_suspicious_activity( hours: int = 24, threshold: int = 5 ) -> list:
    """
    Get accounts with suspicious activity (multiple failed logins).

    Requires:
        - hours is a positive integer
        - threshold is a positive integer
        - Database connection available

    Ensures:
        - Returns list of emails with suspicious activity
        - Counted within specified time window
        - Only includes accounts exceeding threshold

    Returns:
        list: List of tuples (email, failure_count)

    Example:
        suspicious = get_suspicious_activity( hours=24, threshold=5 )
        for email, count in suspicious:
            print( f"{email}: {count} failed attempts" )
    """
    try:
        from datetime import timedelta

        conn = get_auth_db_connection()
        cursor = conn.cursor()

        window_start = (datetime.utcnow() - timedelta( hours=hours )).isoformat()

        cursor.execute(
            """
            SELECT email, COUNT(*) as failure_count
            FROM auth_audit_log
            WHERE event_type = 'login_failure'
                AND event_time >= ?
                AND email IS NOT NULL
            GROUP BY email
            HAVING failure_count >= ?
            ORDER BY failure_count DESC
            """,
            (window_start, threshold)
        )

        rows = cursor.fetchall()
        conn.close()

        return [(row[0], row[1]) for row in rows]

    except Exception as e:
        print( f"Failed to get suspicious activity: {str( e )}" )
        return []


def quick_smoke_test():
    """Quick smoke test for auth audit logging."""
    import cosa.utils.util as du
    from cosa.rest.auth_database import init_auth_database
    from cosa.rest.user_service import create_user

    du.print_banner( "Auth Audit Smoke Test", prepend_nl=True )

    try:
        print( "Initializing database..." )
        init_auth_database()
        print( "✓ Database initialized" )

        # Create test user
        success, msg, user_id = create_user( "audit_test@example.com", "TestPass123!" )
        if not success:
            print( f"✗ Failed to create user: {msg}" )
            return False
        print( "✓ Test user created" )

        # Test logging various events
        print( "Testing event logging..." )
        log_auth_event( "login_success", user_id, "audit_test@example.com", "192.168.1.1", "Test login", True )
        log_auth_event( "login_failure", None, "bad@example.com", "192.168.1.2", "Wrong password", False )
        log_auth_event( "register", user_id, "audit_test@example.com", "192.168.1.1", "New user", True )
        print( "✓ Events logged" )

        # Test get user audit log
        print( "Testing get user audit log..." )
        entries = get_user_audit_log( user_id, limit=10 )
        if len( entries ) >= 2:
            print( f"✓ Retrieved {len( entries )} audit entries" )
        else:
            print( f"✗ Expected at least 2 entries, got {len( entries )}" )
            return False

        # Test get failed logins
        print( "Testing get failed logins..." )
        failures = get_failed_logins( "bad@example.com", limit=10 )
        if len( failures ) >= 1:
            print( f"✓ Retrieved {len( failures )} failed login(s)" )
        else:
            print( "✗ Expected at least 1 failed login" )
            return False

        print( "\n✓ All auth audit tests passed!" )
        return True

    except Exception as e:
        print( f"✗ Auth audit test failed: {e}" )
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    quick_smoke_test()