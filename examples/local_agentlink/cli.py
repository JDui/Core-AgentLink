import argparse
import json
import os
from pathlib import Path
import sys

from .transport import read_json, request


def main():
    parser = argparse.ArgumentParser(description="C-AL demo live CLI")
    parser.add_argument("--workdir", help="Repository root; for absolute invocation from any cwd")
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--live", required=True, action="store_true")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--request-id", help="Explicit UUID for retry deduplication within current host")
    commands = parser.add_subparsers(dest="command", required=True)
    identify = commands.add_parser("identify")
    identify.add_argument("--name", required=True)
    commands.add_parser("inspect")
    log = commands.add_parser("log")
    log.add_argument("--message", required=True)
    log.add_argument("--percent", type=int)
    apply = commands.add_parser("apply")
    apply.add_argument("--proposal", required=True, type=Path)
    apply.add_argument("--dry-run", action="store_true")
    undo = commands.add_parser("undo")
    undo.add_argument("--run-id", required=True)
    finish = commands.add_parser("finish")
    finish.add_argument("--summary", required=True)
    commands.add_parser("cancel")
    args = parser.parse_args()
    try:
        if args.workdir:
            os.chdir(args.workdir)
        payload = {}
        if args.command == "identify":
            payload = {"name": args.name}
        elif args.command == "log":
            payload = {"message": args.message}
            if args.percent is not None:
                payload["percent"] = args.percent
        elif args.command == "apply":
            payload = read_json(args.proposal)
            if not isinstance(payload, dict):
                raise ValueError("Proposal must be an object")
            payload["dryRun"] = args.dry_run
        elif args.command == "undo":
            payload = {"runId": args.run_id}
        elif args.command == "finish":
            payload = {"summary": args.summary}
        if not 0 < args.timeout <= 60:
            raise ValueError("Timeout must be >0 and <=60 seconds")
        result = request(args.state_dir, args.session, args.command, payload, args.timeout, args.request_id)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TimeoutError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

