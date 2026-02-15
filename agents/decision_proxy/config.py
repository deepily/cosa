#!/usr/bin/env python3
"""
Configuration for the Decision Proxy Agent.

Generic trust framework configuration: level thresholds, decay rates,
circuit breaker parameters, active hours, and timezone. No domain-specific
constants — those belong in the domain layer (e.g., swe_team/proxy/config.py).

Dependency Rule:
    This module NEVER imports from notification_proxy or swe_team.
"""

from cosa.agents.utils.proxy_agents.base_config import (   # noqa: F401
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    RECONNECT_INITIAL_DELAY,
    RECONNECT_MAX_DELAY,
    RECONNECT_MAX_ATTEMPTS,
    RECONNECT_BACKOFF_FACTOR,
    get_credentials,
    get_anthropic_api_key,
)


# ============================================================================
# Decision-Proxy-Specific Defaults
# ============================================================================

DEFAULT_SESSION_ID = "decision proxy"
DEFAULT_PROFILE    = "swe_team"

# WebSocket subscription events for decision proxy
SUBSCRIBED_EVENTS = [
    "notification_queue_update",
    "job_state_transition",
    "sys_ping"
]


# ============================================================================
# Trust Mode
# ============================================================================

TRUST_MODE_CHOICES = [ "shadow", "suggest", "active" ]
DEFAULT_TRUST_MODE = "shadow"


# ============================================================================
# Trust Levels
# ============================================================================

TRUST_LEVELS = {
    1 : { "name": "Shadow",                "min_decisions": 0,    "description": "Predict only, log, don't act" },
    2 : { "name": "Suggest",               "min_decisions": 50,   "description": "Queue as provisional, human ratifies" },
    3 : { "name": "Act + Notify",          "min_decisions": 200,  "description": "Commit decision, async audit" },
    4 : { "name": "Autonomous + Audit",    "min_decisions": 500,  "description": "10% random audit" },
    5 : { "name": "Full Autonomy",         "min_decisions": 1000, "description": "Circuit breaker only safety net" },
}

# Default thresholds (configurable via lupin-app.ini)
DEFAULT_L2_THRESHOLD = 50
DEFAULT_L3_THRESHOLD = 200
DEFAULT_L4_THRESHOLD = 500
DEFAULT_L5_THRESHOLD = 1000

# Trust decay
DEFAULT_DECAY_HALF_LIFE_DAYS   = 14
DEFAULT_ROLLING_WINDOW_DAYS    = 30

# Circuit breaker defaults
DEFAULT_CB_ERROR_RATE_THRESHOLD        = 0.15
DEFAULT_CB_CONFIDENCE_COLLAPSE_THRESHOLD = 0.3
DEFAULT_CB_AUTO_DEMOTION_LEVELS        = 2
DEFAULT_CB_RECOVERY_COOLDOWN_SECONDS   = 3600

# Active hours (when user is typically available)
DEFAULT_ACTIVE_HOURS_START = 9    # 09:00
DEFAULT_ACTIVE_HOURS_END   = 22   # 22:00
DEFAULT_TIMEZONE           = "America/Chicago"

# Audit sampling rate at L4
DEFAULT_L4_AUDIT_SAMPLE_RATE = 0.10  # 10%
