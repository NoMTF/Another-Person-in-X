# X/Twitter Automation

Use this reference before enabling X/Twitter posting, replying, likes, reposts, quotes, follows, or crawling.

## Adapter Boundary

- Use an adapter layer. Do not put twikit calls directly inside persona prompts.
- Use `scripts/x_adapter.py` as the local adapter boundary; live twikit calls should be implemented against the installed twikit version on the target host.
- Preferred adapter: twikit cookie mode for owner-controlled accounts.
- Reserved adapter: official X API when the deployment has paid access.
- Every adapter method must support `dry_run` or `shadow_mode`.

## Allowed Default Actions

- Original posts.
- Replies to people under the bot's own posts.
- Low-volume replies to highly relevant timeline posts.
- Likes, reposts, quotes, follows.

## Hard Limits

- All actions go through admin API rate checks.
- Default original posts: 5 per day at randomized times.
- Original-post generation must keep the feed non-empty: roughly 25% concrete questions and 20% concrete opinions/stances, with the remainder split between grounded daily observations and a smaller number of mood fragments.
- "Concrete" means a real object, activity, setting, or timeline topic such as wallpaper, phone, desk, weather, photography, clothing, games, sleep, food, or X behavior. Avoid generic engagement bait such as "大家怎么看".
- Do not count identity labels, bare numbers, broad night/survival words, or catchphrases as concrete details by themselves. Near-duplicate posts with only particles, emoji, or catchphrase changes must be rejected.
- Reply delay defaults to 45-600 seconds.
- New personas start in shadow mode until manually reviewed.
- Oneshot watcher/scheduler/proactive services must wait for the local X API `/health` endpoint before calling `/replies/check`, `/browse/check`, or `/tweet`.
- The local X API must expose `/scheduler/status` with schedule file path, date, posted/pending/failed counts, and next pending time.
- Interaction and browse scans must use per-source timeouts and a total scan budget. A slow X source such as notifications, timeline, search, or own-thread expansion must not block other sources or leave a oneshot service stuck.
- Verify the configured account handle against live tweet payloads after login or migration. If X returns a different `user.screen_name` than configured, update `X_USERNAME` and keep old handles only as monitored/source aliases.

## Priority

1. Owner commands.
2. Replies under own posts that look like questions or direct engagement.
3. Mentions.
4. Quotes of own posts and status-URL references to own posts.
5. High-relevance timeline posts from the followed timeline.
6. High-relevance monitored persona-neighbor accounts.
7. Search results that match persona-interest keywords.
8. Original posts.
9. Likes/follows as low-risk secondary actions.

## Mention And Quote Detection

- Do not rely on a single `tweet.quote` or `tweet.text` field. X clients and twikit versions may expose quote/mention evidence through `quote`, `quoted_tweet`, `quoted_status`, `quoted_status_result`, `quoted_status_permalink`, `entities`, `urls`, `card`, or rendered text.
- Treat `x.com/{own_username}/status/...`, `twitter.com/{own_username}/status/...`, and `@{own_username}` in any of those fields as interaction evidence.
- Keep quote and repost evidence separate. Quote fields and retweet fields can look similar in twikit; do not classify `retweeted_tweet` / `retweeted_status` as a quote.
- Reposts should be detected as `repost` and usually skipped by auto-reply if there is no new text. Quotes can be replied to when low-risk and persona-natural.
- A follow-back request such as `回关`, `互关`, `follow back`, or `fo back` is a follow action candidate, not an ordinary reply candidate, if risk checks pass.

## Proactive Browsing

- Random browsing should prefer the authenticated account's followed timeline first, then monitored persona-neighbor accounts, then search queries.
- Rank candidates by source priority first, persona keyword relevance second. Do not let search keyword hits outrank followed timeline items before the LLM decision step.
- Keep `source_rank`, `persona_score`, `priority_score`, and `persona_hits` in the candidate payload so runners and audit logs can explain why a tweet was selected.
- Do not let proactive browsing collapse into likes only. The decision schema should include `reply`, `like`, `like_reply`, `repost`, `quote`, and `skip`, with separate per-run and per-day caps for replies, likes, reposts, and quotes.
- `scripts/automation_runner.py --kind browse` must be able to emit `repost` and `quote` candidates, not only `like`. Keep conservative per-run defaults: up to 3 likes, 1 repost, and 1 quote unless the operator overrides them.
- Strip URLs before keyword scoring so short keywords such as `AI` do not match random t.co path fragments.
- Skip or heavily downrank self-harm, overdose, doxxing, harassment, and brigading topics before they reach the like/reply decision model.

## Skip Cases

- Harassment, brigading, doxxing, threats, or "go attack this person".
- Dangerous self-harm, medical dosing, illegal guidance, credential theft, evasion, or malware.
- Low-relevance public timeline replies that would look spammy.
- Repeated text or repeated catchphrases in a recent window.
- Anything blocked by `pause_all`, `read_only`, `shadow_mode`, or rate limits.

## Audit Fields

Log every generated action:

- `action`
- `actor`
- `target`
- `reason`
- `risk`
- `persona_slug`
- `anchors`
- `text`
- `sent`
- `shadow`
- adapter metadata without secrets

## Runner

- Use `scripts/automation_runner.py` for scheduled actions.
- It must call `/api/rate/check` before every action.
- It must call `/api/audit` after every generated action, including shadow or skipped actions.
- New profiles should run with `--dry-run` until the owner has reviewed generated text and audit rows.
- Deployment-specific X runtime services should log successful no-op checks, for example `no new X interactions`, so empty inboxes do not look like broken detection.
