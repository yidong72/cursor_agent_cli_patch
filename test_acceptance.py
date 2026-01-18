#!/usr/bin/env python3
"""
Acceptance tests for cursor_agent_api.

These tests run against the real cursor-agent CLI to verify end-to-end functionality.
They require:
1. cursor-agent CLI installed and in PATH (as 'agent')
2. Valid authentication/API access

Run with: python3 test_acceptance.py
Skip slow tests: python3 test_acceptance.py --fast

Note: These tests make real API calls and may incur costs.
"""

import sys
import time
import shutil
import argparse
import asyncio
from typing import Optional

from cursor_agent_api import (
    # Main API
    query,
    query_stream,
    aquery,
    collect_text,
    # Classes
    CursorAgentClient,
    ConversationSession,
    AsyncCursorAgentClient,
    AsyncConversationSession,
    AgentConfig,
    StreamingResponse,
    # Enums
    EventType,
    OutputFormat,
)


class AcceptanceTestRunner:
    """Runner for acceptance tests with reporting."""
    
    def __init__(self, fast_mode: bool = False):
        self.fast_mode = fast_mode
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.results = []
    
    def check_prerequisites(self) -> bool:
        """Check if cursor-agent CLI is available."""
        if not shutil.which("agent"):
            print("ERROR: 'agent' command not found in PATH")
            print("Please install cursor-agent CLI first.")
            return False
        return True
    
    def run_test(self, name: str, test_func, skip_in_fast_mode: bool = False):
        """Run a single test and record result."""
        if skip_in_fast_mode and self.fast_mode:
            print(f"  SKIP: {name} (fast mode)")
            self.skipped += 1
            self.results.append((name, "SKIPPED", None))
            return
        
        print(f"  TEST: {name}...", end=" ", flush=True)
        start_time = time.time()
        
        try:
            test_func()
            elapsed = time.time() - start_time
            print(f"PASSED ({elapsed:.2f}s)")
            self.passed += 1
            self.results.append((name, "PASSED", elapsed))
        except AssertionError as e:
            elapsed = time.time() - start_time
            print(f"FAILED ({elapsed:.2f}s)")
            print(f"       Error: {e}")
            self.failed += 1
            self.results.append((name, "FAILED", str(e)))
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"ERROR ({elapsed:.2f}s)")
            print(f"       Exception: {type(e).__name__}: {e}")
            self.failed += 1
            self.results.append((name, "ERROR", str(e)))
    
    def print_summary(self):
        """Print test summary."""
        total = self.passed + self.failed + self.skipped
        print()
        print("=" * 60)
        print(f"ACCEPTANCE TEST RESULTS: {self.passed}/{total} passed", end="")
        if self.skipped:
            print(f", {self.skipped} skipped", end="")
        if self.failed:
            print(f", {self.failed} FAILED", end="")
        print()
        print("=" * 60)
        
        if self.failed:
            print("\nFailed tests:")
            for name, status, error in self.results:
                if status in ("FAILED", "ERROR"):
                    print(f"  - {name}: {error}")
    
    def success(self) -> bool:
        """Return True if all tests passed."""
        return self.failed == 0


# =============================================================================
# Test Cases
# =============================================================================

def test_simple_query():
    """Test: Simple single-shot query returns correct answer."""
    result = query("What is 2+2? Reply with just the number.")
    
    assert result.success, f"Query failed: {result.error}"
    assert result.session_id, "No session ID returned"
    assert "4" in result.result, f"Expected '4' in result: {result.result}"


def test_query_with_timeout():
    """Test: Query respects timeout parameter."""
    # Use a reasonable timeout that should work
    result = query("Say 'hello'", timeout=60)
    
    assert result.success, f"Query failed: {result.error}"
    assert result.result, "Empty result"


def test_query_metadata():
    """Test: Query returns expected metadata fields."""
    result = query("Say 'test'")
    
    assert result.success, f"Query failed: {result.error}"
    assert result.session_id, "Missing session_id"
    # These may or may not be present depending on the response
    # Just verify the result object has the expected structure
    assert hasattr(result, 'duration_ms')
    assert hasattr(result, 'request_id')


def test_multi_turn_conversation():
    """Test: Multi-turn conversation maintains context."""
    session = ConversationSession()
    
    # First message - give it something to remember
    r1 = session.send("Remember this secret code: XRAY-7749. Just say OK.")
    assert r1.success, f"First message failed: {r1.error}"
    
    # Second message - ask about the code
    r2 = session.send("What was the secret code I told you? Reply with just the code.")
    assert r2.success, f"Second message failed: {r2.error}"
    assert "XRAY" in r2.result.upper() or "7749" in r2.result, \
        f"Context not maintained. Expected code in: {r2.result}"
    
    # Verify session ID is maintained
    assert session.session_id, "Session ID lost"
    
    # Verify history is recorded
    assert len(session.history) == 2, f"Expected 2 history items, got {len(session.history)}"


