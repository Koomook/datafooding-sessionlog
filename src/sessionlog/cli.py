"""Small local CLI. No background collection, remote upload, or model calls."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .adapters import HARNESSES
from .capture import capture
from .core import (
    SessionlogError,
    canonical,
    digest,
    normalize,
    parse_json,
    read_stable,
    source_bytes,
    summary,
    validate,
    write_new,
)
from .translate import TARGETS, translate


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sessionlog", description="Deterministic agent-session preservation.")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)
    for name in ("normalize", "roundtrip"):
        command = commands.add_parser(name)
        command.add_argument("inputs", type=Path, nargs="+")
        command.add_argument("--harness", choices=("auto", *HARNESSES), default="auto")
        command.add_argument("--preserve-invalid", action="store_true")
        if name == "normalize":
            command.add_argument("-o", "--output", type=Path, required=True)
    for name in ("inspect", "validate", "restore", "translate"):
        command = commands.add_parser(name)
        command.add_argument("input", type=Path)
        if name in ("restore", "translate"):
            command.add_argument("--source", type=int, default=0)
            command.add_argument("-o", "--output", type=Path, required=True)
        if name == "translate":
            command.add_argument("--target", choices=TARGETS, required=True)
            command.add_argument("--allow-loss", action="store_true")
            command.add_argument("--report", type=Path, required=True)
    command = commands.add_parser("capture")
    command.add_argument("phase", choices=("start", "end"))
    command.add_argument("--root", type=Path, required=True)
    command.add_argument("--before", type=Path)
    command.add_argument("--path", action="append", default=[])
    command.add_argument("--sqlite", action="append", default=[])
    command.add_argument("--exclude", action="append", default=[])
    command.add_argument("--include-content", action="store_true")
    command.add_argument(
        "--verify", action="append", default=[], help="Explicit command argv as a JSON array"
    )
    command.add_argument("--timeout", type=int, default=300)
    command.add_argument("--at", help="Optional caller-supplied observation timestamp")
    command.add_argument("-o", "--output", type=Path, required=True)
    return p


def execute(args: argparse.Namespace) -> dict:
    if args.command in ("normalize", "roundtrip"):
        inputs = [(args.harness, read_stable(path)) for path in args.inputs]
        envelope = normalize(inputs, preserve_invalid=args.preserve_invalid)
        encoded = canonical(envelope)
        if args.command == "normalize":
            write_new(args.output, encoded)
        else:
            validate(parse_json(encoded))
            if canonical(normalize(inputs, preserve_invalid=args.preserve_invalid)) != encoded:
                raise SessionlogError("determinism failed")
            for source, (_, original) in zip(envelope["sources"], inputs, strict=True):
                if source_bytes(source) != original:
                    raise SessionlogError("source roundtrip failed")
        return {
            "status": "ok",
            "standard_sha256": digest(encoded),
            **summary(envelope),
            **({"byte_exact": True, "deterministic": True} if args.command == "roundtrip" else {}),
        }
    if args.command == "capture":
        if args.output.resolve().is_relative_to(args.root.resolve()):
            raise SessionlogError("capture output must be outside the captured root")
        if not 1 <= args.timeout <= 3600:
            raise SessionlogError("verification timeout must be between 1 and 3600 seconds")
        envelope = capture(
            phase=args.phase,
            root=args.root,
            before=read_stable(args.before, max_bytes=256 * 1024 * 1024) if args.before else None,
            paths=args.path,
            dbs=args.sqlite,
            excludes=args.exclude,
            include_content=args.include_content,
            checks=[parse_json(v) for v in args.verify],
            at=args.at,
            timeout=args.timeout,
        )
        write_new(args.output, canonical(envelope))
        doc = parse_json(source_bytes(envelope["sources"][0]))
        failed = any(c["status"] != "passed" or not c["valid_for_final_state"] for c in doc["checks"])
        return {
            "status": "checks_failed" if failed else "ok",
            "phase": args.phase,
            "state_sha256": doc["state_sha256"],
            "files": len(doc["state"]["files"]),
            "checks": [
                {
                    "status": c["status"],
                    "exit_code": c["exit_code"],
                    "valid_for_final_state": c["valid_for_final_state"],
                }
                for c in doc["checks"]
            ],
        }
    envelope = validate(parse_json(read_stable(args.input, max_bytes=256 * 1024 * 1024)))
    if args.command in ("inspect", "validate"):
        return {"status": "ok", **summary(envelope)}
    if not 0 <= args.source < len(envelope["sources"]):
        raise SessionlogError("source index out of range")
    if args.command == "restore":
        data = source_bytes(envelope["sources"][args.source])
        write_new(args.output, data)
        return {"status": "ok", "byte_length": len(data), "sha256": digest(data)}
    if args.command == "translate":
        data, report = translate(envelope, args.target, source=args.source, allow_loss=args.allow_loss)
        if args.output.resolve() == args.report.resolve() or args.output.exists() or args.report.exists():
            raise SessionlogError("translation requires two distinct, new output files")
        write_new(args.report, canonical(report))
        write_new(args.output, data)
        return {
            "status": "ok",
            "mode": report["mode"],
            "loss_count": len(report["losses"]),
            "continuation_verified": False,
        }
    raise SessionlogError("unknown command")


def main() -> None:
    args = parser().parse_args()
    try:
        result = execute(args)
        sys.stdout.buffer.write(canonical(result))
        if result.get("status") == "checks_failed":
            raise SystemExit(3)
    except (SessionlogError, OSError, ValueError) as exc:
        print(f"sessionlog: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
