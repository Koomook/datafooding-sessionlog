"""Semantic projections informed by the pinned producer source in docs/source-audit.md."""

from __future__ import annotations

from typing import Any

from .core import SessionlogError, canonical, digest, parse_json

HARNESSES = ("claude-code", "codex", "openclaw", "hermes", "state")


def block_content(content: Any) -> list[dict]:
    if content is None:
        return []
    if isinstance(content, str):
        return [{"kind": "text", "text": content}]
    if not isinstance(content, list):
        return [{"kind": "opaque", "value": content}]
    result = []
    for part in content:
        if not isinstance(part, dict):
            result.append({"kind": "opaque", "value": part})
            continue
        t = part.get("type")
        if t in ("text", "input_text", "output_text", "summary_text"):
            result.append(
                {"kind": "text", "text": part["text"]}
                if isinstance(part.get("text"), str)
                else {"kind": "opaque", "value": part}
            )
        elif t in ("thinking", "reasoning", "reasoning_text"):
            result.append(
                {
                    "kind": "reasoning",
                    "text": part.get("thinking", part.get("text", "")),
                    "visibility": "readable",
                }
            )
        elif t in ("redacted_thinking", "encrypted_reasoning"):
            result.append({"kind": "reasoning", "visibility": "opaque", "value": part})
        elif t in ("tool_use", "toolCall"):
            args = part.get("input", part.get("arguments"))
            result.append(call(part.get("id"), part.get("name"), args))
        elif t == "tool_result":
            result.append(
                {
                    "kind": "tool_result",
                    "call_id": part.get("tool_use_id"),
                    "content": part.get("content"),
                    "is_error": part.get("is_error"),
                }
            )
        elif t in ("image", "image_url", "input_image", "audio", "input_audio", "video", "document"):
            result.append({"kind": "media", "media_type": t, "value": part})
        else:
            result.append({"kind": "opaque", "value": part})
    return result


def call(call_id: Any, name: Any, arguments: Any, tool_kind: str = "function") -> dict:
    return {
        "kind": "tool_call",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
        "argument_encoding": "string" if isinstance(arguments, str) else "json",
        "tool_kind": tool_kind,
    }


def message_fields(message: dict, *, meta: bool = False) -> dict:
    role = message.get("role", "unknown")
    if not isinstance(role, str):
        role = "unknown"
    blocks = block_content(message.get("content"))
    if role in ("tool", "toolResult"):
        blocks = [
            {
                "kind": "tool_result",
                "call_id": message.get("tool_call_id", message.get("toolCallId")),
                "content": message.get("content"),
                "is_error": message.get("isError"),
            }
        ]
        role = "tool"
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, str):
        try:
            tool_calls = parse_json(tool_calls)
        except SessionlogError:
            blocks.append({"kind": "opaque", "value": {"tool_calls": tool_calls}})
            tool_calls = None
    if isinstance(tool_calls, list):
        for c in tool_calls:
            if isinstance(c, dict) and isinstance(c.get("function"), dict):
                f = c["function"]
                blocks.append(call(c.get("id"), f.get("name"), f.get("arguments")))
            else:
                blocks.append({"kind": "opaque", "value": c})
    for key in ("reasoning", "reasoning_content", "reasoning_details", "codex_reasoning_items"):
        if message.get(key) is not None:
            blocks.append(
                {
                    "kind": "reasoning",
                    "visibility": "readable" if isinstance(message[key], str) else "opaque",
                    "value": message[key],
                }
            )
    if role == "user" and blocks and all(b["kind"] == "tool_result" for b in blocks):
        role = "tool"
    author = (
        "harness"
        if meta or role in ("system", "developer")
        else {
            "assistant": "model",
            "tool": "tool",
            "user": "unverified",
        }.get(role, "unverified")
    )
    return {"kind": "message", "role": role, "authorship": author, "blocks": blocks}


