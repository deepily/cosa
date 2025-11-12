#!/usr/bin/env python3
"""
Claude Code async notification client with Pydantic validation (Phase 2.4).

This script sends fire-and-forget notifications to Lupin via WebSocket delivery.
Uses Pydantic models for type-safe validation and structured responses.

Usage:
    python3 notify_user_async.py "Message text" --type task --priority high
    python3 notify_user_async.py "Build completed" --type task

Exit Codes:
    0: Success (notification queued or delivered)
    1: Error (validation, network, user not found)

Environment Variables:
    COSA_APP_SERVER_URL: Server URL (default: http://localhost:7999)
"""

import os
import sys
import requests
import argparse
from typing import Optional
from pydantic import ValidationError

# Import Pydantic models
from cosa.cli.notification_models import (
    AsyncNotificationRequest,
    AsyncNotificationResponse,
    NotificationType,
    NotificationPriority
)

# Import config loader for dynamic configuration (Phase 2.5)
from cosa.utils.config_loader import get_api_config, load_api_key

# Import constants (fallbacks)
from cosa.cli.notification_types import (
    DEFAULT_SERVER_URL,
    ENV_SERVER_URL
)


def notify_user_async(
    request: AsyncNotificationRequest,
    server_url: Optional[str] = None,
    debug: bool = False
) -> AsyncNotificationResponse:
    """
    Send fire-and-forget notification with Pydantic validation.

    Sends notification to Lupin API for WebSocket delivery without waiting
    for user response. Uses Pydantic models for type-safe request/response.

    Requires:
        - request is a validated AsyncNotificationRequest model
        - server_url is None or a valid HTTP/HTTPS URL
        - debug is a boolean

    Ensures:
        - Returns AsyncNotificationResponse with status and details
        - Prints status messages to stdout (success) or stderr (errors)
        - Uses Pydantic validation for all data

    Raises:
        - No exceptions raised (all handled internally)

    Args:
        request: AsyncNotificationRequest model (already validated)
        server_url: Override server URL (uses env var if None)
        debug: Enable debug output to stderr

    Returns:
        AsyncNotificationResponse: Structured response with success, status, details
    """

    # Load configuration (Phase 2.5 - dynamic multi-environment config)
    try:
        # Determine environment (default: local)
        env = os.getenv( 'LUPIN_ENV', 'local' )

        # Load config for environment (precedence: env vars > file > defaults)
        config = get_api_config( env )

        # Load API key from configured file
        api_key = load_api_key( config['api_key_file'] )

        # Use configured API URL (can be overridden by server_url parameter)
        base_url = server_url or config['api_url']
        base_url = base_url.rstrip( '/' )

    except Exception as e:
        # Fallback to environment variables/defaults if config loading fails
        if debug:
            print( f"[DEBUG] Config loading failed, using fallback: {e}", file=sys.stderr )
        base_url = server_url or os.getenv( ENV_SERVER_URL, DEFAULT_SERVER_URL )
        base_url = base_url.rstrip( '/' )
        api_key = None  # Will cause authentication error (intentional - forces user to fix config)

    try:
        url = f"{base_url}/api/notify"

        # Convert request to API params (Phase 2.5 - api_key moved to headers)
        params = request.to_api_params()

        # Create headers with API key authentication (Phase 2.5)
        headers = {
            'X-API-Key': api_key
        }

        if debug:
            print( f"[DEBUG] Sending notification to: {url}", file=sys.stderr )
            print( f"[DEBUG] Environment: {env if 'env' in locals() else 'fallback'}", file=sys.stderr )
            print( f"[DEBUG] Request model: {request.model_dump_json( indent=2 )}", file=sys.stderr )
            print( f"[DEBUG] API params: {params}", file=sys.stderr )
            print( f"[DEBUG] API key: {api_key[:20]}...{api_key[-10:] if api_key else 'None'}", file=sys.stderr )

        # Send notification (fire-and-forget - no SSE streaming)
        response = requests.post(
            url,
            params  = params,
            headers = headers,
            timeout = request.timeout
        )

        if response.status_code == 200:
            # Parse JSON response
            data = response.json()

            if debug:
                print( f"[DEBUG] Response data: {data}", file=sys.stderr )

            # Create typed response
            return AsyncNotificationResponse(
                success          = True,
                status           = data.get( "status", "queued" ),
                message          = data.get( "message" ),
                target_user      = request.target_user,
                target_system_id = data.get( "target_system_id" ),
                connection_count = data.get( "connection_count", 0 )
            )

        else:
            # HTTP error
            error_text = response.text if response.text else "No error message"
            return AsyncNotificationResponse(
                success     = False,
                status      = "error",
                message     = f"HTTP {response.status_code}: {error_text}",
                target_user = request.target_user
            )

    except requests.exceptions.ConnectionError:
        return AsyncNotificationResponse(
            success     = False,
            status      = "connection_error",
            message     = f"Cannot reach server at {base_url}. Check that Lupin is running and {ENV_SERVER_URL} is correct.",
            target_user = request.target_user
        )

    except requests.exceptions.Timeout:
        return AsyncNotificationResponse(
            success     = False,
            status      = "timeout",
            message     = f"Server did not respond within {request.timeout} seconds",
            target_user = request.target_user
        )

    except requests.exceptions.RequestException as e:
        return AsyncNotificationResponse(
            success     = False,
            status      = "error",
            message     = f"Request error: {e}",
            target_user = request.target_user
        )

    except Exception as e:
        return AsyncNotificationResponse(
            success     = False,
            status      = "error",
            message     = f"Unexpected error: {e}",
            target_user = request.target_user
        )


