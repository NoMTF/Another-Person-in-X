# Telegram

Use this reference before wiring Telegram bots, owner controls, and chat behavior.

## Token Handling

- Put the bot token only in the host `.env`.
- Never display the token in logs, admin pages, exported bundles, or persona skills.
- Telegram polling and webhook mode are mutually exclusive. Clear webhook before using polling if needed.

## Behavior Split

- Owner DMs: persona chat plus tool/account/server commands.
- Non-owner DMs: disabled through `dmPolicy: "allowlist"` and numeric owner `allowFrom`; do not add any non-owner route.
- Group chats: disabled in the standard persona-agent deployment.
- Default runtime path: OpenClaw native Telegram channel. Preserve native streaming, tool-progress messages, and cleanup behavior unless there is a concrete polling failure.
- If no owner Telegram numeric ID is available during setup, set Telegram DMs to disabled instead of open.

## Streaming And Message Splitting

- For OpenClaw 2026.6.1, valid `channels.telegram.streaming.chunkMode` values are `newline` and `length`; do not set unsupported values such as `paragraph`, and do not add unsupported keys such as `splitLongMessages`.
- Prefer `newline` when the persona may output multiple short bubbles; each line can become a separate Telegram chunk in supported runtime paths.
- Do not simulate multi-message style with one long paragraph containing fake numbering or markdown separators.
- Keep replies concise by default; let persona variation create occasional very short or long-form responses.

## Bridge Mode

- Bridge mode is fallback-only. Do not enable it by default in installers or migrations.
- If OpenClaw's native Telegram channel shows `getUpdates` conflicts, missing ingress rows, or false-green polling health, use `scripts/telegram_bridge.py`.
- Bridge mode owns the Telegram Bot API poller and calls `openclaw agent --json`; OpenClaw still owns persona/model/memory.
- In bridge mode set `channels.telegram.enabled=false` in `openclaw.json` and keep bridge/admin/factory settings outside OpenClaw's schema, for example in `factory.json`.
- When returning from bridge mode, disable the bridge service, set `channels.telegram.enabled=true`, move bridge-tainted sessions aside, and restart the gateway.
- The bridge splits blank-line or short-line replies into separate Telegram messages, which preserves persona-style short bubbles.
- Systemd units should set `HOME`, `OPENCLAW_HOME`, `OPENCLAW_CONFIG_PATH`, `OPENCLAW_STATE_DIR`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `PYTHONUTF8=1`, and `PYTHONIOENCODING=utf-8`.

## Debug Checklist

1. Confirm one poller:

   ```bash
   curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
   ```

2. Check service logs for consumed updates and outbound send attempts.
3. Confirm owner identity values match Telegram numeric ID and username.
4. If messages are consumed but no reply is sent, inspect workspace instructions for accidental tool requirements on every chat.
5. If there is a `terminated by other getUpdates request` error, stop the competing poller and restart the service.
6. In bridge mode, check `{state_dir}/telegram-bridge/events.jsonl` for `BRIDGE_INBOUND` and `BRIDGE_OUTBOUND`; use `scripts/telegram_live_probe.py` after a fresh user message.
