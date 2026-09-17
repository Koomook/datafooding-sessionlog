"""Explicit local state evidence. Never discovers credentials or remote services."""

from __future__ import annotations

import base64
import fnmatch
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from .core import MAX_BYTES, SessionlogError, canonical, digest, normalize, read_stable, validate

SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "credentials*",
    "auth.json",
    "secrets.*",
    ".DS_Store",
)
LOCK_NAMES = {
    "uv.lock",
    "bun.lock",
    "bun.lockb",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "requirements.txt",
    "Cargo.lock",
    "Gemfile.lock",
}
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".local-evidence"}


def run_bytes(argv: list[str], root: Path, timeout: int = 30) -> tuple[int, bytes, bytes]:
    """Bound captured output on disk; never interpolate a shell command."""
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            process = subprocess.Popen(
                argv,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=True,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"},
            )
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                import signal

                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise SessionlogError("evidence command timed out") from None
            if out.tell() > MAX_BYTES or err.tell() > MAX_BYTES:
                raise SessionlogError("evidence command output exceeds 64 MiB")
            out.seek(0)
            err.seek(0)
            return code, out.read(), err.read()
    except OSError as exc:
        raise SessionlogError("evidence command could not start") from exc


def git(root: Path, *args: str, required: bool = True) -> bytes:
    code, out, _ = run_bytes(["git", "--no-optional-locks", *args], root)
    if code and required:
        raise SessionlogError("Git state could not be read")
    return out if code == 0 else b""


