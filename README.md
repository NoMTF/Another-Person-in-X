# Another Person in X

Another Person in X is a complete skill and tooling package for building OpenClaw-based persona agents that can talk through Telegram and operate an owner-controlled X/Twitter account.

It is designed for people who want a persona agent that can be installed, debugged, distilled from public writing, managed from a local web console, and run with autonomous but limited social actions.

## What It Can Do

### Persona Creation

- Generate a persona skill from an existing prompt, skill, document corpus, chat logs, or X/Twitter posts.
- Crawl owner-authorized X/Twitter public posts with runtime cookies.
- Filter non-target authors and remove unsafe/private details before building a runtime skill.
- Produce persona files such as `SKILL.md`, `voice.md`, `social.md`, `memory.md`, retrieval indexes, `ground.py`, and `check_reply.py`.
- Keep raw corpora out of runtime exports by default.

### Telegram Agent

- Connect a Telegram bot to the OpenClaw runtime.
- Restrict Telegram access to configured owners.
- Support normal owner chat and operational commands.
- Drop non-owner messages in owner-only deployments.
- Probe live Telegram inbound/outbound behavior for debugging.

### X/Twitter Automation

- Original posts with randomized daily scheduling.
- Replies under the agent's own posts.
- Mention, quote, repost, and status-link detection.
- Timeline browsing with source priority.
- Likes, reposts, quotes, follows, and follow-back handling.
- Dry-run or shadow mode for testing without sending real X actions.
- Adapter boundary for twikit cookie mode, with room for official API adapters later.

### Local Web Admin Console

- Toggle autonomous posting, replies, browsing, likes, reposts, quotes, and follows.
- Configure frequency, reply delay, daily limits, and shadow/read-only modes.
- Manage multiple personas and rollout states.
- Review audit logs for generated actions.
- Pause all automation immediately.
- Keep credentials out of the browser UI and exported packages.

### Memory

- Uses OpenClaw memory layers where available.
- Adds a local SQLite/FTS memory layer for events, preferences, relationships, failed cases, and post history.
- Injects bounded persona digests instead of dumping full history into context.
- Stores only high-signal memory with source and confidence.

## Typical Use Cases

- Build a Telegram companion bot that speaks in a specific approved persona.
- Run a semi-autonomous or autonomous X/Twitter persona account.
- Distill a writing style from public posts and use it for social replies.
- Maintain several persona profiles on the same server.
- Test X/Twitter automation safely before enabling live actions.
- Migrate an OpenClaw persona deployment between servers.

## Design Principles

- Runtime projects such as OpenClaw and twikit are installed or updated at deployment time instead of being vendored into this repository.
- Automation is enabled through limits, audit logs, owner boundaries, and pause controls.
- Personas should not falsely claim to be the real source person.
- Credentials stay in environment files or secret stores, never inside persona skills, audit exports, or prompts.
- Generated posts should not become empty atmosphere: the scheduler mixes concrete questions, small opinions, daily observations, and a smaller number of mood fragments.

## Repository Layout

```text
.
├── SKILL.md                    # Main skill instructions and workflow
├── agents/                     # Agent configuration examples
├── assets/web-admin/           # React/Vite admin console template
├── references/                 # Deployment, Telegram, X, memory, safety, testing docs
└── scripts/                    # Installer, distiller, adapters, admin API, runners, probes
```

## Requirements

- Linux server recommended: Debian or Ubuntu with systemd.
- Python 3.10+ recommended.
- Node.js only if you want to rebuild the web admin console.
- An OpenAI-compatible model provider.
- A Telegram bot token if Telegram is enabled.
- X/Twitter cookies for an account you own or are explicitly allowed to operate.

## Quick Start

Clone the repository:

```bash
git clone https://github.com/NoMTF/Another-Person-in-X.git
cd Another-Person-in-X
```

Check Python scripts:

```bash
python -m py_compile scripts/*.py
```

Create an initialization template:

```bash
python scripts/init_wizard.py
```

Generate an install plan:

```bash
python scripts/installer.py --profile my-persona
```

Apply on a target Linux host only after reviewing the plan:

```bash
python scripts/installer.py --profile my-persona --apply
```

For a full deployment, read `SKILL.md` first, then follow `references/deployment.md`, `references/telegram.md`, and `references/x-automation.md`.

## Getting a Telegram Bot Token

Telegram bots are created through BotFather.

1. Open Telegram and search for `@BotFather`.
2. Start a chat with BotFather.
3. Send `/newbot`.
4. Choose a display name.
5. Choose a username ending in `bot`, such as `example_persona_bot`.
6. BotFather will return an HTTP API token.
7. Store the token in your deployment `.env` file as `TELEGRAM_BOT_TOKEN`.

Example `.env` entry:

```env
TELEGRAM_BOT_TOKEN=1234567890:replace_with_your_real_token
```

