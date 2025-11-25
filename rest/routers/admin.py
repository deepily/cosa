"""
Admin Router for FastAPI.

Provides administrative endpoints for user management.
All endpoints require admin role authorization.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
import traceback

from cosa.rest.auth_middleware import require_admin
from cosa.rest.admin_service import (
    list_users,
    get_user_details,
    update_user_roles,
    toggle_user_status,
    admin_reset_password
)
from cosa.config.configuration_manager import ConfigurationManager
from cosa.memory.solution_manager_factory import SolutionSnapshotManagerFactory
import cosa.utils.util as du


# ============================================================================
# Pydantic Models
# ============================================================================

class UserListResponse( BaseModel ):
    """Response model for list users endpoint."""
    users: List[Dict]
    total: int
    limit: int
    offset: int


class UserDetailsResponse( BaseModel ):
    """Response model for user details endpoint."""
    id: str
    email: str
    roles: List[str]
    email_verified: bool
    is_active: bool
    created_at: str
    last_login_at: Optional[str]
    audit_log_count: int
    failed_login_count: int


class UpdateRolesRequest( BaseModel ):
    """Request model for updating user roles."""
    roles: List[str] = Field( ..., description="List of roles to assign (admin, user)" )


class UpdateStatusRequest( BaseModel ):
    """Request model for updating user status."""
    is_active: bool = Field( ..., description="Set user active status" )


class ResetPasswordRequest( BaseModel ):
    """Request model for admin password reset."""
    reason: Optional[str] = Field( None, description="Optional reason for audit trail" )


class ResetPasswordResponse( BaseModel ):
    """Response model for password reset."""
    message: str
    temporary_password: str
    user: Dict


class MessageResponse( BaseModel ):
    """Generic message response."""
    message: str
    user: Optional[Dict] = None


# ============================================================================
# Admin Snapshots Models
# ============================================================================

class SnapshotSearchResult( BaseModel ):
    """Individual search result for solution snapshot."""
    id_hash: str = Field( ..., description="Unique identifier (MD5 hash)" )
    question_preview: str = Field( ..., description="Truncated question (100 chars)" )
    question_gist: str = Field( ..., description="Condensed semantic summary" )
    created_date: str = Field( ..., description="Creation timestamp" )
    score: float = Field( ..., description="Similarity score (0-100)" )


class SearchSnapshotsResponse( BaseModel ):
    """Response model for snapshot search endpoint."""
    results: List[SnapshotSearchResult]
    total: int
    query: str


class SnapshotDetailResponse( BaseModel ):
    """Response model for detailed snapshot information."""
    id_hash: str
    question: str
    question_normalized: str
    question_gist: str
    answer: str
    answer_conversational: str
    runtime_stats: dict
    code: List[str]
    created_date: str
    user_id: str


# ============================================================================
# Router Configuration
# ============================================================================

router = APIRouter(
    prefix     = "/admin",
    tags       = ["Admin"],
    responses  = {
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden - Admin role required"},
        404: {"description": "Not Found"},
        500: {"description": "Internal Server Error"}
    }
)


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "/users",
    response_model  = UserListResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "List all users",
    description     = "Get paginated list of users with optional filters. Requires admin role."
)
async def get_users(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    role: Optional[str] = None,
    status_filter: Optional[str] = None,
    admin_user: Dict = Depends( require_admin )
) -> UserListResponse:
    """
    List all users with pagination and filtering.

    Requires:
        - Admin role authorization
        - Valid query parameters

    Ensures:
        - Returns paginated user list
        - Includes total count
        - Applies search and filter criteria

    Query Parameters:
        - limit: Max results (1-1000, default 100)
        - offset: Pagination offset (default 0)
        - search: Email search string
        - role: Filter by role (admin/user)
        - status_filter: Filter by status (active/inactive)

    Returns:
        UserListResponse: Paginated user list with metadata
    """
    try:
        users, total = list_users(
            limit         = limit,
            offset        = offset,
            search        = search,
            role_filter   = role,
            status_filter = status_filter
        )

        return UserListResponse(
            users  = users,
            total  = total,
            limit  = limit,
            offset = offset
        )

    except Exception as e:
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = f"Failed to list users: {str( e )}"
        )


@router.get(
    "/users/{user_id}",
    response_model  = UserDetailsResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "Get user details",
    description     = "Get detailed information for specific user. Requires admin role."
)
async def get_user(
    user_id: str,
    admin_user: Dict = Depends( require_admin )
) -> UserDetailsResponse:
    """
    Get detailed user information.

    Requires:
        - Admin role authorization
        - Valid user ID

    Ensures:
        - Returns enhanced user details
        - Includes audit statistics
        - Returns 404 if user not found

    Path Parameters:
        - user_id: User UUID

    Returns:
        UserDetailsResponse: Detailed user information
    """
    user_details = get_user_details( user_id )

    if not user_details:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail      = "User not found"
        )

    return UserDetailsResponse( **user_details )


@router.put(
    "/users/{user_id}/roles",
    response_model  = MessageResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "Update user roles",
    description     = "Update roles for specific user. Prevents self-demotion. Requires admin role."
)
async def update_roles(
    user_id: str,
    request_body: UpdateRolesRequest,
    request: Request,
    admin_user: Dict = Depends( require_admin )
) -> MessageResponse:
    """
    Update user roles with self-protection.

    Requires:
        - Admin role authorization
        - Valid user ID
        - Valid roles list (admin, user)

    Ensures:
        - Validates roles are allowed
        - Prevents admin self-demotion
        - Updates roles in database
        - Logs to audit trail
        - Returns updated user data

    Path Parameters:
        - user_id: User UUID

    Request Body:
        - roles: List of role strings

    Returns:
        MessageResponse: Success message with updated user
    """
    admin_ip = request.client.host if request.client else "unknown"

    success, message, updated_user = update_user_roles(
        admin_user_id  = admin_user["user_id"],
        target_user_id = user_id,
        new_roles      = request_body.roles,
        admin_email    = admin_user.get( "email", "unknown" ),
        admin_ip       = admin_ip
    )

    if not success:
        # Determine appropriate status code
        if "not found" in message.lower():
            status_code = status.HTTP_404_NOT_FOUND
        elif "cannot remove" in message.lower() or "invalid" in message.lower():
            status_code = status.HTTP_400_BAD_REQUEST
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        raise HTTPException(
            status_code = status_code,
            detail      = message
        )

    return MessageResponse(
        message = message,
        user    = updated_user
    )


@router.put(
    "/users/{user_id}/status",
    response_model  = MessageResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "Toggle user status",
    description     = "Activate or deactivate user account. Prevents self-deactivation. Requires admin role."
)
async def update_status(
    user_id: str,
    request_body: UpdateStatusRequest,
    request: Request,
    admin_user: Dict = Depends( require_admin )
) -> MessageResponse:
    """
    Toggle user account status with session invalidation.

    Requires:
        - Admin role authorization
        - Valid user ID
        - Boolean status value

    Ensures:
        - Prevents admin self-deactivation
        - Updates is_active status
        - Revokes tokens if deactivating
        - Logs to audit trail
        - Returns updated user data

    Path Parameters:
        - user_id: User UUID

    Request Body:
        - is_active: Boolean status value

    Returns:
        MessageResponse: Success message with updated user
    """
    admin_ip = request.client.host if request.client else "unknown"

    success, message, updated_user = toggle_user_status(
        admin_user_id  = admin_user["user_id"],
        target_user_id = user_id,
        is_active      = request_body.is_active,
        admin_email    = admin_user.get( "email", "unknown" ),
        admin_ip       = admin_ip
    )

    if not success:
        # Determine appropriate status code
        if "not found" in message.lower():
            status_code = status.HTTP_404_NOT_FOUND
        elif "cannot deactivate" in message.lower():
            status_code = status.HTTP_400_BAD_REQUEST
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        raise HTTPException(
            status_code = status_code,
            detail      = message
        )

    return MessageResponse(
        message = message,
        user    = updated_user
    )


@router.post(
    "/users/{user_id}/reset-password",
    response_model  = ResetPasswordResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "Admin password reset",
    description     = "Generate temporary password for user. Password shown once only. Requires admin role."
)
async def reset_user_password(
    user_id: str,
    request_body: ResetPasswordRequest,
    request: Request,
    admin_user: Dict = Depends( require_admin )
) -> ResetPasswordResponse:
    """
    Generate temporary password for user (admin reset).

    Requires:
        - Admin role authorization
        - Valid user ID
        - Optional reason for audit

    Ensures:
        - Generates crypto-secure password
        - Password meets strength requirements
        - Password returned ONCE (not stored)
        - Logs to audit trail with reason
        - Returns temporary password

    Path Parameters:
        - user_id: User UUID

    Request Body:
        - reason: Optional audit note

    Returns:
        ResetPasswordResponse: Message, temp password, and user data
    """
    admin_ip = request.client.host if request.client else "unknown"

    success, message, temp_password = admin_reset_password(
        admin_user_id  = admin_user["user_id"],
        target_user_id = user_id,
        admin_email    = admin_user.get( "email", "unknown" ),
        admin_ip       = admin_ip,
        reason         = request_body.reason or ""
    )

    if not success:
        # Determine appropriate status code
        if "not found" in message.lower():
            status_code = status.HTTP_404_NOT_FOUND
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        raise HTTPException(
            status_code = status_code,
            detail      = message
        )

    # Get user data for response
    from cosa.rest.user_service import get_user_by_id
    user_data = get_user_by_id( user_id )

    return ResetPasswordResponse(
        message            = message,
        temporary_password = temp_password,
        user               = {
            "id"    : user_data["id"],
            "email" : user_data["email"]
        }
    )


# ============================================================================
# Solution Snapshots Endpoints
# ============================================================================

def _get_snapshot_manager():
    """
    Helper function to create and initialize LanceDB solution manager.

    Requires:
        - Configuration manager environment variable set
        - LanceDB configuration present in lupin-app.ini

    Ensures:
        - Returns initialized LanceDB manager
        - Manager is ready for queries

    Raises:
        - HTTPException 500 if initialization fails
    """
    try:
        # Get configuration
        config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )

        # Extract LanceDB configuration
        manager_type   = config_mgr.get( "solution snapshots manager type" )
        storage_backend = config_mgr.get( "storage_backend" )
        table_name     = config_mgr.get( "solution snapshots lancedb table" )

        # Get path or URI based on backend
        if storage_backend == "gcs":
            db_path_or_uri = config_mgr.get( "solution snapshots lancedb gcs uri" )
            config = {
                "storage_backend" : storage_backend,
                "gcs_uri"         : db_path_or_uri,
                "table_name"      : table_name
            }
        else:
            db_path = config_mgr.get( "solution snapshots lancedb path" )
            db_path_full = du.get_project_root() + db_path
            config = {
                "storage_backend" : storage_backend,
                "db_path"         : db_path_full,
                "table_name"      : table_name
            }

        # Get debug and verbose flags from configuration
        debug_mode = config_mgr.get( "app_debug", default=False )
        verbose_mode = config_mgr.get( "app_verbose", default=False )

        # Create and initialize manager
        manager = SolutionSnapshotManagerFactory.create_manager(
            manager_type = manager_type,
            config       = config,
            debug        = debug_mode,
            verbose      = verbose_mode
        )

        if not manager.is_initialized():
            manager.initialize()

        return manager

    except Exception as e:
        print( f"[ADMIN-SNAPSHOTS] Failed to initialize snapshot manager: {e}" )
        traceback.print_exc()
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = "Snapshot search is temporarily unavailable"
        )


@router.get(
    "/snapshots/search",
    response_model  = SearchSnapshotsResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "Search solution snapshots",
    description     = "Search snapshots by question text using vector similarity. Requires admin role."
)
async def search_snapshots(
    q: str,
    limit: int = 50,
    admin_user: Dict = Depends( require_admin )
) -> SearchSnapshotsResponse:
    """
    Search solution snapshots using vector similarity search.

    Requires:
        - Admin role authorization
        - Non-empty query string
        - Valid limit (1-100)

    Ensures:
        - Returns list of matching snapshots
        - Results sorted by similarity score descending
        - Question preview truncated to 100 chars
        - Includes similarity score for each result

    Query Parameters:
        - q: Search query text
        - limit: Max results (1-100, default 50)

    Returns:
        SearchSnapshotsResponse: List of matching snapshots with metadata
    """
    if not q or not q.strip():
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = "Query parameter 'q' cannot be empty"
        )

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = "Limit must be between 1 and 100"
        )

    try:
        manager = _get_snapshot_manager()

        # Search snapshots using vector similarity
        results = manager.get_snapshots_by_question(
            question    = q,
            limit       = limit,
            debug       = False
        )

        # Convert results to response format
        search_results = []
        for score, snapshot in results:
            # Truncate question to 100 chars for preview
            question_preview = du.truncate_string( snapshot.question, max_len=100 )

            search_results.append( SnapshotSearchResult(
                id_hash          = snapshot.id_hash,
                question_preview = question_preview,
                question_gist    = snapshot.question_gist,
                created_date     = snapshot.created_date,
                score            = score
            ))

        return SearchSnapshotsResponse(
            results = search_results,
            total   = len( search_results ),
            query   = q
        )

    except Exception as e:
        print( f"[ADMIN-SNAPSHOTS] Search failed for query '{q}': {e}" )
        traceback.print_exc()
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = "Search failed. Please try again or contact support if the problem persists."
        )


@router.get(
    "/snapshots/{id_hash}",
    response_model  = SnapshotDetailResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "Get snapshot details",
    description     = "Retrieve full snapshot details by ID. Requires admin role."
)
async def get_snapshot_details(
    id_hash: str,
    admin_user: Dict = Depends( require_admin )
) -> SnapshotDetailResponse:
    """
    Get complete snapshot data for display in detail modal.

    Requires:
        - Admin role authorization
        - Valid snapshot ID hash

    Ensures:
        - Returns full snapshot data if found
        - Returns 404 if snapshot not found
        - All text fields included (question, answer, etc.)

    Path Parameters:
        - id_hash: Snapshot ID (MD5 hash)

    Returns:
        SnapshotDetailResponse: Complete snapshot information
    """
    try:
        manager = _get_snapshot_manager()

        # Get snapshot by ID
        snapshot = manager.get_snapshot_by_id( id_hash )

        if not snapshot:
            print( f"[ADMIN-SNAPSHOTS] Snapshot not found: {id_hash}" )
            raise HTTPException(
                status_code = status.HTTP_404_NOT_FOUND,
                detail      = "Snapshot not found"
            )

        return SnapshotDetailResponse(
            id_hash               = snapshot.id_hash,
            question              = snapshot.question,
            question_normalized   = snapshot.question_normalized,
            question_gist         = snapshot.question_gist,
            answer                = snapshot.answer,
            answer_conversational = snapshot.answer_conversational,
            runtime_stats         = snapshot.runtime_stats,
            code                  = snapshot.code,
            created_date          = snapshot.created_date,
            user_id               = snapshot.user_id
        )

    except HTTPException:
        raise
    except Exception as e:
        print( f"[ADMIN-SNAPSHOTS] Failed to retrieve snapshot {id_hash}: {e}" )
        traceback.print_exc()
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = "Failed to retrieve snapshot details. Please try again."
        )


@router.delete(
    "/snapshots/{id_hash}",
    response_model  = MessageResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "Delete snapshot",
    description     = "Permanently delete snapshot from database. Requires admin role."
)
async def delete_snapshot(
    id_hash: str,
    admin_user: Dict = Depends( require_admin )
) -> MessageResponse:
    """
    Delete snapshot with physical removal from LanceDB.

    Requires:
        - Admin role authorization
        - Valid snapshot ID hash

    Ensures:
        - Snapshot physically removed from database
        - Returns success message if deleted
        - Returns 404 if snapshot not found

    Path Parameters:
        - id_hash: Snapshot ID (MD5 hash)

    Returns:
        MessageResponse: Success or error message
    """
    try:
        print( f"[ADMIN-SNAPSHOTS] DELETE request for snapshot ID: {id_hash}" )
        manager = _get_snapshot_manager()

        # Get snapshot first to retrieve the question
        print( f"[ADMIN-SNAPSHOTS] Retrieving snapshot for deletion..." )
        snapshot = manager.get_snapshot_by_id( id_hash )

        if not snapshot:
            print( f"[ADMIN-SNAPSHOTS] Snapshot not found for deletion: {id_hash}" )
            raise HTTPException(
                status_code = status.HTTP_404_NOT_FOUND,
                detail      = "Snapshot not found"
            )

        print( f"[ADMIN-SNAPSHOTS] Found snapshot, question: '{snapshot.question[:50]}...'" )
        print( f"[ADMIN-SNAPSHOTS] Question length: {len(snapshot.question)} chars" )
        print( f"[ADMIN-SNAPSHOTS] Attempting physical deletion..." )

        # Delete snapshot using question (LanceDB delete requires question)
        success = manager.delete_snapshot(
            question        = snapshot.question,
            delete_physical = True
        )

        if success:
            print( f"[ADMIN-SNAPSHOTS] Successfully deleted snapshot {id_hash}" )
            return MessageResponse(
                message = f"Snapshot deleted successfully: {id_hash}"
            )
        else:
            print( f"[ADMIN-SNAPSHOTS] Delete operation returned False for {id_hash}" )
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail      = "Failed to delete snapshot"
            )

    except HTTPException:
        raise
    except Exception as e:
        print( f"[ADMIN-SNAPSHOTS] Delete failed for snapshot {id_hash}: {e}" )
        print( f"[ADMIN-SNAPSHOTS] Exception type: {type( e ).__name__}" )
        print( f"[ADMIN-SNAPSHOTS] Exception details: {str( e )}" )
        traceback.print_exc()
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = "Failed to delete snapshot. Please try again."
        )
