#!/usr/bin/env python3
"""
Async usage examples for cursor_agent_api.
"""

import asyncio
import sys
sys.path.insert(0, '..')

from cursor_agent_api import (
    AsyncCursorAgentClient,
    AsyncConversationSession,
    aquery,
    EventType,
)


async def example_simple_async():
    """Simple async query."""
    print("=" * 50)
    print("Example 1: Simple Async Query")
    print("=" * 50)
    
    result = await aquery("What is async/await in Python?")
    print(f"Response: {result.result[:200]}...")
    print()


async def example_parallel_queries():
    """Run multiple queries in parallel."""
    print("=" * 50)
    print("Example 2: Parallel Queries")
    print("=" * 50)
    
    client = AsyncCursorAgentClient()
    
    queries = [
        "What is Python? (one sentence)",
        "What is JavaScript? (one sentence)",
        "What is Rust? (one sentence)",
    ]
    
    print("Running 3 queries in parallel...")
    results = await asyncio.gather(*[
        client.query(q) for q in queries
    ])
    
    for query, result in zip(queries, results):
        print(f"\nQ: {query}")
        print(f"A: {result.result}")
    print()


async def example_async_conversation():
    """Async multi-turn conversation."""
    print("=" * 50)
    print("Example 3: Async Conversation")
    print("=" * 50)
    
    session = AsyncConversationSession()
    
    r1 = await session.send("I'm learning about async programming")
    print(f"Turn 1: {r1.result}")
    
    r2 = await session.send("Give me a simple example")
    print(f"Turn 2: {r2.result[:300]}...")
    print()


async def example_streaming_with_callback():
    """Async streaming with callback."""
    print("=" * 50)
    print("Example 4: Streaming with Callback")
    print("=" * 50)
    
    client = AsyncCursorAgentClient()
    
    def on_event(event):
        if event.type == EventType.ASSISTANT_DELTA and event.text:
            print(event.text, end="", flush=True)
    
    print("Agent: ", end="")
    await client.query_stream(
        "Say hello in 5 different languages",
        callback=on_event
    )
    print("\n")


async def example_timeout_handling():
    """Handling timeouts in async context."""
    print("=" * 50)
    print("Example 5: Timeout Handling")
    print("=" * 50)
    
    client = AsyncCursorAgentClient()
    
    try:
        result = await asyncio.wait_for(
            client.query("What is machine learning?"),
            timeout=30.0
        )
        print(f"Response: {result.result[:200]}...")
    except asyncio.TimeoutError:
        print("Query timed out!")
    print()


async def main():
    """Run all async examples."""
    examples = [
        example_simple_async,
        example_parallel_queries,
        example_async_conversation,
        example_streaming_with_callback,
        example_timeout_handling,
    ]
    
    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"Error in {example.__name__}: {e}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
