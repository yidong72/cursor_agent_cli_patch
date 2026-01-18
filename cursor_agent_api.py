"""
Python API wrapper for cursor-agent CLI.

This module provides a clean Python interface to interact with the cursor-agent
without using its interactive CLI UI. It supports:
- Single-shot queries
- Multi-turn conversations with session resumption
- Streaming responses
- Tool call monitoring

Existing CLI Options Used:
- `--print`: Non-interactive mode
- `--output-format json|stream-json`: Structured output
- `--stream-partial-output`: Token-by-token streaming
- `--resume <session_id>`: Continue conversations
- `-f, --force`: Auto-approve commands (enableRunEverything)
- `--approve-mcps`: Auto-approve MCP servers
- `--model <model>`: Specify model
- `--workspace <path>`: Set working directory
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Iterator, Iterable, Optional, Callable, Any
from enum import Enum


class OutputFormat(Enum):
    """Output format for cursor-agent responses."""
    TEXT = "text"
    JSON = "json"
    STREAM_JSON = "stream-json"


class EventType(Enum):
    """Event types emitted in stream-json mode."""
    SYSTEM_INIT = "system:init"
    USER = "user"
    THINKING_DELTA = "thinking:delta"
    THINKING_COMPLETED = "thinking:completed"
    ASSISTANT = "assistant"           # Full message (non-streaming or final)
    ASSISTANT_DELTA = "assistant:delta"  # Partial message (streaming)
    TOOL_CALL_STARTED = "tool-call-started"
    TOOL_CALL_COMPLETED = "tool-call-completed"
    RESULT_SUCCESS = "result:success"
    RESULT_ERROR = "result:error"
    UNKNOWN = "unknown"


@dataclass
class AgentEvent:
    """Represents an event from cursor-agent stream."""
    type: EventType
    raw_type: str
    subtype: Optional[str]
    data: dict
    text: Optional[str] = None
    session_id: Optional[str] = None
    timestamp_ms: Optional[int] = None


class StreamingResponse:
    """
    Wrapper for streaming responses that supports cancellation.
    
    This class is iterable, so it can be used in for loops just like the
    original generator. It also provides a cancel() method to stop generation.
    
    Example:
        stream = client.query_stream("Write a long story")
        for event in stream:
            if event.type == EventType.ASSISTANT_DELTA:
                print(event.text, end="")
            if some_condition:
                stream.cancel()  # Stop generation
                break
    """
    
    def __init__(self, process: subprocess.Popen, parse_event: Callable[[str], Optional[AgentEvent]]):
        self._process = process
        self._parse_event = parse_event
        self._cancelled = False
        self._events: list[AgentEvent] = []
    
    def __iter__(self) -> Iterator[AgentEvent]:
        """Iterate over events from the stream."""
        if self._process.stdout:
            for line in self._process.stdout:
                if self._cancelled:
                    break
                line = line.strip()
                if line:
                    event = self._parse_event(line)
                    if event:
                        self._events.append(event)
                        yield event
        
        if not self._cancelled:
            self._process.wait()
    
    def cancel(self, signal: int = 15) -> None:
        """
        Cancel the ongoing generation.
        
        Args:
            signal: Signal to send to the process (default: SIGTERM=15)
                   Use signal=9 for SIGKILL if SIGTERM doesn't work.
        """
        if not self._cancelled and self._process.poll() is None:
            self._cancelled = True
            try:
                self._process.send_signal(signal)
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
    
    @property
    def cancelled(self) -> bool:
        """Whether the stream was cancelled."""
        return self._cancelled
    
    @property
    def events(self) -> list[AgentEvent]:
        """List of events received so far."""
        return self._events.copy()
    
    @property
    def process(self) -> subprocess.Popen:
        """The underlying subprocess (for advanced usage)."""
        return self._process
    
    def __enter__(self) -> "StreamingResponse":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Ensure process is terminated when used as context manager."""
        if self._process.poll() is None:
            self.cancel()


@dataclass
class AgentResult:
    """Result from a cursor-agent query."""
    success: bool
    result: str
    session_id: str
    request_id: Optional[str] = None
    duration_ms: Optional[int] = None
    duration_api_ms: Optional[int] = None
    error: Optional[str] = None
    events: list[AgentEvent] = field(default_factory=list)


@dataclass
class AgentConfig:
    """Configuration for cursor-agent client."""
    workspace: Optional[str] = None
    model: Optional[str] = None
    force_approve: bool = False
    approve_mcps: bool = False
    api_key: Optional[str] = None
    headers: list[str] = field(default_factory=list)
    agent_binary: str = "agent"