def validate_environment() -> bool:
    """
    Validate environment setup for notification system.

    Requires:
        - urllib.parse module is available

    Ensures:
        - Returns True if all environment checks pass
        - Returns False if any validation issues found
        - Prints detailed validation results

    Raises:
        - None (handles all exceptions gracefully)

    Returns:
        bool: True if environment is properly configured
    """

    issues = []

    # Check server URL
    server_url = os.getenv( ENV_SERVER_URL, DEFAULT_SERVER_URL )
    if not server_url.startswith( ('http://', 'https://') ):
        issues.append( f"{ENV_SERVER_URL} must start with http:// or https://" )

    # Validate URL format
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse( server_url )
        if not parsed.netloc:
            issues.append( f"Invalid server URL format: {server_url}" )
    except Exception as e:
        issues.append( f"Error parsing server URL: {e}" )

    if issues:
        print( "❌ Environment validation failed:" )
        for issue in issues:
            print( f"  - {issue}" )
        return False

    print( "✅ Environment validation passed" )
    print( f"  Server URL: {server_url}" )
    return True


def main():
    """
    CLI entry point for notify_user_async script.

    Parses command-line arguments, validates with Pydantic models, sends
    notification, and exits with appropriate status code.

    Requires:
        - argparse module is available
        - Pydantic models are importable
        - Command line arguments follow expected format

    Ensures:
        - Parses arguments with argparse
        - Validates with Pydantic (AsyncNotificationRequest)
        - Sends notification with notify_user_async()
        - Outputs status messages
        - Exits with code: 0=success, 1=error

    Raises:
        - SystemExit with appropriate exit code
    """

    # Load config early to get global_notification_recipient default (Phase 2.5.4)
    try:
        env = os.getenv( 'LUPIN_ENV', 'local' )
        config = get_api_config( env )
        # NOTE: Config key is 'global_notification_recipient' but CLI flag is '--target-user'
        # for backward compatibility. This naming mismatch is intentional.
        # TODO: Future version should rename CLI flag to --notification-recipient
        default_target_user = config.get( 'global_notification_recipient' )
    except Exception:
        # Config loading failed - no default target_user
        default_target_user = None

    parser = argparse.ArgumentParser(
        description="Send fire-and-forget notification to Lupin (Phase 2.4 with Pydantic)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Build completed successfully" --type task --priority medium
  %(prog)s "Starting deployment" --type progress --priority low
  %(prog)s "Critical error detected" --type alert --priority urgent
  %(prog)s "Custom message" --type custom

Exit Codes:
  0  Success (notification queued or delivered)
  1  Error (validation, network, user not found)

Environment Variables:
  COSA_APP_SERVER_URL            Server URL (default: http://localhost:7999)
  LUPIN_ENV                      Environment name (default: local)
  LUPIN_NOTIFICATION_RECIPIENT   Global notification recipient email (overrides config file)
        """
    )

    parser.add_argument(
        "message",
        help="Notification message text"
    )

    parser.add_argument(
        "--type",
        choices=["task", "progress", "alert", "custom"],
        default="custom",
        help="Notification type (default: custom)"
    )

    parser.add_argument(
        "--priority",
        choices=["low", "medium", "high", "urgent"],
        default="medium",
        help="Priority level (default: medium)"
    )

    # Use configured global_notification_recipient if available, otherwise require explicit --target-user
    target_user_help = "Target user email address"
    if default_target_user:
        target_user_help += f" (default from config: {default_target_user})"
    else:
        target_user_help += " (required - configure in ~/.notifications/config or use --target-user)"

    parser.add_argument(
        "--target-user",
        default=default_target_user,
        required=(default_target_user is None),
        help=target_user_help
    )

    parser.add_argument(
        "--server",
        help=f"Server URL (overrides {ENV_SERVER_URL})"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Request timeout in seconds (default: 5)"
    )

    parser.add_argument(
        "--validate-env",
        action="store_true",
        help="Validate environment configuration and exit"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output to stderr"
    )

    args = parser.parse_args()

    # Validate environment if requested
    if args.validate_env:
        is_valid = validate_environment()
        sys.exit( 0 if is_valid else 1 )

    try:
        # Construct and validate request model (automatic Pydantic validation)
        request = AsyncNotificationRequest(
            message           = args.message,
            notification_type = NotificationType( args.type ),
            priority          = NotificationPriority( args.priority ),
            target_user       = args.target_user,
            timeout           = args.timeout
        )

    except ValidationError as e:
        # Beautiful error messages from Pydantic
        print( "✗ Invalid parameters:", file=sys.stderr )
        for error in e.errors():
            field = '.'.join( str( loc ) for loc in error['loc'] )
            msg = error['msg']
            print( f"  {field}: {msg}", file=sys.stderr )
        sys.exit( 1 )

    # Send notification
    response = notify_user_async(
        request    = request,
        server_url = args.server,
        debug      = args.debug
    )

    # Output based on response
    if response.success:
        print( f"✓ Notification sent: {response.status}" )
        if response.connection_count > 0:
            print( f"  {response.connection_count} connection(s)" )
        if args.debug and response.target_system_id:
            print( f"  User ID: {response.target_system_id}", file=sys.stderr )
    else:
        print( f"✗ {response.status}: {response.message}", file=sys.stderr )

    sys.exit( 0 if response.success else 1 )


if __name__ == "__main__":
    main()
