"""In-memory domain adapter with bounded, validated project operations."""
import copy
import math
from pathlib import Path
import secrets
import threading
import uuid

from .journal import Journal


def fields(value, allowed):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError("Unknown fields or invalid object")


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Number out of range")
    return value


def text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Invalid text length")
    return value.strip()


class Core:
    def __init__(self, root: Path, journal=None):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.journal = journal or Journal(self.root)
        self.revision = 0
        self.clips = [dict(id="user-clip", name="用户原有片段", start=0, end=1, track=0)]
        self.runs = {}
        self.new_session()

    def new_session(self):
        with self.lock:
            self.session = str(uuid.uuid4())
            self.token = secrets.token_urlsafe(32)
            self.status, self.name, self.percent = "waiting", "", None
            self.authored = set()
            self.agent_control = None
            self.journal.emit(self.session, "session", "waiting", "新会话等待 Agent")

    def cancel(self):
        with self.lock:
            self.status, self.percent = "cancelled", None
            self.journal.emit(self.session, "cancel", "cancelled", "已取消；已提交结果保留")

    def request_termination(self, reason="用户点击终止 Agent"):
        with self.lock:
            if self.status == "finished":
                raise ValueError("Task already finished")
            reason = text(reason, 400)
            if self.agent_control is None:
                self.agent_control = dict(sessionId=self.session, directive="terminate", status="requested", reason=reason)
                self.status, self.percent = "cancelled", None
                self.journal.emit(self.session, "stop-agent", "requested", "终止命令已发送，等待 Agent 确认")
            return copy.deepcopy(self.agent_control)

    def inspect(self):
        with self.lock:
            return copy.deepcopy(dict(sessionId=self.session, status=self.status, agentName=self.name,
                                      percent=self.percent, projectRevision=self.revision,
                                      scope=dict(projectId="demo", tracks=[0, 1], duration=30),
                                      clips=self.clips, runIds=list(self.runs), agentControl=self.agent_control))

    def execute(self, expected_session, token, command, payload):
        with self.lock:
            if expected_session != self.session or not secrets.compare_digest(token, self.token):
                raise ValueError("Stale or invalid session")
            if command == "control":
                fields(payload, [])
                return copy.deepcopy(self.agent_control)
            if command == "stop-agent":
                fields(payload, ["reason"])
                return self.request_termination(payload.get("reason", "User requested agent termination"))
            if command == "ack-stop":
                fields(payload, [])
                if self.agent_control is None:
                    raise ValueError("No termination command to acknowledge")
                if self.agent_control["status"] != "acknowledged":
                    self.agent_control["status"] = "acknowledged"
                    self.journal.emit(self.session, "stop-agent", "acknowledged", "Agent 已确认终止")
                return copy.deepcopy(self.agent_control)
            if command == "inspect":
                fields(payload, [])
                return self.inspect()
            if self.status in ("cancelled", "finished"):
                raise ValueError("Session is terminal; create a new session in the GUI")
            if command == "identify":
                fields(payload, ["name"])
                name = text(payload.get("name"), 8)
                if any(c.isspace() or not c.isprintable() for c in name):
                    raise ValueError("Name must contain 1–8 visible non-whitespace characters")
                if self.status == "active" and name != self.name:
                    raise ValueError("Another agent identity is already active")
                if self.status != "active":
                    self.name, self.status = name, "active"
                    self.journal.emit(self.session, command, "identified", f"{name} 已接管")
                return {"name": name}
            if self.status != "active":
                raise ValueError("Identify before mutating or reporting progress")
            if command == "log":
                fields(payload, ["message", "percent"])
                message = text(payload.get("message"), 2000)
                percent = payload.get("percent")
                if percent is not None:
                    if type(percent) is not int or not 0 <= percent <= 100:
                        raise ValueError("percent must be an integer 0–100")
                    self.percent = percent
                self.journal.emit(self.session, command, "progress", message, percent=self.percent)
                return {"recorded": True}
            if command == "apply":
                return self.apply(payload)
            if command == "undo":
                fields(payload, ["runId"])
                run_id = text(payload.get("runId"), 36)
                original = self.runs.get(run_id)
                if original is None:
                    raise ValueError("Unknown runId")
                current = [c for c in self.clips if c.get("runId") == run_id]
                if current != original:
                    raise ValueError("User edit/removal conflict: undo refused")
                self.clips = [c for c in self.clips if c.get("runId") != run_id]
                del self.runs[run_id]
                self.authored.discard(run_id)
                self.revision += 1
                self.journal.emit(self.session, command, "completed", "已撤回本次片段", {"runId": run_id})
                return {"removed": len(original), "projectRevision": self.revision}
            if command == "finish":
                fields(payload, ["summary"])
                summary = text(payload.get("summary"), 1000)
                if not any(c.get("runId") in self.authored for c in self.clips):
                    raise ValueError("Completion requires an actual non-undone clip from this session")
                self.status, self.percent = "finished", 100
                self.journal.emit(self.session, command, "finished", summary, percent=100)
                return {"finished": True}
            if command == "cancel":
                fields(payload, [])
                self.cancel()
                return {"cancelled": True}
            raise ValueError("Unsupported command")

    def apply(self, payload):
        fields(payload, ["expectedRevision", "events", "dryRun"])
        if type(payload.get("expectedRevision")) is not int or payload["expectedRevision"] != self.revision:
            raise ValueError("Project revision conflict; inspect again")
        if type(payload.get("dryRun", False)) is not bool:
            raise ValueError("dryRun must be boolean")
        events = payload.get("events")
        if not isinstance(events, list) or not 1 <= len(events) <= 32:
            raise ValueError("events must contain 1–32 timed clips")
        if len(self.clips) + len(events) > 64:
            raise ValueError("Demo clip limit reached (64); undo or restart the demo")
        checked = []
        for event in events:
            fields(event, ["name", "start", "end", "track"])
            name = text(event.get("name"), 80)
            start, end = number(event.get("start"), 0, 30), number(event.get("end"), 0, 30)
            track = event.get("track")
            if type(track) is not int or track not in (0, 1) or start >= end:
                raise ValueError("Clip outside track/time scope")
            if any(c["track"] == track and start < c["end"] and c["start"] < end
                   for c in self.clips + checked):
                raise ValueError("Clip overlaps existing or proposed work")
            checked.append(dict(name=name, start=start, end=end, track=track))
        if payload.get("dryRun", False):
            self.journal.emit(self.session, "apply", "validated", "预检通过，尚未写入", {"events": len(checked)})
            return {"dryRun": True, "events": len(checked), "projectRevision": self.revision}
        run_id = str(uuid.uuid4())
        for event in checked:
            event.update(id=str(uuid.uuid4()), runId=run_id)
        self.clips.extend(checked)
        self.runs[run_id] = copy.deepcopy(checked)
        self.authored.add(run_id)
        self.revision += 1
        self.journal.emit(self.session, "apply", "completed", "实际片段已写入演示时间线",
                          {"runId": run_id, "events": len(checked)})
        return {"runId": run_id, "events": len(checked), "projectRevision": self.revision}

