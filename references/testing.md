# Testing

Use this reference before claiming deployment, migration, distillation, or admin UI work is complete.

## Local Skill Validation

```bash
python scripts/installer.py --profile test-profile
python -m py_compile scripts/installer.py scripts/persona_distill.py scripts/admin_server.py scripts/init_wizard.py scripts/default_persona.py scripts/telegram_bridge.py scripts/x_adapter.py scripts/x_signal.py scripts/x_crawler.py scripts/automation_runner.py scripts/schedule_posts.py scripts/health_check.py scripts/telegram_live_probe.py
python PATH_TO_SKILL_CREATOR/scripts/quick_validate.py PATH_TO_SKILL
```

## Distillation Smoke Test

```bash
python scripts/persona_distill.py --input ./fixtures --output ./out --persona-name TestPersona --slug test-persona --min-records 1
python ./out/test-persona/scripts/ground.py "hello" --root ./out/test-persona
python ./out/test-persona/scripts/check_reply.py "hello"
```

Expected:

- `SKILL.md`, `voice.md`, `social.md`, `memory.md` exist.
- Raw secrets are redacted.
- `ground.py` and `check_reply.py` run.

## Admin API Smoke Test

```bash
python scripts/admin_server.py --host 127.0.0.1 --port 18880 --state-dir ./tmp-state
curl http://127.0.0.1:18880/api/health
curl http://127.0.0.1:18880/api/config
curl -X POST http://127.0.0.1:18880/api/pending -H 'Content-Type: application/json' -d '{"action":"post","text":"dry"}'
curl http://127.0.0.1:18880/api/pending
curl -X POST http://127.0.0.1:18880/api/memory -H 'Content-Type: application/json' -d '{"category":"preference","content":"likes short replies","confidence":0.9}'
curl -X POST http://127.0.0.1:18880/api/memory/digest -H 'Content-Type: application/json' -d '{"query":"replies","max_chars":500}'
```

Expected:

- API starts on loopback.
- SQLite DB appears in state dir.
- Feature toggles and limits return defaults.
- Pending queue supports create, list, cancel, and cancel-all.
- Memory digest returns bounded persona context snippets.

## X Adapter Smoke Test

```bash
python scripts/x_adapter.py post --text "hello" --dry-run
python scripts/x_adapter.py repost --tweet-id 123 --dry-run
python scripts/x_adapter.py quote --tweet-id 123 --screen-name example --text "short quote" --dry-run
python scripts/default_persona.py --output ./out --seed 1
```

Expected:

- Returns JSON.
- Does not require cookies in dry-run.
- Does not send a real X action.

## Browse Automation Regression

Run the admin API on a temporary state dir, then feed a followed-timeline fixture with persona keyword hits to the runner:

```bash
python scripts/admin_server.py --host 127.0.0.1 --port 18880 --state-dir ./tmp-state
python scripts/automation_runner.py --kind browse --dry-run --browse-input ./fixtures/browse-high-signal.json --max-browse-items 1 --max-browse-reposts 1 --max-browse-quotes 1
python scripts/automation_runner.py --kind browse --dry-run --browse-input ./fixtures/browse-high-signal-unfollowed.json --max-browse-items 1 --max-browse-follows 1
```

Expected:

- The result contains `like`, `repost`, and `quote` candidates for the high-signal followed-timeline browse item.
- The unfollowed-author fixture contains a `follow` candidate when the author is high-relevance and not already followed.
- Each candidate calls `/api/rate/check`.
- Each candidate writes an audit row.
- `shadow=true` and no real X action is sent.
- If the admin feature toggle for `repost`, `quote`, or `follow` is disabled, the corresponding candidate is skipped with `feature_disabled`.

## Deployment Test

- `systemctl status` shows gateway and admin services active.
- X tools API `/health` and `/scheduler/status` return HTTP 200 for each live account profile; `/scheduler/status` reports posted/pending/failed counts and next pending time.
- Reply watchers can be started manually and exit `0/SUCCESS` when there are no new interactions; a no-op result such as `no new X interactions` is passing evidence, not a failure.
- Post schedulers can be started manually and exit `0/SUCCESS`; late-day schedules reduce the remaining count instead of failing when the configured window cannot fit every requested post.
- `/replies/check` must return within the configured total scan budget even when one X source is slow. Prefer evidence from `search`, `monitor_users`, and current-account timelines over waiting indefinitely on notifications or expanded own threads.
- Quote/repost regression test for two controlled accounts:
  - Account B quotes a recent Account A post with a short persona-faithful sentence.
  - Account A runs `/replies/check` with `mark_seen=false` and should see the quote with `kinds` containing `quote`.
  - Account A reposts a recent Account B post.
  - Account B runs `/replies/check` with `mark_seen=false` and should see the repost with `kinds` containing `repost`; auto-reply should usually skip pure reposts with no new text.
  - Fetch both created tweet IDs with `/tweet/get` and verify quote and repost payloads are separate fields, not collapsed into the same kind.
- Telegram bot receives and sends a normal owner DM reply.
- Live Telegram inbound is proven only when logs show `Inbound message ... -> @BOT_USERNAME` and a profile session contains a non-heartbeat user message. Heartbeat sessions prove model liveness, not chat ingress.
- In bridge mode, live Telegram inbound/reply can also be proven by `BRIDGE_INBOUND` and `BRIDGE_OUTBOUND` in `{state_dir}/telegram-bridge/events.jsonl`.
- To watch for a fresh manual DM:

  ```bash
  python scripts/telegram_live_probe.py --service openclaw-PROFILE-gateway.service --state-dir /root/.openclaw-PROFILE --bot-username BOT_USERNAME --seconds 90
  ```

  Ask the owner to send a new DM after the probe starts. `proved_live_reply=true` is the completion evidence.
- Owner DM and owner-only commands succeed for owner; non-owner DMs are ignored and never become persona chat.
- X actions work in shadow mode before live mode.

## Style Test

- Generate 20 replies to similar prompts.
- Reject if outputs repeat the same catchphrase mechanically.
- Reject if the bot sounds like a generic assistant.
- Confirm mood variation changes rhythm without breaking persona consistency.
- Generate one daily original-post queue. Reject if most posts are abstract atmosphere only; the queue should include concrete questions and small opinions about real objects, activities, timeline behavior, or daily scenes.
- Reject near-duplicate original posts even when only particles, emoji, line breaks, or catchphrases differ.
