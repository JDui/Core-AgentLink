from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

from examples.local_agentlink.core import Core
from examples.local_agentlink.host import Runtime, handler_for
from examples.local_agentlink.journal import Journal
from examples.local_agentlink.transport import atomic_json, read_json, request

REPO = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.core = Core(Path(self.temp.name))
        self.call("identify", {"name": "Codex"})

    def call(self, command, payload=None):
        return self.core.execute(self.core.session, self.core.token, command, payload or {})

    def proposal(self, **changes):
        payload = dict(expectedRevision=self.core.revision,
                       events=[dict(name="微笑", start=2, end=3, track=0)])
        payload.update(changes)
        return payload

    def test_dry_run_does_not_create_result_or_enable_finish(self):
        self.call("apply", self.proposal(dryRun=True))
        self.assertEqual(self.core.revision, 0)
        self.assertEqual(len(self.core.clips), 1)
        with self.assertRaisesRegex(ValueError, "actual"):
            self.call("finish", {"summary": "finished"})

    def test_apply_preserves_user_work_and_undo_conflict_is_atomic(self):
        run = self.call("apply", self.proposal())
        self.core.clips[-1]["name"] = "用户修改"
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.call("undo", {"runId": run["runId"]})
        self.assertEqual(self.core.clips[0]["id"], "user-clip")
        self.assertEqual(len(self.core.clips), 2)
        self.assertIn(run["runId"], self.core.runs)

    def test_undo_removes_only_own_work_and_finish_requires_remaining_clip(self):
        run = self.call("apply", self.proposal())
        self.call("undo", {"runId": run["runId"]})
        self.assertEqual([c["id"] for c in self.core.clips], ["user-clip"])
        with self.assertRaises(ValueError):
            self.call("finish", {"summary": "done"})

    def test_new_session_cannot_finish_using_old_run(self):
        self.call("apply", self.proposal())
        self.core.new_session()
        self.call("identify", {"name": "Claude"})
        with self.assertRaises(ValueError):
            self.call("finish", {"summary": "done"})

    def test_stale_session_and_invalid_token_are_rejected(self):
        session, token = self.core.session, self.core.token
        self.core.new_session()
        with self.assertRaises(ValueError):
            self.core.execute(session, token, "apply", self.proposal())
        with self.assertRaises(ValueError):
            self.core.execute(self.core.session, "bad", "inspect", {})

    def test_cancel_retains_committed_data_and_blocks_further_writes(self):
        self.call("apply", self.proposal())
        self.call("cancel")
        with self.assertRaises(ValueError):
            self.call("log", {"message": "late"})
        self.assertEqual(len(self.call("inspect")["clips"]), 2)

    def test_revision_scope_nan_bool_unknown_fields_and_overlap(self):
        cases = [self.proposal(expectedRevision=99), self.proposal(expectedRevision=False),
                 self.proposal(extra=True), self.proposal(dryRun="false")]
        for event in [dict(name="x", start=float("nan"), end=3, track=0),
                      dict(name="x", start=2, end=3, track=True),
                      dict(name="x", start=2, end=3, track=9),
                      dict(name="x", start=0, end=2, track=0)]:
            cases.append(self.proposal(events=[event]))
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.call("apply", payload)
        self.assertEqual(self.core.revision, 0)

    def test_complete_then_write_rejected(self):
        self.call("apply", self.proposal())
        self.call("finish", {"summary": "真实片段已核对"})
        self.assertEqual(self.call("inspect")["status"], "finished")
        with self.assertRaises(ValueError):
            self.call("apply", self.proposal())


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = Journal(self.root, max_bytes=1200, archives=2, rows=3)

    def emit(self):
        return self.journal.emit("session", "log", "note", "完整 UTF-8 日志🙂" * 8)

    def test_rotation_bounds_complete_records_and_restart_archive_number(self):
        for _ in range(30):
            self.emit()
        paths = list(self.root.glob("*.jsonl"))
        self.assertLessEqual(len(paths), 3)
        for path in paths:
            self.assertLessEqual(path.stat().st_size, 1200)
            for line in path.read_text(encoding="utf-8").splitlines():
                json.loads(line)
        last = max(p.name for p in self.root.glob("archive-*.jsonl"))
        second = Journal(self.root, max_bytes=1200)
        for _ in range(5):
            second.emit("s", "log", "note", "x" * 500)
        self.assertGreater(max(p.name for p in self.root.glob("archive-*.jsonl")), last)

    def test_clear_cursor_never_replays_and_gap_is_explicit(self):
        for _ in range(8):
            self.emit()
        self.assertTrue(self.journal.since(self.journal.epoch, 0)["gap"])
        visible_after = self.journal.seq
        self.assertEqual(self.journal.since(self.journal.epoch, visible_after)["events"], [])
        event = self.emit()
        self.assertEqual(self.journal.since(self.journal.epoch, visible_after)["events"], [event])

    def test_cleanup_preserves_active_log_unmanaged_files_and_undo(self):
        core = Core(self.root, self.journal)
        core.execute(core.session, core.token, "identify", {"name": "Codex"})
        core.execute(core.session, core.token, "apply", {
            "expectedRevision": 0, "events": [dict(name="x", start=2, end=3, track=0)]})
        for _ in range(10):
            self.emit()
        (self.root / "user.jsonl").write_text("user")
        session, runs = core.session, dict(core.runs)
        self.assertGreater(self.journal.cleanup(core.session), 0)
        self.assertTrue(self.journal.path.exists())
        self.assertEqual((self.root / "user.jsonl").read_text(), "user")
        self.assertEqual(core.session, session)
        self.assertEqual(core.runs, runs)
        self.assertEqual(list(self.root.glob("archive-*.jsonl")), [])

    def test_epoch_resets_old_cursor_and_io_failure_is_visible(self):
        second = Journal(self.root)
        second.emit("s", "log", "note", "restart")
        result = second.since(self.journal.epoch, 9999)
        self.assertTrue(result["reset"])
        self.assertEqual(len(result["events"]), 1)
        second.path.unlink()
        second.path.mkdir()
        second.emit("s", "log", "note", "cannot write")
        self.assertIn("failed", second.since()["error"])


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = Runtime(self.root)
        self.addCleanup(self.runtime.close)
        self.runtime.start()

    def cli(self, *args, session=None):
        proc = subprocess.run([sys.executable, str(REPO / "examples/agentlink_cli.py"),
                               "--state-dir", str(self.root), "--session", session or self.runtime.core.session,
                               "--live", *args], cwd=self.temp.name, capture_output=True,
                              encoding="utf-8", timeout=8)
        return proc.returncode, json.loads(proc.stdout)

    def test_real_cli_workflow_and_stale_prompt(self):
        self.assertEqual(self.cli("identify", "--name", "Codex")[0], 0)
        self.assertEqual(self.cli("inspect")[1]["result"]["projectRevision"], 0)
        proposal = self.root / "proposal.json"
        atomic_json(proposal, {"expectedRevision": 0, "events": [dict(name="微笑", start=2, end=3, track=0)]})
        self.assertEqual(self.cli("apply", "--proposal", str(proposal), "--dry-run")[0], 0)
        result = self.cli("apply", "--proposal", str(proposal))[1]["result"]
        self.assertIn("runId", result)
        self.assertEqual(len(self.cli("inspect")[1]["result"]["clips"]), 2)
        self.assertEqual(self.cli("finish", "--summary", "已验证片段")[0], 0)
        old = self.runtime.core.session
        self.runtime.rotate()
        self.assertEqual(self.cli("inspect", session=old)[0], 1)

    def test_request_dedup_and_id_content_collision(self):
        core = self.runtime.core
        packet = dict(id=str(uuid.uuid4()), sessionId=core.session, token=core.token,
                      command="identify", payload={"name": "Codex"})
        self.assertEqual(self.runtime.packet(packet), self.runtime.packet(packet))
        packet = dict(id=str(uuid.uuid4()), sessionId=core.session, token=core.token, command="apply",
                      payload={"expectedRevision": 0, "events": [dict(name="x", start=2, end=3, track=0)]})
        first = self.runtime.packet(packet)
        self.assertEqual(first, self.runtime.packet(packet))
        self.assertEqual(core.revision, 1)
        packet = dict(packet, payload={"expectedRevision": 1})
        with self.assertRaisesRegex(ValueError, "different"):
            self.runtime.packet(packet)

    def test_timeout_is_unknown_and_packet_cleanup(self):
        self.runtime.stop.set()
        self.runtime.thread.join(timeout=2)
        with self.assertRaisesRegex(TimeoutError, "Unknown result"):
            request(self.root, self.runtime.core.session, "inspect", {}, timeout=.1)
        self.assertEqual(list((self.root / "requests").glob("*.json")), [])
        orphan = self.root / "responses" / f"{uuid.uuid4()}-{uuid.uuid4()}.json"
        orphan.write_text("{}")
        os.utime(orphan, (time.time() - 120, time.time() - 120))
        unrelated = self.root / "responses" / "user.json"
        unrelated.write_text("keep")
        self.runtime.cleanup_ipc()
        self.assertFalse(orphan.exists())
        self.assertTrue(unrelated.exists())

    def test_second_host_same_directory_is_rejected(self):
        with self.assertRaises(FileExistsError):
            Runtime(self.root)
        self.assertEqual(read_json(self.root / "session.json")["sessionId"], self.runtime.core.session)

    def test_http_origin_guard_snapshot_and_cleanup(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.runtime))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(url) as response:
                self.assertIn(self.runtime.ui_token, response.read().decode())
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(url + "/cancel", method="POST"))
            self.assertEqual(error.exception.code, 403)
            headers = {"Origin": url, "X-AgentLink-UI": self.runtime.ui_token}
            with urllib.request.urlopen(urllib.request.Request(url + "/snapshot", headers=headers)) as response:
                self.assertEqual(json.load(response)["status"], "waiting")
            with urllib.request.urlopen(urllib.request.Request(url + "/cleanup", headers=headers, method="POST")) as response:
                self.assertTrue(json.load(response)["ok"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

