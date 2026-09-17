"""Explicitly lossy conversation exports, never a promise of harness continuation."""

from __future__ import annotations

from datetime import UTC, datetime

from .core import SessionlogError, canonical, digest, parse_json

TARGETS = ("claude-code", "codex", "openclaw", "hermes")
EPOCH = "1970-01-01T00:00:00.000Z"


def conversation(envelope: dict, source: int = 0) -> tuple[list[dict], list[dict]]:
    """A small documented subset; every omitted block gets its own loss entry."""
    if not 0 <= source < len(envelope["sources"]):
        raise SessionlogError("source index out of range")
    rows, losses = (
        [],
        [
            {
                "code": "native_context_not_portable",
                "detail": "Native metadata, policies, lineage, runtime state, timestamps and IDs are not preserved.",
            }
        ],
    )
    sessions = set()
    for event in envelope["events"]:
        if event["ref"]["source"] != source:
            continue
        if event["kind"] != "message":
            losses.append({"code": "non_message_omitted", "event_id": event["id"]})
            continue
        sessions.add(str(event["session_id"]))
        for block in event.get("blocks", []):
            kind, role = block["kind"], event["role"]
            if kind == "text" and role in ("user", "assistant") and event["authorship"] != "harness":
                rows.append({"role": role, "kind": "text", "text": block["text"]})
            elif kind == "tool_call" and block["tool_kind"] == "function":
                arguments = block["arguments"]
                if isinstance(arguments, str):
                    try:
                        arguments = parse_json(arguments)
                    except SessionlogError:
                        arguments = None
                if (
                    isinstance(arguments, dict)
                    and isinstance(block.get("name"), str)
                    and isinstance(block.get("call_id"), str)
                    and block.get("call_id")
                ):
                    rows.append(
                        {
                            "role": "assistant",
                            "kind": "tool_call",
                            "name": block["name"],
                            "arguments": arguments,
                            "call_id": block["call_id"],
                        }
                    )
                    if block["argument_encoding"] == "string":
                        losses.append({"code": "argument_lexeme_canonicalized", "event_id": event["id"]})
                else:
                    losses.append({"code": "unsupported_tool_call_omitted", "event_id": event["id"]})
            elif kind == "tool_result" and isinstance(block.get("call_id"), str) and block.get("call_id"):
                content = block.get("content")
                if isinstance(content, list) and all(
                    isinstance(p, dict)
                    and p.get("type") in ("text", "output_text")
                    and isinstance(p.get("text"), str)
                    for p in content
                ):
                    content = "".join(p["text"] for p in content)
                    losses.append({"code": "text_result_blocks_joined", "event_id": event["id"]})
                if not isinstance(content, str):
                    losses.append({"code": "unsupported_tool_result_omitted", "event_id": event["id"]})
                    continue
                rows.append(
                    {
                        "role": "tool",
                        "kind": "tool_result",
                        "call_id": block["call_id"],
                        "content": content,
                    }
                )
                if block.get("is_error") is not None:
                    losses.append({"code": "tool_error_flag_omitted", "event_id": event["id"]})
            else:
                losses.append({"code": "unsupported_block_omitted", "event_id": event["id"], "kind": kind})
    if len(sessions) > 1:
        raise SessionlogError("translation requires a source containing one session")
    calls = {row["call_id"] for row in rows if row["kind"] == "tool_call"}
    filtered = []
    for row in rows:
        if row["kind"] == "tool_result" and row["call_id"] not in calls:
            losses.append({"code": "orphan_tool_result_omitted"})
        else:
            filtered.append(row)
    return filtered, losses