class CursorAgentClient:
    """
    Python client for cursor-agent CLI.
    
    Example usage:
        
        # Simple query
        client = CursorAgentClient()
        result = client.query("What is 2+2?")
        print(result.result)
        
        # Multi-turn conversation
        result1 = client.query("Remember the number 42")
        result2 = client.query("What number did I mention?", 
                               session_id=result1.session_id)
        
        # Streaming
        for event in client.query_stream("Explain Python generators"):
            if event.type == EventType.ASSISTANT:
                print(event.text, end="", flush=True)
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
    
    def _build_command(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        output_format: OutputFormat = OutputFormat.JSON,
        stream_partial: bool = False,
        mode: Optional[str] = None,
    ) -> list[str]:
        """Build the command line arguments for cursor-agent."""
        cmd = [self.config.agent_binary, "--print"]
        
        cmd.extend(["--output-format", output_format.value])
        
        if stream_partial and output_format == OutputFormat.STREAM_JSON:
            cmd.append("--stream-partial-output")
        
        if session_id:
            cmd.extend(["--resume", session_id])
        
        if self.config.workspace:
            cmd.extend(["--workspace", self.config.workspace])
        
        if self.config.model:
            cmd.extend(["--model", self.config.model])
        
        if self.config.force_approve:
            cmd.append("-f")
        
        if self.config.approve_mcps:
            cmd.append("--approve-mcps")
        
        if self.config.api_key:
            cmd.extend(["--api-key", self.config.api_key])
        
        for header in self.config.headers:
            cmd.extend(["-H", header])
        
        if mode:
            cmd.extend(["--mode", mode])
        
        # Prompt is passed via stdin, not as argument
        return cmd
    
    def _parse_event(self, line: str) -> Optional[AgentEvent]:
        """Parse a JSON line into an AgentEvent."""
        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError:
            return None
        
        raw_type = data.get("type", "unknown")
        subtype = data.get("subtype")
        
        # Determine event type
        if raw_type == "system" and subtype == "init":
            event_type = EventType.SYSTEM_INIT
        elif raw_type == "user":
            event_type = EventType.USER
        elif raw_type == "thinking":
            event_type = EventType.THINKING_DELTA if subtype == "delta" else EventType.THINKING_COMPLETED
        elif raw_type == "assistant":
            # In streaming mode, partial messages have timestamp_ms, final doesn't
            if "timestamp_ms" in data:
                event_type = EventType.ASSISTANT_DELTA
            else:
                event_type = EventType.ASSISTANT
        elif raw_type == "result":
            event_type = EventType.RESULT_SUCCESS if subtype == "success" else EventType.RESULT_ERROR
        elif raw_type == "tool-call-started":
            event_type = EventType.TOOL_CALL_STARTED
        elif raw_type == "tool-call-completed":
            event_type = EventType.TOOL_CALL_COMPLETED
        else:
            event_type = EventType.UNKNOWN
        
        # Extract text content
        text = None
        if "text" in data:
            text = data["text"]
        elif "result" in data:
            text = data["result"]
        elif "message" in data and isinstance(data["message"], dict):
            content = data["message"].get("content", [])
            if content and isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        break
        
        return AgentEvent(
            type=event_type,
            raw_type=raw_type,
            subtype=subtype,
            data=data,
            text=text,
            session_id=data.get("session_id"),
            timestamp_ms=data.get("timestamp_ms"),
        )
    
    def query(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
        mode: Optional[str] = None,
    ) -> AgentResult:
        """
        Send a query to cursor-agent and get a result.
        
        Args:
            prompt: The prompt/query to send
            session_id: Optional session ID to resume a conversation
            timeout: Optional timeout in seconds
            mode: Optional mode ('plan' or 'ask')
        
        Returns:
            AgentResult with the response
        """
        cmd = self._build_command(
            prompt, 
            session_id=session_id, 
            output_format=OutputFormat.JSON,
            mode=mode,
        )
        
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            if result.returncode != 0:
                return AgentResult(
                    success=False,
                    result="",
                    session_id=session_id or "",
                    error=result.stderr or f"Exit code: {result.returncode}",
                )
            
            # Parse the JSON response
            try:
                data = json.loads(result.stdout.strip())
                return AgentResult(
                    success=data.get("subtype") == "success",
                    result=data.get("result", ""),
                    session_id=data.get("session_id", ""),
                    request_id=data.get("request_id"),
                    duration_ms=data.get("duration_ms"),
                    duration_api_ms=data.get("duration_api_ms"),
                    error=data.get("error") if data.get("is_error") else None,
                )
            except json.JSONDecodeError as e:
                return AgentResult(
                    success=False,
                    result=result.stdout,
                    session_id=session_id or "",
                    error=f"Failed to parse JSON: {e}",
                )
        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                result="",
                session_id=session_id or "",
                error="Request timed out",
            )
        except Exception as e:
            return AgentResult(
                success=False,
                result="",
                session_id=session_id or "",
                error=str(e),
            )
    
    def query_stream(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        stream_partial: bool = True,
        mode: Optional[str] = None,
    ) -> StreamingResponse:
        """
        Send a query to cursor-agent and stream events.
        
        Args:
            prompt: The prompt/query to send
            session_id: Optional session ID to resume a conversation
            stream_partial: Whether to stream partial text deltas
            mode: Optional mode ('plan' or 'ask')
        
        Returns:
            StreamingResponse that can be iterated over and cancelled.
            
        Example:
            # Basic usage (backward compatible)
            for event in client.query_stream("Hello"):
                print(event.text)
            
            # With cancellation
            stream = client.query_stream("Write a long story")
            for event in stream:
                print(event.text, end="")
                if should_stop:
                    stream.cancel()
                    break
            
            # As context manager (auto-cleanup)
            with client.query_stream("Hello") as stream:
                for event in stream:
                    print(event.text)
        """
        cmd = self._build_command(
            prompt,
            session_id=session_id,
            output_format=OutputFormat.STREAM_JSON,
            stream_partial=stream_partial,
            mode=mode,
        )
        
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        
        # Send prompt
        if process.stdin:
            process.stdin.write(prompt)
            process.stdin.close()
        
        return StreamingResponse(process, self._parse_event)
    
    def create_session(self) -> str:
        """Create a new empty chat session and return its ID."""
        result = subprocess.run(
            [self.config.agent_binary, "create-chat"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    
    def list_models(self) -> list[str]:
        """List available models."""
        result = subprocess.run(
            [self.config.agent_binary, "--list-models"],
            capture_output=True,
            text=True,
        )
        # Parse the output - it's typically a list of model names
        return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]


class ConversationSession:
    """
    Manages a multi-turn conversation session.
    
    Example:
        session = ConversationSession()
        
        response1 = session.send("Hello, my name is Alice")
        print(response1.result)
        
        response2 = session.send("What's my name?")
        print(response2.result)  # Should mention Alice
    """
    
    def __init__(
        self,
        client: Optional[CursorAgentClient] = None,
        session_id: Optional[str] = None,
    ):
        self.client = client or CursorAgentClient()
        self._session_id = session_id
        self._history: list[tuple[str, AgentResult]] = []
    
    @property
    def session_id(self) -> Optional[str]:
        return self._session_id
    
    @property
    def history(self) -> list[tuple[str, AgentResult]]:
        return self._history.copy()
    
    def send(
        self,
        prompt: str,
        timeout: Optional[int] = None,
        mode: Optional[str] = None,
    ) -> AgentResult:
        """Send a message and get a response."""
        result = self.client.query(
            prompt,
            session_id=self._session_id,
            timeout=timeout,
            mode=mode,
        )
        
        # Update session ID from response
        if result.session_id:
            self._session_id = result.session_id
        
        self._history.append((prompt, result))
        return result
    
    def send_stream(
        self,
        prompt: str,
        stream_partial: bool = True,
        mode: Optional[str] = None,
    ) -> StreamingResponse:
        """
        Send a message and stream the response.
        
        Returns:
            StreamingResponse that can be iterated and cancelled.
            
        Note:
            Call finalize_stream() after iteration to update session history.
            
        Example:
            stream = session.send_stream("Hello")
            for event in stream:
                print(event.text, end="")
                if should_stop:
                    stream.cancel()
                    break
            session.finalize_stream(prompt, stream)
        """
        return self.client.query_stream(
            prompt,
            session_id=self._session_id,
            stream_partial=stream_partial,
            mode=mode,
        )
    
    def finalize_stream(self, prompt: str, stream: StreamingResponse) -> Optional[AgentResult]:
        """
        Finalize a streaming response and update session history.
        
        Call this after iterating over a StreamingResponse to update
        the session ID and conversation history.
        
        Args:
            prompt: The original prompt sent
            stream: The StreamingResponse that was iterated
            
        Returns:
            AgentResult reconstructed from events, or None if no result event found
        """
        events = stream.events
        
        # Update session ID from any event that has it
        for event in events:
            if event.session_id:
                self._session_id = event.session_id
        
        # Reconstruct result from events for history
        result_event = next(
            (e for e in reversed(events) if e.type in (EventType.RESULT_SUCCESS, EventType.RESULT_ERROR)),
            None
        )
        if result_event:
            result = AgentResult(
                success=result_event.type == EventType.RESULT_SUCCESS,
                result=result_event.text or "",
                session_id=self._session_id or "",
                events=events,
            )
            self._history.append((prompt, result))
            return result
        return None
    
    def reset(self):
        """Start a new session."""
        self._session_id = None
        self._history = []


# Async support (optional, requires asyncio)
import asyncio
from concurrent.futures import ThreadPoolExecutor


class AsyncCursorAgentClient:
    """
    Async wrapper for CursorAgentClient.
    
    Example:
        async def main():
            client = AsyncCursorAgentClient()
            result = await client.query("What is 2+2?")
            print(result.result)
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self._sync_client = CursorAgentClient(config)
        self._executor = ThreadPoolExecutor(max_workers=4)
    
    async def query(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
        mode: Optional[str] = None,
    ) -> AgentResult:
        """Async version of query."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._sync_client.query(prompt, session_id, timeout, mode)
        )
    
    async def query_stream(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        stream_partial: bool = True,
        mode: Optional[str] = None,
        callback: Optional[Callable[[AgentEvent], None]] = None,
    ) -> list[AgentEvent]:
        """
        Async streaming query.
        
        Since Python subprocess doesn't support true async iteration,
        this runs in a thread and collects events, optionally calling
        a callback for each event.
        """
        def _stream():
            events = []
            for event in self._sync_client.query_stream(
                prompt, session_id, stream_partial, mode
            ):
                events.append(event)
                if callback:
                    callback(event)
            return events
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _stream)
    
    async def create_session(self) -> str:
        """Async version of create_session."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_client.create_session
        )


