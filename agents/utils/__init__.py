#!/usr/bin/env python3
"""
COSA Agents Utilities Package.

Shared utilities for COSA agent implementations.

Modules:
    voice_io: Consolidated Voice-First I/O Layer for all COSA agents
    proxy_agents: Shared proxy agent infrastructure (WebSocket listener,
                  responder, strategy protocol, config, CLI helpers)
"""

from . import voice_io
from . import proxy_agents

__all__ = [ "voice_io", "proxy_agents" ]
