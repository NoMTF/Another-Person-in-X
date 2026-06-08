#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


TELEGRAM_TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")
SENSITIVE_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "MODEL_API_KEY",
    "X_AUTH_TOKEN",
    "X_CT0",
    "FACTORY_ADMIN_TOKEN",
}


def load_env(path: Path) -> tuple[list[str], dict[str, str]]:
    if not path.exists():
        return [], {}
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key:
            values[key] = unquote_env_value(value.strip())
    return lines, values


def unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def format_env_value(value: str) -> str:
    if re.search(r"\s|#|'|\"", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def write_env(path: Path, updates: dict[str, str]) -> list[str]:
    lines, _ = load_env(path)
    written: list[str] = []
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key, _ = stripped.split("=", 1)
        key = key.strip()
        if key in updates and updates[key]:
            output.append(f"{key}={format_env_value(updates[key])}")
            written.append(key)
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if value and key not in seen:
            output.append(f"{key}={format_env_value(value)}")
            written.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except Exception:
        pass
    return written


def iter_cookie_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("cookies", "cookie", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        nested: list[dict[str, Any]] = []
        for value in payload.values():
            if isinstance(value, list):
                nested.extend(item for item in value if isinstance(item, dict))
        return nested
    return []


def extract_cookie_editor_values(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    cookies = iter_cookie_items(payload)
    found: dict[str, str] = {}
    for cookie in cookies:
        name = str(cookie.get("name", "")).strip()
        value = str(cookie.get("value", "")).strip()
        if name in {"auth_token", "ct0"} and value:
            found[name] = value
    updates: dict[str, str] = {}
    if found.get("auth_token"):
        updates["X_AUTH_TOKEN"] = found["auth_token"]
    if found.get("ct0"):
        updates["X_CT0"] = found["ct0"]
    return updates


def validate_updates(updates: dict[str, str]) -> list[str]:
    warnings: list[str] = []
    token = updates.get("TELEGRAM_BOT_TOKEN", "")
    if token and not TELEGRAM_TOKEN_RE.match(token):
        warnings.append("TELEGRAM_BOT_TOKEN does not look like a Telegram bot token.")
    auth = updates.get("X_AUTH_TOKEN", "")
    if auth and len(auth) < 20:
        warnings.append("X_AUTH_TOKEN is unusually short.")
    ct0 = updates.get("X_CT0", "")
    if ct0 and len(ct0) < 20:
        warnings.append("X_CT0 is unusually short.")
    api_key = updates.get("MODEL_API_KEY", "")
    if api_key and len(api_key) < 16:
        warnings.append("MODEL_API_KEY is unusually short.")
    return warnings


def prompt_secret(label: str, key: str) -> str:
    value = getpass.getpass(f"{label} ({key}, blank to skip): ").strip()
    return value


def verify_telegram(token: str, timeout: int = 12) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, f"Telegram getMe failed with HTTP {exc.code}."
    except Exception as exc:
        return False, f"Telegram getMe failed: {exc.__class__.__name__}."
    if payload.get("ok"):
        result = payload.get("result") or {}
        username = result.get("username") or "unknown"
        return True, f"Telegram getMe OK for @{username}."
    return False, "Telegram getMe returned ok=false."


def print_template() -> None:
    sys.stdout.write(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=",
                "MODEL_API_KEY=",
                "X_AUTH_TOKEN=",
                "X_CT0=",
                "FACTORY_ADMIN_TOKEN=",
            ]
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely collect manually provided Telegram, model, and X cookie secrets into a local .env file."
    )
    parser.add_argument("--env", default=".env", help="Path to the env file to update.")
    parser.add_argument("--telegram-token", default="", help="Telegram Bot API token.")
    parser.add_argument("--model-api-key", default="", help="OpenAI-compatible model API key.")
    parser.add_argument("--x-auth-token", default="", help="X/Twitter auth_token cookie value.")
    parser.add_argument("--x-ct0", default="", help="X/Twitter ct0 cookie value.")
    parser.add_argument("--factory-admin-token", default="", help="Admin API token.")
    parser.add_argument("--cookie-editor-json", default="", help="Cookie-Editor JSON export containing auth_token and ct0.")
    parser.add_argument("--interactive", action="store_true", help="Prompt for missing secrets with hidden input.")
    parser.add_argument("--verify-telegram", action="store_true", help="Call Telegram getMe to validate TELEGRAM_BOT_TOKEN.")
    parser.add_argument("--print-template", action="store_true", help="Print a blank .env template and exit.")
    args = parser.parse_args()

    if args.print_template:
        print_template()
        return 0

    updates: dict[str, str] = {}
    if args.cookie_editor_json:
        updates.update(extract_cookie_editor_values(Path(args.cookie_editor_json)))

    cli_updates = {
        "TELEGRAM_BOT_TOKEN": args.telegram_token.strip(),
        "MODEL_API_KEY": args.model_api_key.strip(),
        "X_AUTH_TOKEN": args.x_auth_token.strip(),
        "X_CT0": args.x_ct0.strip(),
        "FACTORY_ADMIN_TOKEN": args.factory_admin_token.strip(),
    }
    updates.update({key: value for key, value in cli_updates.items() if value})

    if args.interactive:
        prompts = [
            ("Telegram Bot API token", "TELEGRAM_BOT_TOKEN"),
            ("Model API key", "MODEL_API_KEY"),
            ("X auth_token cookie", "X_AUTH_TOKEN"),
            ("X ct0 cookie", "X_CT0"),
            ("Factory admin token", "FACTORY_ADMIN_TOKEN"),
        ]
        for label, key in prompts:
            if not updates.get(key):
                value = prompt_secret(label, key)
                if value:
                    updates[key] = value

    if not updates:
        print("No secrets provided. Use --interactive, CLI flags, or --cookie-editor-json.", file=sys.stderr)
        return 2

    warnings = validate_updates(updates)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if args.verify_telegram and updates.get("TELEGRAM_BOT_TOKEN"):
        ok, message = verify_telegram(updates["TELEGRAM_BOT_TOKEN"])
        print(message)
        if not ok:
            return 3

    env_path = Path(args.env)
    written = write_env(env_path, updates)
    redacted = [key for key in written if key in SENSITIVE_KEYS]
    print(json.dumps({"env": str(env_path), "written_keys": redacted}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
