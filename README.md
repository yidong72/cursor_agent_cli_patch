# Cursor Agent Python API

A Python wrapper for the `cursor-agent` CLI that exposes its input/output functionality for programmatic use without the interactive UI.

## Features

- **Simple Queries**: Send prompts and get structured JSON responses
- **Multi-turn Conversations**: Maintain context across multiple exchanges
- **Streaming**: Get real-time token-by-token output
- **Async Support**: asyncio-compatible API for concurrent usage
- **Tool Monitoring**: Track tool calls (file edits, shell commands, etc.)

## Prerequisites

1. `cursor-agent` CLI must be installed and authenticated
2. Python 3.10+

To verify cursor-agent is working:
```bash
echo "Hello" | agent --print --output-format json
```

## Quick Start

### Simple Query

```python
from cursor_agent_api import query

result = query("What is the capital of France?")
print(result.result)  # "The capital of France is Paris."
print(result.session_id)  # UUID for this conversation
```

### Multi-turn Conversation

```python
from cursor_agent_api import ConversationSession

session = ConversationSession()

# First message
r1 = session.send("My favorite color is blue")
print(r1.result)

# Follow-up (maintains context)
r2 = session.send("What's my favorite color?")
print(r2.result)  # Will mention blue
```

### Streaming Responses

```python
from cursor_agent_api import query_stream, EventType

for event in query_stream("Write a short poem about coding"):
    if event.type == EventType.ASSISTANT_DELTA:
        print(event.text, end="", flush=True)
    elif event.type == EventType.THINKING_DELTA:
        # Optional: show thinking process
        pass
print()
```

### Cancelling Generation

```python
from cursor_agent_api import query_stream, EventType

stream = query_stream("Write a very long story")
for event in stream:
    if event.type == EventType.ASSISTANT_DELTA:
        print(event.text, end="", flush=True)
    
    # Stop generation after receiving 50 events
    if len(stream.events) > 50:
        stream.cancel()
        break

print(f"\nCancelled after {len(stream.events)} events")
```

### Using collect_text Helper

```python
from cursor_agent_api import query_stream, collect_text

events = query_stream("Explain Python in one sentence")
text = collect_text(events)
print(text)
```

## API Reference

For detailed documentation of all data structures, JSON event formats, and field descriptions, see **[API.md](API.md)**.

### Classes

#### `CursorAgentClient`

Main client for interacting with cursor-agent.

```python
from cursor_agent_api import CursorAgentClient, AgentConfig

config = AgentConfig(
    workspace="/path/to/project",  # Working directory
    model="sonnet-4",              # Model to use
    force_approve=True,            # Auto-approve tool calls (-f flag)
    approve_mcps=True,             # Auto-approve MCP servers
)

client = CursorAgentClient(config)
result = client.query("List all Python files")
```

#### `ConversationSession`

Manages multi-turn conversations.

```python
from cursor_agent_api import ConversationSession

session = ConversationSession()

# Conversation history is maintained
for prompt in prompts:
    result = session.send(prompt)
    print(result.result)

# Access history
for prompt, result in session.history:
    print(f"User: {prompt}")
    print(f"Agent: {result.result}")
```

#### `AsyncCursorAgentClient` / `AsyncConversationSession`

Async versions for concurrent usage.

```python
import asyncio
from cursor_agent_api import AsyncCursorAgentClient, aquery

async def main():
    # Quick async query
    result = await aquery("What is 2+2?")
    print(result.result)
    
    # Or with a client
    client = AsyncCursorAgentClient()
    result = await client.query("Hello")

asyncio.run(main())
```

### Event Types

When streaming, you receive `AgentEvent` objects with these types:

| Event Type | Description |
|------------|-------------|
| `SYSTEM_INIT` | Session initialization info |
| `USER` | Echo of user message |
| `THINKING_DELTA` | Incremental thinking text |
| `THINKING_COMPLETED` | Thinking phase finished |
| `ASSISTANT_DELTA` | Incremental response text |
| `ASSISTANT` | Complete response message |
| `TOOL_CALL_STARTED` | Tool execution began |
| `TOOL_CALL_COMPLETED` | Tool execution finished |
| `RESULT_SUCCESS` | Final successful result |
| `RESULT_ERROR` | Final error result |

### AgentResult

Response object with these fields:

```python
@dataclass
class AgentResult:
    success: bool           # Whether the query succeeded
    result: str             # The text response
    session_id: str         # Session ID for resuming
    request_id: str         # Unique request identifier
    duration_ms: int        # Total duration
    duration_api_ms: int    # API call duration
    error: str              # Error message if failed
    events: list            # All events (if streaming)
```

## CLI Options Used

The wrapper uses these cursor-agent CLI options:

| Option | Description |
|--------|-------------|
| `--print` | Non-interactive mode |
| `--output-format json\|stream-json` | Structured output |
| `--stream-partial-output` | Token-by-token streaming |
| `--resume <session_id>` | Continue conversation |
| `-f, --force` | Auto-approve commands |
| `--approve-mcps` | Auto-approve MCP servers |
| `--model <model>` | Specify model |
| `--workspace <path>` | Working directory |

## Advanced Examples

### Monitor Tool Calls

```python
from cursor_agent_api import query_stream, EventType

for event in query_stream("Create a file called test.txt with 'Hello'", 
                          config=AgentConfig(force_approve=True)):
    if event.type == EventType.TOOL_CALL_STARTED:
        print(f"Tool started: {event.data}")
    elif event.type == EventType.TOOL_CALL_COMPLETED:
        print(f"Tool completed: {event.data}")
    elif event.type == EventType.ASSISTANT_DELTA:
        print(event.text, end="")
```

### Parallel Queries (Async)

```python
import asyncio
from cursor_agent_api import AsyncCursorAgentClient

async def main():
    client = AsyncCursorAgentClient()
    
    # Run multiple queries concurrently
    results = await asyncio.gather(
        client.query("What is Python?"),
        client.query("What is JavaScript?"),
        client.query("What is Rust?"),
    )
    
    for r in results:
        print(f"Answer: {r.result[:100]}...")

asyncio.run(main())
```

### Custom Configuration

```python
from cursor_agent_api import CursorAgentClient, AgentConfig

config = AgentConfig(
    workspace="/home/user/myproject",
    model="gpt-5",
    force_approve=True,
    approve_mcps=True,
    headers=["X-Custom-Header: value"],
)

client = CursorAgentClient(config)
result = client.query("Refactor this codebase", timeout=300)
```

## Testing

### Unit Tests (No CLI Required)

```bash
# Using unittest
python3 test_unit.py

# Using pytest (if installed)
python3 -m pytest test_unit.py -v
```

### Acceptance Tests (Requires cursor-agent CLI)

Real end-to-end tests that verify all use cases against the actual CLI:

```bash
# Run all acceptance tests
python3 test_acceptance.py

# Run fast mode (skip slow tests)
python3 test_acceptance.py --fast
```

**Acceptance tests cover:**
- Simple and complex queries
- Multi-turn conversations with context
- Streaming responses and cancellation
- Event parsing (system, user, assistant, thinking, tool calls)
- Async operations (query, conversation, parallel)
- Session management and resume
- Error handling

### Legacy Integration Tests

```bash
python3 test_api.py
```

## Patching cursor-agent

The original `patch-cursor-agent` script enables the "Run Everything" feature:

```bash
# Apply the patch
patch-cursor-agent

# This changes:
# enableRunEverything = false → enableRunEverything = true
```

This allows using the `-f` flag to auto-approve all tool calls.

## License

MIT
# cursor_agent_cli_patch
