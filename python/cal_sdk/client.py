import json
from pathlib import Path
import time
import uuid

from ._files import atomic_json, read_json


class AgentLinkError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


class AgentLink:
    """Explicit project/session binding. Obtain both from the current GUI Prompt."""
    def __init__(self, state_dir, session_id, project_id):
        self.root = Path(state_dir).resolve()
        self.session_id = str(uuid.UUID(session_id))
        self.project_id = project_id

    def _session(self):
        session = read_json(self.root / "session.json")
        if session.get("version") != 1:
            raise AgentLinkError("ProtocolVersion", "Unsupported session version")
        if session.get("sessionId") != self.session_id or session.get("projectId") != self.project_id:
            raise AgentLinkError("StaleSession", "Obtain a fresh Prompt")
        age = time.time() * 1000 - session.get("heartbeatMs", 0)
        if not -1000 <= age <= 6000:
            raise AgentLinkError("Disconnected", "Host heartbeat expired or invalid")
        return session

    def call(self, command, payload=None, *, timeout=10, request_id=None):
        payload = {} if payload is None else payload
        if not isinstance(payload, dict) or not 0 < timeout <= 60:
            raise ValueError("Invalid payload or timeout")
        session = self._session()
        if command not in ("inspect", "events", "cleanup", "cancel", "control", "stop-agent", "ack-stop"):
            signal = self.control()
            if signal:
                raise AgentLinkError("AgentTerminationRequested", "Stop work and call checkpoint() to acknowledge termination")
        request_id = str(uuid.UUID(request_id)) if request_id else str(uuid.uuid4())
        name = f"{self.session_id}-{request_id}.json"
        control = command in ("stop-agent", "control", "ack-stop")
        request = self.root / ("control-requests" if control else "requests") / name
        response = self.root / ("control-responses" if control else "responses") / name
        response.unlink(missing_ok=True)
        atomic_json(request, dict(version=1, id=request_id, sessionId=self.session_id,
                                 projectId=self.project_id, token=session["token"],
                                 command=command, payload=payload))
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                try:
                    current = self._session()
                except (AgentLinkError, OSError) as exc:
                    raise AgentLinkError("UnknownResult", "Session lost after publication; inspect before retrying") from exc
                if current["token"] != session["token"]:
                    raise AgentLinkError("UnknownResult", "Session changed after publication")
                if response.exists():
                    packet = read_json(response)
                    response.unlink(missing_ok=True)
                    if packet.get("version") != 1 or packet.get("id") != request_id:
                        raise AgentLinkError("UnknownResult", "Mismatched response; inspect before retrying")
                    if not packet.get("ok"):
                        error = packet.get("error") or {}
                        raise AgentLinkError(error.get("code", "InvalidPacket"), error.get("message", "Operation failed"))
                    return packet["result"]
                time.sleep(.05)
            raise AgentLinkError("UnknownResult", f"{command} timed out; inspect before retrying a mutation")
        finally:
            request.unlink(missing_ok=True)

    def control(self):
        """Read session-scoped termination without waiting for a busy domain adapter."""
        self._session()
        signal = read_json(self.root / "agent-control.json")
        if signal is not None and (not isinstance(signal, dict) or signal.get("version") != 1
                or signal.get("sessionId") != self.session_id or signal.get("projectId") != self.project_id
                or signal.get("directive") != "terminate" or signal.get("status") not in ("requested", "acknowledged")):
            raise AgentLinkError("InvalidControl", "Termination signal does not match this session")
        return signal

    def request_termination(self, reason="User requested agent termination"):
        return self.call("stop-agent", {"reason": reason})

    def checkpoint(self):
        """Agent-side hook: acknowledge then unwind the current task; GUI must not call this."""
        signal = self.control()
        if signal:
            self.call("ack-stop")
            raise AgentLinkError("AgentTerminationRequested", signal["reason"])


class LogProjection:
    """Client-local display clearing; never reset host state or raw logs."""
    def __init__(self, max_rows=400):
        self.epoch = None
        self.after = self.latest = self.visible_after = 0
        self.rows = []
        self.max_rows = max_rows
        self.gap = False

    def query(self):
        return dict(epoch=self.epoch, after=self.after)

    def accept(self, page):
        if page["epoch"] != self.epoch:
            self.epoch = page["epoch"]
            self.after = self.latest = self.visible_after = 0
            self.rows = []
            self.gap = False
        self.gap |= page["gap"]
        for event in page["events"]:
            if event["seq"] <= max(self.after, self.visible_after):
                continue
            if event["phase"] == "progress":
                self.rows = [row for row in self.rows if not (
                    row["sessionId"] == event["sessionId"] and row["operation"] == event["operation"]
                    and row["phase"] == "progress")]
            self.rows.append(event)
        self.rows = self.rows[-self.max_rows:]
        self.after = max(self.after, page["seq"], self.visible_after)
        self.latest = max(self.latest, page["latestSeq"])

    def clear(self):
        # Cover unread retained history as well as an older in-flight events page.
        self.visible_after = self.after = self.latest
        self.rows = []
        self.gap = False

