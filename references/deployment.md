# Deployment

Use this reference before installing, migrating, or repairing an OpenClaw Agent Factory profile.

## Deployment Shape

- Use a coding agent or Claude Code as the deployment engineer.
- Use OpenClaw as the runtime.
- Install OpenClaw at runtime from the current upstream package unless the user pins a version.
- Keep one profile per persona/account pair. Do not overwrite an existing OpenClaw home unless the user explicitly asks.
- Set `HOME`, `OPENCLAW_HOME`, `OPENCLAW_CONFIG_PATH`, and `OPENCLAW_STATE_DIR` to the profile state dir in systemd. Do not leave `HOME=/root` for secondary profiles; otherwise old sessions, devices, Telegram polling, and skills can bleed across profiles.
- Default paths:
  - Install root: `/opt/openclaw-agent-factory/{profile}`
  - State: `/root/.openclaw-{profile}`
  - Workspace: `/root/.openclaw-{profile}/workspace`
  - Config: `/root/.openclaw-{profile}/openclaw.json`
  - Admin DB: `/root/.openclaw-{profile}/factory.sqlite3`

## Installer Flow

1. Run a dry plan first:

   ```bash
   python3 scripts/installer.py --profile PROFILE --owner-telegram-id ID --owner-username USER
   ```

2. Review generated files and commands.
3. Copy or fill `.env` on the host with real secrets. Never print `.env`.
4. Apply only after review:

   ```bash
   python3 scripts/installer.py --profile PROFILE --apply
   ```

5. Confirm services:

   ```bash
   systemctl status openclaw-PROFILE-gateway.service openclaw-PROFILE-admin.service --no-pager
   journalctl -u openclaw-PROFILE-gateway.service -n 120 --no-pager
   ```

## Migration

- Stop the old gateway before starting the migrated profile if both use the same Telegram bot token.
- If two gateway services use different Telegram tokens but share `HOME=/root`, fix HOME isolation before testing. Shared HOME can make logs and conversation bindings appear to belong to the wrong bot.
- Copy sanitized persona skill, workspace instructions, memory DB, and audit DB.
- Do not copy raw X cookies or model keys through logs. Recreate `.env` manually on the destination.
- Keep old service disabled but not deleted until Telegram, admin API, and X shadow-mode tests pass.

## Admin UI

- Build the UI on the host:

  ```bash
  cd /opt/openclaw-agent-factory/PROFILE/assets/web-admin
  npm install
  npm run build
  systemctl restart openclaw-PROFILE-admin.service
  ```

- Bind admin API to `127.0.0.1`.
- Use SSH tunneling:

  ```bash
  ssh -L 18880:127.0.0.1:18880 user@host
  ```

## Rollback

- Pin `--openclaw-version` during reinstall when a new upstream release breaks behavior.
- Keep persona skill versions in separate folders or versioned paths.
- Disable automation first, then restart gateway, then re-enable after audit checks.

## Live Telegram Verification

- Prove the service is unique:

  ```bash
  systemctl is-active openclaw-PROFILE-gateway.service
  systemctl is-active openclaw-gateway.service || true
  ss -ltnp | grep openclaw
  ```

- Prove channel health:

  ```bash
  python3 /opt/openclaw-agent-factory/PROFILE/scripts/health_check.py --state-dir /root/.openclaw-PROFILE --service openclaw-PROFILE-gateway.service
  ```

- Prove real inbound by sending a fresh DM to the bot and checking for `Inbound message ... -> @BOT_USERNAME` plus a new session file under the profile's `agents/main/sessions`.
