import json
import sqlite3
import subprocess
import sys

import pytest

from sessionlog.capture import capture, workspace_state
from sessionlog.core import SessionlogError, canonical, digest, parse_json, source_bytes, validate


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Synthetic Test"], cwd=root, check=True)
    (root / "demo.py").write_text("before\n")
    (root / "uv.lock").write_text("synthetic-lock\n")
    (root / ".gitignore").write_text("ignored\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "synthetic"], cwd=root, check=True)
    (root / "demo.py").write_text("dirty-before\n")
    (root / "untracked.txt").write_text("untracked\n")
    (root / ".env").write_text("SYNTHETIC_SECRET=never-record\n")
    (root / "ignored").write_text("ignored\n")
    return root


def doc(envelope):
    validate(envelope)
    return parse_json(source_bytes(envelope["sources"][0]))


def test_start_end_dirty_state_and_failed_verification(workspace):
    start = capture(phase="start", root=workspace, include_content=True)
    initial = doc(start)
    assert any(f["path"] == "untracked.txt" for f in initial["state"]["files"])
    assert any(f.get("dependency_lock") for f in initial["state"]["files"])
    assert initial["state"]["excluded"] == [{"path": ".env", "reason": "exclusion_policy"}]
    assert b"never-record" not in canonical(start)
    assert canonical(start) == canonical(capture(phase="start", root=workspace, include_content=True))
    (workspace / "demo.py").write_text("after\n")
    (workspace / "new.py").write_text("new\n")
    end = capture(
        phase="end",
        root=workspace,
        before=canonical(start),
        include_content=True,
        checks=[[sys.executable, "-c", "print('synthetic evidence'); raise SystemExit(7)"]],
    )
    final = doc(end)
    assert final["before_sha256"] == digest(canonical(start))
    assert final["changes"]["modified"] == ["demo.py"]
    assert final["changes"]["added"] == ["new.py"]
    assert final["checks"][0]["status"] == "failed"
    assert final["checks"][0]["exit_code"] == 7


def test_capture_options_roots_and_symlinks(workspace, tmp_path):
    (workspace / "link").symlink_to(tmp_path / "outside")
    state = workspace_state(workspace, [], [], False, [])
    assert next(f for f in state["files"] if f["path"] == "link")["followed"] is False
    with pytest.raises(SessionlogError):
        workspace_state(workspace, ["../outside"], [], False, [])
    start = capture(phase="start", root=workspace)
    with pytest.raises(SessionlogError, match="selections"):
        capture(phase="end", root=workspace, before=canonical(start), paths=["extra"])
    with pytest.raises(SessionlogError):
        capture(phase="end", root=tmp_path, before=canonical(start))


def test_later_mutation_invalidates_earlier_passing_check(workspace):
    start = capture(phase="start", root=workspace)
    end = capture(
        phase="end",
        root=workspace,
        before=canonical(start),
        checks=[
            [sys.executable, "-c", "pass"],
            [sys.executable, "-c", "from pathlib import Path; Path('demo.py').write_text('mutation')"],
        ],
    )
    checks = doc(end)["checks"]
    assert all(c["status"] == "passed" for c in checks)
    assert all(c["valid_for_final_state"] is False for c in checks)


def test_sqlite_logical_snapshot_is_consistent(workspace):
    database = workspace / "test.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE items (id INTEGER, content BLOB)")
    connection.executemany("INSERT INTO items VALUES (?, ?)", [(2, b"b"), (1, b"a")])
    connection.commit()
    connection.close()
    envelope = capture(phase="start", root=workspace, dbs=["test.sqlite"], include_content=True)
    snap = doc(envelope)["state"]["databases"][0]
    assert snap["byte_identical_backup"] is False
    assert [row[0] for row in snap["tables"][0]["rows"]] == [1, 2]
    assert snap["sha256"] == digest(canonical(snap["tables"]))


def test_excluded_tracked_secrets_do_not_enter_patch_payload(workspace):
    import base64

    (workspace / ".env").write_text("SYNTHETIC=initial-secret\n")
    subprocess.run(["git", "add", ".env"], cwd=workspace, check=True)
    (workspace / ".env").write_text("SYNTHETIC=changed-secret\n")
    captured = doc(capture(phase="start", root=workspace, include_content=True))
    for key in ("staged_diff_base64", "unstaged_diff_base64"):
        patch = base64.b64decode(captured["state"]["git"][key])
        assert b"initial-secret" not in patch
        assert b"changed-secret" not in patch


def test_cross_file_drift_detected(workspace, monkeypatch):
    import sessionlog.capture as module

    original = module.workspace_state
    count = 0

    def drifting(*args):
        nonlocal count
        result = original(*args)
        count += 1
        if count == 1:
            (workspace / "demo.py").write_text("changed during capture")
        return result

    monkeypatch.setattr(module, "workspace_state", drifting)
    with pytest.raises(SessionlogError, match="changed during capture"):
        capture(phase="start", root=workspace)


def test_capture_cli_failure_still_writes_evidence(workspace, tmp_path):
    start, end = tmp_path / "start.json", tmp_path / "end.json"
    prefix = [sys.executable, "-m", "sessionlog.cli", "capture"]
    first = subprocess.run(
        [*prefix, "start", "--root", str(workspace), "-o", str(start)], capture_output=True
    )
    assert first.returncode == 0, first.stderr
    last = subprocess.run(
        [
            *prefix,
            "end",
            "--root",
            str(workspace),
            "--before",
            str(start),
            "--verify",
            json.dumps([sys.executable, "-c", "raise SystemExit(2)"]),
            "-o",
            str(end),
        ],
        capture_output=True,
    )
    assert last.returncode == 3, last.stderr
    assert end.exists()
    assert doc(json.loads(end.read_bytes()))["checks"][0]["exit_code"] == 2