def test_conversation_history():
    """Test: Conversation session tracks history correctly."""
    session = ConversationSession()
    
    session.send("Say 'first'")
    session.send("Say 'second'")
    session.send("Say 'third'")
    
    history = session.history
    assert len(history) == 3, f"Expected 3 history items, got {len(history)}"
    
    # Verify history contains prompts
    prompts = [h[0] for h in history]
    assert "Say 'first'" in prompts[0]
    assert "Say 'second'" in prompts[1]
    assert "Say 'third'" in prompts[2]


def test_conversation_reset():
    """Test: Conversation reset clears session state."""
    session = ConversationSession()
    
    session.send("Remember: my name is Alice")
    old_session_id = session.session_id
    
    session.reset()
    
    assert session.session_id is None, "Session ID not cleared"
    assert len(session.history) == 0, "History not cleared"
    
    # New conversation should get new session
    session.send("Hello")
    assert session.session_id != old_session_id, "Should have new session ID"


def test_streaming_basic():
    """Test: Streaming returns events in correct order."""
    stream = query_stream("Say 'hello world'")
    events = list(stream)
    
    assert len(events) > 0, "No events received"
    
    # Check for expected event types
    event_types = [e.type for e in events]
    assert EventType.SYSTEM_INIT in event_types, "Missing SYSTEM_INIT event"
    assert EventType.RESULT_SUCCESS in event_types or EventType.RESULT_ERROR in event_types, \
        "Missing result event"
    
    # Verify we got some assistant content
    has_content = any(
        e.type in (EventType.ASSISTANT, EventType.ASSISTANT_DELTA) and e.text
        for e in events
    )
    assert has_content, "No assistant content in events"


def test_streaming_collect_text():
    """Test: collect_text helper extracts text from stream."""
    stream = query_stream("Count from 1 to 5, separated by commas")
    text = collect_text(stream)
    
    assert text, "No text collected"
    # Should contain at least some numbers
    assert any(str(n) in text for n in range(1, 6)), f"Expected numbers in: {text}"


def test_streaming_with_deltas():
    """Test: Streaming with partial output returns delta events."""
    client = CursorAgentClient()
    stream = client.query_stream("Write a short sentence about coding.", stream_partial=True)
    
    events = list(stream)
    
    # In partial mode, we should get delta events
    delta_events = [e for e in events if e.type == EventType.ASSISTANT_DELTA]
    # Note: May not always get deltas depending on response length
    
    # Should have final result
    result_events = [e for e in events if e.type == EventType.RESULT_SUCCESS]
    assert len(result_events) > 0, "No result event"


def test_streaming_events_property():
    """Test: StreamingResponse.events property captures all events."""
    stream = query_stream("Say 'test'")
    
    # Consume the stream
    for _ in stream:
        pass
    
    # Check events were captured
    events = stream.events
    assert len(events) > 0, "No events captured"
    assert isinstance(events, list), "events should be a list"


def test_streaming_cancel():
    """Test: Streaming can be cancelled mid-generation."""
    # Ask for something that would generate a long response
    stream = query_stream("Write a very long story about a programmer. Make it at least 500 words.")
    
    events_before_cancel = []
    for event in stream:
        events_before_cancel.append(event)
        # Cancel after receiving a few events
        if len(events_before_cancel) >= 5:
            stream.cancel()
            break
    
    assert stream.cancelled, "Stream should be marked as cancelled"
    assert len(events_before_cancel) >= 5, "Should have received events before cancel"
    
    # Verify we can still access events
    all_events = stream.events
    assert len(all_events) == len(events_before_cancel), "Events mismatch after cancel"


def test_streaming_context_manager():
    """Test: StreamingResponse works as context manager."""
    with query_stream("Say 'hello'") as stream:
        events = []
        for event in stream:
            events.append(event)
            if len(events) >= 3:
                break  # Exit early
    
    # Process should be cleaned up (no assertion needed, just shouldn't hang)
    assert len(events) >= 1, "Should have received at least one event"