class AsyncConversationSession:
    """Async version of ConversationSession."""
    
    def __init__(
        self,
        client: Optional[AsyncCursorAgentClient] = None,
        session_id: Optional[str] = None,
    ):
        self.client = client or AsyncCursorAgentClient()
        self._session_id = session_id
        self._history: list[tuple[str, AgentResult]] = []
    
    @property
    def session_id(self) -> Optional[str]:
        return self._session_id
    
    async def send(
        self,
        prompt: str,
        timeout: Optional[int] = None,
        mode: Optional[str] = None,
    ) -> AgentResult:
        """Send a message and get a response."""
        result = await self.client.query(
            prompt,
            session_id=self._session_id,
            timeout=timeout,
            mode=mode,
        )
        
        if result.session_id:
            self._session_id = result.session_id
        
        self._history.append((prompt, result))
        return result


# Convenience functions
def query(prompt: str, **kwargs) -> AgentResult:
    """Quick single-shot query."""
    client = CursorAgentClient()
    return client.query(prompt, **kwargs)


def query_stream(prompt: str, **kwargs) -> StreamingResponse:
    """
    Quick single-shot streaming query.
    
    Returns:
        StreamingResponse that can be iterated and cancelled.
        
    Example:
        # Basic usage
        for event in query_stream("Hello"):
            print(event.text)
        
        # With cancellation
        stream = query_stream("Write a long story")
        for event in stream:
            print(event.text, end="")
            if should_stop:
                stream.cancel()
                break
    """
    client = CursorAgentClient()
    return client.query_stream(prompt, **kwargs)


