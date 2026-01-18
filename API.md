# Cursor Agent API - Data Structures Reference

This document provides detailed documentation of all data structures used in the Cursor Agent Python API.

## Table of Contents

- [Enums](#enums)
  - [OutputFormat](#outputformat)
  - [EventType](#eventtype)
- [Data Classes](#data-classes)
  - [AgentConfig](#agentconfig)
  - [AgentResult](#agentresult)
  - [AgentEvent](#agentevent)
  - [StreamingResponse](#streamingresponse)
- [JSON Event Structures](#json-event-structures)
  - [System Init Event](#system-init-event)
  - [User Event](#user-event)
  - [Thinking Events](#thinking-events)
  - [Assistant Events](#assistant-events)
  - [Tool Call Events](#tool-call-events)
  - [Result Events](#result-events)

---

## Enums

### OutputFormat

Output format options for cursor-agent responses.

```python
class OutputFormat(Enum):
    TEXT = "text"           # Plain text output (human-readable)
    JSON = "json"           # Single JSON object with final result
    STREAM_JSON = "stream-json"  # Newline-delimited JSON events
```

| Value | CLI Flag | Description |
|-------|----------|-------------|
| `TEXT` | `--output-format text` | Human-readable plain text output |
| `JSON` | `--output-format json` | Single JSON object containing the final result |
| `STREAM_JSON` | `--output-format stream-json` | Newline-delimited JSON events (NDJSON) for real-time streaming |

---

### EventType

Event types emitted in `stream-json` mode. Each event corresponds to a specific phase of the agent's response.

```python
class EventType(Enum):
    SYSTEM_INIT = "system:init"
    USER = "user"
    THINKING_DELTA = "thinking:delta"
    THINKING_COMPLETED = "thinking:completed"
    ASSISTANT = "assistant"
    ASSISTANT_DELTA = "assistant:delta"
    TOOL_CALL_STARTED = "tool-call-started"
    TOOL_CALL_COMPLETED = "tool-call-completed"
    RESULT_SUCCESS = "result:success"
    RESULT_ERROR = "result:error"
    UNKNOWN = "unknown"
```

| Event Type | Raw Type | Subtype | Description |
|------------|----------|---------|-------------|
| `SYSTEM_INIT` | `system` | `init` | Session initialization with metadata |
| `USER` | `user` | - | Echo of the user's input message |
| `THINKING_DELTA` | `thinking` | `delta` | Incremental thinking/reasoning text |
| `THINKING_COMPLETED` | `thinking` | `completed` | Thinking phase finished |
| `ASSISTANT_DELTA` | `assistant` | - | Incremental response text (with `timestamp_ms`) |
| `ASSISTANT` | `assistant` | - | Complete response message (without `timestamp_ms`) |
| `TOOL_CALL_STARTED` | `tool-call-started` | - | Tool execution began |
| `TOOL_CALL_COMPLETED` | `tool-call-completed` | - | Tool execution finished |
| `RESULT_SUCCESS` | `result` | `success` | Final successful result |
| `RESULT_ERROR` | `result` | `error` | Final error result |
| `UNKNOWN` | (any other) | - | Unrecognized event type |

---

## Data Classes

### AgentConfig

Configuration options for the `CursorAgentClient`.

```python
@dataclass
class AgentConfig:
    workspace: Optional[str] = None
    model: Optional[str] = None
    force_approve: bool = False
    approve_mcps: bool = False
    api_key: Optional[str] = None
    headers: list[str] = field(default_factory=list)
    agent_binary: str = "agent"
```

| Field | Type | Default | CLI Flag | Description |
|-------|------|---------|----------|-------------|
| `workspace` | `str \| None` | `None` | `--workspace <path>` | Working directory for the agent |
| `model` | `str \| None` | `None` | `--model <model>` | Model to use (e.g., `"sonnet-4"`, `"gpt-4"`) |
| `force_approve` | `bool` | `False` | `-f, --force` | Auto-approve all tool calls (requires enableRunEverything patch) |
| `approve_mcps` | `bool` | `False` | `--approve-mcps` | Auto-approve MCP server connections |
| `api_key` | `str \| None` | `None` | `--api-key <key>` | API key for authentication |
| `headers` | `list[str]` | `[]` | `-H <header>` | Custom HTTP headers (can specify multiple) |
| `agent_binary` | `str` | `"agent"` | - | Path to the cursor-agent binary |

**Example:**

```python
config = AgentConfig(
    workspace="/home/user/myproject",
    model="sonnet-4",
    force_approve=True,
    approve_mcps=True,
    headers=["X-Custom-Header: value"],
)
```

---

### AgentResult

Result object returned from a cursor-agent query.

```python
@dataclass
class AgentResult:
    success: bool
    result: str
    session_id: str
    request_id: Optional[str] = None
    duration_ms: Optional[int] = None
    duration_api_ms: Optional[int] = None
    error: Optional[str] = None
    events: list[AgentEvent] = field(default_factory=list)
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | `True` if the query completed successfully |
| `result` | `str` | The text response from the agent |
| `session_id` | `str` | UUID for this conversation session (use to resume) |
| `request_id` | `str \| None` | Unique identifier for this specific request |
| `duration_ms` | `int \| None` | Total request duration in milliseconds |
| `duration_api_ms` | `int \| None` | API call duration in milliseconds |
| `error` | `str \| None` | Error message if `success=False` |
| `events` | `list[AgentEvent]` | All events collected during streaming (empty for non-streaming) |

**Example Response (JSON mode):**

```json
{
  "type": "result",
  "subtype": "success",
  "result": "The capital of France is Paris.",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "request_id": "req_abc123",
  "duration_ms": 1523,
  "duration_api_ms": 1456,
  "is_error": false
}
```

---

### AgentEvent

Represents a single event from the cursor-agent stream.

```python
@dataclass
class AgentEvent:
    type: EventType
    raw_type: str
    subtype: Optional[str]
    data: dict
    text: Optional[str] = None
    session_id: Optional[str] = None
    timestamp_ms: Optional[int] = None
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | `EventType` | Parsed event type enum |
| `raw_type` | `str` | Original `type` field from JSON |
| `subtype` | `str \| None` | Original `subtype` field from JSON |
| `data` | `dict` | Complete raw JSON data of the event |
| `text` | `str \| None` | Extracted text content (if available) |
| `session_id` | `str \| None` | Session ID (present in some events) |
| `timestamp_ms` | `int \| None` | Timestamp in milliseconds (present in delta events) |

**Text Extraction Logic:**

The `text` field is populated from one of these sources (in order):
1. `data["text"]` - Direct text field
2. `data["result"]` - Result text (for result events)
3. `data["message"]["content"][*]["text"]` - Text from message content blocks

---

### StreamingResponse

Wrapper for streaming responses that supports cancellation. Returned by `query_stream()` methods.

```python
class StreamingResponse:
    # Properties
    cancelled: bool           # Whether the stream was cancelled
    events: list[AgentEvent]  # List of events received so far
    process: subprocess.Popen # The underlying subprocess
    
    # Methods
    def cancel(signal: int = 15) -> None  # Stop generation
    def __iter__() -> Iterator[AgentEvent]  # Iterate over events
    def __enter__() / __exit__()  # Context manager support
```

| Property/Method | Type | Description |
|-----------------|------|-------------|
| `cancelled` | `bool` | `True` if `cancel()` was called |
| `events` | `list[AgentEvent]` | All events received so far (even after cancellation) |
| `process` | `Popen` | Underlying subprocess for advanced usage |
| `cancel(signal)` | `None` | Stop generation. Default signal is SIGTERM (15), use 9 for SIGKILL |

**Basic Usage (Backward Compatible):**

```python
# Works exactly like before
for event in client.query_stream("Hello"):
    print(event.text)
```

**With Cancellation:**

```python
stream = client.query_stream("Write a very long story")
for event in stream:
    if event.type == EventType.ASSISTANT_DELTA:
        print(event.text, end="", flush=True)
    
    # Stop generation based on some condition
    if len(stream.events) > 100:
        stream.cancel()
        break

print(f"\nStopped after {len(stream.events)} events")
```

**As Context Manager (Auto-Cleanup):**

```python
with client.query_stream("Hello") as stream:
    for event in stream:
        print(event.text)
        if should_stop:
            break  # Process is automatically terminated on exit
```

**With ConversationSession:**

```python
session = ConversationSession()

# Stream with cancellation support
stream = session.send_stream("Write a poem")
for event in stream:
    print(event.text, end="")
    if should_stop:
        stream.cancel()
        break

# Update session history after streaming
session.finalize_stream("Write a poem", stream)
```

---

## JSON Event Structures

These are the raw JSON structures emitted by cursor-agent in `stream-json` mode.

### System Init Event

Emitted at the start of a session with initialization metadata.

```json
{
  "type": "system",
  "subtype": "init",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "request_id": "req_abc123",
  "model": "sonnet-4",
  "workspace": "/home/user/project"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | Always `"system"` |
| `subtype` | `string` | Always `"init"` |
| `session_id` | `string` | UUID for this session |
| `request_id` | `string` | Unique request identifier |
| `model` | `string` | Model being used |
| `workspace` | `string` | Working directory path |

---

### User Event

Echo of the user's input message.

```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "text",
        "text": "What is 2+2?"
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | Always `"user"` |
| `message` | `object` | Message object |
| `message.role` | `string` | Always `"user"` |
| `message.content` | `array` | Array of content blocks |
| `message.content[].type` | `string` | Content type (`"text"`) |
| `message.content[].text` | `string` | The user's input text |

---

### Thinking Events

Events for the model's reasoning/thinking process.

**Thinking Delta (incremental):**

```json
{
  "type": "thinking",
  "subtype": "delta",
  "text": "Let me think about this...",
  "timestamp_ms": 1705123456789
}
```

**Thinking Completed:**

```json
{
  "type": "thinking",
  "subtype": "completed"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | Always `"thinking"` |
| `subtype` | `string` | `"delta"` for incremental, `"completed"` when done |
| `text` | `string` | Incremental thinking text (delta only) |
| `timestamp_ms` | `int` | Unix timestamp in milliseconds (delta only) |

---

### Assistant Events

Events for the assistant's response.

**Assistant Delta (streaming, incremental text):**

```json
{
  "type": "assistant",
  "text": "The answer",
  "timestamp_ms": 1705123456789
}
```

**Assistant Complete (full message):**

```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "text",
        "text": "The answer is 4."
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | Always `"assistant"` |
| `text` | `string` | Incremental text (delta only) |
| `timestamp_ms` | `int` | Unix timestamp (delta only, used to distinguish from complete) |
| `message` | `object` | Full message object (complete only) |
| `message.role` | `string` | Always `"assistant"` |
| `message.content` | `array` | Array of content blocks |

**Note:** Delta events have `timestamp_ms`, complete events do not. This is how the parser distinguishes them.

---

### Tool Call Events

Events for tool/function execution.

**Tool Call Started:**

```json
{
  "type": "tool-call-started",
  "tool_name": "Shell",
  "tool_call_id": "call_abc123",
  "parameters": {
    "command": "ls -la",
    "description": "List directory contents"
  }
}
```

**Tool Call Completed:**

```json
{
  "type": "tool-call-completed",
  "tool_name": "Shell",
  "tool_call_id": "call_abc123",
  "result": {
    "success": true,
    "output": "total 32\ndrwxr-xr-x 4 user user 4096 ...",
    "exit_code": 0
  },
  "duration_ms": 156
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | `"tool-call-started"` or `"tool-call-completed"` |
| `tool_name` | `string` | Name of the tool (e.g., `"Shell"`, `"Read"`, `"Write"`) |
| `tool_call_id` | `string` | Unique identifier for this tool call |
| `parameters` | `object` | Tool input parameters (started only) |
| `result` | `object` | Tool execution result (completed only) |
| `duration_ms` | `int` | Execution time in milliseconds (completed only) |

**Common Tool Names:**

| Tool | Description |
|------|-------------|
| `Shell` | Execute shell commands |
| `Read` | Read file contents |
| `Write` | Write/create files |
| `StrReplace` | Edit files with string replacement |
| `Glob` | Find files matching patterns |
| `Grep` | Search file contents |
| `LS` | List directory contents |
| `Delete` | Delete files |

---

### Result Events

Final events indicating query completion.

**Success Result:**

```json
{
  "type": "result",
  "subtype": "success",
  "result": "The answer is 4.",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "request_id": "req_abc123",
  "duration_ms": 1523,
  "duration_api_ms": 1456,
  "is_error": false
}
```

**Error Result:**

```json
{
  "type": "result",
  "subtype": "error",
  "error": "Request timed out",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "request_id": "req_abc123",
  "is_error": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | Always `"result"` |
| `subtype` | `string` | `"success"` or `"error"` |
| `result` | `string` | Final response text (success only) |
| `error` | `string` | Error message (error only) |
| `session_id` | `string` | Session UUID |
| `request_id` | `string` | Request identifier |
| `duration_ms` | `int` | Total duration in milliseconds |
| `duration_api_ms` | `int` | API call duration in milliseconds |
| `is_error` | `bool` | `true` if this is an error result |

---

## Complete Event Stream Example

Here's an example of a complete event stream for a simple query:

```json
{"type":"system","subtype":"init","session_id":"abc-123","model":"sonnet-4"}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"What is 2+2?"}]}}
{"type":"thinking","subtype":"delta","text":"Simple arithmetic...","timestamp_ms":1705123456789}
{"type":"thinking","subtype":"completed"}
{"type":"assistant","text":"The ","timestamp_ms":1705123456790}
{"type":"assistant","text":"answer ","timestamp_ms":1705123456791}
{"type":"assistant","text":"is 4.","timestamp_ms":1705123456792}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"The answer is 4."}]}}
{"type":"result","subtype":"success","result":"The answer is 4.","session_id":"abc-123","duration_ms":1523}
```

---

## Usage Examples

### Processing Events by Type

```python
from cursor_agent_api import query_stream, EventType

for event in query_stream("Hello"):
    match event.type:
        case EventType.SYSTEM_INIT:
            print(f"Session: {event.session_id}")
        case EventType.THINKING_DELTA:
            print(f"[Thinking] {event.text}")
        case EventType.ASSISTANT_DELTA:
            print(event.text, end="", flush=True)
        case EventType.TOOL_CALL_STARTED:
            tool = event.data.get("tool_name")
            print(f"\n[Tool: {tool}]")
        case EventType.TOOL_CALL_COMPLETED:
            result = event.data.get("result", {})
            print(f"[Tool completed: {result}]")
        case EventType.RESULT_SUCCESS:
            print(f"\n[Done in {event.data.get('duration_ms')}ms]")
        case EventType.RESULT_ERROR:
            print(f"\n[Error: {event.data.get('error')}]")
```

### Accessing Raw Event Data

```python
from cursor_agent_api import query_stream

for event in query_stream("List files"):
    # Access raw JSON data
    raw = event.data
    
    # Event metadata
    print(f"Type: {raw.get('type')}")
    print(f"Subtype: {raw.get('subtype')}")
    
    # Tool-specific data
    if event.type == EventType.TOOL_CALL_COMPLETED:
        tool_result = raw.get("result", {})
        exit_code = tool_result.get("exit_code")
        output = tool_result.get("output")
```
