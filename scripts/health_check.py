#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict


def parse_env(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def run(cmd: list[str]) -> Dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {"returncode": proc.returncode, "output": proc.stdout[-4000:]}


def telegram_probe(token: str) -> Dict[str, Any]:
    if not token:
        return {"token_present": False}
    out: Dict[str, Any] = {"token_present": True, "token_len": len(token)}
    for method in ("getMe", "getWebhookInfo"):
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", timeout=12) as response:
                data = json.load(response)
            result = data.get("result")
            if isinstance(result, dict) and result.get("url"):
                result = dict(result)
                result["url"] = "[REDACTED_URL]"
            out[method] = {"ok": data.get("ok"), "result": result}
        except Exception as exc:
            out[method] = {"ok": False, "error": str(exc)}
    return out


def http_json(url: str, timeout: int = 12) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
        return {"ok": 200 <= response.status < 300, "status": response.status, "json": data}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")[-1000:]
        except Exception:
            body = ""
        return {"ok": False, "status": exc.code, "error": str(exc), "body": body}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def x_api_probe(base_url: str) -> Dict[str, Any]:
    if not base_url:
        return {"configured": False}
    base = base_url.rstrip("/")
    return {
        "configured": True,
        "base_url": base,
        "health": http_json(f"{base}/health"),
        "scheduler_status": http_json(f"{base}/scheduler/status"),
    }


def sqlite_counts(state_dir: Path) -> Dict[str, Any]:
    db_path = state_dir / "state" / "openclaw.sqlite"
    if not db_path.exists():
        return {"exists": False}
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    tables = ["channel_ingress_events", "delivery_queue_entries", "current_conversation_bindings", "acp_sessions", "diagnostic_events"]
    counts: Dict[str, Any] = {"exists": True, "path": str(db_path)}
    for table in tables:
        try:
            counts[table] = con.execute(f"select count(*) as n from {table}").fetchone()["n"]
        except Exception as exc:
            counts[table] = {"error": str(exc)}
    con.close()
    return counts


def bridge_summary(state_dir: Path) -> Dict[str, Any]:
    path = state_dir / "telegram-bridge" / "events.jsonl"
    if not path.exists():
        return {"enabled": False, "events_path": str(path)}
    inbound = 0
    outbound = 0
    poll_errors = 0
    latest: list[dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-300:]:
            if not raw.strip():
                continue
            item = json.loads(raw)
            event = item.get("event")
            if event == "BRIDGE_INBOUND":
                inbound += 1
            elif event == "BRIDGE_OUTBOUND":
                outbound += 1
            elif event == "poll_error":
                poll_errors += 1
            safe_item = {k: v for k, v in item.items() if k not in {"text", "token"}}
            latest.append(safe_item)
    except Exception as exc:
        return {"enabled": True, "events_path": str(path), "error": str(exc)}
    return {
        "enabled": True,
        "events_path": str(path),
        "inbound_events": inbound,
        "outbound_events": outbound,
        "poll_errors": poll_errors,
        "latest": latest[-8:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Redacted health check for OpenClaw Agent Factory profiles.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--service", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--x-api", default="", help="Optional local X tools API base URL, for example http://127.0.0.1:8787.")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    env = parse_env(Path(args.env_file) if args.env_file else state_dir / ".env")
    report = {
        "state_dir": str(state_dir),
        "service": args.service,
        "service_active": run(["systemctl", "is-active", args.service]) if args.service else None,
        "service_enabled": run(["systemctl", "is-enabled", args.service]) if args.service else None,
        "openclaw_status": run(["env", f"HOME={state_dir}", f"OPENCLAW_HOME={state_dir}", f"OPENCLAW_CONFIG_PATH={state_dir / 'openclaw.json'}", f"OPENCLAW_STATE_DIR={state_dir}", "openclaw", "channels", "status"]),
        "telegram": telegram_probe(env.get("TELEGRAM_BOT_TOKEN", "")),
        "x_api": x_api_probe(args.x_api or env.get("X_TOOLS_API", "")),
        "telegram_bridge": bridge_summary(state_dir),
        "sqlite": sqlite_counts(state_dir),
        "sessions": sorted(str(p) for p in (state_dir / "agents" / "main" / "sessions").glob("*.jsonl"))[-10:],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
