#!/usr/bin/env python3
"""
Unit tests for cursor_agent_api with full coverage.

Run with: python3 -m pytest test_unit.py -v
Or: python3 test_unit.py
"""

import json
import subprocess
import unittest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from io import StringIO

from cursor_agent_api import (
    # Enums
    OutputFormat,
    EventType,
    # Data classes
    AgentConfig,
    AgentEvent,
    AgentResult,
    StreamingResponse,
    # Classes
    CursorAgentClient,
    ConversationSession,
    AsyncCursorAgentClient,
    AsyncConversationSession,
    # Convenience functions
    query,
    query_stream,
    aquery,
    collect_text,
)


class TestOutputFormat(unittest.TestCase):
    """Tests for OutputFormat enum."""
    
    def test_values(self):
        self.assertEqual(OutputFormat.TEXT.value, "text")
        self.assertEqual(OutputFormat.JSON.value, "json")
        self.assertEqual(OutputFormat.STREAM_JSON.value, "stream-json")
    
    def test_all_formats_defined(self):
        formats = list(OutputFormat)
        self.assertEqual(len(formats), 3)


class TestEventType(unittest.TestCase):
    """Tests for EventType enum."""
    
    def test_values(self):
        self.assertEqual(EventType.SYSTEM_INIT.value, "system:init")
        self.assertEqual(EventType.USER.value, "user")
        self.assertEqual(EventType.THINKING_DELTA.value, "thinking:delta")
        self.assertEqual(EventType.THINKING_COMPLETED.value, "thinking:completed")
        self.assertEqual(EventType.ASSISTANT.value, "assistant")
        self.assertEqual(EventType.ASSISTANT_DELTA.value, "assistant:delta")
        self.assertEqual(EventType.TOOL_CALL_STARTED.value, "tool-call-started")
        self.assertEqual(EventType.TOOL_CALL_COMPLETED.value, "tool-call-completed")
        self.assertEqual(EventType.RESULT_SUCCESS.value, "result:success")
        self.assertEqual(EventType.RESULT_ERROR.value, "result:error")
        self.assertEqual(EventType.UNKNOWN.value, "unknown")
    
    def test_all_event_types_defined(self):
        events = list(EventType)
        self.assertEqual(len(events), 11)


class TestAgentConfig(unittest.TestCase):
    """Tests for AgentConfig dataclass."""
    
    def test_default_values(self):
        config = AgentConfig()
        self.assertIsNone(config.workspace)
        self.assertIsNone(config.model)
        self.assertFalse(config.force_approve)
        self.assertFalse(config.approve_mcps)
        self.assertIsNone(config.api_key)
        self.assertEqual(config.headers, [])
        self.assertEqual(config.agent_binary, "agent")
    
    def test_custom_values(self):
        config = AgentConfig(
            workspace="/home/user/project",
            model="gpt-4",
            force_approve=True,
            approve_mcps=True,
            api_key="sk-test",
            headers=["X-Custom: value"],
            agent_binary="/usr/bin/agent",
        )
        self.assertEqual(config.workspace, "/home/user/project")
        self.assertEqual(config.model, "gpt-4")
        self.assertTrue(config.force_approve)
        self.assertTrue(config.approve_mcps)
        self.assertEqual(config.api_key, "sk-test")
        self.assertEqual(config.headers, ["X-Custom: value"])
        self.assertEqual(config.agent_binary, "/usr/bin/agent")


class TestAgentEvent(unittest.TestCase):
    """Tests for AgentEvent dataclass."""
    
    def test_required_fields(self):
        event = AgentEvent(
            type=EventType.ASSISTANT,
            raw_type="assistant",
            subtype=None,
            data={"text": "Hello"},
        )
        self.assertEqual(event.type, EventType.ASSISTANT)
        self.assertEqual(event.raw_type, "assistant")
        self.assertIsNone(event.subtype)
        self.assertEqual(event.data, {"text": "Hello"})
    
    def test_optional_fields(self):
        event = AgentEvent(
            type=EventType.ASSISTANT_DELTA,
            raw_type="assistant",
            subtype=None,
            data={},
            text="Hello",
            session_id="abc-123",
            timestamp_ms=1234567890,
        )
        self.assertEqual(event.text, "Hello")
        self.assertEqual(event.session_id, "abc-123")
        self.assertEqual(event.timestamp_ms, 1234567890)
    
    def test_default_optional_fields(self):
        event = AgentEvent(
            type=EventType.UNKNOWN,
            raw_type="unknown",
            subtype=None,
            data={},
        )
        self.assertIsNone(event.text)
        self.assertIsNone(event.session_id)
        self.assertIsNone(event.timestamp_ms)


