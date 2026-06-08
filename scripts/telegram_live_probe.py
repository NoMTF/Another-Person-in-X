#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def run(cmd: List[str]) -> str:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.stdout


def journal(service: str, since: str) -> str:
    return run(["journalctl", "-u", service, "--since", since, "--no-pager"])


def parse_ts(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def session_messages(state_dir: Path, since_epoch: float) -> List[Dict[str, Any]]:
    root = state_dir / "agents" / "main" / "sessions"
    messages: List[Dict[str, Any]] = []
    if not root.exists():
        return messages
    for path in sorted(root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if item.get("type") != "message":
                    continue
                msg = item.get("message", {})
                content = msg.get("content")
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
                ts_value = item.get("timestamp", "")
                ts_epoch = parse_ts(ts_value)
                if ts_epoch and ts_epoch < since_epoch:
                    continue
                messages.append(
                    {
                        "path": str(path),
                        "timestamp": ts_value,
                        "role": msg.get("role", ""),
                        "text": text[:500],
                        "heartbeat": text.strip() == "[OpenClaw heartbeat poll]" or text.strip() == "HEARTBEAT_OK",
                    }
                )
        except Exception:
            continue
    return messages


def bridge_events(state_dir: Path, since_epoch: float) -> List[Dict[str, Any]]:
    path = state_dir / "telegram-bridge" / "events.jsonl"
    if not path.exists():
        return []
    events: List[Dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]:
            if not raw.strip():
                continue
            item = json.loads(raw)
            ts_epoch = parse_ts(str(item.get("ts", "")))
            if ts_epoch and ts_epoch < since_epoch:
                continue
            events.append({k: v for k, v in item.items() if k not in {"text", "token"}})
    except Exception:
        return []
    return events


def summarize(service: str, state_dir: Path, bot_username: str, since: str, since_epoch: float) -> Dict[str, Any]:
    logs = journal(service, since)
    inbound_marker = f"-> @{bot_username.lstrip('@')}"
    inbound_lines = [line for line in logs.splitlines() if "Inbound message" in line]
    outbound_lines = [line for line in logs.splitlines() if "telegram outbound send ok" in line]
    messages = session_messages(state_dir, since_epoch)
    bridge = bridge_events(state_dir, since_epoch)
    bridge_inbound = [item for item in bridge if item.get("event") == "BRIDGE_INBOUND"]
    bridge_outbound = [item for item in bridge if item.get("event") == "BRIDGE_OUTBOUND"]
    non_heartbeat_user = [m for m in messages if m["role"] == "user" and not m["heartbeat"]]
    non_heartbeat_assistant = [m for m in messages if m["role"] == "assistant" and not m["heartbeat"]]
    proved_inbound = bool((inbound_lines and non_heartbeat_user) or bridge_inbound)
    proved_reply = bool((inbound_lines and non_heartbeat_user and outbound_lines and non_heartbeat_assistant) or (bridge_inbound and bridge_outbound))
    return {
        "service": service,
        "state_dir": str(state_dir),
        "bot_username": bot_username,
        "since": since,
        "inbound_count": len(inbound_lines),
        "inbound_to_target_count": sum(1 for line in inbound_lines if inbound_marker in line),
        "outbound_count": len(outbound_lines),
        "latest_inbound": inbound_lines[-5:],
        "latest_outbound": outbound_lines[-5:],
        "non_heartbeat_user_count": len(non_heartbeat_user),
        "non_heartbeat_assistant_count": len(non_heartbeat_assistant),
        "latest_non_heartbeat_user": non_heartbeat_user[-3:],
        "latest_non_heartbeat_assistant": non_heartbeat_assistant[-3:],
        "bridge_inbound_count": len(bridge_inbound),
        "bridge_outbound_count": len(bridge_outbound),
        "latest_bridge_events": bridge[-8:],
        "proved_live_inbound": proved_inbound,
        "proved_live_reply": proved_reply,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch OpenClaw Telegram live inbound/reply evidence without reading secrets.")
    parser.add_argument("--service", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--bot-username", required=True)
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--poll", type=int, default=5)
    args = parser.parse_args()
    since = "now"
    since_epoch = time.time()
    deadline = time.time() + max(1, args.seconds)
    result: Dict[str, Any] = {}
    while time.time() <= deadline:
        result = summarize(args.service, Path(args.state_dir), args.bot_username, since, since_epoch)
        if result["proved_live_reply"]:
            break
        time.sleep(max(1, args.poll))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("proved_live_reply") else 2


if __name__ == "__main__":
    raise SystemExit(main())
