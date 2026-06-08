#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path


QUESTIONS = [
    ("profile", "Profile name", "persona"),
    ("deployment_mode", "Deployment mode (systemd/docker)", "systemd"),
    ("target", "Target host label (local/ssh alias/ip)", "local"),
    ("owner_telegram_id", "Owner Telegram numeric ID", ""),
    ("owner_username", "Owner username without @", ""),
    ("telegram_bot_token_env", "Telegram token env var name", "TELEGRAM_BOT_TOKEN"),
    ("model_provider", "Model provider key", "tokenflux"),
    ("model_id", "Model id", "gpt-5.5"),
    ("model_base_url", "Model base URL", "https://tokenflux.dev/v1"),
    ("model_api_key_env", "Model API key env var name", "MODEL_API_KEY"),
    ("has_prompt", "Existing prompt/skill/corpus path (blank if none)", ""),
    ("crawl_x_handle", "X/Twitter handle to crawl/distill (blank to skip)", ""),
    ("automation_level", "Automation level (full-auto-limited/shadow/manual)", "full-auto-limited"),
    ("install_openclaw", "Install or update OpenClaw at runtime? (yes/no)", "yes"),
]


def ask(key: str, prompt: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive initializer for OpenClaw Agent Factory deployments.")
    parser.add_argument("--output", default="factory-init.json", help="Path to write non-secret answers.")
    parser.add_argument("--env-output", default=".env.example", help="Path to write secret env placeholders.")
    parser.add_argument("--write-env", default="", help="Optional real .env path. Prompts for secrets with getpass and writes chmod 0600 where supported.")
    parser.add_argument("--non-interactive-json", default="", help="Use answers from a JSON file instead of prompting.")
    args = parser.parse_args()

    if args.non_interactive_json:
        answers = json.loads(Path(args.non_interactive_json).read_text(encoding="utf-8-sig"))
    else:
        answers = {key: ask(key, prompt, default) for key, prompt, default in QUESTIONS}
        answers["x_cookie_auth"] = ask("x_cookie_auth", "Use X cookie auth? (yes/no)", "no")
        answers["persona_name"] = ask("persona_name", "Persona name (blank for synthetic default)", "")
        answers["synthetic_persona"] = not bool(answers["persona_name"])

    output = Path(args.output)
    output.write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")

    env_lines = [
        "# Fill on the target host. Do not commit or paste into chat.",
        f"{answers.get('telegram_bot_token_env', 'TELEGRAM_BOT_TOKEN')}=",
        f"{answers.get('model_api_key_env', 'MODEL_API_KEY')}=",
        "X_AUTH_TOKEN=",
        "X_CT0=",
        "FACTORY_ADMIN_TOKEN=",
    ]
    env_path = Path(args.env_output)
    if not env_path.exists():
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    secret_path = ""
    if args.write_env:
        if args.non_interactive_json:
            raise SystemExit("--write-env requires interactive mode so secrets are not stored in JSON")
        values = {
            answers.get("telegram_bot_token_env", "TELEGRAM_BOT_TOKEN"): getpass.getpass("Telegram bot token: "),
            answers.get("model_api_key_env", "MODEL_API_KEY"): getpass.getpass("Model API key: "),
            "X_AUTH_TOKEN": getpass.getpass("X auth_token (blank to skip): "),
            "X_CT0": getpass.getpass("X ct0 (blank to skip): "),
            "FACTORY_ADMIN_TOKEN": getpass.getpass("Factory admin token (blank to auto-skip): "),
        }
        env_real = Path(args.write_env)
        env_real.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
        try:
            env_real.chmod(0o600)
        except Exception:
            pass
        secret_path = str(env_real)
    print(json.dumps({"answers": str(output), "env_template": str(env_path), "env_written": secret_path}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