class TestAgentResult(unittest.TestCase):
    """Tests for AgentResult dataclass."""
    
    def test_required_fields(self):
        result = AgentResult(
            success=True,
            result="Hello",
            session_id="abc-123",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.result, "Hello")
        self.assertEqual(result.session_id, "abc-123")
    
    def test_optional_fields(self):
        result = AgentResult(
            success=True,
            result="Hello",
            session_id="abc-123",
            request_id="req-456",
            duration_ms=1000,
            duration_api_ms=900,
            error=None,
            events=[],
        )
        self.assertEqual(result.request_id, "req-456")
        self.assertEqual(result.duration_ms, 1000)
        self.assertEqual(result.duration_api_ms, 900)
        self.assertIsNone(result.error)
        self.assertEqual(result.events, [])
    
    def test_error_result(self):
        result = AgentResult(
            success=False,
            result="",
            session_id="abc-123",
            error="Something went wrong",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Something went wrong")


class TestStreamingResponse(unittest.TestCase):
    """Tests for StreamingResponse class."""
    
    def _create_mock_process(self, lines):
        """Helper to create a mock process with stdout lines."""
        process = Mock(spec=subprocess.Popen)
        process.stdout = StringIO("\n".join(lines) + "\n" if lines else "")
        process.poll.return_value = None
        process.wait.return_value = 0
        return process
    
    def _create_parse_event(self):
        """Helper to create a simple parse_event function."""
        def parse_event(line):
            try:
                data = json.loads(line)
                return AgentEvent(
                    type=EventType.ASSISTANT_DELTA,
                    raw_type=data.get("type", "unknown"),
                    subtype=data.get("subtype"),
                    data=data,
                    text=data.get("text"),
                    session_id=data.get("session_id"),
                    timestamp_ms=data.get("timestamp_ms"),
                )
            except json.JSONDecodeError:
                return None
        return parse_event
    
    def test_iteration(self):
        """Test iterating over events."""
        lines = [
            '{"type": "assistant", "text": "Hello", "timestamp_ms": 123}',
            '{"type": "assistant", "text": " World", "timestamp_ms": 124}',
        ]
        process = self._create_mock_process(lines)
        stream = StreamingResponse(process, self._create_parse_event())
        
        events = list(stream)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].text, "Hello")
        self.assertEqual(events[1].text, " World")
    
    def test_events_property(self):
        """Test events property returns copy of events."""
        lines = ['{"type": "assistant", "text": "Hi", "timestamp_ms": 123}']
        process = self._create_mock_process(lines)
        stream = StreamingResponse(process, self._create_parse_event())
        
        list(stream)  # Consume iterator
        
        events = stream.events
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].text, "Hi")
        
        # Verify it's a copy
        events.append(None)
        self.assertEqual(len(stream.events), 1)
    
    def test_cancel(self):
        """Test cancelling the stream."""
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        process.wait.return_value = 0
        process.stdout = iter([])
        
        stream = StreamingResponse(process, self._create_parse_event())
        
        self.assertFalse(stream.cancelled)
        stream.cancel()
        self.assertTrue(stream.cancelled)
        process.send_signal.assert_called_once_with(15)
    
    def test_cancel_with_custom_signal(self):
        """Test cancelling with custom signal."""
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        process.wait.return_value = 0
        
        stream = StreamingResponse(process, self._create_parse_event())
        stream.cancel(signal=9)
        
        process.send_signal.assert_called_once_with(9)
    
    def test_cancel_already_cancelled(self):
        """Test cancelling an already cancelled stream."""
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        process.wait.return_value = 0
        
        stream = StreamingResponse(process, self._create_parse_event())
        stream.cancel()
        stream.cancel()  # Second cancel should be no-op
        
        self.assertEqual(process.send_signal.call_count, 1)
    
    def test_cancel_process_already_terminated(self):
        """Test cancelling when process already terminated."""
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = 0  # Already terminated
        
        stream = StreamingResponse(process, self._create_parse_event())
        stream.cancel()
        
        process.send_signal.assert_not_called()
    
    def test_cancel_with_timeout(self):
        """Test cancel falls back to kill on timeout."""
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 2), 0]
        
        stream = StreamingResponse(process, self._create_parse_event())
        stream.cancel()
        
        process.send_signal.assert_called_once()
        process.kill.assert_called_once()
    
    def test_context_manager(self):
        """Test using as context manager."""
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        process.wait.return_value = 0
        process.stdout = iter([])
        
        stream = StreamingResponse(process, self._create_parse_event())
        
        with stream as s:
            self.assertIs(s, stream)
        
        # Process should be terminated on exit
        process.send_signal.assert_called()
    
    def test_context_manager_process_finished(self):
        """Test context manager when process already finished."""
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = 0  # Already finished
        process.stdout = iter([])
        
        stream = StreamingResponse(process, self._create_parse_event())
        
        with stream:
            pass
        
        # Should not try to cancel finished process
        process.send_signal.assert_not_called()
    
    def test_process_property(self):
        """Test process property."""
        process = Mock(spec=subprocess.Popen)
        stream = StreamingResponse(process, self._create_parse_event())
        self.assertIs(stream.process, process)
    
    def test_iteration_stops_on_cancel(self):
        """Test iteration stops when cancelled."""
        # Create a process that would yield many lines
        lines = [f'{{"type": "assistant", "text": "{i}", "timestamp_ms": {i}}}' for i in range(100)]
        
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        process.wait.return_value = 0
        
        # Use a generator for stdout to allow interleaved cancel
        def line_generator():
            for line in lines:
                yield line + "\n"
        
        process.stdout = line_generator()
        stream = StreamingResponse(process, self._create_parse_event())
        
        collected = []
        for event in stream:
            collected.append(event)
            if len(collected) >= 5:
                stream.cancel()
        
        self.assertEqual(len(collected), 5)
        self.assertTrue(stream.cancelled)
    
    def test_empty_lines_skipped(self):
        """Test empty lines are skipped."""
        lines = [
            '{"type": "assistant", "text": "Hi", "timestamp_ms": 123}',
            '',
            '   ',
            '{"type": "assistant", "text": "Bye", "timestamp_ms": 124}',
        ]
        process = self._create_mock_process(lines)
        stream = StreamingResponse(process, self._create_parse_event())
        
        events = list(stream)
        self.assertEqual(len(events), 2)
    
    def test_invalid_json_skipped(self):
        """Test invalid JSON lines are skipped."""
        lines = [
            '{"type": "assistant", "text": "Hi", "timestamp_ms": 123}',
            'not valid json',
            '{"type": "assistant", "text": "Bye", "timestamp_ms": 124}',
        ]
        process = self._create_mock_process(lines)
        stream = StreamingResponse(process, self._create_parse_event())
        
        events = list(stream)
        self.assertEqual(len(events), 2)


