"""The example application owns its project; Rust owns the control lifecycle."""
import copy
import json
import math
import sys
import uuid


def fields(value, names):
    if not isinstance(value, dict) or set(value) - set(names):
        raise ValueError("Unknown fields or invalid object")


class Timeline:
    def __init__(self):
        self.revision = 0
        self.clips = [dict(id="user-clip", name="用户原有片段", start=0, end=1, track=0)]
        self.runs = {}

    def execute(self, context, command, payload):
        if context.get("version") != 1 or context.get("projectId") != "demo":
            raise ValueError("Wrong protocol or project")
        if command == "inspect":
            fields(payload, [])
            return dict(projectRevision=self.revision,
                        scope=dict(tracks=[0, 1], duration=30), clips=copy.deepcopy(self.clips), runIds=list(self.runs))
        if command == "apply":
            fields(payload, ["expectedRevision", "events", "dryRun"])
            if type(payload.get("expectedRevision")) is not int or payload["expectedRevision"] != self.revision:
                raise ValueError("Revision conflict; inspect again")
            if type(payload.get("dryRun", False)) is not bool:
                raise ValueError("dryRun must be boolean")
            events = payload.get("events")
            if not isinstance(events, list) or not 1 <= len(events) <= 32 or len(self.clips) + len(events) > 64:
                raise ValueError("Batch/clip limit exceeded")
            checked = []
            for event in events:
                fields(event, ["name", "start", "end", "track"])
                name = event.get("name")
                if not isinstance(name, str) or not name.strip() or len(name) > 80:
                    raise ValueError("Invalid clip name")
                start, end, track = event.get("start"), event.get("end"), event.get("track")
                for number in (start, end):
                    if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 30:
                        raise ValueError("Invalid time")
                if type(track) is not int or track not in (0, 1) or start >= end:
                    raise ValueError("Outside track/time scope")
                if any(c["track"] == track and start < c["end"] and c["start"] < end for c in self.clips + checked):
                    raise ValueError("Overlapping user or proposed clip")
                checked.append(dict(name=name, start=start, end=end, track=track))
            if payload.get("dryRun", False):
                return dict(dryRun=True, eventCount=len(checked), projectRevision=self.revision)
            run_id = str(uuid.uuid4())
            for event in checked:
                event.update(id=str(uuid.uuid4()), runId=run_id, sessionId=context["sessionId"])
            self.clips.extend(checked)
            self.runs[run_id] = copy.deepcopy(checked)
            self.revision += 1
            return dict(runId=run_id, eventCount=len(checked), projectRevision=self.revision)
        if command == "undo":
            fields(payload, ["runId"])
            run_id = payload.get("runId")
            original = self.runs.get(run_id)
            current = [c for c in self.clips if c.get("runId") == run_id]
            if original is None or current != original:
                raise ValueError("Undo conflict: run missing or user edited a clip")
            if any(c["sessionId"] != context["sessionId"] for c in original):
                raise ValueError("Run belongs to another session")
            self.clips = [c for c in self.clips if c.get("runId") != run_id]
            del self.runs[run_id]
            self.revision += 1
            return dict(removed=len(original), projectRevision=self.revision)
        if command == "finish":
            fields(payload, ["summary"])
            if not any(c.get("sessionId") == context["sessionId"] for c in self.clips):
                raise ValueError("No actual non-undone clip from this session")
            return dict(finished=True, projectRevision=self.revision)
        raise ValueError("Unsupported domain command")


def serve():
    timeline = Timeline()
    sys.stdout.reconfigure(encoding="utf-8")
    # stdout is reserved for the protocol; diagnostics belong on stderr.
    while True:
        raw = sys.stdin.buffer.readline(65537)
        if not raw:
            break
        request_id = None
        try:
            if len(raw) > 65536 or not raw.endswith(b"\n"):
                raise ValueError("Adapter input exceeds limit")
            packet = json.loads(raw.decode("utf-8"))
            request_id = packet["id"]
            result = timeline.execute(packet["context"], packet["command"], packet["payload"])
            response = dict(id=request_id, ok=True, result=result)
        except (ValueError, KeyError, TypeError) as exc:
            response = dict(id=request_id, ok=False, error=dict(code="DomainValidation", message=str(exc)))
        print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == "__main__":
    serve()