def project(
    harness: str, records: list[tuple[int, dict]], source: int, source_hash: str
) -> tuple[list, list]:
    if harness not in HARNESSES:
        raise SessionlogError("unsupported harness")
    events, issues = [], []
    session_id = None

    def add(index: int, native: dict, fields: dict, nested: int | None = None) -> None:
        ref = {"source": source, "record": index}
        if nested is not None:
            ref["message"] = nested
        event = {
            "id": digest(canonical([source_hash, ref])),
            "ref": ref,
            "session_id": session_id,
            "native": native,
            **fields,
        }
        events.append(event)

    for index, r in records:
        if "__sessionlog_invalid_line__" in r:
            add(index, r, {"kind": "opaque"})
            issues.append({"code": "invalid_record_preserved", "source": source, "record": index})
            continue
        t = r.get("type")
        fields: dict = {"kind": "control", "control_type": t or "unknown"}
        if harness == "claude-code":
            session_id = r.get("sessionId", session_id)
            if t in ("user", "assistant") and isinstance(r.get("message"), dict):
                fields = message_fields(r["message"], meta=bool(r.get("isMeta") or r.get("isCompactSummary")))
            elif t not in (
                "system",
                "progress",
                "attachment",
                "file-history-snapshot",
                "summary",
                "queue-operation",
                "last-prompt",
                "custom-title",
                "agent-name",
                "agent-color",
            ):
                fields = {"kind": "opaque"}
        elif harness == "codex":
            p = r.get("payload")
            if not isinstance(p, dict):
                fields = {"kind": "opaque"}
            elif t == "session_meta":
                session_id = p.get("id", session_id)
            elif t == "response_item":
                pt = p.get("type")
                if pt == "message":
                    fields = message_fields(p)
                elif pt == "agent_message":
                    fields = message_fields({**p, "role": "assistant"})
                    fields["channel"] = "inter_agent"
                elif pt in ("function_call", "custom_tool_call", "local_shell_call"):
                    fields = {
                        "kind": "message",
                        "role": "assistant",
                        "authorship": "model",
                        "blocks": [
                            call(
                                p.get("call_id", p.get("id")),
                                p.get("name", pt),
                                p.get("arguments", p.get("input", p.get("action"))),
                                "function" if pt == "function_call" else pt,
                            )
                        ],
                    }
                elif pt in ("function_call_output", "custom_tool_call_output", "local_shell_call_output"):
                    fields = {
                        "kind": "message",
                        "role": "tool",
                        "authorship": "tool",
                        "blocks": [
                            {
                                "kind": "tool_result",
                                "call_id": p.get("call_id", p.get("id")),
                                "content": p.get("output"),
                                "is_error": p.get("is_error"),
                            }
                        ],
                    }
                elif pt == "reasoning":
                    blocks = block_content(p.get("summary")) + block_content(p.get("content"))
                    for b in blocks:
                        if b["kind"] == "text":
                            b.update(kind="reasoning", visibility="readable")
                    if p.get("encrypted_content"):
                        blocks.append(
                            {"kind": "reasoning", "visibility": "opaque", "value": p["encrypted_content"]}
                        )
                    fields = {"kind": "message", "role": "assistant", "authorship": "model", "blocks": blocks}
                else:
                    fields = {"kind": "opaque"}
            elif t == "event_msg":
                # A status mirror is not a second user/model message. Keep its payload.
                fields = {"kind": "control", "control_type": "event_msg:" + str(p.get("type", "unknown"))}
                if p.get("type") in ("user_message", "agent_message", "agent_reasoning"):
                    fields["blocks"] = block_content(p.get("message", p.get("text")))
                    fields["channel"] = "status_mirror"
                elif p.get("type") == "item_completed" and isinstance(p.get("item"), dict):
                    fields["blocks"] = block_content(p["item"].get("content", p["item"].get("text")))
                    fields["channel"] = "status_mirror"
            elif t not in ("turn_context", "compacted", "world_state", "world_state_item"):
                fields = {"kind": "opaque"}
        elif harness == "openclaw":
            if t == "session":
                session_id = r.get("id")
            elif t == "message" and isinstance(r.get("message"), dict):
                fields = message_fields(r["message"])
            elif t not in (
                "thinking_level_change",
                "model_change",
                "compaction",
                "reset",
                "branch_summary",
                "custom",
                "label",
                "session_info",
                "custom_message",
                "leaf",
            ):
                fields = {"kind": "opaque"}
        elif harness == "hermes":
            if not isinstance(r.get("messages"), list):
                raise SessionlogError("Hermes input must contain complete session objects with messages")
            session_id = r.get("id", r.get("session_id"))
            add(
                index,
                {k: v for k, v in r.items() if k not in ("messages", "segments")},
                {"kind": "control", "control_type": "session"},
            )
            for nested, m in enumerate(r["messages"]):
                if not isinstance(m, dict):
                    raise SessionlogError("Hermes message must be an object")
                add(index, m, message_fields(m, meta=bool(m.get("_compressed_summary"))), nested)
            if r.get("segments"):
                issues.append({"code": "lineage_flattened_once", "source": source, "record": index})
            continue
        elif harness == "state":
            if r.get("capture_schema") != "datafooding.state/v1":
                raise SessionlogError("unsupported state capture schema")
            fields = {"kind": "state", "phase": r.get("phase")}
        add(index, r, fields)
        if fields["kind"] == "opaque":
            issues.append({"code": "unknown_record_preserved", "source": source, "record": index})

    calls = set()
    for event in events:
        for b in event.get("blocks", []):
            key = (str(event["session_id"]), str(b.get("call_id")))
            if b["kind"] == "tool_call" and b.get("call_id") is not None:
                if key in calls:
                    issues.append({"code": "duplicate_call_id", "ref": event["ref"]})
                calls.add(key)
            if b["kind"] == "tool_result" and (b.get("call_id") is None or key not in calls):
                issues.append({"code": "unmatched_tool_result", "ref": event["ref"]})
    return events, issues
