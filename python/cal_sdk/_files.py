import json
import os
from pathlib import Path
import tempfile

LIMIT = 64 * 1024


def read_json(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular packet file")
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("Packet exceeds 64 KiB")
    def reject(value):
        raise ValueError(f"Invalid JSON number: {value}")
    return json.loads(data.decode("utf-8-sig"), parse_constant=reject)


def atomic_json(path, value):
    if path.is_symlink():
        raise ValueError("Refusing symlink target")
    data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(data) > LIMIT:
        raise ValueError("Packet exceeds 64 KiB")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)