async def aquery(prompt: str, **kwargs) -> AgentResult:
    """Async quick single-shot query."""
    client = AsyncCursorAgentClient()
    return await client.query(prompt, **kwargs)


def collect_text(events: Iterable[AgentEvent], include_thinking: bool = False) -> str:
    """
    Collect all text from a stream of events.
    
    Args:
        events: Iterable of AgentEvents (StreamingResponse or list)
        include_thinking: Whether to include thinking text
    
    Returns:
        Concatenated text from the stream
    """
    parts = []
    for event in events:
        if event.type == EventType.ASSISTANT_DELTA and event.text:
            parts.append(event.text)
        elif event.type == EventType.THINKING_DELTA and include_thinking and event.text:
            parts.append(f"[thinking: {event.text}]")
        elif event.type == EventType.RESULT_SUCCESS:
            # Use the final result instead if no deltas were collected
            if not parts and event.text:
                return event.text
    return "".join(parts)


if __name__ == "__main__":
    # Demo usage
    print("=== Cursor Agent API Demo ===\n")
    
    # Simple query
    print("1. Simple query:")
    result = query("What is 2+2?")
    print(f"   Result: {result.result}")
    print(f"   Session ID: {result.session_id}")
    print()
    
    # Multi-turn conversation
    print("2. Multi-turn conversation:")
    session = ConversationSession()
    
    r1 = session.send("Remember the secret code: ALPHA-7")
    print(f"   Agent: {r1.result}")
    
    r2 = session.send("What is the secret code?")
    print(f"   Agent: {r2.result}")
    print()
    
    # Streaming
    print("3. Streaming response:")
    print("   Agent: ", end="", flush=True)
    for event in query_stream("Write a haiku about coding"):
        if event.type == EventType.ASSISTANT and event.text:
            print(event.text, end="", flush=True)
    print("\n")