def translate(
    envelope: dict, target: str, *, source: int = 0, allow_loss: bool = False
) -> tuple[bytes, dict]:
    if target not in TARGETS:
        raise SessionlogError("unsupported translation target")
    rows, losses = conversation(envelope, source)
    report = {
        "schema": "datafooding.translation-report/v1",
        "target": target,
        "source": source,
        "mode": "conversation_subset",
        "continuation_verified": False,
        "losses": losses,
        "conversation_items": len(rows),
        "conversation_sha256": digest(canonical(rows)),
        "synthetic_timestamp": EPOCH,
        "generated_ids": True,
        "usage_values_are_synthetic_placeholders": True,
    }
    if not allow_loss:
        raise SessionlogError("translation has losses; use --allow-loss and inspect the required --report")
    sid_hash = digest(canonical(rows))
    sid = f"{sid_hash[:8]}-{sid_hash[8:12]}-4{sid_hash[13:16]}-a{sid_hash[17:20]}-{sid_hash[20:32]}"
    records, messages = [], []
    if target == "codex":
        records.append(
            {
                "timestamp": EPOCH,
                "type": "session_meta",
                "payload": {
                    "id": sid,
                    "session_id": sid,
                    "timestamp": EPOCH,
                    "cwd": "/sessionlog-export",
                    "originator": "sessionlog-conversation-export",
                    "cli_version": "0.1.0",
                    "source": "cli",
                    "model_provider": None,
                    "base_instructions": None,
                    "history_mode": "legacy",
                },
            }
        )
    elif target == "openclaw":
        records.append(
            {"type": "session", "version": 4, "id": sid, "timestamp": EPOCH, "cwd": "/sessionlog-export"}
        )
    parent = None
    for index, row in enumerate(rows):
        record_id = digest(canonical([sid, index]))[:32]
        role, kind = row["role"], row["kind"]
        if target == "claude-code":
            if kind == "text":
                blocks = [{"type": "text", "text": row["text"]}]
            elif kind == "tool_call":
                blocks = [
                    {"type": "tool_use", "id": row["call_id"], "name": row["name"], "input": row["arguments"]}
                ]
            else:
                blocks = [{"type": "tool_result", "tool_use_id": row["call_id"], "content": row["content"]}]
            native_role = "user" if role == "tool" else role
            message = {"role": native_role, "content": blocks}
            if native_role == "assistant":
                message.update(
                    id="msg_" + record_id,
                    type="message",
                    model="sessionlog-export",
                    stop_reason="tool_use" if kind == "tool_call" else "end_turn",
                    stop_sequence=None,
                    usage={"input_tokens": 0, "output_tokens": 0},
                )
            records.append(
                {
                    "type": native_role,
                    "uuid": record_id,
                    "parentUuid": parent,
                    "sessionId": sid,
                    "timestamp": EPOCH,
                    "cwd": "/sessionlog-export",
                    "isSidechain": False,
                    "message": message,
                }
            )
        elif target == "codex":
            if kind == "text":
                payload = {
                    "type": "message",
                    "role": role,
                    "content": [
                        {"type": "input_text" if role == "user" else "output_text", "text": row["text"]}
                    ],
                }
            elif kind == "tool_call":
                payload = {
                    "type": "function_call",
                    "call_id": row["call_id"],
                    "name": row["name"],
                    "arguments": canonical(row["arguments"]).decode().rstrip("\n"),
                }
            else:
                payload = {
                    "type": "function_call_output",
                    "call_id": row["call_id"],
                    "output": row["content"],
                }
            records.append({"timestamp": EPOCH, "type": "response_item", "payload": payload})
        elif target == "openclaw":
            if kind == "text":
                message = {"role": role, "content": [{"type": "text", "text": row["text"]}], "timestamp": 0}
            elif kind == "tool_call":
                message = {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "id": row["call_id"],
                            "name": row["name"],
                            "arguments": row["arguments"],
                        }
                    ],
                    "timestamp": 0,
                }
            else:
                message = {
                    "role": "toolResult",
                    "toolCallId": row["call_id"],
                    "toolName": "sessionlog-export",
                    "content": [{"type": "text", "text": row["content"]}],
                    "isError": False,
                    "timestamp": 0,
                }
            if role == "assistant":
                message.update(
                    api="openai-completions",
                    provider="sessionlog",
                    model="sessionlog-export",
                    stopReason="toolUse" if kind == "tool_call" else "stop",
                    usage={
                        "input": 0,
                        "output": 0,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "totalTokens": 0,
                        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
                    },
                )
            records.append(
                {
                    "type": "message",
                    "id": record_id,
                    "parentId": parent,
                    "timestamp": EPOCH,
                    "message": message,
                }
            )
        elif target == "hermes":
            message = {"role": role, "timestamp": 0}
            if kind == "text":
                message["content"] = row["text"]
            elif kind == "tool_call":
                message.update(
                    content=None,
                    tool_calls=[
                        {
                            "id": row["call_id"],
                            "type": "function",
                            "function": {
                                "name": row["name"],
                                "arguments": canonical(row["arguments"]).decode().rstrip("\n"),
                            },
                        }
                    ],
                )
            else:
                message.update(content=row["content"], tool_call_id=row["call_id"])
            messages.append(message)
        parent = record_id
    if target == "hermes":
        records = [
            {
                "id": sid,
                "source": "sessionlog",
                "started_at": datetime(1970, 1, 1, tzinfo=UTC).timestamp(),
                "messages": messages,
            }
        ]
    return b"".join(canonical(record) for record in records), report
