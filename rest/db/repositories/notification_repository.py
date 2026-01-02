"""
Notification repository for CRUD operations on Notification model.

Provides notification-specific methods beyond base repository functionality,
including sender-based grouping and activity-anchored window loading.
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case

from cosa.rest.postgres_models import Notification
from cosa.rest.db.repositories.base import BaseRepository


class NotificationRepository( BaseRepository[Notification] ):
    """
    Repository for Notification model with sender-aware operations.

    Extends BaseRepository with notification-specific methods:
        - Sender-based grouping for multi-project views
        - Activity-anchored window loading
        - State management
        - Response tracking
    """

    def __init__( self, session: Session ):
        """
        Initialize NotificationRepository with session.

        Requires:
            - session: Active SQLAlchemy session (from get_db())

        Example:
            with get_db() as session:
                notif_repo = NotificationRepository( session )
                notif = notif_repo.create_notification(...)
        """
        super().__init__( Notification, session )

    def create_notification(
        self,
        sender_id: str,
        recipient_id: uuid.UUID,
        message: str,
        type: str,
        priority: str,
        title: Optional[str] = None,
        response_requested: bool = False,
        response_type: Optional[str] = None,
        response_default: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        expires_at: Optional[datetime] = None
    ) -> Notification:
        """
        Create new notification.

        Requires:
            - sender_id: Sender identifier (e.g., claude.code@lupin.deepily.ai)
            - recipient_id: Valid user UUID
            - message: Notification message text
            - type: Notification type (task, progress, alert, custom)
            - priority: Priority level (urgent, high, medium, low)

        Ensures:
            - Notification created with 'created' state
            - created_at set to current timestamp
            - Response fields populated if response_requested

        Returns:
            Created Notification instance

        Example:
            with get_db() as session:
                repo = NotificationRepository( session )
                notif = repo.create_notification(
                    sender_id    = "claude.code@lupin.deepily.ai",
                    recipient_id = user.id,
                    message      = "[LUPIN] Build completed",
                    type         = "task",
                    priority     = "medium"
                )
        """
        return self.create(
            sender_id          = sender_id,
            recipient_id       = recipient_id,
            message            = message,
            type               = type,
            priority           = priority,
            title              = title,
            response_requested = response_requested,
            response_type      = response_type,
            response_default   = response_default,
            timeout_seconds    = timeout_seconds,
            expires_at         = expires_at,
            state              = "created"
        )

    def get_by_recipient( self, recipient_id: uuid.UUID, limit: int = 100, offset: int = 0 ) -> List[Notification]:
        """
        Get notifications for a recipient.

        Requires:
            - recipient_id: Valid user UUID

        Ensures:
            - Returns notifications ordered by created_at descending
            - Applies pagination

        Returns:
            List of Notification instances
        """
        return self.session.query( Notification ).filter(
            Notification.recipient_id == recipient_id
        ).order_by(
            desc( Notification.created_at )
        ).limit( limit ).offset( offset ).all()

    def get_sender_last_activities( self, recipient_id: uuid.UUID ) -> List[Dict]:
        """
        Get last activity timestamp per sender for a recipient.

        Requires:
            - recipient_id: Valid user UUID

        Ensures:
            - Returns list of {sender_id, last_activity, notification_count}
            - Ordered by last_activity descending (most recent first)
            - Used for activity-anchored window loading

        Returns:
            List of sender activity summaries

        Example:
            activities = repo.get_sender_last_activities( user.id )
            # [
            #   {"sender_id": "claude.code@lupin.deepily.ai", "last_activity": datetime(...), "count": 5},
            #   {"sender_id": "claude.code@cosa.deepily.ai", "last_activity": datetime(...), "count": 2}
            # ]
        """
        results = self.session.query(
            Notification.sender_id,
            func.max( Notification.created_at ).label( 'last_activity' ),
            func.count( Notification.id ).label( 'notification_count' )
        ).filter(
            Notification.recipient_id == recipient_id
        ).group_by(
            Notification.sender_id
        ).order_by(
            desc( 'last_activity' )
        ).all()

        return [
            {
                "sender_id"     : row.sender_id,
                "last_activity" : row.last_activity,
                "count"         : row.notification_count
            }
            for row in results
        ]

    def get_sender_conversation(
        self,
        sender_id: str,
        recipient_id: uuid.UUID,
        anchor: Optional[datetime] = None,
        window_hours: int = 24
    ) -> List[Notification]:
        """
        Load conversation window relative to anchor (activity-anchored loading).

        Requires:
            - sender_id: Sender identifier
            - recipient_id: Valid user UUID
            - anchor: Reference timestamp (defaults to sender's last activity)
            - window_hours: Hours before anchor to include (default: 24)

        Ensures:
            - Returns notifications within [anchor - window_hours, anchor]
            - Ordered by created_at ascending (oldest first for insertBefore prepend)
            - If anchor is None, uses sender's last activity as anchor

        Returns:
            List of Notification instances in chronological order (oldest first)

        Example:
            # Load last 24 hours relative to sender's last activity
            messages = repo.get_sender_conversation(
                sender_id    = "claude.code@lupin.deepily.ai",
                recipient_id = user.id,
                window_hours = 24
            )
        """
        # If no anchor provided, find sender's last activity
        if anchor is None:
            last_activity = self.session.query(
                func.max( Notification.created_at )
            ).filter(
                Notification.sender_id == sender_id,
                Notification.recipient_id == recipient_id
            ).scalar()

            if last_activity is None:
                return []  # No notifications from this sender

            anchor = last_activity

        # Calculate window start
        window_start = anchor - timedelta( hours=window_hours )

        return self.session.query( Notification ).filter(
            Notification.sender_id == sender_id,
            Notification.recipient_id == recipient_id,
            Notification.created_at >= window_start,
            Notification.created_at <= anchor
        ).order_by(
            Notification.created_at.asc()  # Oldest first - insertBefore prepends newest to top
        ).all()

    def update_state( self, notification_id: uuid.UUID, new_state: str ) -> Optional[Notification]:
        """
        Update notification state.

        Requires:
            - notification_id: Valid notification UUID
            - new_state: Target state (created, queued, delivered, responded, expired, error)

        Ensures:
            - State updated
            - Appropriate timestamp updated based on state transition

        Returns:
            Updated Notification instance or None if not found
        """
        notification = self.get_by_id( notification_id )
        if not notification:
            return None

        notification.state = new_state

        # Update appropriate timestamp based on state
        now = datetime.utcnow()
        if new_state == "delivered":
            notification.delivered_at = now
        elif new_state == "responded":
            notification.responded_at = now

        self.session.flush()
        return notification

    def update_response( self, notification_id: uuid.UUID, response_value: dict ) -> Optional[Notification]:
        """
        Record user response to notification.

        Requires:
            - notification_id: Valid notification UUID
            - response_value: Response data (flexible JSONB storage)

        Ensures:
            - response_value stored
            - responded_at timestamp set
            - state updated to 'responded'

        Returns:
            Updated Notification instance or None if not found

        Example:
            repo.update_response(
                notification_id = notif.id,
                response_value  = {"value": "yes", "source": "ui_button"}
            )
        """
        notification = self.get_by_id( notification_id )
        if not notification:
            return None

        notification.response_value = response_value
        notification.responded_at = datetime.utcnow()
        notification.state = "responded"

        self.session.flush()
        return notification

    def get_pending_for_recipient( self, recipient_id: uuid.UUID ) -> List[Notification]:
        """
        Get pending (unresponded) notifications requiring response.

        Requires:
            - recipient_id: Valid user UUID

        Ensures:
            - Returns notifications where response_requested = True
            - Excludes already responded or expired
            - Ordered by created_at ascending (oldest first)

        Returns:
            List of pending Notification instances
        """
        return self.session.query( Notification ).filter(
            Notification.recipient_id == recipient_id,
            Notification.response_requested == True,
            Notification.state.in_( ['created', 'queued', 'delivered'] )
        ).order_by(
            Notification.created_at.asc()
        ).all()

    def mark_expired( self, notification_id: uuid.UUID ) -> Optional[Notification]:
        """
        Mark notification as expired (timeout reached).

        Requires:
            - notification_id: Valid notification UUID

        Ensures:
            - state set to 'expired'
            - Can optionally apply response_default if configured

        Returns:
            Updated Notification instance or None if not found
        """
        notification = self.get_by_id( notification_id )
        if not notification:
            return None

        notification.state = "expired"

        # If default response was configured, apply it
        if notification.response_default:
            notification.response_value = {"value": notification.response_default, "source": "timeout_default"}

        self.session.flush()
        return notification

    def count_by_sender( self, recipient_id: uuid.UUID ) -> Dict[str, int]:
        """
        Count notifications grouped by sender.

        Requires:
            - recipient_id: Valid user UUID

        Ensures:
            - Returns dict of sender_id -> count

        Returns:
            Dictionary mapping sender IDs to notification counts
        """
        results = self.session.query(
            Notification.sender_id,
            func.count( Notification.id ).label( 'count' )
        ).filter(
            Notification.recipient_id == recipient_id
        ).group_by(
            Notification.sender_id
        ).all()

        return { row.sender_id: row.count for row in results }

    def delete_by_sender( self, sender_id: str, recipient_id: uuid.UUID ) -> int:
        """
        Delete all notifications from a sender for a recipient.

        Requires:
            - sender_id: Sender identifier (e.g., claude.code@lupin.deepily.ai)
            - recipient_id: Valid user UUID

        Ensures:
            - All notifications matching sender_id AND recipient_id deleted
            - Returns count of deleted notifications

        Returns:
            Number of notifications deleted

        Example:
            with get_db() as session:
                repo = NotificationRepository( session )
                count = repo.delete_by_sender(
                    sender_id    = "claude.code@lupin.deepily.ai",
                    recipient_id = user.id
                )
                print( f"Deleted {count} notifications" )
        """
        deleted = self.session.query( Notification ).filter(
            Notification.sender_id == sender_id,
            Notification.recipient_id == recipient_id
        ).delete()

        self.session.flush()
        return deleted

    def get_sender_conversations_by_date(
        self,
        sender_id: str,
        recipient_id: uuid.UUID,
        anchor: Optional[datetime] = None,
        window_hours: int = 168,  # Default 7 days
        include_hidden: bool = False,
        timezone_name: str = "America/New_York"
    ) -> Dict[str, List[Notification]]:
        """
        Load conversation grouped by date (ISO format).

        Requires:
            - sender_id: Sender identifier
            - recipient_id: Valid user UUID
            - anchor: Reference timestamp (defaults to sender's last activity)
            - window_hours: Hours before anchor to include (default: 168 = 7 days)
            - include_hidden: Whether to include hidden notifications (default: False)
            - timezone_name: IANA timezone for date grouping (default: America/New_York)

        Ensures:
            - Returns dict of date_string -> list of notifications
            - Date keys sorted descending (newest first: 2025-01-02, 2025-01-01, ...)
            - Each date key is ISO format (YYYY-MM-DD) in specified timezone
            - Notifications within each date ordered by created_at ascending

        Returns:
            Dict mapping date strings to notification lists

        Example:
            conversations = repo.get_sender_conversations_by_date(
                sender_id    = "claude.code@lupin.deepily.ai",
                recipient_id = user.id,
                window_hours = 168  # 7 days
            )
            # {"2025-01-01": [notif1, notif2], "2024-12-31": [notif3]}
        """
        import zoneinfo

        # If no anchor provided, find sender's last activity
        if anchor is None:
            last_activity = self.session.query(
                func.max( Notification.created_at )
            ).filter(
                Notification.sender_id == sender_id,
                Notification.recipient_id == recipient_id
            ).scalar()

            if last_activity is None:
                return {}  # No notifications from this sender

            anchor = last_activity

        # Calculate window start
        window_start = anchor - timedelta( hours=window_hours )

        # Build query
        query = self.session.query( Notification ).filter(
            Notification.sender_id == sender_id,
            Notification.recipient_id == recipient_id,
            Notification.created_at >= window_start,
            Notification.created_at <= anchor
        )

        # Filter hidden unless explicitly requested
        if not include_hidden:
            query = query.filter( Notification.is_hidden == False )

        notifications = query.order_by( Notification.created_at.asc() ).all()

        # Group by date in specified timezone
        try:
            tz = zoneinfo.ZoneInfo( timezone_name )
        except Exception:
            tz = zoneinfo.ZoneInfo( "America/New_York" )  # Fallback

        date_groups: Dict[str, List[Notification]] = {}
        for notif in notifications:
            # Convert to local timezone and extract date
            local_time = notif.created_at.astimezone( tz )
            date_key = local_time.strftime( "%Y-%m-%d" )

            if date_key not in date_groups:
                date_groups[ date_key ] = []
            date_groups[ date_key ].append( notif )

        # Sort dates descending (newest first)
        return dict( sorted( date_groups.items(), reverse=True ) )

    def soft_delete_by_date(
        self,
        sender_id: str,
        recipient_id: uuid.UUID,
        date_string: str,
        timezone_name: str = "America/New_York"
    ) -> int:
        """
        Soft delete all notifications for a sender on a specific date.

        Requires:
            - sender_id: Sender identifier (e.g., claude.code@lupin.deepily.ai)
            - recipient_id: Valid user UUID
            - date_string: ISO format date (YYYY-MM-DD)
            - timezone_name: IANA timezone for date interpretation

        Ensures:
            - Sets is_hidden=True for all matching notifications
            - Uses timezone-aware date boundaries
            - Returns count of hidden notifications

        Returns:
            Number of notifications hidden

        Example:
            with get_db() as session:
                repo = NotificationRepository( session )
                count = repo.soft_delete_by_date(
                    sender_id    = "claude.code@lupin.deepily.ai",
                    recipient_id = user.id,
                    date_string  = "2025-01-01"
                )
                print( f"Hidden {count} notifications" )
        """
        import zoneinfo
        from datetime import date

        try:
            tz = zoneinfo.ZoneInfo( timezone_name )
        except Exception:
            tz = zoneinfo.ZoneInfo( "America/New_York" )  # Fallback

        # Parse date string and create timezone-aware boundaries
        target_date = date.fromisoformat( date_string )
        day_start = datetime( target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=tz )
        day_end = datetime( target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=tz )

        # Update matching notifications to hidden
        updated = self.session.query( Notification ).filter(
            Notification.sender_id == sender_id,
            Notification.recipient_id == recipient_id,
            Notification.created_at >= day_start,
            Notification.created_at <= day_end,
            Notification.is_hidden == False  # Only hide visible ones
        ).update( { "is_hidden": True }, synchronize_session="fetch" )

        self.session.flush()
        return updated

    def get_sender_date_summaries(
        self,
        sender_id: str,
        recipient_id: uuid.UUID,
        include_hidden: bool = False,
        timezone_name: str = "America/New_York"
    ) -> List[Dict]:
        """
        Get date-grouped summaries for a sender with counts.

        Requires:
            - sender_id: Sender identifier
            - recipient_id: Valid user UUID
            - include_hidden: Whether to include hidden notifications
            - timezone_name: IANA timezone for date grouping

        Ensures:
            - Returns list of date summaries ordered by date descending
            - Each summary includes date, count, and new_count

        Returns:
            List of date summary dicts

        Example:
            summaries = repo.get_sender_date_summaries(
                sender_id    = "claude.code@lupin.deepily.ai",
                recipient_id = user.id
            )
            # [{"date": "2025-01-01", "count": 5, "new_count": 2}, ...]
        """
        import zoneinfo

        try:
            tz = zoneinfo.ZoneInfo( timezone_name )
        except Exception:
            tz = zoneinfo.ZoneInfo( "America/New_York" )  # Fallback

        # Build query
        query = self.session.query( Notification ).filter(
            Notification.sender_id == sender_id,
            Notification.recipient_id == recipient_id
        )

        if not include_hidden:
            query = query.filter( Notification.is_hidden == False )

        notifications = query.order_by( Notification.created_at.desc() ).all()

        # Group by date and calculate counts
        date_counts: Dict[str, Dict] = {}
        for notif in notifications:
            local_time = notif.created_at.astimezone( tz )
            date_key = local_time.strftime( "%Y-%m-%d" )

            if date_key not in date_counts:
                date_counts[ date_key ] = { "count": 0, "new_count": 0 }

            date_counts[ date_key ][ "count" ] += 1

            # Count "new" as notifications not yet delivered/responded
            if notif.state in [ "created", "queued" ]:
                date_counts[ date_key ][ "new_count" ] += 1

        # Convert to sorted list (newest first)
        return [
            { "date": date_key, **counts }
            for date_key, counts in sorted( date_counts.items(), reverse=True )
        ]

    def get_sender_last_activities_visible(
        self,
        recipient_id: uuid.UUID,
        include_hidden: bool = False
    ) -> List[Dict]:
        """
        Get last activity timestamp per sender for a recipient (excluding hidden).

        Requires:
            - recipient_id: Valid user UUID
            - include_hidden: Whether to include hidden notifications in counts

        Ensures:
            - Returns list of {sender_id, last_activity, notification_count, new_count}
            - Excludes senders with all notifications hidden (unless include_hidden)
            - Ordered by last_activity descending (most recent first)

        Returns:
            List of sender activity summaries
        """
        # Build base query
        query = self.session.query(
            Notification.sender_id,
            func.max( Notification.created_at ).label( 'last_activity' ),
            func.count( Notification.id ).label( 'notification_count' ),
            func.sum(
                case(
                    ( Notification.state.in_( [ 'created', 'queued' ] ), 1 ),
                    else_=0
                )
            ).label( 'new_count' )
        ).filter(
            Notification.recipient_id == recipient_id
        )

        if not include_hidden:
            query = query.filter( Notification.is_hidden == False )

        results = query.group_by(
            Notification.sender_id
        ).order_by(
            desc( 'last_activity' )
        ).all()

        return [
            {
                "sender_id"     : row.sender_id,
                "last_activity" : row.last_activity,
                "count"         : row.notification_count,
                "new_count"     : row.new_count or 0
            }
            for row in results
        ]


def quick_smoke_test():
    """
    Quick smoke test for NotificationRepository - validates CRUD and sender operations.
    """
    import cosa.utils.util as cu

    cu.print_banner( "NotificationRepository Smoke Test", prepend_nl=True )

    try:
        # Test 1: Module imports
        print( "Testing module imports..." )
        from cosa.rest.db.database import get_db
        from cosa.rest.postgres_models import Notification, User
        print( "✓ Imports successful" )

        # Test 2: Repository instantiation
        print( "Testing repository instantiation..." )
        with get_db() as session:
            repo = NotificationRepository( session )
            assert repo is not None
            assert repo.model == Notification
            print( "✓ Repository instantiated correctly" )

        # Test 3: Check repository methods exist
        print( "Testing repository methods..." )
        methods = [
            'create_notification', 'get_by_recipient', 'get_sender_last_activities',
            'get_sender_conversation', 'update_state', 'update_response',
            'get_pending_for_recipient', 'mark_expired', 'count_by_sender'
        ]
        for method in methods:
            assert hasattr( NotificationRepository, method ), f"Missing method: {method}"
        print( f"✓ All {len( methods )} repository methods defined" )

        # Test 4: Test with actual database (if available)
        print( "Testing database operations..." )
        try:
            with get_db() as session:
                repo = NotificationRepository( session )

                # Check if we have any users to test with
                user = session.query( User ).first()
                if user:
                    # Test get_sender_last_activities (should work even with no data)
                    activities = repo.get_sender_last_activities( user.id )
                    print( f"  Found {len( activities )} sender(s) for user {user.email}" )

                    # Test count_by_sender
                    counts = repo.count_by_sender( user.id )
                    print( f"  Sender counts: {counts}" )

                    print( "✓ Database operations successful" )
                else:
                    print( "  ⚠ No users found for testing (this is OK for new databases)" )

        except Exception as db_error:
            print( f"  ⚠ Database test skipped: {db_error}" )
            print( "  (This is OK if database is not running)" )

        print( "\n✓ Smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
