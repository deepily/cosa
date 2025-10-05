"""
Admin Router for FastAPI.

Provides administrative endpoints for user management.
All endpoints require admin role authorization.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

from cosa.rest.auth_middleware import require_admin
from cosa.rest.admin_service import (
    list_users,
    get_user_details,
    update_user_roles,
    toggle_user_status,
    admin_reset_password
)


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
