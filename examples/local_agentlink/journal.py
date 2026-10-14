"""Single-writer JSONL retention and an epoch/sequence based GUI projection."""
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
import uuid


class Journal:
    def __init__(self, root: Path, max_bytes=2 * 1024 * 1024, archives=2, rows=400):
        if max_bytes < 256 or archives < 0 or rows < 1:
            raise ValueError("Invalid retention limits")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "activity.jsonl"
        self.epoch = str(uuid.uuid4())
        self.seq = 0
        self.max_bytes, self.archives = max_bytes, archives
        self.events = deque(maxlen=rows)
        self.lock = threading.RLock()
        self.error = None

    def _archives(self):
        return sorted(
            (p for p in self.root.iterdir()
             if re.fullmatch(r"archive-[0-9]+\.jsonl", p.name)
             and p.is_file() and not p.is_symlink()),
            key=lambda p: int(p.stem.split("-")[1]),
        )

    def emit(self, session, operation, phase, message, details=None, percent=None):
        with self.lock:
            next_seq = self.seq + 1
            event = dict(epoch=self.epoch, seq=next_seq,
                         time=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         sessionId=session, operation=operation, phase=phase,
                         message=str(message)[:2000], details=details or {}, percent=percent)
            data = (json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            if len(data) > self.max_bytes:
                raise ValueError("Log event exceeds file limit")
            self.seq = next_seq
            self.events.append(event)
            try:
                if self.path.is_symlink():
                    raise OSError("Refusing symlink log path")
                size = self.path.stat().st_size if self.path.exists() else 0
                if size + len(data) > self.max_bytes:
                    old = self._archives()
                    number = int(old[-1].stem.split("-")[1]) + 1 if old else 1
                    archive = self.root / f"archive-{number:06d}.jsonl"
                    if archive.exists() or archive.is_symlink():
                        raise OSError("Archive target already exists")
                    self.path.rename(archive)
                    old = self._archives()
                    for path in old[:max(0, len(old) - self.archives)]:
                        path.unlink()
                with self.path.open("ab") as stream:
                    stream.write(data)
                self.error = None
            except OSError as exc:
                self.error = f"Log persistence failed: {exc}"
            return event

    def since(self, epoch=None, after=0):
        with self.lock:
            reset = epoch != self.epoch
            after = 0 if reset else after
            first = self.events[0]["seq"] if self.events else self.seq + 1
            return dict(epoch=self.epoch, seq=self.seq, reset=reset,
                        gap=after < first - 1,
                        events=[dict(e) for e in self.events if e["seq"] > after],
                        error=self.error)

    def cleanup(self, session):
        """Only managed regular archive files; preserve active log and core state."""
        with self.lock:
            count = 0
            try:
                for path in self._archives():
                    path.unlink()
                    count += 1
            except OSError as exc:
                self.emit(session, "cleanup", "failed", str(exc), {"removed": count})
                raise
            self.emit(session, "cleanup", "completed", "已清理旧日志归档", {"removed": count})
            return count