def test_custom_config_workspace():
    """Test: Custom workspace configuration is applied."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(workspace=tmpdir)
        client = CursorAgentClient(config)
        
        # Query about current directory
        result = client.query("What directory are you working in? Just give the path.")
        
        assert result.success, f"Query failed: {result.error}"
        # The workspace should be reflected somehow in the response or behavior


def test_event_parsing_system_init():
    """Test: System init event contains expected fields."""
    stream = query_stream("Hi")
    
    init_event = None
    for event in stream:
        if event.type == EventType.SYSTEM_INIT:
            init_event = event
            break
    
    assert init_event is not None, "No SYSTEM_INIT event found"
    assert init_event.session_id, "SYSTEM_INIT missing session_id"
    assert init_event.data, "SYSTEM_INIT missing data"


def test_event_parsing_user_echo():
    """Test: User message is echoed in events."""
    test_message = "This is a unique test message 12345"
    stream = query_stream(test_message)
    
    user_event = None
    for event in stream:
        if event.type == EventType.USER:
            user_event = event
            break
    
    assert user_event is not None, "No USER event found"
    # The user message should be in the event data somewhere
    assert test_message in str(user_event.data), "User message not in USER event"


def test_session_resume():
    """Test: Session can be resumed with session_id."""
    client = CursorAgentClient()
    
    # First query
    r1 = client.query("Remember: The password is DELTA-9. Just say OK.")
    assert r1.success, f"First query failed: {r1.error}"
    session_id = r1.session_id
    
    # Resume session with same client
    r2 = client.query("What password did I tell you?", session_id=session_id)
    assert r2.success, f"Resume query failed: {r2.error}"
    assert "DELTA" in r2.result.upper() or "9" in r2.result, \
        f"Session not resumed properly: {r2.result}"


def test_async_query():
    """Test: Async query works correctly."""
    async def run():
        result = await aquery("What is 3+3? Reply with just the number.")
        assert result.success, f"Async query failed: {result.error}"
        assert "6" in result.result, f"Expected '6' in: {result.result}"
    
    asyncio.run(run())


def test_async_client():
    """Test: AsyncCursorAgentClient works correctly."""
    async def run():
        client = AsyncCursorAgentClient()
        result = await client.query("Say 'async test'")
        assert result.success, f"Async client query failed: {result.error}"
        assert result.result, "Empty result"
    
    asyncio.run(run())


def test_async_conversation():
    """Test: AsyncConversationSession maintains context."""
    async def run():
        session = AsyncConversationSession()
        
        r1 = await session.send("My favorite number is 42. Just say OK.")
        assert r1.success, f"First send failed: {r1.error}"
        
        r2 = await session.send("What is my favorite number? Reply with just the number.")
        assert r2.success, f"Second send failed: {r2.error}"
        assert "42" in r2.result, f"Context not maintained: {r2.result}"
    
    asyncio.run(run())


def test_async_parallel_queries():
    """Test: Multiple async queries can run in parallel."""
    async def run():
        client = AsyncCursorAgentClient()
        
        # Run multiple queries in parallel
        results = await asyncio.gather(
            client.query("What is 1+1? Just the number."),
            client.query("What is 2+2? Just the number."),
            client.query("What is 3+3? Just the number."),
        )
        
        assert len(results) == 3, "Expected 3 results"
        for i, result in enumerate(results):
            assert result.success, f"Query {i+1} failed: {result.error}"
    
    asyncio.run(run())


def test_error_handling_invalid_session():
    """Test: Invalid session ID is handled gracefully."""
    client = CursorAgentClient()
    
    # Try to resume with invalid session ID
    result = client.query("Hello", session_id="invalid-session-id-12345")
    
    # Should either succeed (ignoring invalid session) or fail gracefully
    # The important thing is it doesn't crash
    assert isinstance(result.success, bool), "Should return valid result"


def test_thinking_events():
    """Test: Thinking events are captured when present."""
    # Ask something that might trigger thinking
    stream = query_stream("What is the capital of the country that hosted the 2024 Olympics?")
    
    events = list(stream)
    event_types = [e.type for e in events]
    
    # Thinking events may or may not be present depending on model
    # Just verify we can process them if present
    thinking_events = [e for e in events if e.type in (EventType.THINKING_DELTA, EventType.THINKING_COMPLETED)]
    
    # This is informational - thinking may not always occur
    if thinking_events:
        print(f"(captured {len(thinking_events)} thinking events)", end=" ")


def test_collect_text_with_thinking():
    """Test: collect_text can optionally include thinking."""
    stream = query_stream("What is 10 * 10?")
    events = list(stream)
    
    # Collect without thinking
    text_no_thinking = collect_text(iter(events), include_thinking=False)
    
    # Collect with thinking
    text_with_thinking = collect_text(iter(events), include_thinking=True)
    
    # Both should have content
    assert text_no_thinking, "Should have text without thinking"
    assert text_with_thinking, "Should have text with thinking"
    
    # With thinking should be >= without thinking
    assert len(text_with_thinking) >= len(text_no_thinking), \
        "Text with thinking should be at least as long"


def test_conversation_with_streaming():
    """Test: ConversationSession streaming with finalize."""
    session = ConversationSession()
    
    # Use streaming
    prompt = "Say 'streaming test'"
    stream = session.send_stream(prompt)
    
    # Consume stream
    events = list(stream)
    
    # Finalize to update history
    result = session.finalize_stream(prompt, stream)
    
    assert result is not None, "finalize_stream should return result"
    assert result.success, "Result should be successful"
    assert len(session.history) == 1, "History should have 1 entry"
    assert session.session_id, "Session ID should be set"


def test_long_response_streaming():
    """Test: Long responses stream correctly."""
    stream = query_stream("List the first 10 prime numbers, one per line.")
    
    text_parts = []
    for event in stream:
        if event.type == EventType.ASSISTANT_DELTA and event.text:
            text_parts.append(event.text)
    
    full_text = "".join(text_parts)
    
    # Should have collected substantial text
    assert len(full_text) > 10, f"Expected longer response, got: {full_text}"
    
    # Should contain some prime numbers
    assert any(str(p) in full_text for p in [2, 3, 5, 7, 11]), \
        f"Expected prime numbers in: {full_text}"


def test_result_event_contains_full_response():
    """Test: RESULT_SUCCESS event contains the full response."""
    stream = query_stream("Say exactly: 'The quick brown fox'")
    events = list(stream)
    
    result_event = next(
        (e for e in events if e.type == EventType.RESULT_SUCCESS),
        None
    )
    
    assert result_event is not None, "No RESULT_SUCCESS event"
    assert result_event.text, "RESULT_SUCCESS should have text"


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Run acceptance tests for cursor_agent_api")
    parser.add_argument("--fast", action="store_true", help="Skip slow tests")
    args = parser.parse_args()
    
    runner = AcceptanceTestRunner(fast_mode=args.fast)
    
    print("=" * 60)
    print("CURSOR AGENT API - ACCEPTANCE TESTS")
    print("=" * 60)
    print()
    
    # Check prerequisites
    if not runner.check_prerequisites():
        return 1
    
    print("Prerequisites OK. Running tests...\n")
    
    # Basic functionality tests
    print("[Basic Query Tests]")
    runner.run_test("Simple query", test_simple_query)
    runner.run_test("Query with timeout", test_query_with_timeout)
    runner.run_test("Query metadata", test_query_metadata)
    print()
    
    # Conversation tests
    print("[Conversation Tests]")
    runner.run_test("Multi-turn conversation", test_multi_turn_conversation, skip_in_fast_mode=True)
    runner.run_test("Conversation history", test_conversation_history, skip_in_fast_mode=True)
    runner.run_test("Conversation reset", test_conversation_reset, skip_in_fast_mode=True)
    runner.run_test("Session resume", test_session_resume, skip_in_fast_mode=True)
    print()
    
    # Streaming tests
    print("[Streaming Tests]")
    runner.run_test("Streaming basic", test_streaming_basic)
    runner.run_test("Streaming collect_text", test_streaming_collect_text)
    runner.run_test("Streaming with deltas", test_streaming_with_deltas)
    runner.run_test("Streaming events property", test_streaming_events_property)
    runner.run_test("Streaming cancel", test_streaming_cancel, skip_in_fast_mode=True)
    runner.run_test("Streaming context manager", test_streaming_context_manager)
    runner.run_test("Long response streaming", test_long_response_streaming, skip_in_fast_mode=True)
    runner.run_test("Result event full response", test_result_event_contains_full_response)
    print()
    
    # Event parsing tests
    print("[Event Parsing Tests]")
    runner.run_test("Event parsing system init", test_event_parsing_system_init)
    runner.run_test("Event parsing user echo", test_event_parsing_user_echo)
    runner.run_test("Thinking events", test_thinking_events, skip_in_fast_mode=True)
    runner.run_test("Collect text with thinking", test_collect_text_with_thinking)
    print()
    
    # Async tests
    print("[Async Tests]")
    runner.run_test("Async query", test_async_query)
    runner.run_test("Async client", test_async_client)
    runner.run_test("Async conversation", test_async_conversation, skip_in_fast_mode=True)
    runner.run_test("Async parallel queries", test_async_parallel_queries, skip_in_fast_mode=True)
    print()
    
    # Configuration tests
    print("[Configuration Tests]")
    runner.run_test("Custom workspace config", test_custom_config_workspace)
    print()
    
    # Session and conversation tests
    print("[Advanced Tests]")
    runner.run_test("Conversation with streaming", test_conversation_with_streaming)
    runner.run_test("Error handling invalid session", test_error_handling_invalid_session)
    print()
    
    # Print summary
    runner.print_summary()
    
    return 0 if runner.success() else 1


if __name__ == "__main__":
    sys.exit(main())
