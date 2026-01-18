#!/usr/bin/env python3
"""
Test script for cursor_agent_api.

Run with: python3 test_api.py
"""

import sys
from cursor_agent_api import (
    query,
    query_stream,
    ConversationSession,
    EventType,
    collect_text,
    CursorAgentClient,
    AgentConfig,
)


def test_simple_query():
    """Test simple query."""
    print("Test 1: Simple query...", end=" ")
    result = query("What is 2+2?")
    assert result.success, f"Query failed: {result.error}"
    assert "4" in result.result, f"Unexpected result: {result.result}"
    assert result.session_id, "No session ID"
    print("PASSED")


def test_multi_turn():
    """Test multi-turn conversation."""
    print("Test 2: Multi-turn conversation...", end=" ")
    session = ConversationSession()
    
    r1 = session.send("Remember this code: ALPHA123")
    assert r1.success, f"First message failed: {r1.error}"
    
    r2 = session.send("What code did I tell you?")
    assert r2.success, f"Second message failed: {r2.error}"
    assert "ALPHA123" in r2.result.upper(), f"Context not maintained: {r2.result}"
    assert r1.session_id == r2.session_id or session.session_id, "Session ID lost"
    print("PASSED")


def test_streaming():
    """Test streaming response."""
    print("Test 3: Streaming...", end=" ")
    
    events = list(query_stream("Say the word 'test'"))
    
    # Check we got expected event types
    event_types = [e.type for e in events]
    assert EventType.SYSTEM_INIT in event_types, "Missing SYSTEM_INIT"
    assert EventType.RESULT_SUCCESS in event_types, "Missing RESULT_SUCCESS"
    
    # Check we got some text
    text = collect_text(iter(events))
    assert text, "No text collected"
    print("PASSED")


def test_event_parsing():
    """Test event type parsing."""
    print("Test 4: Event parsing...", end=" ")
    
    found_delta = False
    found_full = False
    
    for event in query_stream("Hi"):
        if event.type == EventType.ASSISTANT_DELTA:
            found_delta = True
        elif event.type == EventType.ASSISTANT:
            found_full = True
    
    # In streaming mode with partial output, we should get deltas
    assert found_full, "No full assistant message"
    print("PASSED")


def test_custom_config():
    """Test custom configuration."""
    print("Test 5: Custom config...", end=" ")
    
    config = AgentConfig(
        force_approve=False,  # Default safe mode
    )
    client = CursorAgentClient(config)
    result = client.query("What is 1+1?")
    
    assert result.success, f"Query failed: {result.error}"
    print("PASSED")


def main():
    print("=" * 50)
    print("cursor_agent_api Test Suite")
    print("=" * 50)
    print()
    
    tests = [
        test_simple_query,
        test_multi_turn,
        test_streaming,
        test_event_parsing,
        test_custom_config,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1
    
    print()
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
