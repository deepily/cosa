#!/usr/bin/env python3
"""
Configuration for the SWE Engineering Proxy domain layer.

SWE-specific constants: accepted senders, category cap levels.
Generic trust config lives in decision_proxy/config.py.

Dependency Rule:
    This module imports from decision_proxy (Layer 3) for base config re-exports.
    This module NEVER imports from notification_proxy.
"""

# ============================================================================
# SWE Team Sender Patterns
# ============================================================================

DEFAULT_ACCEPTED_SENDERS = [
    "swe.lead@lupin.deepily.ai",
    "swe.coder@lupin.deepily.ai",
    "swe.tester@lupin.deepily.ai",
]

# ============================================================================
# Category Cap Levels (max trust level for high-risk categories)
# ============================================================================

# Deployment, destructive, and architecture decisions are capped at L3
# (Act + Notify) — they always require human awareness even at peak trust.
DEFAULT_DEPLOYMENT_CAP_LEVEL    = 3
DEFAULT_DESTRUCTIVE_CAP_LEVEL   = 3
DEFAULT_ARCHITECTURE_CAP_LEVEL  = 3

# Testing, deps, and general can reach full autonomy (L5)
DEFAULT_TESTING_CAP_LEVEL       = 5
DEFAULT_DEPS_CAP_LEVEL          = 5
DEFAULT_GENERAL_CAP_LEVEL       = 5
