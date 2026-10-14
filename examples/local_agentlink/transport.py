"""Atomic, bounded local IPC. The CLI never opens domain data for writing."""
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

LIMIT = 64 * 1024
TTL = 6


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(data) > LIMIT:
        raise ValueError("Packet too large")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(data)
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def read_json(path: Path):
    if path.is_symlink():
        raise ValueError("Refusing symlink packet")
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("Packet too large")
    def reject_constant(value):
        raise ValueError(f"Invalid JSON number: {value}")
    return json.loads(data.decode("utf-8-sig"), parse_constant=reject_constant)


def session_at(root: Path, expected_session):
    session = read_json(root / "session.json")
    if session.get("sessionId") != expected_session:
        raise ValueError("Prompt session is stale; obtain a new Prompt")
    if time.time() - session.get("heartbeat", 0) > TTL:
        raise ValueError("Host heartbeat expired")
    return session


def request(root: Path, expected_session, command, payload, timeout=10, request_id=None):
    root = Path(root).resolve()
    expected_session = str(uuid.UUID(expected_session))
    request_id = str(uuid.UUID(request_id)) if request_id else str(uuid.uuid4())
    session = session_at(root, expected_session)
    filename = f"{expected_session}-{request_id}.json"
    response_path = root / "responses" / filename
    request_path = root / "requests" / filename
    # A retry is explicit. Remove a prior transport response, not the host's dedup cache.
    response_path.unlink(missing_ok=True)
    atomic_json(request_path, dict(id=request_id, sessionId=expected_session,
                                  token=session["token"], command=command, payload=payload))
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            current = session_at(root, expected_session)
            if current["token"] != session["token"]:
                raise ValueError("Session changed; stop old work")
            if response_path.exists():
                response = read_json(response_path)
                response_path.unlink(missing_ok=True)
                if not response.get("ok"):
                    raise ValueError(response.get("error", "Operation failed"))
                return response["result"]
            time.sleep(0.05)
        raise TimeoutError(f"Unknown result for {command}; inspect before retrying a write")
    finally:
        request_path.unlink(missing_ok=True)