def safe_relative(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise SessionlogError("selected files must be relative paths inside the root")
    path = root / relative
    # Never traverse a symlinked ancestor, even if its final component is regular.
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise SessionlogError("selected path traverses a symlink")
    return path


def sqlite_snapshot(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise SessionlogError("SQLite selection must be a regular file")
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        tables = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        result = []
        total = 0
        for name, definition in tables:
            escaped = name.replace('"', '""')
            rows = []
            cursor = connection.execute(f'SELECT * FROM "{escaped}"')
            for row in cursor:
                encoded = [
                    {"blob_base64": base64.b64encode(v).decode("ascii")} if isinstance(v, bytes) else v
                    for v in row
                ]
                serialized = canonical(encoded)
                total += len(serialized)
                if total > MAX_BYTES:
                    raise SessionlogError("SQLite logical snapshot exceeds 64 MiB")
                rows.append(encoded)
            rows.sort(key=canonical)
            result.append(
                {
                    "table": name,
                    "definition": definition,
                    "columns": [c[0] for c in cursor.description],
                    "rows": rows,
                }
            )
        connection.rollback()
        return {
            "kind": "sqlite_logical_snapshot",
            "tables": result,
            "sha256": digest(canonical(result)),
            "byte_identical_backup": False,
        }
    except sqlite3.Error as exc:
        raise SessionlogError("SQLite snapshot failed") from exc
    finally:
        if "connection" in locals():
            connection.close()


def workspace_state(
    root: Path, paths: list[str], dbs: list[str], include_content: bool, extra_excludes: list[str]
) -> dict:
    is_git = bool(git(root, "rev-parse", "--is-inside-work-tree", required=False).strip())
    names = set(paths)
    git_state = None
    if is_git:
        top = git(root, "rev-parse", "--show-toplevel").decode().strip()
        if Path(top).resolve() != root:
            raise SessionlogError("capture root must be the Git worktree root")
        for chunk in git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0"):
            if chunk:
                names.add(os.fsdecode(chunk))
        status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        index = git(root, "ls-files", "--stage", "-z")
        staged = git(root, "diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv")
        unstaged = git(root, "diff", "--binary", "--no-ext-diff", "--no-textconv")
        git_state = {
            "head": git(root, "rev-parse", "--verify", "HEAD", required=False).decode().strip() or None,
            "status_base64": base64.b64encode(status).decode(),
            "index_sha256": digest(index),
            "staged_diff_sha256": digest(staged),
            "unstaged_diff_sha256": digest(unstaged),
        }
    elif not paths and not dbs:
        raise SessionlogError("non-Git capture requires explicit --path or --sqlite selections")
    files, excluded = [], []
    for name in sorted(names):
        path = safe_relative(root, name)
        relative = Path(name)
        if (
            any(p in EXCLUDED_PARTS for p in relative.parts)
            or any(fnmatch.fnmatch(relative.name, pattern) for pattern in SECRET_PATTERNS)
            or any(fnmatch.fnmatch(name, pattern) for pattern in extra_excludes)
        ):
            excluded.append({"path": name, "reason": "exclusion_policy"})
            continue
        if path.is_symlink():
            files.append({"path": name, "kind": "symlink", "target": os.readlink(path), "followed": False})
        elif not path.exists():
            files.append({"path": name, "kind": "missing"})
        elif path.is_dir():
            files.append({"path": name, "kind": "directory_or_submodule", "captured": False})
        else:
            data = read_stable(path)
            entry = {
                "path": name,
                "kind": "file",
                "sha256": digest(data),
                "byte_length": len(data),
                "mode": path.stat().st_mode & 0o777,
                "dependency_lock": relative.name in LOCK_NAMES,
            }
            if include_content:
                entry["base64"] = base64.b64encode(data).decode()
            files.append(entry)
    if is_git and include_content:
        safe_names = [entry["path"] for entry in files if entry["kind"] in ("file", "missing")]
        # Exclusions apply to patch payloads too, including tracked credential files.
        git_state["index_base64"] = base64.b64encode(index).decode()
        for key, flags in (("staged_diff_base64", ["--cached"]), ("unstaged_diff_base64", [])):
            patch = (
                git(root, "diff", *flags, "--binary", "--no-ext-diff", "--no-textconv", "--", *safe_names)
                if safe_names
                else b""
            )
            git_state[key] = base64.b64encode(patch).decode()
        git_state["patch_scope"] = "selected_nonexcluded_files"
    databases = []
    for name in sorted(set(dbs)):
        snapshot = sqlite_snapshot(safe_relative(root, name))
        if not include_content:
            snapshot["tables"] = [
                {"table": t["table"], "columns": t["columns"], "row_count": len(t["rows"])}
                for t in snapshot["tables"]
            ]
        databases.append({"path": name, **snapshot})
    return {
        "cwd": str(root),
        "root_id": digest(os.fsencode(root)),
        "git": git_state,
        "files": files,
        "databases": databases,
        "excluded": excluded,
        "contents_included": include_content,
        "coverage": {
            "selection": "git_tracked_and_nonignored_untracked" if is_git else "explicit_files",
            "external_services": "not_captured",
            "ignored_files": "not_captured_unless_selected",
            "unselected_databases": "not_captured",
            "dependency_installation": "not_captured",
            "atomic_machine_snapshot": False,
        },
    }


def capture(
    *,
    phase: str,
    root: Path,
    before: bytes | None = None,
    paths: list[str] | None = None,
    dbs: list[str] | None = None,
    include_content: bool = False,
    excludes: list[str] | None = None,
    checks: list[list[str]] | None = None,
    at: str | None = None,
    timeout: int = 300,
) -> dict:
    root = root.resolve(strict=True)
    if phase not in ("start", "end"):
        raise SessionlogError("capture phase must be start or end")
    paths, dbs, excludes = paths or [], dbs or [], excludes or []
    previous = None
    if phase == "start" and (before or checks):
        raise SessionlogError("start capture cannot include a previous capture or verification checks")
    if phase == "end":
        from .core import parse_json, source_bytes

        if before is None:
            raise SessionlogError("end capture requires --before")
        previous_envelope = validate(parse_json(before))
        if len(previous_envelope["sources"]) != 1 or previous_envelope["sources"][0]["harness"] != "state":
            raise SessionlogError("--before must be a start capture")
        previous = parse_json(source_bytes(previous_envelope["sources"][0]))
        if previous.get("phase") != "start" or previous["state"]["root_id"] != digest(os.fsencode(root)):
            raise SessionlogError("start capture root or phase does not match")
        selection = {"paths": paths, "dbs": dbs, "excludes": excludes, "include_content": include_content}
        if selection != previous["selection"]:
            raise SessionlogError("end capture must use the same selections as start")
    evidence = []
    for argv in checks or []:
        if not isinstance(argv, list) or not argv or not all(isinstance(s, str) and s for s in argv):
            raise SessionlogError("--verify requires a nonempty JSON array of argv strings")
        try:
            check_before = workspace_state(root, paths, dbs, include_content, excludes)
            code, out, err = run_bytes(argv, root, timeout)
            check_after = workspace_state(root, paths, dbs, include_content, excludes)
            result = {
                "argv": argv,
                "exit_code": code,
                "status": "passed" if code == 0 else "failed",
                "stdout_sha256": digest(out),
                "stderr_sha256": digest(err),
                "stdout_bytes": len(out),
                "stderr_bytes": len(err),
                "state_before_sha256": digest(canonical(check_before)),
                "state_after_sha256": digest(canonical(check_after)),
            }
            if include_content:
                result.update(
                    stdout_base64=base64.b64encode(out).decode(), stderr_base64=base64.b64encode(err).decode()
                )
            evidence.append(result)
        except SessionlogError as exc:
            evidence.append({"argv": argv, "status": "error", "reason": str(exc), "exit_code": None})
    state = workspace_state(root, paths, dbs, include_content, excludes)
    # Read selected state twice, detecting cross-file drift as well as partial writes.
    if state != workspace_state(root, paths, dbs, include_content, excludes):
        raise SessionlogError("workspace changed during capture; retry when quiescent")
    for check in evidence:
        check["valid_for_final_state"] = (
            check.get("state_before_sha256") == check.get("state_after_sha256") == digest(canonical(state))
        )
    versions = {"python_runtime": sys.version.split()[0]}
    for executable in ("git", "uv", "node", "bun"):
        if shutil.which(executable):
            try:
                code, out, err = run_bytes([executable, "--version"], root, 10)
                versions[executable] = {
                    "exit_code": code,
                    "output": (out + err).decode("utf-8", "replace").strip(),
                }
            except SessionlogError:
                versions[executable] = {"status": "unavailable"}
        else:
            versions[executable] = {"status": "not_installed"}
    doc = {
        "capture_schema": "datafooding.state/v1",
        "phase": phase,
        "state": state,
        "state_sha256": digest(canonical(state)),
        "versions": versions,
        "checks": evidence,
        "selection": {"paths": paths, "dbs": dbs, "excludes": excludes, "include_content": include_content},
    }
    if at is not None:
        doc["observed_at_supplied"] = at
    if previous is not None:
        doc["before_sha256"] = digest(before)
        old = {f["path"]: f for f in previous["state"]["files"]}
        new = {f["path"]: f for f in state["files"]}
        doc["changes"] = {
            "added": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "modified": sorted(k for k in new.keys() & old.keys() if new[k] != old[k]),
        }
    return normalize([("state", canonical(doc))])
