# Another Person in X

Skill and tooling package for building OpenClaw-based persona agents that can run Telegram and X/Twitter workflows with owner controls, memory, persona distillation, autonomous posting, replies, likes, reposts, quotes, follows, and a local admin console.

## What Is Included

- `SKILL.md`: operating workflow and deployment boundaries.
- `scripts/`: installer, init wizard, persona distiller, Telegram bridge, X adapter, crawler, automation runner, health checks, and admin API.
- `references/`: deployment, Telegram, X automation, memory, distillation, safety, and testing notes.
- `assets/web-admin/`: FastAPI-compatible React/Vite admin console template.
- `agents/`: agent configuration examples.

## Safety Defaults

- Owner-only Telegram/runtime access.
- No credentials in exported persona skills or logs.
- Rate limits, audit logs, pause/read-only controls, and shadow mode.
- X/Twitter actions pass adapter boundaries, risk checks, and recent-output dedupe.

## Quick Validation

```bash
python -m py_compile scripts/*.py
```

For deployment, start with `SKILL.md`, then run the init wizard and installer for the target host/profile.
