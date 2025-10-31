#!/usr/bin/env python3
"""
Notifications Database Access Layer.

Provides Python interface for CRUD operations on the lupin-notifications.db database.
Phase 2.0 Foundation - Week 1

Database Schema: src/scripts/create_notifications_table.py
Design Reference: src/rnd/sse-notifications/05-phase2-design-decisions.md
"""

import sqlite3
import sys
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

# Bootstrap: Use LUPIN_ROOT environment variable for standalone execution
lupin_root = os.environ.get( 'LUPIN_ROOT' )
if lupin_root is None:
    raise RuntimeError(
        "LUPIN_ROOT environment variable not set.\n"
        "Set it before running:\n"
        "  export LUPIN_ROOT=/path/to/project\n"
        "  python -m cosa.rest.notifications_database"
    )

src_path = os.path.join( lupin_root, 'src' )
if src_path not in sys.path:
    sys.path.insert( 0, src_path )

# Now cosa is importable
import cosa.utils.util as cu


class NotificationsDatabase:
    """
    Database access layer for notifications system.

    Provides CRUD operations and state management for lupin-notifications.db.
    """

    def __init__( self, db_path: Optional[str] = None, debug: bool = False ):
        """
        Initialize NotificationsDatabase.

        Requires:
            - db_path: Optional database path (defaults to canonical path)
            - debug: Enable debug output

        Ensures:
            - Database connection ready for operations
        """
        self.debug           = debug
        self.db_path         = db_path or ( cu.get_project_root() + "/src/conf/long-term-memory/lupin-notifications.db" )

        if self.debug: print( f"NotificationsDatabase initialized: {self.db_path}" )

        # Verify database exists
        if not os.path.exists( self.db_path ):
            raise FileNotFoundError(
                f"Notifications database not found: {self.db_path}\n"
                "Run: python src/scripts/create_notifications_table.py"
            )


    def _get_connection( self ) -> sqlite3.Connection:
        """
        Get database connection.

        Ensures:
            - Returns active SQLite connection
        """
        conn = sqlite3.connect( self.db_path )
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        return conn


    def create_notification(
        self,
        sender_id: str,
        recipient_id: str,
        title: str,
        message: str,
        type: str = "task",
        priority: str = "medium",
        source_context: str = "internal",
        source_sender: Optional[str] = None,
        response_requested: bool = False,
        response_type: Optional[str] = None,
        response_default: Optional[str] = None,
        timeout_seconds: Optional[int] = None
    ) -> str:
        """
        Create a new notification record.

        Requires:
            - sender_id: Email-style sender ID
            - recipient_id: User UUID from auth database
            - title: Terse, technical notification title
            - message: TTS-friendly prose message
            - type: task, progress, alert, custom
            - priority: urgent, high, medium, low

        Ensures:
            - Returns notification UUID
            - Record inserted with state='created'

        Raises:
            - sqlite3.Error on database failure
        """
        notification_id = str( uuid.uuid4() )
        created_at      = datetime.utcnow().isoformat()

        # Calculate expiration if response required
        expires_at = None
        if response_requested and timeout_seconds:
            from datetime import timedelta
            expires_at = ( datetime.utcnow() + timedelta( seconds=timeout_seconds ) ).isoformat()

        conn   = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute( """
                INSERT INTO notifications (
                    id, sender_id, recipient_id, title, message, type, priority,
                    source_context, source_sender,
                    created_at, state,
                    response_requested, response_type, response_default, timeout_seconds, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                notification_id, sender_id, recipient_id, title, message, type, priority,
                source_context, source_sender or sender_id,
                created_at, "created",
                1 if response_requested else 0, response_type, response_default, timeout_seconds, expires_at
            ) )

            conn.commit()

            if self.debug: print( f"Created notification: {notification_id[:8]}... ({title})" )

            return notification_id

        finally:
            conn.close()


    def get_notification( self, notification_id: str ) -> Optional[Dict[str, Any]]:
        """
        Retrieve notification by ID.

        Requires:
            - notification_id: UUID of notification

        Ensures:
            - Returns dict with all fields, or None if not found
        """
        conn   = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute( "SELECT * FROM notifications WHERE id = ?", ( notification_id, ) )
            row = cursor.fetchone()

            if row:
                return dict( row )

            return None

        finally:
            conn.close()


    def get_notifications_by_recipient(
        self,
        recipient_id: str,
        state: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query notifications by recipient and optional state filter.

        Requires:
            - recipient_id: User UUID
            - state: Optional state filter (created, delivered, responded, expired, deleted)
            - limit: Optional result limit

        Ensures:
            - Returns list of notification dicts (newest first)
        """
        conn   = self._get_connection()
        cursor = conn.cursor()

        try:
            if state:
                query = "SELECT * FROM notifications WHERE recipient_id = ? AND state = ? ORDER BY created_at DESC"
                params = ( recipient_id, state )
            else:
                query = "SELECT * FROM notifications WHERE recipient_id = ? ORDER BY created_at DESC"
                params = ( recipient_id, )

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute( query, params )
            rows = cursor.fetchall()

            return [ dict( row ) for row in rows ]

        finally:
            conn.close()


    def get_expired_notifications( self ) -> List[Dict[str, Any]]:
        """
        Query notifications past their expiration time.

        Ensures:
            - Returns list of expired notifications (state='delivered', expires_at < now)
        """
        conn   = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.utcnow().isoformat()

            cursor.execute( """
                SELECT * FROM notifications
                WHERE state = 'delivered'
                  AND expires_at IS NOT NULL
                  AND expires_at < ?
                ORDER BY expires_at ASC
            """, ( now, ) )

            rows = cursor.fetchall()

            return [ dict( row ) for row in rows ]

        finally:
            conn.close()


    def update_state(
        self,
        notification_id: str,
        new_state: str,
        delivered_at: Optional[str] = None,
        responded_at: Optional[str] = None
    ) -> bool:
        """
        Update notification state (state machine transition).

        Requires:
            - notification_id: UUID of notification
            - new_state: created, delivered, responded, expired, deleted
            - delivered_at: ISO timestamp (for created → delivered transition)
            - responded_at: ISO timestamp (for delivered → responded transition)

        Ensures:
            - Returns True if update succeeded, False if notification not found

        Raises:
            - sqlite3.Error on database failure
        """
        conn   = self._get_connection()
        cursor = conn.cursor()

        try:
            # Build dynamic update query based on provided timestamps
            updates = [ "state = ?" ]
            params  = [ new_state ]

            if delivered_at:
                updates.append( "delivered_at = ?" )
                params.append( delivered_at )

            if responded_at:
                updates.append( "responded_at = ?" )
                params.append( responded_at )

            params.append( notification_id )

            query = f"UPDATE notifications SET {', '.join( updates )} WHERE id = ?"

            cursor.execute( query, tuple( params ) )
            conn.commit()

            updated = cursor.rowcount > 0

            if self.debug: print( f"Updated notification {notification_id[:8]}... state → {new_state}" )

            return updated

        finally:
            conn.close()


    def update_response(
        self,
        notification_id: str,
        response_value: str,
        responded_at: Optional[str] = None
    ) -> bool:
        """
        Record user response to notification.

        Requires:
            - notification_id: UUID of notification
            - response_value: JSON string (e.g., '{"answer": "yes", "method": "button_click"}')
            - responded_at: Optional timestamp (defaults to now)

        Ensures:
            - Returns True if update succeeded
            - Sets state='responded', response_value, responded_at
        """
        conn   = self._get_connection()
        cursor = conn.cursor()

        try:
            timestamp = responded_at or datetime.utcnow().isoformat()

            cursor.execute( """
                UPDATE notifications
                SET state = 'responded', response_value = ?, responded_at = ?
                WHERE id = ?
            """, ( response_value, timestamp, notification_id ) )

            conn.commit()

            updated = cursor.rowcount > 0

            if self.debug: print( f"Recorded response for {notification_id[:8]}..." )

            return updated

        finally:
            conn.close()


    def soft_delete( self, notification_id: str ) -> bool:
        """
        Soft delete notification (set state='deleted', keep row).

        Requires:
            - notification_id: UUID of notification

        Ensures:
            - Returns True if delete succeeded
            - Sets state='deleted', deleted_at timestamp
            - Row preserved for audit trail
        """
        conn   = self._get_connection()
        cursor = conn.cursor()

        try:
            deleted_at = datetime.utcnow().isoformat()

            cursor.execute( """
                UPDATE notifications
                SET state = 'deleted', deleted_at = ?
                WHERE id = ?
            """, ( deleted_at, notification_id ) )

            conn.commit()

            deleted = cursor.rowcount > 0

            if self.debug: print( f"Soft deleted notification {notification_id[:8]}..." )

            return deleted

        finally:
            conn.close()


def quick_smoke_test():
    """
    Quick smoke test for NotificationsDatabase - validates basic functionality.

    Tests:
    1. Database connection and module instantiation
    2. CRUD workflow (create → read → update → delete)
    3. State transitions (created → delivered → responded)
    4. LLM interpretation helper (Phase 2.1 placeholder)
    """
    cu.print_banner( "NotificationsDatabase Smoke Test", prepend_nl=True )

    try:
        # Test 1: Database connection and module instantiation
        print( "Test 1: Instantiating NotificationsDatabase..." )
        db = NotificationsDatabase( debug=False )
        print( f"✓ Database connected: {db.db_path}" )

        # Test 2: CRUD workflow
        print( "\nTest 2: Testing CRUD workflow..." )

        # CREATE
        notification_id = db.create_notification(
            sender_id      = "smoke.test@deepily.ai",
            recipient_id   = "test_user_smoke",
            title          = "Smoke Test Notification",
            message        = "This is a smoke test notification for Phase 2.0",
            type           = "task",
            priority       = "low"
        )
        print( f"✓ CREATE: Notification created (id: {notification_id[:8]}...)" )

        # READ
        notification = db.get_notification( notification_id )
        if not notification:
            raise AssertionError( "Failed to read created notification" )
        if notification["title"] != "Smoke Test Notification":
            raise AssertionError( f"Title mismatch: {notification['title']}" )
        print( f"✓ READ: Notification retrieved (title: {notification['title']})" )

        # UPDATE
        success = db.update_state(
            notification_id,
            "delivered",
            delivered_at = datetime.utcnow().isoformat()
        )
        if not success:
            raise AssertionError( "Failed to update notification state" )

        updated = db.get_notification( notification_id )
        if updated["state"] != "delivered":
            raise AssertionError( f"State update failed: expected 'delivered', got '{updated['state']}'" )
        print( "✓ UPDATE: State transitioned (created → delivered)" )

        # DELETE (soft delete)
        success = db.soft_delete( notification_id )
        if not success:
            raise AssertionError( "Failed to soft delete notification" )

        deleted = db.get_notification( notification_id )
        if deleted["state"] != "deleted":
            raise AssertionError( f"Soft delete failed: expected 'deleted', got '{deleted['state']}'" )
        print( "✓ DELETE: Soft delete successful (state = deleted)" )

        # Cleanup: Hard delete test notification
        conn   = db._get_connection()
        cursor = conn.cursor()
        cursor.execute( "DELETE FROM notifications WHERE id = ?", ( notification_id, ) )
        conn.commit()
        conn.close()
        print( "✓ Cleanup: Test notification removed" )

        # Test 3: State transition workflow
        print( "\nTest 3: Testing state transition workflow..." )

        notification_id_2 = db.create_notification(
            sender_id          = "smoke.test@deepily.ai",
            recipient_id       = "test_user_smoke",
            title              = "Response Required Test",
            message            = "Do you want to continue?",
            type               = "alert",
            priority           = "high",
            response_requested = True,
            response_type      = "yes_no",
            timeout_seconds    = 120
        )
        print( "✓ Created response-required notification" )

        # Transition: created → delivered
        db.update_state(
            notification_id_2,
            "delivered",
            delivered_at = datetime.utcnow().isoformat()
        )
        print( "✓ Transitioned: created → delivered" )

        # Transition: delivered → responded
        db.update_response(
            notification_id_2,
            '{"answer": "yes", "method": "smoke_test", "confidence": "high"}'
        )

        final = db.get_notification( notification_id_2 )
        if final["state"] != "responded":
            raise AssertionError( f"Final state incorrect: expected 'responded', got '{final['state']}'" )
        print( "✓ Transitioned: delivered → responded" )
        print( f"✓ Final state verified: {final['state']}" )

        # Cleanup
        conn   = db._get_connection()
        cursor = conn.cursor()
        cursor.execute( "DELETE FROM notifications WHERE id = ?", ( notification_id_2, ) )
        conn.commit()
        conn.close()
        print( "✓ Cleanup: Test notification removed" )

        # Test 4: LLM interpretation helper (placeholder for Phase 2.1)
        print( "\nTest 4: LLM interpretation helper..." )
        print( "⊘ SKIPPED: LLM interpretation helper not implemented until Phase 2.1" )
        print( "  (Will test: 'sure' → 'yes', 'nope' → 'no', etc.)" )

        print( "\n" + "="*60 )
        print( "✓ Smoke test completed successfully" )
        print( "="*60 )

        return 0

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit( quick_smoke_test() )
