"""Exercise pinned, separately checked-out upstream readers on synthetic exports.

Run with the official SDK dependencies available. This never opens a real session
store or starts a model. Pass --sources and --output paths explicitly.
"""

import argparse
import importlib
import subprocess
import sys
from pathlib import Path

from sessionlog.core import canonical, normalize, parse_json, write_new
from sessionlog.translate import TARGETS, conversation, translate

PINNED = {
    "claude-agent-sdk-python": "9d398b6b7ed8a1bf9527c8939f75a8abfa6f165b",
    "hermes-agent": "6005aa1fd9aac8b1024ace50fec8cd1c85a04bae",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sources", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    for name, commit in PINNED.items():
        root = args.sources / name
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if actual != commit:
            raise RuntimeError(f"upstream commit mismatch: {name}")
        sys.path.insert(0, str(root / "src" if name.startswith("claude") else root))
    synthetic = {
        "id": "synthetic",
        "messages": [
            {"role": "user", "content": "Read the synthetic fixture."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"fixture.txt"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call1", "content": "synthetic fixture"},
            {"role": "assistant", "content": "The fixture is readable."},
        ],
    }
    standard = normalize([("hermes", canonical(synthetic))])
    args.output.mkdir(parents=True, exist_ok=True)
    for target in TARGETS:
        data, losses = translate(standard, target, allow_loss=True)
        write_new(args.output / f"{target}.jsonl", data)
        write_new(args.output / f"{target}.losses.json", canonical(losses))
    sdk = importlib.import_module("claude_agent_sdk._internal.sessions")
    entries = sdk._parse_transcript_entries((args.output / "claude-code.jsonl").read_text())
    messages = sdk._entries_to_session_messages(entries, None, 0)
    # Exercise both native chain construction and its visible-message projection.
    chain = sdk._build_conversation_chain(entries)
    assert len(chain) == 4
    assert [r["message"]["role"] for r in chain] == ["user", "assistant", "user", "assistant"]
    hermes = importlib.import_module("hermes_cli.session_export")
    exported = hermes.render_sessions_export([parse_json((args.output / "hermes.jsonl").read_bytes())])
    assert conversation(normalize([("hermes", exported.encode())]))[0] == conversation(standard)[0]
    report = {
        "synthetic_only": True,
        "commits": PINNED,
        "claude_official_reader": {
            "chain_entries": len(chain),
            "visible_messages": len(messages),
            "passed": True,
        },
        "hermes_official_export_renderer": {"conversation_items": 4, "passed": True},
        "live_continuation": "not_tested",
    }
    write_new(args.output / "python-readers.json", canonical(report))
    print(canonical(report).decode(), end="")


if __name__ == "__main__":
    main()