Keep this token private. Anyone with it can control the bot.

## Getting X/Twitter Cookies

The default live X/Twitter adapter uses twikit cookie mode. You need two cookie values from an account you own or have permission to automate:

- `auth_token`
- `ct0`

Recommended manual method:

1. Install a browser cookie editor extension, such as Cookie-Editor.
2. Log in to `https://x.com` in the same browser profile.
3. Open `https://x.com` while logged in.
4. Open the cookie editor extension.
5. Find the cookies named `auth_token` and `ct0`.
6. Copy only their values.
7. Put them into your deployment `.env` file:

```env
X_AUTH_TOKEN=replace_with_auth_token_value
X_CT0=replace_with_ct0_value
```

Important notes:

- Do not use cookies from an account you do not own or manage.
- Do not paste cookies into chats, issues, screenshots, README files, or exported persona packages.
- If a cookie leaks, log out of X/Twitter sessions and rotate it by signing in again.
- Cookies can expire or be invalidated by X/Twitter security checks.

### Why There Is No One-Click Cookie Extractor

It is technically possible to write a tool that reads browser cookies automatically, but this project intentionally does not include one. A one-click cookie extractor is too easy to misuse as credential-stealing software, and it also makes accidental leaks more likely.

The safer pattern is:

- The user manually copies `auth_token` and `ct0` from their own logged-in browser.
- The local init wizard accepts pasted values without printing them.
- `.env` files are ignored by Git.
- Health checks redact secrets before showing diagnostics.

A future helper can safely validate manually pasted values and write them to a local `.env`, but it should not read browser cookie databases automatically.

## Model Provider Configuration

Use an OpenAI-compatible provider.

Example:

```env
MODEL_PROVIDER=openai-compatible
MODEL_BASE_URL=https://example.com/v1
MODEL_API_KEY=replace_with_api_key
MODEL_ID=replace_with_model_name
```

Keep model API keys in `.env` or a secret store. Do not put them in persona files.

## Persona Distillation

Distill from local files:

```bash
python scripts/persona_distill.py \
  --input ./corpus \
  --output ./out \
  --persona-name "Example Persona" \
  --slug example-persona
```

Crawl X/Twitter posts for an authorized account:

```bash
X_AUTH_TOKEN=... X_CT0=... python scripts/x_crawler.py \
  --screen-name example_user \
  --output ./corpus/example_user.jsonl
```

Then run distillation on the output corpus.

## Admin Console

The admin API is local by default:

```bash
python scripts/admin_server.py --host 127.0.0.1 --port 18880 --state-dir ./state
```

The web admin template lives in `assets/web-admin/`.

Useful controls:

- `pause_all`: stop every automated action immediately.
- `read_only`: allow monitoring but block sending.
- `shadow_mode`: generate and audit actions without sending them.
- Daily limits for posts, replies, likes, reposts, quotes, and follows.
- Persona registry for multi-role deployments.
- Audit log for action reason, risk, text, and send status.

## X/Twitter Automation Policy

Default priority:

1. Owner commands.
2. Replies under own posts.
3. Mentions.
4. Quotes of own posts.
5. Followed timeline posts that match persona interests.
6. Monitored neighbor accounts.
7. Search results.
8. Original posts.
9. Likes and follows as secondary actions.

Automation should skip or downrank:

- Harassment or pile-ons.
- Doxxing and privacy exposure.
- Dangerous self-harm or medical dosing.
- Illegal instructions.
- Credential theft or evasion.
- Malware.
- Sexual content involving minors.
- Repeated low-signal text or near-duplicate catchphrases.

## Testing

Basic script validation:

```bash
python -m py_compile scripts/*.py
```

Admin API smoke test:

```bash
python scripts/admin_server.py --host 127.0.0.1 --port 18880 --state-dir ./tmp-state
curl http://127.0.0.1:18880/api/health
```

X adapter dry-run:

```bash
python scripts/x_adapter.py post --text "hello" --dry-run
python scripts/x_adapter.py repost --tweet-id 123 --dry-run
python scripts/x_adapter.py quote --tweet-id 123 --screen-name example --text "short quote" --dry-run
```

Deployment checks are listed in `references/testing.md`.

## Security Checklist

- `.env` is ignored by Git.
- Never commit cookies, bot tokens, model keys, screenshots containing secrets, or raw corpora with private data.
- Start new personas in shadow mode.
- Keep the admin API bound to `127.0.0.1` unless it is protected behind a trusted tunnel or reverse proxy.
- Review audit logs before enabling high-frequency autonomous actions.
- Use owner-only Telegram access for real deployments.

## Project Status

This repository is a practical deployment skill and toolkit, not a hosted service. It expects a human operator to provide credentials, choose a deployment target, review generated personas, and set automation limits responsibly.
