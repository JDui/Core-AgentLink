"""Run a real Python client against the Rust host, retaining the user clip."""
import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))
from cal_sdk import AgentLink


def run(client):
    client.checkpoint()
    client.call("identify", {"name": "Python"})
    before = client.call("inspect")
    proposal = dict(expectedRevision=before["domain"]["projectRevision"],
                    events=[dict(name="演示微笑", start=2, end=3, track=0)])
    client.call("log", {"message": "Inspect completed; applying one timed clip", "percent": 25})
    client.call("apply", dict(proposal, dryRun=True))
    client.checkpoint()
    result = client.call("apply", proposal)
    after = client.call("inspect")
    client.checkpoint()
    if not any(c.get("runId") == result["runId"] for c in after["domain"]["clips"]):
        raise RuntimeError("Applied clip missing")
    client.call("finish", {"summary": "One actual clip applied and inspected"})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    print(run(AgentLink(args.state_dir, args.session, "demo")))

