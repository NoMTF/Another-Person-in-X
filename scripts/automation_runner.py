#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


MOODS = ["everyday", "excited", "tired", "serious", "sharp", "very-short", "long-form"]


@dataclass
class Candidate:
    action: str
    reason: str
    target: str = ""
    text: str = ""
    risk: str = "low"


def api_json(base: str, path: str, payload: Dict[str, Any] = None, token: str = "") -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def generate_candidates(kind: str) -> List[Candidate]:
    mood = random.choice(MOODS)
    if kind == "post":
        return [Candidate("post", f"scheduled original post; mood={mood}", text=f"[draft mood={mood}]")]
    if kind == "browse":
        return [Candidate("like", f"low-risk relevant timeline item; mood={mood}", target="dry-run-target")]
    return []


def run_adapter(script_dir: Path, candidate: Candidate, dry_run: bool) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(script_dir / "x_adapter.py"),
        candidate.action,
        "--dry-run" if dry_run else "--adapter",
    ]
    if dry_run:
        cmd.extend(["--adapter", "twikit"])
    else:
        cmd.append("twikit")
    if candidate.text:
        cmd.extend(["--text", candidate.text])
    if candidate.target:
        if candidate.action == "follow":
            cmd.extend(["--user", candidate.target])
        else:
            cmd.extend(["--tweet-id", candidate.target])
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"ok": False, "error": proc.stdout, "returncode": proc.returncode}


def main() -> int:
    parser = argparse.ArgumentParser(description="Limited autonomous action runner for OpenClaw Agent Factory.")
    parser.add_argument("--admin-api", default="http://127.0.0.1:18880")
    parser.add_argument("--admin-token", default="")
    parser.add_argument("--kind", choices=["post", "browse"], default="post")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    candidates = generate_candidates(args.kind)
    results = []
    for candidate in candidates:
        rate = api_json(args.admin_api, "/api/rate/check", {"action": candidate.action, "increment": True}, args.admin_token)
        if not rate.get("ok"):
            results.append({"candidate": candidate.__dict__, "skipped": rate})
            continue
        adapter_result = run_adapter(script_dir, candidate, dry_run=args.dry_run)
        api_json(
            args.admin_api,
            "/api/audit",
            {
                "action": candidate.action,
                "target": candidate.target,
                "reason": candidate.reason,
                "risk": candidate.risk,
                "text": candidate.text,
                "sent": bool(adapter_result.get("ok") and not args.dry_run),
                "shadow": args.dry_run or bool(adapter_result.get("dry_run")),
                "metadata": {"adapter": adapter_result},
            },
            args.admin_token,
        )
        results.append({"candidate": candidate.__dict__, "adapter": adapter_result})
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
