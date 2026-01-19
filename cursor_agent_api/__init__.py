"""
Cursor Agent Python API

A Python wrapper for the cursor-agent CLI that exposes its input/output
functionality for programmatic use without the interactive UI.

Basic usage:
    from cursor_agent_api import query, query_stream, EventType

    # Simple query
    result = query("What is 2+2?")
    print(result.result)

    # Streaming
    for event in query_stream("Write a poem"):
        if event.type == EventType.ASSISTANT_DELTA:
            print(event.text, end="")
"""

__version__ = "0.1.0"

from .client import (
    # Enums
    OutputFormat,
    EventType,
    # Data classes
    AgentEvent,
    AgentResult,
    AgentConfig,
    # Response wrapper
    StreamingResponse,
    # Sync client
    CursorAgentClient,
    ConversationSession,
    # Async client
    AsyncCursorAgentClient,
    AsyncConversationSession,
    # Convenience functions
    query,
    query_stream,
    aquery,
    collect_text,
)

__all__ = [
    # Version
    "__version__",
    # Enums
    "OutputFormat",
    "EventType",
    # Data classes
    "AgentEvent",
    "AgentResult",
    "AgentConfig",
    # Response wrapper
    "StreamingResponse",
    # Sync client
    "CursorAgentClient",
    "ConversationSession",
    # Async client
    "AsyncCursorAgentClient",
    "AsyncConversationSession",
    # Convenience functions
    "query",
    "query_stream",
    "aquery",
    "collect_text",
]
