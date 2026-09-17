import copy
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sessionlog.core import (
    SessionlogError,
    canonical,
    normalize,
    parse_json,
    read_stable,
    source_bytes,
    validate,
    write_new,
)
from sessionlog.translate import TARGETS, conversation, translate


@pytest.mark.parametrize("harness", TARGETS)
def test_preservation_determinism_and_detection(native_fixtures, harness):
    # Deliberate CRLF, leading/trailing blanks, and no final newline.
    raw = b"\r\n" + native_fixtures[harness].replace(b"\n", b"\r\n").rstrip()
    result = normalize([(harness, raw)])
    assert source_bytes(result["sources"][0]) == raw
    assert canonical(result) == canonical(normalize([(harness, raw)]))
    assert normalize([("auto", raw)]) == result
    assert validate(parse_json(canonical(result))) == result
    assert result["events"]


def test_roles_lineage_unknown_fields_and_tool_edges(native_fixtures):
    result = normalize([("claude-code", native_fixtures["claude-code"])])
    assert [e.get("role") for e in result["events"][:4]] == ["user", "assistant", "tool", "assistant"]
    assert result["events"][0]["authorship"] == "unverified"
    assert result["events"][4]["native"]["logicalParentUuid"] == "a2"
    assert result["events"][-1]["native"]["new_field"] == 9007199254740993
    assert result["events"][-1]["kind"] == "opaque"
    assert not any(i["code"] == "unmatched_tool_result" for i in result["diagnostics"])


def test_codex_mirror_not_double_counted_custom_tool_and_reasoning(native_fixtures):
    result = normalize([("codex", native_fixtures["codex"])])
    assert sum(e.get("role") == "user" for e in result["events"]) == 1
    blocks = [b for e in result["events"] for b in e.get("blocks", [])]
    assert any(b.get("tool_kind") == "custom_tool_call" for b in blocks)
    assert any(b.get("visibility") == "opaque" for b in blocks)
    assert result["events"][0]["native"]["payload"]["parent_thread_id"] == "synthetic-parent"


def test_hermes_lineage_not_double_counted(native_fixtures):
    result = normalize([("hermes", native_fixtures["hermes"])])
    assert sum(e["kind"] == "message" for e in result["events"]) == 4
    assert result["diagnostics"][0]["code"] == "lineage_flattened_once"
    pretty = json.dumps(json.loads(native_fixtures["hermes"]), indent=2).encode()
    assert normalize([("auto", pretty)])["sources"][0]["harness"] == "hermes"


@pytest.mark.parametrize(
    "bad", [b'{"type":', b'{"a":1,"a":2}', b'{"v":NaN}', b'{"v":1e999}', b"[1]", b"\xff"]
)
def test_invalid_requires_explicit_preservation(bad):
    with pytest.raises(SessionlogError):
        normalize([("codex", bad)])
    result = normalize([("codex", bad)], preserve_invalid=True)
    assert source_bytes(result["sources"][0]) == bad
    assert result["diagnostics"][0]["code"] == "invalid_record_preserved"


def test_depth_limit_empty_unknown_and_multi_sources(native_fixtures):
    with pytest.raises(SessionlogError):
        parse_json("[" * 102 + "0" + "]" * 102)
    for data in (b"", b"  \n", b'{"unknown":true}'):
        with pytest.raises(SessionlogError):
            normalize([("auto", data)])
    result = normalize([("auto", v) for v in native_fixtures.values()])
    assert len(result["sources"]) == 4
    assert len({e["id"] for e in result["events"]}) == len(result["events"])


@pytest.mark.parametrize("mutation", ["source", "event", "rights", "order", "version", "extra"])
def test_tamper_rejected(native_fixtures, mutation):
    result = copy.deepcopy(normalize([("codex", native_fixtures["codex"])]))
    if mutation == "source":
        result["sources"][0]["sha256"] = "0" * 64
    elif mutation == "event":
        result["events"][2]["blocks"][0]["text"] = "changed"
    elif mutation == "rights":
        result["rights"]["training"] = "granted"
    elif mutation == "order":
        result["events"].reverse()
    elif mutation == "version":
        result["adapter_version"] = "99.0.0"
    else:
        result["unexpected"] = True
    with pytest.raises(SessionlogError):
        validate(result)


@pytest.mark.parametrize("source", TARGETS)
@pytest.mark.parametrize("target", TARGETS)
def test_cross_harness_conversation_subset(native_fixtures, source, target):
    envelope = normalize([(source, native_fixtures[source])])
    with pytest.raises(SessionlogError, match="losses"):
        translate(envelope, target)
    native, report = translate(envelope, target, allow_loss=True)
    restored = normalize([(target, native)])
    assert any(row["kind"] == "tool_call" for row in conversation(envelope)[0])
    assert any(row["kind"] == "tool_result" for row in conversation(envelope)[0])
    assert conversation(envelope)[0] == conversation(restored)[0]
    assert report["continuation_verified"] is False
    assert report["losses"]
    assert translate(envelope, target, allow_loss=True)[0] == native


@given(st.text(max_size=500), st.booleans())
@settings(max_examples=80, deadline=None)
def test_arbitrary_text_and_line_endings_roundtrip(text, crlf):
    record = {"type": "user", "uuid": "u", "sessionId": "s", "message": {"role": "user", "content": text}}
    raw = canonical(record)
    if crlf:
        raw = raw.replace(b"\n", b"\r\n")
    result = normalize([("claude-code", raw)])
    assert result["events"][0]["blocks"][0]["text"] == text
    assert source_bytes(result["sources"][0]) == raw


def test_output_permissions_and_no_clobber(tmp_path):
    path = tmp_path / "output"
    write_new(path, b"first")
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SessionlogError):
        write_new(path, b"second")
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(SessionlogError):
        read_stable(link)
    assert path.read_bytes() == b"first"


def test_cli_end_to_end(tmp_path, native_fixtures):
    source, standard, restored = [tmp_path / n for n in ("native.jsonl", "standard.json", "restored.jsonl")]
    source.write_bytes(native_fixtures["claude-code"])

    def run(*args):
        return subprocess.run([sys.executable, "-m", "sessionlog.cli", *map(str, args)], capture_output=True)

    assert run("normalize", source, "-o", standard).returncode == 0
    assert run("validate", standard).returncode == 0
    assert run("restore", standard, "-o", restored).returncode == 0
    assert restored.read_bytes() == source.read_bytes()
    assert run("normalize", source, "-o", standard).returncode == 2
    assert run("restore", standard, "--source", -1, "-o", tmp_path / "other").returncode == 2
    assert json.loads(run("roundtrip", source).stdout)["byte_exact"] is True


def test_schema_matches_all_projections(native_fixtures):
    schema = json.loads((Path(__file__).parents[1] / "schema/sessionlog-v1.schema.json").read_text())
    for harness, data in native_fixtures.items():
        jsonschema.Draft202012Validator(schema).validate(normalize([(harness, data)]))
