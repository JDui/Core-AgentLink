"""SDK/domain tests always run; real Rust IPC tests require C_AL_CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "python"))
from cal_sdk import AgentLink, AgentLinkError, LogProjection
from examples.rust_python.adapter import Timeline


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.timeline = Timeline()
        self.context = dict(version=1, projectId="demo", sessionId=str(uuid.uuid4()))
        self.proposal = dict(expectedRevision=0, events=[dict(name="x", start=2, end=3, track=0)])

    def call(self, command, payload):
        return self.timeline.execute(self.context, command, payload)

    def test_dry_run_finish_apply_revision_and_undo_conflict(self):
        self.call("apply", dict(self.proposal, dryRun=True))
        self.assertEqual(self.timeline.revision, 0)
        with self.assertRaises(ValueError):
            self.call("finish", {"summary": "done"})
        run = self.call("apply", self.proposal)
        self.assertTrue(self.call("finish", {"summary": "done"})["finished"])
        with self.assertRaises(ValueError):
            self.call("apply", self.proposal)
        self.timeline.clips[-1]["name"] = "user edited"
        with self.assertRaises(ValueError):
            self.call("undo", {"runId": run["runId"]})
        self.assertEqual(self.timeline.clips[0]["id"], "user-clip")

    def test_undo_removes_only_own_result_and_rejects_other_session(self):
        run = self.call("apply", self.proposal)
        with self.assertRaises(ValueError):
            self.timeline.execute(dict(self.context, sessionId=str(uuid.uuid4())), "undo", {"runId": run["runId"]})
        self.call("undo", {"runId": run["runId"]})
        self.assertEqual(len(self.timeline.clips), 1)
        with self.assertRaises(ValueError):
            self.call("finish", {"summary": "done"})

    def test_scope_and_payload_validation(self):
        for event in [dict(name="x", start=0, end=2, track=0), dict(name="x", start=2, end=3, track=True),
                      dict(name="x", start=float("nan"), end=3, track=0)]:
            with self.assertRaises(ValueError):
                self.call("apply", dict(self.proposal, events=[event]))
        with self.assertRaises(ValueError):
            self.call("apply", dict(self.proposal, dryRun="false"))


class ProjectionTests(unittest.TestCase):
    def test_clear_skips_unread_history_and_in_flight_pages(self):
        projection = LogProjection()
        page = dict(epoch="one", seq=2, latestSeq=10, gap=False,
                    events=[dict(seq=1, sessionId="s", operation="log", phase="note")])
        projection.accept(page)
        projection.clear()
        projection.accept(dict(page, seq=8, events=[dict(seq=6, sessionId="s", operation="log", phase="note")]))
        self.assertEqual(projection.rows, [])
        self.assertEqual(projection.after, 10)
        projection.accept(dict(epoch="new", seq=1, latestSeq=1, gap=False,
                               events=[dict(seq=1, sessionId="new", operation="log", phase="note")]))
        self.assertEqual(len(projection.rows), 1)

    def test_sdk_rejects_non_object_before_publication(self):
        client = AgentLink(".", str(uuid.uuid4()), "demo")
        with self.assertRaises(ValueError):
            client.call("apply", [])


@unittest.skipUnless(os.environ.get("C_AL_CLI"), "Set C_AL_CLI to the built Rust CLI for live interoperability")
class RustLiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cli = Path(os.environ["C_AL_CLI"]).resolve()
        self.host = subprocess.Popen([str(self.cli), "serve", "--state-dir", str(self.root),
                                      "--project-id", "demo", "--python", sys.executable,
                                      "--adapter", str(REPO / "examples/rust_python/adapter.py")],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_host)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            session = self.root / "session.json"
            if session.exists():
                data = json.loads(session.read_text(encoding="utf-8"))
                self.client = AgentLink(self.root, data["sessionId"], "demo")
                return
            if self.host.poll() is not None:
                self.fail("Rust host exited before session publication")
            time.sleep(.05)
        self.fail("Rust host failed to become ready")

    def stop_host(self):
        if self.host.poll() is None:
            # Kill only the test-created process. On Windows use console control in manual smoke.
            self.host.terminate()
            self.host.wait(timeout=8)

    def test_rust_cli_and_python_sdk_share_one_real_session(self):
        result = subprocess.run([str(self.cli), "identify", "--state-dir", str(self.root),
                                 "--project-id", "demo", "--session", self.client.session_id,
                                 "--name", "Codex"], capture_output=True, encoding="utf-8", timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        proposal = dict(expectedRevision=0, events=[dict(name="微笑", start=2, end=3, track=0)])
        self.client.call("apply", dict(proposal, dryRun=True))
        with self.assertRaises(AgentLinkError):
            self.client.call("finish", {"summary": "not yet"})
        request_id = str(uuid.uuid4())
        run = self.client.call("apply", proposal, request_id=request_id)
        self.assertEqual(run, self.client.call("apply", proposal, request_id=request_id))
        snapshot = self.client.call("inspect")
        self.assertEqual(len(snapshot["domain"]["clips"]), 2)
        self.client.call("finish", {"summary": "actual clip checked"})
        self.assertEqual(self.client.call("inspect")["status"], "finished")

    def test_cancel_cleanup_and_stale_binding(self):
        self.client.call("identify", {"name": "Python"})
        self.client.call("log", {"message": "real note"})
        page = self.client.call("events", {})
        self.assertTrue(page["events"])
        self.client.call("cleanup", {})
        self.client.call("cancel", {})
        with self.assertRaisesRegex(AgentLinkError, "TerminalSession"):
            self.client.call("log", {"message": "late"})
        with self.assertRaisesRegex(AgentLinkError, "StaleSession"):
            AgentLink(self.root, str(uuid.uuid4()), "demo").call("inspect")
        with self.assertRaisesRegex(AgentLinkError, "StaleSession"):
            AgentLink(self.root, self.client.session_id, "other").call("inspect")

