from __future__ import annotations

import pytest

from sessionlog.core import canonical


@pytest.fixture
def native_fixtures():
    """All content is synthetic; no real agent transcript is checked in."""
    claude = [
        {
            "type": "user",
            "uuid": "u1",
            "parentUuid": None,
            "sessionId": "synthetic",
            "message": {"role": "user", "content": "Fix the synthetic test. 한글"},
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": "u1",
            "sessionId": "synthetic",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Read the fixture."},
                    {"type": "tool_use", "id": "call1", "name": "read_file", "input": {"path": "demo.py"}},
                ],
            },
        },
        {
            "type": "user",
            "uuid": "t1",
            "parentUuid": "a1",
            "sessionId": "synthetic",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "call1", "content": "return 0"}],
            },
        },
        {
            "type": "assistant",
            "uuid": "a2",
            "parentUuid": "t1",
            "sessionId": "synthetic",
            "message": {"role": "assistant", "content": "The fixture is ready."},
        },
        {
            "type": "system",
            "uuid": "c1",
            "parentUuid": "a2",
            "sessionId": "synthetic",
            "subtype": "compact_boundary",
            "logicalParentUuid": "a2",
        },
        {"type": "future_record", "uuid": "f1", "sessionId": "synthetic", "new_field": 9007199254740993},
    ]
    codex = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": "synthetic",
                "parent_thread_id": "synthetic-parent",
                "history_base": {"ordinal": 2},
            },
        },
        {"type": "event_msg", "payload": {"type": "user_message", "message": "Fix the fixture."}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Fix the fixture."}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "read_file",
                "call_id": "call1",
                "arguments": '{ "path" : "demo.py" }',
            },
        },
        {
            "type": "response_item",
            "payload": {"type": "function_call_output", "call_id": "call1", "output": "return 0"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "call_id": "patch1",
                "input": "*** Begin Patch\n*** End Patch",
            },
        },
        {
            "type": "response_item",
            "payload": {"type": "custom_tool_call_output", "call_id": "patch1", "output": "Done"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "A public summary"}],
                "encrypted_content": "synthetic-ciphertext",
            },
        },
        {"type": "world_state", "payload": {"full": False, "state": {"cwd": "/synthetic"}}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Ready."}],
            },
        },
    ]
    openclaw = [
        {"type": "session", "version": 4, "id": "synthetic", "cwd": "/synthetic", "timestamp": "2026-01-01"},
        {
            "type": "message",
            "id": "u1",
            "parentId": None,
            "message": {"role": "user", "content": "Inspect fixture"},
        },
        {
            "type": "message",
            "id": "a1",
            "parentId": "u1",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "toolCall", "id": "call1", "name": "read_file", "arguments": {"path": "demo.py"}}
                ],
            },
        },
        {
            "type": "message",
            "id": "t1",
            "parentId": "a1",
            "message": {
                "role": "toolResult",
                "toolCallId": "call1",
                "content": [{"type": "text", "text": "return 0"}],
                "isError": False,
            },
        },
        {"type": "leaf", "id": "leaf1", "parentId": "t1", "targetId": "u1"},
        {
            "type": "compaction",
            "id": "c1",
            "parentId": "u1",
            "firstKeptEntryId": "u1",
            "summary": "Synthetic",
        },
    ]
    hermes_messages = [
        {"role": "user", "content": "Inspect fixture", "timestamp": 1.25},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"demo.py"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call1", "content": "return 0"},
        {"role": "assistant", "content": "Ready.", "reasoning_content": "Synthetic reasoning"},
    ]
    hermes = [
        {
            "id": "synthetic",
            "source": "cli",
            "parent_session_id": "synthetic-parent",
            "messages": hermes_messages,
            "segments": [{"id": "synthetic", "messages": hermes_messages}],
            "lineage_session_ids": ["synthetic"],
        }
    ]
    return {
        name: b"".join(canonical(row) for row in rows)
        for name, rows in (
            ("claude-code", claude),
            ("codex", codex),
            ("openclaw", openclaw),
            ("hermes", hermes),
        )
    }