class TestCursorAgentClient(unittest.TestCase):
    """Tests for CursorAgentClient class."""
    
    def test_init_default_config(self):
        """Test initialization with default config."""
        client = CursorAgentClient()
        self.assertIsNotNone(client.config)
        self.assertEqual(client.config.agent_binary, "agent")
    
    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = AgentConfig(model="gpt-4", workspace="/tmp")
        client = CursorAgentClient(config)
        self.assertEqual(client.config.model, "gpt-4")
        self.assertEqual(client.config.workspace, "/tmp")
    
    def test_build_command_basic(self):
        """Test basic command building."""
        client = CursorAgentClient()
        cmd = client._build_command("Hello", output_format=OutputFormat.JSON)
        
        self.assertIn("agent", cmd)
        self.assertIn("--print", cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("json", cmd)
    
    def test_build_command_with_session(self):
        """Test command building with session ID."""
        client = CursorAgentClient()
        cmd = client._build_command("Hello", session_id="abc-123")
        
        self.assertIn("--resume", cmd)
        self.assertIn("abc-123", cmd)
    
    def test_build_command_with_all_options(self):
        """Test command building with all options."""
        config = AgentConfig(
            workspace="/tmp",
            model="gpt-4",
            force_approve=True,
            approve_mcps=True,
            api_key="sk-test",
            headers=["X-Custom: value"],
        )
        client = CursorAgentClient(config)
        cmd = client._build_command(
            "Hello",
            output_format=OutputFormat.STREAM_JSON,
            stream_partial=True,
            mode="plan",
        )
        
        self.assertIn("--workspace", cmd)
        self.assertIn("/tmp", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("gpt-4", cmd)
        self.assertIn("-f", cmd)
        self.assertIn("--approve-mcps", cmd)
        self.assertIn("--api-key", cmd)
        self.assertIn("sk-test", cmd)
        self.assertIn("-H", cmd)
        self.assertIn("X-Custom: value", cmd)
        self.assertIn("--stream-partial-output", cmd)
        self.assertIn("--mode", cmd)
        self.assertIn("plan", cmd)
    
    def test_build_command_stream_partial_only_with_stream_json(self):
        """Test stream_partial flag only added with STREAM_JSON format."""
        client = CursorAgentClient()
        
        # With STREAM_JSON
        cmd1 = client._build_command("Hi", output_format=OutputFormat.STREAM_JSON, stream_partial=True)
        self.assertIn("--stream-partial-output", cmd1)
        
        # With JSON (should not include)
        cmd2 = client._build_command("Hi", output_format=OutputFormat.JSON, stream_partial=True)
        self.assertNotIn("--stream-partial-output", cmd2)
    
    def test_parse_event_system_init(self):
        """Test parsing system init event."""
        client = CursorAgentClient()
        line = '{"type": "system", "subtype": "init", "session_id": "abc-123"}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.SYSTEM_INIT)
        self.assertEqual(event.raw_type, "system")
        self.assertEqual(event.subtype, "init")
        self.assertEqual(event.session_id, "abc-123")
    
    def test_parse_event_user(self):
        """Test parsing user event."""
        client = CursorAgentClient()
        line = '{"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "Hello"}]}}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.USER)
        self.assertEqual(event.text, "Hello")
    
    def test_parse_event_thinking_delta(self):
        """Test parsing thinking delta event."""
        client = CursorAgentClient()
        line = '{"type": "thinking", "subtype": "delta", "text": "Thinking...", "timestamp_ms": 123}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.THINKING_DELTA)
        self.assertEqual(event.text, "Thinking...")
    
    def test_parse_event_thinking_completed(self):
        """Test parsing thinking completed event."""
        client = CursorAgentClient()
        line = '{"type": "thinking", "subtype": "completed"}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.THINKING_COMPLETED)
    
    def test_parse_event_assistant_delta(self):
        """Test parsing assistant delta event (with timestamp)."""
        client = CursorAgentClient()
        line = '{"type": "assistant", "text": "Hello", "timestamp_ms": 123}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.ASSISTANT_DELTA)
        self.assertEqual(event.text, "Hello")
        self.assertEqual(event.timestamp_ms, 123)
    
    def test_parse_event_assistant_complete(self):
        """Test parsing assistant complete event (without timestamp)."""
        client = CursorAgentClient()
        line = '{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi there"}]}}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.ASSISTANT)
        self.assertEqual(event.text, "Hi there")
    
    def test_parse_event_tool_call_started(self):
        """Test parsing tool call started event."""
        client = CursorAgentClient()
        line = '{"type": "tool-call-started", "tool_name": "Shell", "parameters": {"command": "ls"}}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.TOOL_CALL_STARTED)
    
    def test_parse_event_tool_call_completed(self):
        """Test parsing tool call completed event."""
        client = CursorAgentClient()
        line = '{"type": "tool-call-completed", "tool_name": "Shell", "result": {"output": "file.txt"}}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.TOOL_CALL_COMPLETED)
    
    def test_parse_event_result_success(self):
        """Test parsing result success event."""
        client = CursorAgentClient()
        line = '{"type": "result", "subtype": "success", "result": "Done!", "session_id": "abc"}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.RESULT_SUCCESS)
        self.assertEqual(event.text, "Done!")
    
    def test_parse_event_result_error(self):
        """Test parsing result error event."""
        client = CursorAgentClient()
        line = '{"type": "result", "subtype": "error", "error": "Failed"}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.RESULT_ERROR)
    
    def test_parse_event_unknown(self):
        """Test parsing unknown event type."""
        client = CursorAgentClient()
        line = '{"type": "custom_event", "data": "something"}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.UNKNOWN)
    
    def test_parse_event_invalid_json(self):
        """Test parsing invalid JSON returns None."""
        client = CursorAgentClient()
        line = 'not valid json'
        
        event = client._parse_event(line)
        
        self.assertIsNone(event)
    
    @patch('cursor_agent_api.client.subprocess.run')
    def test_query_success(self, mock_run):
        """Test successful query."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"type": "result", "subtype": "success", "result": "4", "session_id": "abc", "request_id": "req", "duration_ms": 100, "duration_api_ms": 90}',
            stderr='',
        )
        
        client = CursorAgentClient()
        result = client.query("What is 2+2?")
        
        self.assertTrue(result.success)
        self.assertEqual(result.result, "4")
        self.assertEqual(result.session_id, "abc")
        self.assertEqual(result.request_id, "req")
        self.assertEqual(result.duration_ms, 100)
    
    @patch('cursor_agent_api.client.subprocess.run')
    def test_query_error_return_code(self, mock_run):
        """Test query with non-zero return code."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout='',
            stderr='Error message',
        )
        
        client = CursorAgentClient()
        result = client.query("test")
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Error message")
    
    @patch('cursor_agent_api.client.subprocess.run')
    def test_query_invalid_json_response(self, mock_run):
        """Test query with invalid JSON response."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='not valid json',
            stderr='',
        )
        
        client = CursorAgentClient()
        result = client.query("test")
        
        self.assertFalse(result.success)
        self.assertIn("Failed to parse JSON", result.error)
    
    @patch('cursor_agent_api.client.subprocess.run')
    def test_query_timeout(self, mock_run):
        """Test query with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)
        
        client = CursorAgentClient()
        result = client.query("test", timeout=30)
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Request timed out")
    
    @patch('cursor_agent_api.client.subprocess.run')
    def test_query_exception(self, mock_run):
        """Test query with exception."""
        mock_run.side_effect = Exception("Connection failed")
        
        client = CursorAgentClient()
        result = client.query("test")
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Connection failed")
    
    @patch('cursor_agent_api.client.subprocess.run')
    def test_query_with_mode(self, mock_run):
        """Test query with mode parameter."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"type": "result", "subtype": "success", "result": "ok", "session_id": "abc"}',
            stderr='',
        )
        
        client = CursorAgentClient()
        client.query("test", mode="plan")
        
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        self.assertIn("--mode", cmd)
        self.assertIn("plan", cmd)
    
    @patch('cursor_agent_api.client.subprocess.Popen')
    def test_query_stream(self, mock_popen):
        """Test streaming query."""
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_process.stdout = StringIO('{"type": "assistant", "text": "Hi", "timestamp_ms": 123}\n')
        mock_process.stderr = Mock()
        mock_process.poll.return_value = None
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process
        
        client = CursorAgentClient()
        stream = client.query_stream("Hello")
        
        self.assertIsInstance(stream, StreamingResponse)
        
        events = list(stream)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].text, "Hi")
    
    @patch('cursor_agent_api.client.subprocess.run')
    def test_create_session(self, mock_run):
        """Test creating a new session."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='abc-123-session\n',
            stderr='',
        )
        
        client = CursorAgentClient()
        session_id = client.create_session()
        
        self.assertEqual(session_id, "abc-123-session")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("create-chat", cmd)
    
    @patch('cursor_agent_api.client.subprocess.run')
    def test_list_models(self, mock_run):
        """Test listing models."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='gpt-4\nsonnet-4\nclaude-3\n',
            stderr='',
        )
        
        client = CursorAgentClient()
        models = client.list_models()
        
        self.assertEqual(models, ['gpt-4', 'sonnet-4', 'claude-3'])
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("--list-models", cmd)


class TestConversationSession(unittest.TestCase):
    """Tests for ConversationSession class."""
    
    def test_init_default(self):
        """Test default initialization."""
        session = ConversationSession()
        
        self.assertIsNotNone(session.client)
        self.assertIsNone(session.session_id)
        self.assertEqual(session.history, [])
    
    def test_init_with_client(self):
        """Test initialization with custom client."""
        client = CursorAgentClient(AgentConfig(model="gpt-4"))
        session = ConversationSession(client=client)
        
        self.assertIs(session.client, client)
    
    def test_init_with_session_id(self):
        """Test initialization with existing session ID."""
        session = ConversationSession(session_id="abc-123")
        
        self.assertEqual(session.session_id, "abc-123")
    
    @patch.object(CursorAgentClient, 'query')
    def test_send(self, mock_query):
        """Test sending a message."""
        mock_query.return_value = AgentResult(
            success=True,
            result="Hello!",
            session_id="new-session",
        )
        
        session = ConversationSession()
        result = session.send("Hi")
        
        self.assertTrue(result.success)
        self.assertEqual(result.result, "Hello!")
        self.assertEqual(session.session_id, "new-session")
        self.assertEqual(len(session.history), 1)
        self.assertEqual(session.history[0], ("Hi", result))
    
    @patch.object(CursorAgentClient, 'query')
    def test_send_maintains_session(self, mock_query):
        """Test session ID is maintained across calls."""
        mock_query.side_effect = [
            AgentResult(success=True, result="Hi", session_id="sess-1"),
            AgentResult(success=True, result="Bye", session_id="sess-1"),
        ]
        
        session = ConversationSession()
        session.send("Hello")
        session.send("Goodbye")
        
        # Second call should use session_id from first call
        self.assertEqual(mock_query.call_count, 2)
        second_call = mock_query.call_args_list[1]
        self.assertEqual(second_call[1]['session_id'], "sess-1")
    
    @patch.object(CursorAgentClient, 'query_stream')
    def test_send_stream(self, mock_query_stream):
        """Test streaming send."""
        mock_stream = Mock(spec=StreamingResponse)
        mock_query_stream.return_value = mock_stream
        
        session = ConversationSession()
        stream = session.send_stream("Hello")
        
        self.assertIs(stream, mock_stream)
    
    @patch.object(CursorAgentClient, 'query_stream')
    def test_finalize_stream(self, mock_query_stream):
        """Test finalizing stream updates history."""
        mock_stream = Mock(spec=StreamingResponse)
        mock_stream.events = [
            AgentEvent(
                type=EventType.SYSTEM_INIT,
                raw_type="system",
                subtype="init",
                data={},
                session_id="sess-123",
            ),
            AgentEvent(
                type=EventType.RESULT_SUCCESS,
                raw_type="result",
                subtype="success",
                data={"result": "Done"},
                text="Done",
            ),
        ]
        mock_query_stream.return_value = mock_stream
        
        session = ConversationSession()
        stream = session.send_stream("Hello")
        result = session.finalize_stream("Hello", stream)
        
        self.assertEqual(session.session_id, "sess-123")
        self.assertEqual(len(session.history), 1)
        self.assertTrue(result.success)
        self.assertEqual(result.result, "Done")
    
    @patch.object(CursorAgentClient, 'query_stream')
    def test_finalize_stream_no_result(self, mock_query_stream):
        """Test finalizing stream with no result event."""
        mock_stream = Mock(spec=StreamingResponse)
        mock_stream.events = [
            AgentEvent(
                type=EventType.ASSISTANT_DELTA,
                raw_type="assistant",
                subtype=None,
                data={},
                text="Hi",
            ),
        ]
        
        session = ConversationSession()
        result = session.finalize_stream("Hello", mock_stream)
        
        self.assertIsNone(result)
        self.assertEqual(len(session.history), 0)
    
    def test_reset(self):
        """Test resetting session."""
        session = ConversationSession(session_id="abc-123")
        session._history = [("Hi", Mock())]
        
        session.reset()
        
        self.assertIsNone(session.session_id)
        self.assertEqual(session.history, [])
    
    def test_history_returns_copy(self):
        """Test history property returns a copy."""
        session = ConversationSession()
        session._history = [("Hi", Mock())]
        
        history = session.history
        history.append(("Bye", Mock()))
        
        self.assertEqual(len(session.history), 1)


class TestAsyncCursorAgentClient(unittest.TestCase):
    """Tests for AsyncCursorAgentClient class."""
    
    def test_init_default(self):
        """Test default initialization."""
        client = AsyncCursorAgentClient()
        self.assertIsNotNone(client._sync_client)
        self.assertIsNotNone(client._executor)
    
    def test_init_with_config(self):
        """Test initialization with config."""
        config = AgentConfig(model="gpt-4")
        client = AsyncCursorAgentClient(config)
        self.assertEqual(client._sync_client.config.model, "gpt-4")
    
    @patch.object(CursorAgentClient, 'query')
    def test_async_query(self, mock_query):
        """Test async query."""
        import asyncio
        
        mock_query.return_value = AgentResult(
            success=True,
            result="4",
            session_id="abc",
        )
        
        client = AsyncCursorAgentClient()
        
        async def run_test():
            return await client.query("What is 2+2?")
        
        result = asyncio.run(run_test())
        
        self.assertTrue(result.success)
        self.assertEqual(result.result, "4")
    
    @patch.object(CursorAgentClient, 'query_stream')
    def test_async_query_stream(self, mock_query_stream):
        """Test async query stream."""
        import asyncio
        
        # Create mock events
        mock_events = [
            AgentEvent(type=EventType.ASSISTANT_DELTA, raw_type="assistant", subtype=None, data={}, text="Hi"),
        ]
        
        mock_stream = Mock(spec=StreamingResponse)
        mock_stream.__iter__ = Mock(return_value=iter(mock_events))
        mock_query_stream.return_value = mock_stream
        
        client = AsyncCursorAgentClient()
        collected = []
        
        async def run_test():
            return await client.query_stream("Hello", callback=lambda e: collected.append(e))
        
        events = asyncio.run(run_test())
        
        self.assertEqual(len(events), 1)
        self.assertEqual(len(collected), 1)
    
    @patch.object(CursorAgentClient, 'create_session')
    def test_async_create_session(self, mock_create_session):
        """Test async create session."""
        import asyncio
        
        mock_create_session.return_value = "new-session-123"
        
        client = AsyncCursorAgentClient()
        
        async def run_test():
            return await client.create_session()
        
        session_id = asyncio.run(run_test())
        
        self.assertEqual(session_id, "new-session-123")


class TestAsyncConversationSession(unittest.TestCase):
    """Tests for AsyncConversationSession class."""
    
    def test_init_default(self):
        """Test default initialization."""
        session = AsyncConversationSession()
        self.assertIsNotNone(session.client)
        self.assertIsNone(session.session_id)
    
    def test_init_with_session_id(self):
        """Test initialization with session ID."""
        session = AsyncConversationSession(session_id="abc-123")
        self.assertEqual(session.session_id, "abc-123")
    
    def test_async_send(self):
        """Test async send."""
        import asyncio
        
        async def run_test():
            session = AsyncConversationSession()
            
            # Create a proper async mock
            expected_result = AgentResult(
                success=True,
                result="Hello!",
                session_id="sess-123",
            )
            
            async def mock_query(*args, **kwargs):
                return expected_result
            
            session.client.query = mock_query
            
            result = await session.send("Hi")
            
            self.assertTrue(result.success)
            self.assertEqual(result.result, "Hello!")
            self.assertEqual(session.session_id, "sess-123")
            self.assertEqual(len(session._history), 1)
        
        asyncio.run(run_test())


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for convenience functions."""
    
    @patch.object(CursorAgentClient, 'query')
    def test_query_function(self, mock_query):
        """Test query convenience function."""
        mock_query.return_value = AgentResult(
            success=True,
            result="4",
            session_id="abc",
        )
        
        result = query("What is 2+2?")
        
        self.assertTrue(result.success)
        self.assertEqual(result.result, "4")
    
    @patch.object(CursorAgentClient, 'query_stream')
    def test_query_stream_function(self, mock_query_stream):
        """Test query_stream convenience function."""
        mock_stream = Mock(spec=StreamingResponse)
        mock_query_stream.return_value = mock_stream
        
        result = query_stream("Hello")
        
        self.assertIs(result, mock_stream)
    
    @patch.object(CursorAgentClient, 'query')
    def test_aquery_function(self, mock_sync_query):
        """Test aquery convenience function."""
        import asyncio
        
        # aquery uses AsyncCursorAgentClient which wraps sync client in executor
        mock_sync_query.return_value = AgentResult(
            success=True,
            result="42",
            session_id="abc",
        )
        
        async def run_test():
            return await aquery("What is the answer?")
        
        result = asyncio.run(run_test())
        
        self.assertTrue(result.success)
        self.assertEqual(result.result, "42")
    
    def test_collect_text_with_deltas(self):
        """Test collect_text with delta events."""
        events = [
            AgentEvent(type=EventType.ASSISTANT_DELTA, raw_type="assistant", subtype=None, data={}, text="Hello"),
            AgentEvent(type=EventType.ASSISTANT_DELTA, raw_type="assistant", subtype=None, data={}, text=" "),
            AgentEvent(type=EventType.ASSISTANT_DELTA, raw_type="assistant", subtype=None, data={}, text="World"),
        ]
        
        text = collect_text(events)
        
        self.assertEqual(text, "Hello World")
    
    def test_collect_text_with_thinking(self):
        """Test collect_text with thinking events included."""
        events = [
            AgentEvent(type=EventType.THINKING_DELTA, raw_type="thinking", subtype="delta", data={}, text="Hmm"),
            AgentEvent(type=EventType.ASSISTANT_DELTA, raw_type="assistant", subtype=None, data={}, text="Hi"),
        ]
        
        # Without thinking
        text1 = collect_text(events, include_thinking=False)
        self.assertEqual(text1, "Hi")
        
        # With thinking
        text2 = collect_text(iter(events), include_thinking=True)
        self.assertEqual(text2, "[thinking: Hmm]Hi")
    
    def test_collect_text_fallback_to_result(self):
        """Test collect_text falls back to result when no deltas."""
        events = [
            AgentEvent(type=EventType.RESULT_SUCCESS, raw_type="result", subtype="success", data={}, text="Final answer"),
        ]
        
        text = collect_text(events)
        
        self.assertEqual(text, "Final answer")
    
    def test_collect_text_empty(self):
        """Test collect_text with no text events."""
        events = [
            AgentEvent(type=EventType.SYSTEM_INIT, raw_type="system", subtype="init", data={}),
        ]
        
        text = collect_text(events)
        
        self.assertEqual(text, "")
    
    def test_collect_text_with_none_text(self):
        """Test collect_text handles None text values."""
        events = [
            AgentEvent(type=EventType.ASSISTANT_DELTA, raw_type="assistant", subtype=None, data={}, text=None),
            AgentEvent(type=EventType.ASSISTANT_DELTA, raw_type="assistant", subtype=None, data={}, text="Hi"),
        ]
        
        text = collect_text(events)
        
        self.assertEqual(text, "Hi")


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and error handling."""
    
    def test_agent_result_with_is_error_field(self):
        """Test parsing result with is_error field."""
        client = CursorAgentClient()
        
        with patch('cursor_agent_api.client.subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"type": "result", "subtype": "success", "result": "ok", "session_id": "abc", "is_error": true, "error": "warning"}',
                stderr='',
            )
            
            result = client.query("test")
            
            # is_error=true means error field should be populated
            self.assertEqual(result.error, "warning")
    
    def test_parse_event_with_empty_content_array(self):
        """Test parsing event with empty content array."""
        client = CursorAgentClient()
        line = '{"type": "assistant", "message": {"content": []}}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.ASSISTANT)
        self.assertIsNone(event.text)
    
    def test_parse_event_with_non_text_content(self):
        """Test parsing event with non-text content type."""
        client = CursorAgentClient()
        line = '{"type": "assistant", "message": {"content": [{"type": "image", "url": "http://example.com"}]}}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.ASSISTANT)
        self.assertIsNone(event.text)
    
    def test_parse_event_with_non_dict_message(self):
        """Test parsing event where message is not a dict."""
        client = CursorAgentClient()
        line = '{"type": "user", "message": "just a string"}'
        
        event = client._parse_event(line)
        
        self.assertEqual(event.type, EventType.USER)
        self.assertIsNone(event.text)
    
    def test_streaming_response_no_stdout(self):
        """Test StreamingResponse when stdout is None."""
        process = Mock(spec=subprocess.Popen)
        process.stdout = None
        process.poll.return_value = 0
        process.wait.return_value = 0
        
        stream = StreamingResponse(process, lambda x: None)
        events = list(stream)
        
        self.assertEqual(events, [])


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestOutputFormat))
    suite.addTests(loader.loadTestsFromTestCase(TestEventType))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentResult))
    suite.addTests(loader.loadTestsFromTestCase(TestStreamingResponse))
    suite.addTests(loader.loadTestsFromTestCase(TestCursorAgentClient))
    suite.addTests(loader.loadTestsFromTestCase(TestConversationSession))
    suite.addTests(loader.loadTestsFromTestCase(TestAsyncCursorAgentClient))
    suite.addTests(loader.loadTestsFromTestCase(TestAsyncConversationSession))
    suite.addTests(loader.loadTestsFromTestCase(TestConvenienceFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())
