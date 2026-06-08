#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


MAX_TELEGRAM_TEXT = 3900


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_event(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": now_iso(), **event}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


class TelegramAPI:
    def __init__(self, token: str, timeout: int = 35) -> None:
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is empty")
        self.base = f"https://api.telegram.org/bot{token}"
        self.timeout = timeout

    def call(self, method: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = None if payload is None else urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.base}/{method}", data=data)
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            result = json.load(response)
        if not result.get("ok"):
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        return result

    def delete_webhook(self) -> None:
        self.call("deleteWebhook", {"drop_pending_updates": "false"})

    def get_updates(self, offset: int | None, timeout: int) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "timeout": str(timeout),
            "allowed_updates": json.dumps(["message", "edited_message"], ensure_ascii=False),
        }
        if offset is not None:
            payload["offset"] = str(offset)
        return self.call("getUpdates", payload).get("result", [])

    def send_message(self, chat_id: int | str, text: str, reply_to_message_id: int | None = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"chat_id": str(chat_id), "text": text}
        if reply_to_message_id is not None:
            payload["reply_parameters"] = json.dumps({"message_id": reply_to_message_id}, ensure_ascii=False)
        return self.call("sendMessage", payload)

    def send_chat_action(self, chat_id: int | str, action: str = "typing") -> None:
        try:
            self.call("sendChatAction", {"chat_id": str(chat_id), "action": action})
        except Exception:
            pass


def extract_text(message: Dict[str, Any]) -> str:
    text = message.get("text")
    if isinstance(text, str):
        return text.strip()
    caption = message.get("caption")
    if isinstance(caption, str):
        return caption.strip()
    return ""


def should_handle(message: Dict[str, Any], owner_chat_id: str, group_mode: str) -> tuple[bool, str]:
    chat = message.get("chat") or {}
    chat_type = chat.get("type", "")
    chat_id = str(chat.get("id", ""))
    if chat_type == "private":
        if owner_chat_id and chat_id == owner_chat_id:
            return True, "owner-private"
        return False, "non-owner-private"
    if group_mode == "owner-only" and owner_chat_id and chat_id == owner_chat_id:
        return True, "owner-group"
    return False, f"unsupported-chat:{chat_type or 'unknown'}"


def split_reply(text: str) -> List[str]:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ["我这边刚刚没组织好语言，再发一次嘛 qwq"]

    chunks: List[str] = []
    current = ""
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            if current:
                chunks.append(current)
                current = ""
            continue
        if len(line) > MAX_TELEGRAM_TEXT:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(line), MAX_TELEGRAM_TEXT):
                chunks.append(line[i : i + MAX_TELEGRAM_TEXT])
            continue
        if current and len(current) + 1 + len(line) <= 900:
            current = f"{current}\n{line}"
        else:
            if current:
                chunks.append(current)
            current = line
    if current:
        chunks.append(current)
    return chunks or ["我这边刚刚没组织好语言，再发一次嘛 qwq"]


def parse_agent_text(stdout: str) -> str:
    raw = stdout.strip()
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        first = raw.find("{")
        last = raw.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return raw
        data = json.loads(raw[first : last + 1])

    payloads = data.get("result", {}).get("payloads", [])
    texts = [item.get("text", "") for item in payloads if isinstance(item, dict) and item.get("text")]
    if texts:
        return "\n".join(texts).strip()
    result = data.get("result", {})
    for key in ("finalAssistantVisibleText", "finalAssistantRawText"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def agent_env(state_dir: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(state_dir),
            "OPENCLAW_HOME": str(state_dir),
            "OPENCLAW_CONFIG_PATH": str(state_dir / "openclaw.json"),
            "OPENCLAW_STATE_DIR": str(state_dir),
            "LANG": env.get("LANG") or "C.UTF-8",
            "LC_ALL": env.get("LC_ALL") or "C.UTF-8",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def run_agent(state_dir: Path, profile: str, chat_id: str, text: str, timeout: int) -> tuple[str, Dict[str, Any]]:
    session_key = f"agent:main:telegram-bridge:{profile}:{chat_id}"
    cmd = [
        "openclaw",
        "agent",
        "--json",
        "--channel",
        "telegram",
        "--reply-channel",
        "telegram",
        "--reply-account",
        "default",
        "--reply-to",
        chat_id,
        "--session-key",
        session_key,
        "--message",
        text,
        "--timeout",
        str(timeout),
    ]
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=agent_env(state_dir))
    meta = {"returncode": proc.returncode, "stdout_chars": len(proc.stdout)}
    if proc.returncode != 0:
        meta["error_preview"] = proc.stdout[-500:]
        return "", meta
    try:
        return parse_agent_text(proc.stdout), meta
    except Exception as exc:
        meta["error_preview"] = f"{type(exc).__name__}: {exc}"
        return "", meta


def iter_messages(update: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for key in ("message", "edited_message"):
        value = update.get(key)
        if isinstance(value, dict):
            yield value


def main() -> int:
    parser = argparse.ArgumentParser(description="Resilient Telegram Bot API bridge for an OpenClaw profile.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--bot-username", default="")
    parser.add_argument("--owner-chat-id", default="")
    parser.add_argument("--poll-timeout", type=int, default=25)
    parser.add_argument("--agent-timeout", type=int, default=240)
    parser.add_argument("--group-mode", choices=["disabled", "owner-only"], default="disabled")
    parser.add_argument("--send-fallback", action="store_true")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    bridge_dir = state_dir / "telegram-bridge"
    offset_path = bridge_dir / "offset.json"
    event_path = bridge_dir / "events.jsonl"
    api = TelegramAPI(os.environ.get("TELEGRAM_BOT_TOKEN", ""), timeout=max(45, args.poll_timeout + 20))
    state = read_json(offset_path, {})
    offset = state.get("offset")
    if not isinstance(offset, int):
        offset = None

    api.delete_webhook()
    append_event(event_path, {"event": "bridge_start", "profile": args.profile, "bot_username": args.bot_username})

    while True:
        try:
            updates = api.get_updates(offset, args.poll_timeout)
        except Exception as exc:
            append_event(event_path, {"event": "poll_error", "error": str(exc)[:500]})
            time.sleep(5)
            continue

        for update in updates:
            update_id = int(update.get("update_id", 0))
            offset = update_id + 1
            write_json(offset_path, {"offset": offset, "updated_at": now_iso()})
            for message in iter_messages(update):
                chat = message.get("chat") or {}
                chat_id = str(chat.get("id", ""))
                text = extract_text(message)
                should, reason = should_handle(message, args.owner_chat_id, args.group_mode)
                if not should or not text:
                    append_event(event_path, {"event": "skip", "update_id": update_id, "chat_id": chat_id, "reason": reason, "text_len": len(text)})
                    continue

                append_event(event_path, {"event": "BRIDGE_INBOUND", "update_id": update_id, "chat_id": chat_id, "text_len": len(text)})
                api.send_chat_action(chat_id)
                reply, meta = run_agent(state_dir, args.profile, chat_id, text, args.agent_timeout)
                parts = split_reply(reply)
                if not reply and not args.send_fallback:
                    append_event(event_path, {"event": "agent_empty", "update_id": update_id, "chat_id": chat_id, "meta": meta})
                    continue
                sent = 0
                for index, part in enumerate(parts):
                    api.send_message(chat_id, part, message.get("message_id") if index == 0 else None)
                    sent += 1
                    time.sleep(0.8)
                append_event(event_path, {"event": "BRIDGE_OUTBOUND", "update_id": update_id, "chat_id": chat_id, "parts": sent, "meta": meta})


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
