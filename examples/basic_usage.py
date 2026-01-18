#!/usr/bin/env python3
"""
Basic usage examples for cursor_agent_api.
"""

import sys
sys.path.insert(0, '..')

from cursor_agent_api import (
    query,
    query_stream,
    ConversationSession,
    EventType,
    collect_text,
    AgentConfig,
    CursorAgentClient,
)


def example_simple_query():
    """Simple one-shot query."""
    print("=" * 50)
    print("Example 1: Simple Query")
    print("=" * 50)
    
    result = query("What is the meaning of life according to Douglas Adams?")
    
    print(f"Success: {result.success}")
    print(f"Response: {result.result}")
    print(f"Session ID: {result.session_id}")
    print(f"Duration: {result.duration_ms}ms")
    print()


def example_multi_turn():
    """Multi-turn conversation maintaining context."""
    print("=" * 50)
    print("Example 2: Multi-turn Conversation")
    print("=" * 50)
    
    session = ConversationSession()
    
    # First turn
    print("User: My name is Alice and I like cats.")
    r1 = session.send("My name is Alice and I like cats.")
    print(f"Agent: {r1.result}")
    print()
    
    # Second turn - agent should remember
    print("User: What's my name and what do I like?")
    r2 = session.send("What's my name and what do I like?")
    print(f"Agent: {r2.result}")
    print()
    
    print(f"Session maintained: {session.session_id}")
    print(f"History length: {len(session.history)}")
    print()


def example_streaming():
    """Streaming response with real-time output."""
    print("=" * 50)
    print("Example 3: Streaming Response")
    print("=" * 50)
    
    print("Agent: ", end="", flush=True)
    
    for event in query_stream("Write a haiku about programming"):
        if event.type == EventType.ASSISTANT_DELTA and event.text:
            print(event.text, end="", flush=True)
    
    print("\n")


def example_streaming_with_thinking():
    """Show both thinking and response."""
    print("=" * 50)
    print("Example 4: Streaming with Thinking")
    print("=" * 50)
    
    for event in query_stream("What is 17 * 23?"):
        if event.type == EventType.THINKING_DELTA and event.text:
            print(f"[Thinking: {event.text}]", end="", flush=True)
        elif event.type == EventType.THINKING_COMPLETED:
            print("\n---")
        elif event.type == EventType.ASSISTANT_DELTA and event.text:
            print(event.text, end="", flush=True)
    
    print("\n")


def example_collect_text():
    """Using collect_text helper."""
    print("=" * 50)
    print("Example 5: Collect Text Helper")
    print("=" * 50)
    
    events = query_stream("Say hello in French, Spanish, and German")
    text = collect_text(events)
    
    print(f"Collected: {text}")
    print()


def example_custom_config():
    """Using custom configuration."""
    print("=" * 50)
    print("Example 6: Custom Configuration")
    print("=" * 50)
    
    config = AgentConfig(
        force_approve=True,  # Auto-approve commands
        # model="sonnet-4",  # Uncomment to specify model
    )
    
    client = CursorAgentClient(config)
    result = client.query("What model are you using?")
    
    print(f"Response: {result.result}")
    print()


def example_plan_mode():
    """Using plan mode (read-only analysis)."""
    print("=" * 50)
    print("Example 7: Plan Mode")
    print("=" * 50)
    
    result = query(
        "Analyze the current directory structure",
        mode="plan"
    )
    
    print(f"Analysis: {result.result[:500]}...")
    print()


if __name__ == "__main__":
    examples = [
        example_simple_query,
        example_multi_turn,
        example_streaming,
        example_streaming_with_thinking,
        example_collect_text,
        example_custom_config,
        # example_plan_mode,  # Uncomment to test
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"Error in {example.__name__}: {e}")
            print()
