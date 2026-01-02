"""
Orchestration module for Claude Code task dispatch.

This module provides infrastructure for programmatically invoking Claude Code
with voice I/O capabilities via MCP tools.

Classes:
    CosaDispatcher: Routes tasks to appropriate Claude Code runtime
    Task: Task definition dataclass
    TaskType: Enum for bounded vs interactive execution modes
    TaskResult: Result dataclass from task execution

Example:
    from cosa.orchestration import CosaDispatcher, Task, TaskType

    dispatcher = CosaDispatcher()
    result = await dispatcher.dispatch( Task(
        id="task-001",
        project="lupin",
        prompt="Run tests and fix failures",
        type=TaskType.BOUNDED
    ) )
"""

from cosa.orchestration.claude_code_dispatcher import (
    CosaDispatcher,
    Task,
    TaskType,
    TaskResult
)

__all__ = [
    "CosaDispatcher",
    "Task",
    "TaskType",
    "TaskResult"
]
