"""
CoSA CLI Package - Command Line Interface tools for Claude Code integration

This package provides CLI scripts for Claude Code to communicate with the 
Genie-in-the-Box FastAPI application through notifications and future 
bidirectional communication.

Main Components:
- notify_user: Send notifications to user via Genie-in-the-Box API
- notification_types: Constants and enums for notification types
- test_notifications: End-to-end testing suite
"""

__version__ = "0.1.0"
__author__ = "CoSA Development Team"

# Make main functions available at package level
from .notify_user import notify_user
from .notification_types import NotificationType, NotificationPriority

__all__ = [
    'notify_user',
    'NotificationType', 
    'NotificationPriority'
]