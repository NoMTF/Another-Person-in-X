---
name: another-person-in-x
description: |
  Build, deploy, debug, and maintain OpenClaw-based persona agents for Telegram and X/Twitter.
  Use when installing OpenClaw with a coding agent or Claude Code, generating persona skills from X/Twitter or supplied prompts,
  configuring autonomous posting/replying/liking/reposting/following with rate limits, running a local admin console,
  adding long-term memory, or standardizing multi-role persona bot deployments.
---

# Another Person in X

This skill turns a coding agent or Claude Code into the deployment and maintenance engineer for an OpenClaw runtime persona bot. OpenClaw should run the agent; a coding agent / Claude Code should install, debug, migrate, and repair it.

## Core Rules

- Prefer a coding agent or Claude Code for deployment/debugging. Use OpenClaw self-management only when no external coding agent is available.
- Do not vendor long-lived upstream projects such as OpenClaw, twikit, Node, Python packages, or model SDKs. Install or update them at runtime, optionally pinned by version.
- Default automation is full-auto with limits: posting, replying, browsing, likes, reposts, quotes, and follows may run automatically, but every action must pass rate limits, risk checks, owner policy, and audit logging.
- Telegram/private bot access is owner-only. Non-owner users must not chat with the persona or operate X accounts or servers in this deployment pattern.
- Keep impersonation boundaries explicit. Generated personas may imitate style only with permission or clear synthetic labeling; do not make the bot falsely claim to be a real person.
- Raw corpora and credentials never go into runtime persona skills or exported bundles. Runtime skills contain only sanitized corpora, indexes, digests, and scripts.
- If asked to deploy a real bot, first read this skill, then use `scripts/installer.py`, `scripts/persona_distill.py`, and `scripts/admin_server.py` instead of rewriting one-off deployment glue.

## Workflow

1. **Plan and collect inputs**: target host, profile name, Telegram bot token, model provider/base URL/API key, owner Telegram ID/username, optional X cookies, existing prompt/skill/corpus, and automation level. Use `scripts/credential_helper.py` for manually provided secrets or Cookie-Editor JSON exports; never read browser cookie databases automatically.
2. **Install runtime**: use `scripts/installer.py` to generate/apply OpenClaw profile config, systemd service, admin API service, state directories, and dependency install commands.
3. **Create persona**: use `scripts/persona_distill.py` to ingest X/Twitter exports, existing skills, prompt text, chat logs, or documents. Generate a persona skill with retrieval, self-check, variation, and sanitized indexes.
4. **Enable memory**: follow `references/memory.md`. Use OpenClaw `memory-core`/`memory-wiki` plus the bundled SQLite memory store for high-signal events and persona digests.
5. **Configure automation**: follow `references/x-automation.md`. Default daily post target is 5 randomized posts; actions run through risk checks, rate limiter, recent-output dedupe, and audit.
6. **Run local admin console**: use `scripts/admin_server.py` with `assets/web-admin/`. Bind to `127.0.0.1`; expose through SSH tunnel or trusted reverse proxy only.
7. **Verify**: run installer dry-run, distiller fixture tests, admin API health, OpenClaw health, Telegram echo test, X shadow-mode test, and persona style variation test.

## Included Tools

- `scripts/installer.py`: creates an install plan or applies it for Debian/Ubuntu systemd and Docker-style layouts. It installs current OpenClaw unless a version is pinned.
- `scripts/init_wizard.py`: collects non-secret deployment inputs and writes an env template without storing credentials in the skill.
- `scripts/credential_helper.py`: safely writes manually provided Telegram/model/X secrets into a local `.env`, imports Cookie-Editor JSON exports, optionally validates Telegram `getMe`, and redacts secret values from output.
- `scripts/default_persona.py`: generates a clearly labeled synthetic persona skill when no prompt, corpus, or authorized persona is provided.
- `scripts/persona_distill.py`: normalizes corpora, filters non-target X authors, redacts unsafe/private details, builds indexes, scores multiple distillation strategies, and emits a persona skill.
- `scripts/x_crawler.py`: crawls owner-authorized X/Twitter user posts with runtime twikit cookies into JSONL for persona distillation.
- `scripts/admin_server.py`: FastAPI admin API backed by SQLite for feature flags, rate config, persona registry, audit log, pause/read-only controls, and memory entries.
- `scripts/x_adapter.py`: X/Twitter adapter boundary with twikit and official-API placeholders, dry-run support, and no vendored long-lived dependencies.
- `scripts/x_signal.py`: pure scoring helpers for X mention/quote detection, follow-back intent, persona-interest browse ranking, and high-risk browse skipping.
- `scripts/automation_runner.py`: limited scheduled-action runner that checks admin rate limits, writes audit rows, and calls the X adapter in dry-run or live mode.
- `scripts/schedule_posts.py`: creates the default randomized 5/day original-post pending queue.
- `scripts/health_check.py`: redacted OpenClaw/Telegram/profile health report for repeatable debugging.
- `scripts/telegram_live_probe.py`: watches journal/session evidence for a fresh Telegram inbound message and outbound reply without reading secrets.
- `assets/web-admin/`: React/Vite admin UI template that talks to the local admin API.
- `references/`: concise operating references for deployment, Telegram, X automation, memory, distillation, safety, and testing.

## Defaults

- Deployment: Linux systemd profile under `/opt/openclaw-agent-factory/{profile}` and `/root/.openclaw-{profile}`.
- Admin bind: `127.0.0.1:18880`.
- OpenClaw gateway bind: loopback unless explicitly exposed with token/password auth.
- Automation: enabled but limited; 5 original posts/day; shadow mode available and recommended for new personas.
- Memory: official OpenClaw memory plus local SQLite FTS; no cloud memory by default.
- Persona variation: sample `mood_state` for every generated action; variation changes rhythm and temperature, not identity or core values.

## Reference Loading

- Read `references/deployment.md` before installing or migrating a server.
- Read `references/distillation.md` before generating or updating a persona skill.
- Read `references/telegram.md` before wiring Telegram bots or owner-only chat controls.
- Read `references/x-automation.md` before enabling X/Twitter actions.
- Read `references/memory.md` before changing long-term memory.
- Read `references/safety.md` before changing risk filters, owner policy, or redaction.
- Read `references/testing.md` before claiming completion.
