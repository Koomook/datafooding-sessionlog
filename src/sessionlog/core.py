"""Canonical encoding, bounded parsing, and immutable source preservation."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from collections import Counter
from pathlib import Path
from typing import Any

from . import __version__

SCHEMA = "datafooding.sessionlog/v1"
MAX_BYTES = 64 * 1024 * 1024
RIGHTS = {
    k: "unknown"
    for k in (
        "access",
        "operations",
        "evaluation",
        "training",
        "derivative",
        "resale",
        "export",
        "retention",
        "revocation",
        "deletion",
    )
}


class SessionlogError(ValueError):
    """Invalid input or an unfulfilled preservation contract."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SessionlogError("duplicate JSON object key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise SessionlogError("non-finite JSON number")


def parse_json(data: bytes | str) -> Any:
    try:
        result = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 100:
                raise SessionlogError("JSON nesting exceeds 100")
            if isinstance(value, dict):
                pending.extend((v, depth + 1) for v in value.values())
            elif isinstance(value, list):
                pending.extend((v, depth + 1) for v in value)
            elif isinstance(value, float) and not (-float("inf") < value < float("inf")):
                raise SessionlogError("non-finite JSON number")
        return result
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SessionlogError("invalid UTF-8 JSON or excessive nesting") from exc


def read_stable(path: Path, *, max_bytes: int = MAX_BYTES) -> bytes:
    """Read a regular file without following a final symlink; reject observed drift."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
                raise SessionlogError("input must be a regular file within the size limit")
            data = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise SessionlogError(f"cannot safely read {path.name}") from exc

    def key(s):
        return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns

    if key(before) != key(after) or key(after) != key(current) or len(data) > max_bytes:
        raise SessionlogError("input changed during read or exceeds the size limit")
    return data


def write_new(path: Path, data: bytes) -> None:
    """Never clobber a file or follow an existing output symlink."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise SessionlogError("output already exists") from exc


def native_records(data: bytes, harness: str, preserve_invalid: bool) -> list[tuple[int, Any]]:
    # Hermes /save JSON and the state producer emit a whole document; export JSONL
    # emits a complete session on each line. Do not confuse messages with sessions.
    if harness in ("hermes", "state", "auto"):
        try:
            doc = parse_json(data)
            if isinstance(doc, dict) and ("messages" in doc or doc.get("capture_schema")):
                return [(0, doc)]
            if harness == "hermes" and isinstance(doc, list) and all(isinstance(x, dict) for x in doc):
                return list(enumerate(doc))
        except SessionlogError:
            pass
    records = []
    for index, line in enumerate(data.splitlines()):
        if not line.strip():
            continue
        try:
            record = parse_json(line)
            if not isinstance(record, dict):
                raise SessionlogError("a native record must be an object")
        except SessionlogError as exc:
            if not preserve_invalid:
                raise SessionlogError(f"invalid native record at line {index + 1}: {exc}") from exc
            record = {"__sessionlog_invalid_line__": base64.b64encode(line).decode("ascii")}
        records.append((index, record))
    if not records:
        raise SessionlogError("no native records")
    return records


def detect(records: list[tuple[int, dict]]) -> str:
    candidates = set()
    for _, r in records[:100]:
        if r.get("capture_schema") == "datafooding.state/v1":
            candidates.add("state")
        if isinstance(r.get("messages"), list) and ("id" in r or "session_id" in r):
            candidates.add("hermes")
        if r.get("type") == "session" and "id" in r:
            candidates.add("openclaw")
        if r.get("type") in ("session_meta", "response_item", "event_msg", "turn_context") and "payload" in r:
            candidates.add("codex")
        if "uuid" in r and ("sessionId" in r or "parentUuid" in r):
            candidates.add("claude-code")
    if len(candidates) != 1:
        raise SessionlogError("format is ambiguous or unknown; supply --harness")
    return candidates.pop()


def normalize(inputs: list[tuple[str, bytes]], *, preserve_invalid: bool = False) -> dict:
    from .adapters import project

    sources, events, diagnostics = [], [], []
    if not inputs:
        raise SessionlogError("at least one source is required")
    for source_index, (harness, data) in enumerate(inputs):
        if len(data) > MAX_BYTES:
            raise SessionlogError("source exceeds 64 MiB")
        records = native_records(data, harness, preserve_invalid)
        if harness == "auto":
            harness = detect(records)
        source = {
            "index": source_index,
            "harness": harness,
            "sha256": digest(data),
            "byte_length": len(data),
            "base64": base64.b64encode(data).decode("ascii"),
        }
        sources.append(source)
        projected, issues = project(harness, records, source_index, source["sha256"])
        events.extend(projected)
        diagnostics.extend(issues)
    return {
        "schema": SCHEMA,
        "adapter_version": __version__,
        "preserve_invalid": preserve_invalid,
        "sources": sources,
        "events": events,
        "diagnostics": diagnostics,
        "rights": dict(RIGHTS),
    }


def source_bytes(source: dict) -> bytes:
    try:
        data = base64.b64decode(source["base64"], validate=True)
    except (ValueError, TypeError, KeyError) as exc:
        raise SessionlogError("invalid preserved source") from exc
    if len(data) != source.get("byte_length") or digest(data) != source.get("sha256"):
        raise SessionlogError("source digest or byte length mismatch")
    return data


def validate(envelope: Any) -> dict:
    if not isinstance(envelope, dict) or envelope.get("schema") != SCHEMA:
        raise SessionlogError("unsupported standard schema")
    if envelope.get("adapter_version") != __version__:
        raise SessionlogError("adapter version mismatch; use the matching release")
    try:
        sources = envelope["sources"]
        if not isinstance(sources, list) or not isinstance(envelope["preserve_invalid"], bool):
            raise SessionlogError("invalid sources or parser policy")
        inputs = [(s["harness"], source_bytes(s)) for s in sources]
        expected = normalize(inputs, preserve_invalid=envelope["preserve_invalid"])
        if canonical(expected) != canonical(envelope):
            raise SessionlogError("envelope differs from deterministic projection")
    except (KeyError, TypeError, AttributeError) as exc:
        raise SessionlogError("malformed standard envelope") from exc
    return envelope


def summary(envelope: dict) -> dict:
    return {
        "schema": envelope["schema"],
        "sources": len(envelope["sources"]),
        "source_bytes": sum(s["byte_length"] for s in envelope["sources"]),
        "events": len(envelope["events"]),
        "kinds": dict(sorted(Counter(e["kind"] for e in envelope["events"]).items())),
        "blocks": dict(
            sorted(Counter(b["kind"] for e in envelope["events"] for b in e.get("blocks", [])).items())
        ),
        "diagnostics": dict(sorted(Counter(d["code"] for d in envelope["diagnostics"]).items())),
    }
