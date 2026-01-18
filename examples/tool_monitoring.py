#!/usr/bin/env python3
"""
Example showing how to monitor tool calls from cursor-agent.

This is useful for:
- Logging what the agent is doing
- Building approval workflows
- Creating audit trails
- Implementing safety checks

Run after installing:
    pip install -e ..
    python tool_monitoring.py
"""

from cursor_agent_api import (
    query_stream,
    EventType,
    AgentConfig,
    CursorAgentClient,
)


def monitor_tool_calls():
    """Monitor and log all tool calls."""
    print("=" * 50)
    print("Tool Call Monitoring Example")
    print("=" * 50)
    
    config = AgentConfig(
        force_approve=True,  # Auto-approve for this demo
    )
    client = CursorAgentClient(config)
    
    prompt = "List the files in the current directory"
    
    print(f"Prompt: {prompt}\n")
    print("-" * 30)
    
    tool_calls = []
    
    for event in client.query_stream(prompt):
        if event.type == EventType.TOOL_CALL_STARTED:
            tool_data = event.data
            print(f"🔧 TOOL STARTED: {tool_data}")
            tool_calls.append({
                'type': 'started',
                'data': tool_data
            })
            
        elif event.type == EventType.TOOL_CALL_COMPLETED:
            tool_data = event.data
            print(f"✅ TOOL COMPLETED: {tool_data}")
            tool_calls.append({
                'type': 'completed',
                'data': tool_data
            })
            
        elif event.type == EventType.ASSISTANT_DELTA and event.text:
            print(event.text, end="", flush=True)
            
        elif event.type == EventType.RESULT_SUCCESS:
            print(f"\n\n----- FINAL RESULT -----")
            print(event.text)
    
    print(f"\n----- TOOL CALL SUMMARY -----")
    print(f"Total tool operations: {len(tool_calls)}")
    for i, call in enumerate(tool_calls):
        print(f"  {i+1}. {call['type']}: {call['data'].get('type', 'unknown')}")


def inspect_all_events():
    """Print all event types for debugging."""
    print("=" * 50)
    print("All Events Inspector")
    print("=" * 50)
    
    prompt = "What files are in the current directory?"
    
    print(f"Prompt: {prompt}\n")
    
    for event in query_stream(prompt):
        # Print event type and key info
        print(f"[{event.type.value}]", end=" ")
        
        if event.text:
            text_preview = event.text[:50].replace('\n', '\\n')
            print(f"text={text_preview}...", end=" ")
        
        if event.session_id:
            print(f"session={event.session_id[:8]}...", end=" ")
            
        print()  # newline
    
    print("-" * 30)


if __name__ == "__main__":
    print("Note: This example may trigger tool calls.")
    print("Make sure cursor-agent is configured correctly.\n")
    
    inspect_all_events()
    print()
    # Uncomment to run tool monitoring (may modify files):
    # monitor_tool_calls()
