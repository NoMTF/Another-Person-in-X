# X/Twitter Automation

Use this reference before enabling X/Twitter posting, replying, likes, reposts, quotes, follows, or crawling.

## Adapter Boundary

- Use an adapter layer. Do not put twikit calls directly inside persona prompts.
- Use `scripts/x_adapter.py` as the local adapter boundary; live twikit calls should be implemented against the installed twikit version on the target host.
- Preferred adapter: twikit cookie mode for owner-controlled accounts.
- Reserved adapter: official X API when the deployment has paid access.
- Every adapter method must support `dry_run` or `shadow_mode`.
- Repost success must be verified after the write. A twikit `retweet()` HTTP 200 or GraphQL response alone is not enough; fetch the target tweet again with the same authenticated account and require viewer `retweeted=true` before counting the action, spending the daily repost quota, or writing a `*_sent` audit row. If verification fails, log `verified=false` / `repost_failed` and do not silently downgrade it into a like.

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
- Original-post schedulers must check recent posted and pending history before filling a plan. High-repeat topic groups such as wallpaper/phone/desktop should cool down across runs, repeated question prefixes such as "有没有" should be capped, and location/address questions should be rejected.
- If an existing daily plan has posted items but no pending items, refill the remaining day without deleting posted evidence. If generation cannot fill every missing slot in one pass, keep the valid posts and let the next scheduler run continue the refill instead of leaving the feed empty.
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
- Do not let proactive browsing collapse into likes only. The decision schema should include `reply`, `like`, `like_reply`, `repost`, `quote`, `follow`, and `skip`, with separate per-run and per-day caps for replies, likes, reposts, quotes, and follows.
- `scripts/automation_runner.py --kind browse` must be able to emit `quote`, `repost`, and `follow` candidates, not only `like`. Default quote volume is higher than repost volume; quote is the main boost action because it adds persona context, while bare repost is a small quote-gated supplement.
- Runtime proactive browse scripts should prefer quote for high-match followed/monitored items when they can produce a short persona-natural sentence. Bare reposts must not outnumber quotes in a run/day unless the operator explicitly overrides the mix.
- Runtime proactive browse scripts must only increment `reposts_sent` / daily repost counters after adapter metadata proves `verified=true` or the API status endpoint returns `retweeted=true`.
- Browse-time follows should only target high-relevance authors that are not already followed and are not the active account itself. Followed-timeline items are treated as already followed unless the source payload explicitly says otherwise.
- Strip URLs before keyword scoring so short keywords such as `AI` do not match random t.co path fragments.
- Skip or heavily downrank self-harm, overdose, doxxing, harassment, and brigading topics before they reach proactive like/repost/quote/follow decisions.
- If a direct reply, mention, or quote of the bot contains self-harm or "want to die" language, route it to the persona crisis-support reply mode instead of the normal browse engagement model.

## Skip Cases

- Harassment, brigading, doxxing, threats, or "go attack this person".
- Dangerous self-harm instructions or method details, medical dosing, illegal guidance, credential theft, evasion, or malware.
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
